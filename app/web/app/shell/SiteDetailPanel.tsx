/**
 * Site-detail & explanation panel — "Why this site?" (S3-05, completed S4-03).
 *
 * A pure view over the S2-08 `get_site_detail` payload for one selected cell,
 * opened identically from a map click or a shortlist row (the shared
 * SiteSelection). For an ELIGIBLE site it shows the cell id, location,
 * suitability score and rank, the S2-06 explanation (headline, positive factors,
 * weaknesses), each criterion's served value and its contribution to the score,
 * the cell's wind / demand / infrastructure / geographic context and its data
 * quality. For an EXCLUDED site it shows the cell id, its not-eligible status,
 * the exclusion reasons and data quality — and no score or rank rows at all, so
 * an excluded cell is never presented as a ranked one.
 *
 * Every piece of explanation text — the headline, positive factors, weaknesses,
 * proxy caveats, data-quality notes, and exclusion reasons — is carried VERBATIM
 * from the payload; the explanations are the ones THIS run materialised with
 * its own weights (S4-03). This component never generates, rephrases,
 * re-derives, or reorders explanation strings, and performs no decision math:
 * contributions and features are iterated in the order the service served them
 * and only rounded for display. Section headings, field labels and the status
 * line are the only UI-authored copy, and none of them use "best site" language.
 */
import type { SiteDetail } from "../api/decision-service";
import {
  CRITERIA,
  GROUP_LABELS,
  HIDDEN_CONTEXT_FIELDS,
  fieldDisplay,
  formatValue,
  type FieldGroup,
} from "./criteria";

export interface SiteDetailPanelProps {
  /** Site detail for the current selection, as served by the decision service. */
  site: SiteDetail;
}

/** One exclusion reason as served by S2-06: a stable code and verbatim text. */
interface ExclusionReason {
  code: string;
  text: string;
}

/** Narrow an unknown explanation field to a non-empty array of strings. */
function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

/** Narrow an unknown explanation field to a list of {code, text} reasons. */
function asExclusionReasons(value: unknown): ExclusionReason[] {
  if (!Array.isArray(value)) return [];
  const reasons: ExclusionReason[] = [];
  for (const item of value) {
    if (
      item &&
      typeof item === "object" &&
      typeof (item as { text?: unknown }).text === "string"
    ) {
      const { code, text } = item as { code?: unknown; text: string };
      reasons.push({ code: typeof code === "string" ? code : text, text });
    }
  }
  return reasons;
}

/** Format the total suitability score (eligible cells only). */
function formatScore(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(3)
    : "Not available";
}

/** Format the engine rank (eligible cells only). */
function formatRank(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `#${value.toLocaleString("en-AU")}`
    : "Not available";
}

/** A criterion's contribution to the score: a served share, 3 decimals. */
function formatContribution(value: number | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(3) : "—";
}

/** The served centroid as "30.123° S, 151.686° E", or null when absent. */
function formatLocation(lat: unknown, lon: unknown): string | null {
  if (typeof lat !== "number" || typeof lon !== "number") return null;
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  const ns = lat < 0 ? "S" : "N";
  const ew = lon < 0 ? "W" : "E";
  return `${Math.abs(lat).toFixed(3)}° ${ns}, ${Math.abs(lon).toFixed(3)}° ${ew}`;
}

/** Render a verbatim string list under a UI heading, only when non-empty. */
function StringListSection({
  heading,
  items,
}: {
  heading: string;
  items: string[];
}): JSX.Element | null {
  if (items.length === 0) return null;
  return (
    <section className="om-detail__section">
      <h4 className="om-detail__heading">{heading}</h4>
      <ul className="om-detail__list">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

/** A two-column label/value table for one context group, if it has rows. */
function ContextTable({
  heading,
  rows,
}: {
  heading: string;
  rows: [string, unknown][];
}): JSX.Element | null {
  if (rows.length === 0) return null;
  return (
    <section className="om-detail__section">
      <h4 className="om-detail__heading">{heading}</h4>
      <div className="om-results__scroll">
        <table className="om-results om-detail__context">
          <tbody>
            {rows.map(([key, value]) => (
              <tr key={key}>
                <th scope="row">{fieldDisplay(key).label}</th>
                <td>{formatValue(key, value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** Context groups shown under "Site context", in reading order. */
const CONTEXT_GROUPS: FieldGroup[] = ["wind", "demand", "infrastructure", "geography"];

export default function SiteDetailPanel({ site }: SiteDetailPanelProps): JSX.Element {
  const eligible = site.eligible === true;
  const explanation = site.explanation ?? {};
  const headline =
    typeof explanation.headline === "string" ? explanation.headline : null;
  const positiveFactors = asStringArray(explanation.positive_factors);
  const weaknesses = asStringArray(explanation.weaknesses);
  const proxyCaveats = asStringArray(explanation.proxy_caveats);
  const dataQualityNotes = asStringArray(explanation.data_quality_notes);
  const exclusionReasons = asExclusionReasons(explanation.exclusion_reasons);

  const features: Record<string, unknown> = site.features ?? {};
  const contributions: Record<string, number> = site.contributions ?? {};

  // Scored criteria in served order: the contribution keys first, then any
  // criterion the features carry without a contribution (an excluded cell).
  const criterionKeys = Object.keys(contributions);
  for (const key of Object.keys(features)) {
    if (CRITERIA[key] && !criterionKeys.includes(key)) criterionKeys.push(key);
  }
  const showContributions = eligible && Object.keys(contributions).length > 0;

  // Every other served column, as context, grouped by theme in served order.
  // Columns this panel does not know are still shown (under geography) rather
  // than silently dropped.
  const contextEntries = Object.entries(features).filter(
    ([key]) => !criterionKeys.includes(key) && !HIDDEN_CONTEXT_FIELDS.has(key),
  );
  const rowsFor = (group: FieldGroup): [string, unknown][] =>
    contextEntries.filter(([key]) => fieldDisplay(key).group === group);

  const location = formatLocation(features.centroid_lat, features.centroid_lon);
  const confidence = features.data_confidence;
  const confidenceScore = features.confidence_score;

  return (
    <div className="om-detail">
      <dl className="om-facts">
        <div><dt>Site ID</dt><dd><code>{site.cell_id}</code></dd></div>
        <div>
          <dt>Status</dt>
          <dd>{eligible ? "Eligible candidate" : "Not eligible — excluded"}</dd>
        </div>
        {location && <div><dt>Location</dt><dd>{location}</dd></div>}
        {eligible ? (
          <>
            <div><dt>Suitability score</dt><dd>{formatScore(site.suitability_score)}</dd></div>
            <div><dt>Rank</dt><dd>{formatRank(site.rank)}</dd></div>
          </>
        ) : (
          <div>
            <dt>Score and rank</dt>
            <dd>None — excluded cells are not scored or ranked</dd>
          </div>
        )}
        {typeof confidence === "string" && confidence !== "" && (
          <div>
            <dt>Data confidence</dt>
            <dd>
              <span className={`om-confidence om-confidence--${confidence}`}>
                {confidence}
              </span>
              {typeof confidenceScore === "number" && Number.isFinite(confidenceScore)
                ? ` (${confidenceScore.toFixed(2)})`
                : null}
            </dd>
          </div>
        )}
      </dl>

      {headline && <p className="om-detail__headline">{headline}</p>}

      {exclusionReasons.length > 0 && (
        <section className="om-detail__section">
          <h4 className="om-detail__heading">Why excluded</h4>
          <ul className="om-detail__list">
            {exclusionReasons.map((reason) => (
              <li key={reason.code}>{reason.text}</li>
            ))}
          </ul>
        </section>
      )}

      <StringListSection heading="Positive factors" items={positiveFactors} />
      <StringListSection heading="Weaknesses" items={weaknesses} />

      {criterionKeys.length > 0 && (
        <section className="om-detail__section">
          <h4 className="om-detail__heading">
            {showContributions ? "Criterion values and contributions" : "Criterion values"}
          </h4>
          <div className="om-results__scroll">
            <table className="om-results">
              <thead>
                <tr>
                  <th scope="col">Criterion</th>
                  <th scope="col" className="om-results__num">Value</th>
                  {showContributions && (
                    <th scope="col" className="om-results__num">Contribution to score</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {criterionKeys.map((key) => (
                  <tr key={key}>
                    <th scope="row">
                      {fieldDisplay(key).label}
                      <span className="om-detail__theme">
                        {GROUP_LABELS[fieldDisplay(key).group]}
                        {fieldDisplay(key).isProxy ? " · proxy" : ""}
                      </span>
                    </th>
                    <td className="om-results__num">{formatValue(key, features[key])}</td>
                    {showContributions && (
                      <td className="om-results__num">
                        {formatContribution(contributions[key])}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {showContributions && (
            <p className="om-detail__note">
              Contributions are each criterion&apos;s share of the suitability
              score under this run&apos;s weights; they add up to the score.
            </p>
          )}
        </section>
      )}

      {CONTEXT_GROUPS.map((group) => (
        <ContextTable
          key={group}
          heading={`Site context — ${GROUP_LABELS[group]}`}
          rows={rowsFor(group)}
        />
      ))}

      <ContextTable heading={GROUP_LABELS.quality} rows={rowsFor("quality")} />
      <StringListSection heading="Data-quality notes" items={dataQualityNotes} />
      <StringListSection heading="Demand proxy caveats" items={proxyCaveats} />
    </div>
  );
}
