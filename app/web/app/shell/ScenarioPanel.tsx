"use client";
import { useEffect, useState } from "react";
import type { DecisionService, ScenarioComparison } from "../api/decision-service";

/** The service owns every rank and delta. The panel only selects visible rows. */
export default function ScenarioPanel({ service, selectedCellId }: {
  service: DecisionService | null; selectedCellId: string | null;
}): React.JSX.Element {
  const [comparison, setComparison] = useState<ScenarioComparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => { setComparison(null); setError(null); }, [service]);
  async function compare(): Promise<void> {
    if (!service) return;
    setLoading(true); setError(null);
    try { setComparison(await service.compareScenarios({ scenario_a: "wind_led", scenario_b: "grid_led" })); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Comparison unavailable"); }
    finally { setLoading(false); }
  }
  const selected = comparison?.rows?.find((row) => row.cell_id === selectedCellId);
  const visible = comparison?.rows?.slice(0, 10) ?? [];
  return <div>
    <h2>Scenario comparison</h2>
    <p>Wind-led versus Grid-led: a preference comparison, not probabilistic uncertainty. Positive rank delta means an improved rank in Grid-led.</p>
    <button onClick={() => void compare()} disabled={!service || loading}>{loading ? "Comparing…" : "Compare Wind-led and Grid-led"}</button>
    {error && <p role="alert">{error}</p>}
    {comparison && <>
      <p>{comparison.labels?.a} / {comparison.labels?.b} · {comparison.rows?.length.toLocaleString()} common eligible cells.</p>
      {selected && <p>Selected cell comparison: {selected.cell_id} · {selected.rank_a} → {selected.rank_b} · delta {selected.rank_delta}</p>}
      <table><thead><tr><th>Cell</th><th>Wind-led rank</th><th>Grid-led rank</th><th>Engine rank delta</th></tr></thead><tbody>
        {visible.map((row) => <tr key={row.cell_id}><td>{row.cell_id}</td><td>{row.rank_a}</td><td>{row.rank_b}</td><td>{row.rank_delta}</td></tr>)}
      </tbody></table>
      <p>Why ranks change: the scenarios apply different criterion weights to the same input and normalisation population. The controls show the actual weights. Run each preset to inspect its engine-specific factors and contributions for the same cell.</p>
    </>}
  </div>;
}
