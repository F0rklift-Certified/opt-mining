"use client";

/**
 * Scenario-comparison panel (S3-06).
 *
 * A pure view over the S2-07 engine's `compare_scenarios` output, surfaced by
 * the S2-08 service's `POST /scenario-comparison` operation. The user picks two
 * of the named S2-07 WEIGHTING presets (the non-editable `WEIGHTING_OPTIONS`
 * from S3-02's AnalysisControls) and triggers the comparison; AppShell makes the
 * single HTTP call and hands the result here. The engine returns, per cell, the
 * rank under scenario A, the rank under scenario B and the rank delta — this
 * component renders those values exactly as served. There is NO UI-side
 * re-ranking, re-scoring or re-sorting: rows arrive ordered by the engine
 * (ascending rank under scenario A) and are displayed in that order, top slice
 * first.
 *
 * These are PREFERENCE / WEIGHTING scenarios — different value judgements about
 * what matters (e.g. resource strength vs grid proximity). They are NOT
 * probabilistic uncertainty scenarios: no scenario is more or less "likely", and
 * the comparison carries no probabilities. The copy below states this
 * explicitly, per the task guidance.
 */
import type {
  ScenarioComparison,
  ScenarioComparisonRequest,
} from "../api/decision-service";
import type { WeightingOption } from "./AnalysisControls";

/** How many of the engine-ordered rows to display (a display slice, not a re-rank). */
const DISPLAY_ROW_LIMIT = 20;

export interface ScenarioComparisonProps {
  /**
   * The weighting presets available to compare. Only non-editable, named S2-07
   * scenarios (e.g. Wind-led, Grid-led) are valid comparison keys; the editable
   * Baseline is not a named scenario and is filtered out by AppShell.
   */
  presets: WeightingOption[];
  /** Currently chosen scenario A key (a preset id). */
  scenarioA: string;
  onScenarioAChange: (id: string) => void;
  /** Currently chosen scenario B key (a preset id). */
  scenarioB: string;
  onScenarioBChange: (id: string) => void;
  /** Trigger the comparison for the chosen pair. */
  onCompare: () => void;
  /** True while a comparison request is in flight. */
  loading: boolean;
  /** A failure message for the last comparison attempt, if any. */
  error: string | null;
  /** The engine's last comparison result, or null before the first run. */
  comparison: ScenarioComparison | null;
}

/** Resolve a preset id to its human label, falling back to the raw key. */
function presetLabel(presets: WeightingOption[], id: string | undefined): string {
  if (!id) return "";
  const match = presets.find((preset) => preset.id === id);
  return match ? match.label : id;
}

/** Format a rank for display; the engine may omit a rank (cell not ranked here). */
function formatRank(rank: number | null | undefined): string {
  return rank === null || rank === undefined ? "—" : String(rank);
}

/**
 * Describe a rank delta in plain words. The engine defines
 * `rank_delta = rank_a - rank_b`, so a NEGATIVE delta means the cell ranks
 * better (nearer rank 1) under scenario A, and a POSITIVE delta means it ranks
 * better under scenario B. Rendered verbatim from the engine value — no maths.
 */
function formatDelta(delta: number | null | undefined): string {
  if (delta === null || delta === undefined) return "—";
  if (delta === 0) return "0";
  return delta > 0 ? `+${delta}` : String(delta);
}

export default function ScenarioComparison({
  presets,
  scenarioA,
  onScenarioAChange,
  scenarioB,
  onScenarioBChange,
  onCompare,
  loading,
  error,
  comparison,
}: ScenarioComparisonProps): JSX.Element {
  const samePair = scenarioA === scenarioB;
  const canCompare = presets.length >= 2 && !samePair && !loading;

  const labels = comparison?.labels ?? {};
  const rows = comparison?.rows ?? [];
  const shownRows = rows.slice(0, DISPLAY_ROW_LIMIT);
  // Column headers echo the two compared scenario keys the engine reported,
  // mapped back to their preset labels for readability.
  const columnA = presetLabel(presets, labels.a) || presetLabel(presets, scenarioA);
  const columnB = presetLabel(presets, labels.b) || presetLabel(presets, scenarioB);

  return (
    <div className="om-comparison">
      <p className="om-comparison__note">
        These are <strong>weighting / preference</strong> scenarios — each one is
        a different judgement about what matters most (for example, resource
        strength versus grid proximity). They are <strong>not</strong>{" "}
        probabilistic or uncertainty scenarios: no scenario is more or less
        likely, and the comparison carries no probabilities. It only shows how
        the engine ranks sites under each set of preferences.
      </p>

      <div className="om-comparison__controls">
        {/*
          Scenarios are chosen with radio groups rather than a <select>: the
          shell's R1.2 guard forbids any combobox/listbox control (the fixed-NSW
          design), and AnalysisControls follows the same convention.
        */}
        <fieldset className="om-comparison__field" disabled={loading}>
          <legend>Scenario A</legend>
          {presets.map((preset) => (
            <label key={preset.id} className="om-comparison__option">
              <input
                type="radio"
                name="scenario-a"
                value={preset.id}
                checked={scenarioA === preset.id}
                onChange={() => onScenarioAChange(preset.id)}
              />
              {preset.label}
            </label>
          ))}
        </fieldset>

        <fieldset className="om-comparison__field" disabled={loading}>
          <legend>Scenario B</legend>
          {presets.map((preset) => (
            <label key={preset.id} className="om-comparison__option">
              <input
                type="radio"
                name="scenario-b"
                value={preset.id}
                checked={scenarioB === preset.id}
                onChange={() => onScenarioBChange(preset.id)}
              />
              {preset.label}
            </label>
          ))}
        </fieldset>

        <button type="button" onClick={onCompare} disabled={!canCompare}>
          {loading ? "Comparing…" : "Compare scenarios"}
        </button>
      </div>

      {samePair && (
        <p className="om-comparison__hint" role="status">
          Choose two different scenarios to compare their rankings.
        </p>
      )}

      {error && (
        <p className="om-service-error" role="alert">
          Scenario comparison unavailable: {error}
        </p>
      )}

      {!error && comparison && shownRows.length === 0 && (
        <p className="om-comparison__hint">
          The engine returned no comparable cells for this pair.
        </p>
      )}

      {!error && shownRows.length > 0 && (
        <div className="om-comparison__results">
          <p className="om-comparison__caption">
            Per-cell ranks under each preference, in engine order (top{" "}
            {shownRows.length} of {rows.length.toLocaleString()} cells). A
            negative delta means the cell ranks better under{" "}
            <strong>{columnA}</strong>; a positive delta means it ranks better
            under <strong>{columnB}</strong>.
          </p>
          <div className="om-results__scroll">
            <table className="om-results om-comparison__table">
              <thead>
                <tr>
                  <th scope="col">Site ID</th>
                  <th scope="col" className="om-results__num">
                    Rank — {columnA}
                  </th>
                  <th scope="col" className="om-results__num">
                    Rank — {columnB}
                  </th>
                  <th scope="col" className="om-results__num">
                    Rank delta
                  </th>
                </tr>
              </thead>
              <tbody>
                {shownRows.map((row) => (
                  <tr key={row.cell_id}>
                    <th scope="row">
                      <code>{row.cell_id}</code>
                    </th>
                    <td className="om-results__num">{formatRank(row.rank_a)}</td>
                    <td className="om-results__num">{formatRank(row.rank_b)}</td>
                    <td className="om-results__num">{formatDelta(row.rank_delta)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!error && !comparison && !loading && (
        <p className="om-comparison__hint">
          Pick two preference scenarios and compare to see how the site ranking
          changes between them.
        </p>
      )}
    </div>
  );
}

export { DISPLAY_ROW_LIMIT };
