/**
 * Site-detail & explanation panel (S3-05).
 *
 * A pure view over the S2-08 `get_site_detail` payload for one selected cell.
 * It renders the engine's raw/derived features, per-criterion component scores,
 * total suitability score, eligibility, and the S2-06 explanation structure.
 *
 * Every piece of explanation text — the headline, positive factors, weaknesses,
 * proxy caveats, data-quality notes, and exclusion reasons — is carried VERBATIM
 * from the payload. This component never generates, rephrases, re-derives, or
 * reorders explanation strings, and performs no decision math: contributions and
 * features are iterated in the order the service served them. Section headings
 * ("Positive factors", "Component scores", …) are the only UI-authored copy, and
 * none of them use "best site" language — screening-level framing comes from the
 * served explanation text itself.
 */
import type { SiteDetail } from "../api/decision-service";

export interface SiteDetailPanelProps {
  /** Site detail for the current selection, as served by the decision service. */
  site: SiteDetail;
}

/** Display labels for the engine's criteria; unknown keys show as served. */
const COMPONENT_LABELS: Readonly<Record<string, string>> = {
  wind_speed: "Wind speed",
  dist_transmission_km: "Transmission distance",
  demand_proxy: "Demand",
  dist_substation_km: "Substation distance",
  slope_deg: "Slope",
  inside_rez: "Inside REZ",
};

/**
 * Units of measurement for the engine's raw/derived feature values, keyed by
 * the feature name the service serves. Appended to the Features read-out so each
 * numeric value carries its unit (S1-08 / S1-10 feature definitions):
 *   - `wind_speed` is metres per second (Sanity_Range [0, 25] m/s);
 *   - `dist_transmission_km` / `dist_substation_km` are kilometres;
 *   - `slope_deg` is degrees;
 *   - `elevation_m` is metres;
 *   - `demand_proxy` is a dimensionless normalised proxy index ([0, 1]) — a
 *     rank of demand proximity, not a physical quantity — so its "unit" is the
 *     index-scale label `(index, 0–1)` rather than a measurement unit;
 *   - `inside_rez` is a boolean flag, so it carries no unit.
 * Unknown feature keys and non-numeric values carry no unit.
 */
const FEATURE_UNITS: Readonly<Record<string, string>> = {
  wind_speed: "m/s",
  dist_transmission_km: "km",
  dist_substation_km: "km",
  slope_deg: "°",
  elevation_m: "m",
  demand_proxy: "(index, 0–1)",
};

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

/** Format the total suitability score; excluded cells carry null. */
function formatScore(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(3)
    : "Not scored";
}

/** Format the engine rank; excluded cells carry null. */
function formatRank(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value)
    ? String(value)
    : "Not ranked";
}

/** Component-score values are finite numbers served by the engine. */
function formatComponent(value: number): string {
  return Number.isFinite(value) ? value.toFixed(3) : "—";
}

/** Safe display of a raw/derived feature value of unknown runtime type. */
function formatFeature(value: unknown): string {
  if (typeof value === "number") return Number.isFinite(value) ? value.toFixed(3) : "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "—";
  return String(value);
}

/**
 * Display a feature value with its unit of measurement appended, when the key
 * has a known unit and the value is a finite number. Non-numeric values (the
 * `inside_rez` boolean, missing "—") and unit-less keys (`demand_proxy`) are
 * shown as-is. The degree unit abuts its value (e.g. `7.000°`); all others are
 * space-separated (e.g. `9.500 m/s`).
 */
function formatFeatureWithUnit(key: string, value: unknown): string {
  const formatted = formatFeature(value);
  const unit = FEATURE_UNITS[key];
  if (!unit || typeof value !== "number" || !Number.isFinite(value)) {
    return formatted;
  }
  return unit === "°" ? `${formatted}${unit}` : `${formatted} ${unit}`;
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

export default function SiteDetailPanel({ site }: SiteDetailPanelProps): JSX.Element {
  const explanation = site.explanation ?? {};
  const headline =
    typeof explanation.headline === "string" ? explanation.headline : null;
  const positiveFactors = asStringArray(explanation.positive_factors);
  const weaknesses = asStringArray(explanation.weaknesses);
  const proxyCaveats = asStringArray(explanation.proxy_caveats);
  const dataQualityNotes = asStringArray(explanation.data_quality_notes);
  const exclusionReasons = asExclusionReasons(explanation.exclusion_reasons);

  const contributions = Object.entries(site.contributions ?? {});
  const features = Object.entries(site.features ?? {});

  return (
    <div className="om-detail">
      <dl className="om-facts">
        <div><dt>Site ID</dt><dd><code>{site.cell_id}</code></dd></div>
        <div><dt>Eligible</dt><dd>{site.eligible ? "Yes" : "No"}</dd></div>
        <div><dt>Suitability score</dt><dd>{formatScore(site.suitability_score)}</dd></div>
        <div><dt>Rank</dt><dd>{formatRank(site.rank)}</dd></div>
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

      {contributions.length > 0 && (
        <section className="om-detail__section">
          <h4 className="om-detail__heading">Component scores</h4>
          <div className="om-results__scroll">
            <table className="om-results">
              <thead>
                <tr>
                  <th scope="col">Criterion</th>
                  <th scope="col" className="om-results__num">Component score</th>
                </tr>
              </thead>
              <tbody>
                {contributions.map(([key, value]) => (
                  <tr key={key}>
                    <th scope="row">{COMPONENT_LABELS[key] ?? key}</th>
                    <td className="om-results__num">{formatComponent(value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {features.length > 0 && (
        <section className="om-detail__section">
          <h4 className="om-detail__heading">Features</h4>
          <div className="om-results__scroll">
            <table className="om-results">
              <thead>
                <tr>
                  <th scope="col">Feature</th>
                  <th scope="col" className="om-results__num">Value</th>
                </tr>
              </thead>
              <tbody>
                {features.map(([key, value]) => (
                  <tr key={key}>
                    <th scope="row">{COMPONENT_LABELS[key] ?? key}</th>
                    <td className="om-results__num">{formatFeatureWithUnit(key, value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <StringListSection heading="Demand proxy caveats" items={proxyCaveats} />
      <StringListSection heading="Data-quality notes" items={dataQualityNotes} />
    </div>
  );
}
