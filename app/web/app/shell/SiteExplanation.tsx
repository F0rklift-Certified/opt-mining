import type { SiteDetail } from "../api/decision-service";

function display(value: unknown): string {
  if (value == null) return "Unavailable (not imputed)";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4);
  if (typeof value === "object" && "code" in value && "text" in value)
    return `${String(value.code)}: ${String(value.text)}`;
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

/** Verbatim S2-06 factors, caveats and reasons; no narrative generated in the UI. */
export default function SiteExplanation({ site, excludedCount }: { site: SiteDetail; excludedCount: number }): React.JSX.Element {
  return <div className="om-detail">
    <dl className="om-facts">
      <div><dt>Site ID</dt><dd><code>{site.cell_id}</code></dd></div>
      <div><dt>Rank</dt><dd>{site.rank ?? "Not ranked"}</dd></div>
      <div><dt>Suitability</dt><dd>{site.suitability_score?.toFixed(3) ?? "Not scored"}</dd></div>
      <div><dt>Eligible</dt><dd>{site.eligible ? "Yes" : "No"}</dd></div>
      <div><dt>Excluded cells in run</dt><dd>{excludedCount.toLocaleString()}</dd></div>
      <div><dt>Data confidence</dt><dd>{display(site.features?.data_confidence)}</dd></div>
    </dl>
    <p>Demand proxy is allocated regional demand, not measured local demand. Infrastructure proximity is not available grid capacity.</p>
    {Object.entries(site.explanation ?? {}).filter(([key]) => key !== "cell_id").map(([key, raw]) => {
      const value: unknown = raw;
      return <div key={key}>
      <h3>{key.replaceAll("_", " ")}</h3>
      {Array.isArray(value) ? <ul>{value.map((item, index) => <li key={index}>{display(item)}</li>)}</ul> : <p>{display(value)}</p>}
    </div>; })}
    <details><summary>Raw and derived input features</summary>
      <p>Wind speed: m/s; distance features: km; slope: degrees; demand proxy: dimensionless; REZ membership: boolean. Values are rounded for display, not recalculated.</p>
      <table><thead><tr><th>Feature</th><th>Value</th></tr></thead><tbody>
        {Object.entries(site.features ?? {}).map(([feature, value]) => <tr key={feature}><td>{feature}</td><td>{display(value)}</td></tr>)}
      </tbody></table>
    </details>
    <h3>Engine contribution breakdown</h3>
    {site.eligible ? <table><thead><tr><th>Criterion</th><th>Weighted contribution</th></tr></thead><tbody>
      {Object.entries(site.contributions ?? {}).map(([feature, value]) => <tr key={feature}><td>{feature}</td><td>{value.toFixed(6)}</td></tr>)}
    </tbody></table> : <p>Hard-excluded cells have no score, rank or contributions. Favourable wind cannot override an exclusion.</p>}
    <p>Screening only. This cell is an area for further investigation, not a site approval or engineering-grade design.</p>
  </div>;
}
