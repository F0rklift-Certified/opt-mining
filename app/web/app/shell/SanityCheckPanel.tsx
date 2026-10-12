/**
 * SanityCheckPanel — the in-app S1-12 sanity-check / validation surface (S3-08).
 *
 * A pure view over `GET /sanity-check` (the sanity Results_Sidecar projected by
 * `pipeline.service.get_sanity_check`). It mirrors `DataQualityBanner`'s
 * loading / error / content contract and renders VERBATIM the fields the service
 * already computed:
 *   - the model-not-trained `caveat`, shown prominently at the top on EVERY
 *     state (including a passing result) — FR2/AC3;
 *   - the lineage line from `run_metadata` (run timestamp, pipeline version,
 *     resolved shortlist), or "lineage metadata unavailable" when the fields are
 *     empty/missing — FR5/AC7;
 *   - the baseline-vs-scenario disclosure driven by the `isBaselineRun` prop
 *     derived in `AppShell` — AC8;
 *   - each check's expected / observed with an explicit PASS or FAIL badge;
 *   - the known-wind-farm comparison table with the top-ranked band N rendered
 *     in the in-band column header (Finding 8);
 *   - the FULL contradictions list, each row carrying its source check label.
 *
 * The component performs NO decision arithmetic — no pass/fail or percentile is
 * computed here; it formats fields the service already produced (NFR1).
 */
import type { SanityCheck } from "../api/decision-service";

export interface SanityCheckPanelProps {
  sanity: SanityCheck | null;
  error: string | null;
  loading: boolean;
  /**
   * True only when the active single-run selection is the UNMODIFIED baseline
   * (option id is the default AND the baseline criteria are untouched). Derived
   * in `AppShell`; the panel renders — but never computes — the disclosure.
   */
  isBaselineRun: boolean;
}

/** The always-on caveat heading, shown on every state including a pass. */
function Caveat({ text }: { text: string }): JSX.Element {
  const copy =
    text.trim().length > 0
      ? text
      : "The model is NOT trained to reproduce the known wind/REZ locations — a strong overlap is corroboration, not a target the model was fit to.";
  return (
    <p className="om-sanity__caveat" role="note">
      <strong>Caveat.</strong> {copy}
    </p>
  );
}

/** Format a nullable numeric field served by the engine (no arithmetic). */
function formatNumber(value: number | null | undefined, digits: number): string {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(digits)
    : "—";
}

/** Format an integer rank/count served by the engine. */
function formatInteger(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? String(value) : "—";
}

export default function SanityCheckPanel({
  sanity,
  error,
  loading,
  isBaselineRun,
}: SanityCheckPanelProps): JSX.Element {
  if (loading) {
    return (
      <section className="om-sanity om-sanity--loading" role="status">
        Loading the sanity-check / validation result…
      </section>
    );
  }

  if (error) {
    return (
      <section className="om-sanity om-sanity--failed" role="alert">
        <strong>Sanity-check result is unavailable.</strong> {error}
      </section>
    );
  }

  if (!sanity) return <></>;

  const checks = sanity.checks ?? [];
  const contradictions = sanity.contradictions ?? [];
  const windFarms = sanity.wind_farms ?? [];
  const metadata = sanity.run_metadata ?? null;
  const topBandN = sanity.top_band_n ?? 0;

  const hasLineage =
    metadata !== null &&
    [metadata.run_timestamp, metadata.pipeline_version, metadata.resolved_shortlist_path].some(
      (field) => typeof field === "string" && field.trim().length > 0,
    );

  return (
    <section className="om-sanity" aria-label="Sanity check / validation result">
      <Caveat text={sanity.caveat ?? ""} />

      {isBaselineRun ? (
        <p className="om-sanity__lineage-state om-sanity__lineage-state--baseline" role="status">
          This sanity result reflects the same engine output as the map and
          shortlist (the unmodified baseline run).
        </p>
      ) : (
        <p className="om-sanity__lineage-state om-sanity__lineage-state--scenario" role="alert">
          Sanity reflects the BASELINE run, not the current scenario — the figures
          below do not correspond to the weights currently shown on the
          map/shortlist.
        </p>
      )}

      <p className="om-sanity__lineage">
        {hasLineage && metadata ? (
          <>
            <span>Run {metadata.run_timestamp || "—"}</span>
            {" · "}
            <span>pipeline {metadata.pipeline_version || "—"}</span>
            {" · "}
            <span>
              shortlist <code>{metadata.resolved_shortlist_path || "—"}</code>
            </span>
          </>
        ) : (
          "lineage metadata unavailable"
        )}
      </p>

      {sanity.preliminary_disclaimer && sanity.preliminary_disclaimer.trim().length > 0 && (
        <p className="om-sanity__disclaimer">{sanity.preliminary_disclaimer}</p>
      )}

      <section className="om-sanity__section">
        <h3 className="om-sanity__heading">Checks</h3>
        {checks.length > 0 ? (
          <ul className="om-sanity__checks">
            {checks.map((check) => (
              <li key={check.name} className="om-sanity__check">
                <span
                  className={`om-sanity__badge ${
                    check.passed ? "om-sanity__badge--pass" : "om-sanity__badge--fail"
                  }`}
                >
                  {check.passed ? "PASS" : "FAIL"}
                </span>{" "}
                <strong>{check.name}</strong>: expected {check.expected}; observed{" "}
                {check.observed}
              </li>
            ))}
          </ul>
        ) : (
          <p>No checks were returned.</p>
        )}
      </section>

      <section className="om-sanity__section">
        <h3 className="om-sanity__heading">Known wind-farm comparison</h3>
        {windFarms.length > 0 ? (
          <div className="om-results__scroll">
            <table className="om-results om-sanity__wind-farms">
              <thead>
                <tr>
                  <th scope="col">Wind farm</th>
                  <th scope="col">Site ID</th>
                  <th scope="col" className="om-results__num">Score</th>
                  <th scope="col" className="om-results__num">Rank</th>
                  <th scope="col" className="om-results__num">Percentile</th>
                  <th scope="col">In top-ranked band (rank ≤ {topBandN})</th>
                </tr>
              </thead>
              <tbody>
                {windFarms.map((row) => (
                  <tr key={`${row.wind_farm}-${row.cell_id}`}>
                    <th scope="row">{row.wind_farm}</th>
                    <td><code>{row.cell_id}</code></td>
                    <td className="om-results__num">{formatNumber(row.score, 3)}</td>
                    <td className="om-results__num">{formatInteger(row.rank)}</td>
                    <td className="om-results__num">{formatNumber(row.percentile, 2)}</td>
                    <td>{row.in_upper_quartile ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p>No known wind farms were located for comparison.</p>
        )}
      </section>

      <section className="om-sanity__section">
        <h3 className="om-sanity__heading">Contradictions investigated</h3>
        {contradictions.length > 0 ? (
          <ul className="om-sanity__contradictions">
            {contradictions.map((item, index) => (
              <li key={`${item.check}-${index}`} className="om-sanity__contradiction">
                <span className="om-sanity__check-label">{item.check}</span>{" "}
                <span className="om-sanity__kind">({item.kind})</span>:{" "}
                {item.description}
                {item.investigation_note && item.investigation_note.trim().length > 0 && (
                  <span className="om-sanity__note"> — {item.investigation_note}</span>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p>No contradictions were recorded.</p>
        )}
      </section>
    </section>
  );
}
