"use client";

/**
 * Scenario-comparison panel (S3-06, extended with custom weights).
 *
 * A pure view over the S2-07 engine's `compare_scenarios` output, surfaced by
 * the S2-08 service's `POST /scenario-comparison` operation. Each scenario SIDE
 * (A and B) is EITHER one of the named S2-07 WEIGHTING presets (the
 * non-editable `WEIGHTING_OPTIONS` from S3-02's AnalysisControls) OR a `Custom`
 * weight set the user edits over the SIX frozen criteria (the criteria set and
 * directions stay fixed — only the weights change). AppShell makes the single
 * HTTP call, passing each side as either a scenario key or an explicit weights
 * configuration, and hands the result here. The engine returns, per cell, the
 * rank under side A, the rank under side B and the rank delta — this component
 * renders those values exactly as served. There is NO UI-side re-ranking,
 * re-scoring, re-sorting or delta arithmetic: rows arrive ordered by the engine
 * (ascending rank under side A) and are displayed in that order, top slice
 * first. Editing a Custom side's weights and pressing Compare re-issues the
 * request; the engine does all the maths.
 *
 * These are PREFERENCE / WEIGHTING scenarios — different value judgements about
 * what matters (e.g. resource strength vs grid proximity). They are NOT
 * probabilistic uncertainty scenarios: no scenario is more or less "likely", and
 * the comparison carries no probabilities. The copy below states this
 * explicitly, per the task guidance.
 */
import type {
  Criterion,
  ScenarioComparison,
} from "../api/decision-service";
import {
  featureLabel,
  validateWeights,
  type WeightingOption,
} from "./AnalysisControls";

/** How many of the engine-ordered rows to display (a display slice, not a re-rank). */
const DISPLAY_ROW_LIMIT = 20;

/** Sentinel side value selecting the user-editable Custom weight set. */
export const CUSTOM_SIDE = "custom";

export interface ScenarioComparisonProps {
  /**
   * The weighting presets available to compare. Only non-editable, named S2-07
   * scenarios (e.g. Wind-led, Grid-led) are valid preset comparison keys; the
   * editable Baseline is not a named scenario and is filtered out by AppShell.
   */
  presets: WeightingOption[];
  /** Currently chosen side A: a preset id or the `CUSTOM_SIDE` sentinel. */
  scenarioA: string;
  onScenarioAChange: (id: string) => void;
  /** Currently chosen side B: a preset id or the `CUSTOM_SIDE` sentinel. */
  scenarioB: string;
  onScenarioBChange: (id: string) => void;
  /** Side A's custom criteria (editable only when scenarioA === CUSTOM_SIDE). */
  customCriteriaA: Criterion[];
  onCustomCriteriaAChange: (criteria: Criterion[]) => void;
  /** Side B's custom criteria (editable only when scenarioB === CUSTOM_SIDE). */
  customCriteriaB: Criterion[];
  onCustomCriteriaBChange: (criteria: Criterion[]) => void;
  /** Trigger the comparison for the chosen pair. */
  onCompare: () => void;
  /** True while a comparison request is in flight. */
  loading: boolean;
  /** A failure message for the last comparison attempt, if any. */
  error: string | null;
  /** The engine's last comparison result, or null before the first run. */
  comparison: ScenarioComparison | null;
}

/** Resolve a side value to its human label; `CUSTOM_SIDE` reads as "Custom". */
function sideLabel(
  presets: WeightingOption[],
  side: string | undefined,
  customName: string,
): string {
  if (!side) return "";
  if (side === CUSTOM_SIDE) return customName;
  const match = presets.find((preset) => preset.id === side);
  return match ? match.label : side;
}

/**
 * Resolve an engine-returned label key to a column heading. The engine echoes
 * a scenario key for a preset side, or `custom_a` / `custom_b` for a custom
 * side — both read as "Custom (A)" / "Custom (B)" here.
 */
function columnLabel(
  presets: WeightingOption[],
  labelKey: string | undefined,
  side: "A" | "B",
): string {
  if (labelKey === `custom_${side.toLowerCase()}`) return `Custom (${side})`;
  const match = presets.find((preset) => preset.id === labelKey);
  return match ? match.label : labelKey ?? "";
}

/** Format a rank for display; the engine may omit a rank (cell not ranked here). */
function formatRank(rank: number | null | undefined): string {
  return rank === null || rank === undefined ? "—" : String(rank);
}

/**
 * Describe a rank delta in plain words. The engine defines
 * `rank_delta = rank_a - rank_b`, so a NEGATIVE delta means the cell ranks
 * better (nearer rank 1) under side A, and a POSITIVE delta means it ranks
 * better under side B. Rendered verbatim from the engine value — no maths.
 */
function formatDelta(delta: number | null | undefined): string {
  if (delta === null || delta === undefined) return "—";
  if (delta === 0) return "0";
  return delta > 0 ? `+${delta}` : String(delta);
}

/**
 * A per-side scenario chooser: a radio group over the named presets PLUS a
 * `Custom` option, and (when Custom is chosen) an editable weight table over
 * the six frozen criteria. The editor mirrors the S3-02 AnalysisControls
 * pattern exactly — same labels, same `type="number"` controls, same
 * `.om-weights` table, same `validateWeights` guard — and edits only the
 * touched criterion, carrying the rest through unchanged. It performs NO
 * scoring, ranking or normalisation: it only collects weight numbers for the
 * engine.
 */
function SideChooser({
  side,
  legend,
  radioName,
  presets,
  value,
  onValueChange,
  customCriteria,
  onCustomCriteriaChange,
  loading,
}: {
  side: "A" | "B";
  legend: string;
  radioName: string;
  presets: WeightingOption[];
  value: string;
  onValueChange: (id: string) => void;
  customCriteria: Criterion[];
  onCustomCriteriaChange: (criteria: Criterion[]) => void;
  loading: boolean;
}): JSX.Element {
  const isCustom = value === CUSTOM_SIDE;
  const validationError = isCustom ? validateWeights(customCriteria) : null;

  function handleWeightInput(index: number, weight: number): void {
    const next = customCriteria.map((criterion, i) =>
      i === index ? { ...criterion, weight } : criterion,
    );
    onCustomCriteriaChange(next);
  }

  return (
    <div className="om-comparison__side">
      <fieldset className="om-comparison__field" disabled={loading}>
        <legend>{legend}</legend>
        {presets.map((preset) => (
          <label key={preset.id} className="om-comparison__option">
            <input
              type="radio"
              name={radioName}
              value={preset.id}
              checked={value === preset.id}
              onChange={() => onValueChange(preset.id)}
            />
            {preset.label}
          </label>
        ))}
        <label className="om-comparison__option">
          <input
            type="radio"
            name={radioName}
            value={CUSTOM_SIDE}
            checked={isCustom}
            onChange={() => onValueChange(CUSTOM_SIDE)}
          />
          Custom weights
        </label>
      </fieldset>

      {isCustom && (
        <div className="om-comparison__editor">
          <table className="om-weights">
            <caption>Custom ({side}) weights</caption>
            <thead>
              <tr>
                <th scope="col">Criterion</th>
                <th scope="col">Weight</th>
                <th scope="col">Interpretation</th>
              </tr>
            </thead>
            <tbody>
              {customCriteria.map((criterion, index) => (
                <tr key={criterion.feature}>
                  <td>{featureLabel(criterion.feature)}</td>
                  <td>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      aria-label={`Custom ${side} ${featureLabel(criterion.feature)} weight`}
                      value={Number.isNaN(criterion.weight) ? "" : criterion.weight}
                      disabled={loading}
                      onChange={(event) =>
                        handleWeightInput(index, event.target.valueAsNumber)
                      }
                    />
                  </td>
                  <td>{criterion.rationale}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {validationError && (
            <p className="om-controls__error" role="alert">
              {validationError}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default function ScenarioComparison({
  presets,
  scenarioA,
  onScenarioAChange,
  scenarioB,
  onScenarioBChange,
  customCriteriaA,
  onCustomCriteriaAChange,
  customCriteriaB,
  onCustomCriteriaBChange,
  onCompare,
  loading,
  error,
  comparison,
}: ScenarioComparisonProps): JSX.Element {
  // Two Custom sides are indistinguishable as a pair only when neither is
  // custom; two custom sides can legitimately be compared (different weights).
  const samePreset =
    scenarioA === scenarioB && scenarioA !== CUSTOM_SIDE;
  // The engine is the authoritative validator, but a locally-invalid custom
  // weight set (empty / all-zero / negative) can never produce a useful run,
  // so the Compare action waits until each custom side is at least shaped right.
  const customAInvalid =
    scenarioA === CUSTOM_SIDE && validateWeights(customCriteriaA) !== null;
  const customBInvalid =
    scenarioB === CUSTOM_SIDE && validateWeights(customCriteriaB) !== null;
  const canCompare =
    presets.length >= 1 &&
    !samePreset &&
    !customAInvalid &&
    !customBInvalid &&
    !loading;

  const labels = comparison?.labels ?? {};
  const rows = comparison?.rows ?? [];
  const shownRows = rows.slice(0, DISPLAY_ROW_LIMIT);
  // Column headers echo the two compared sides the engine reported, mapped back
  // to their preset / custom labels for readability.
  const columnA =
    columnLabel(presets, labels.a, "A") || sideLabel(presets, scenarioA, "Custom (A)");
  const columnB =
    columnLabel(presets, labels.b, "B") || sideLabel(presets, scenarioB, "Custom (B)");

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
      <p className="om-comparison__note">
        Pick a named preset for each side, or choose <strong>Custom weights</strong>{" "}
        to adjust the six criteria weights yourself. The criteria and their
        directions are fixed — only the weights change — so both sides stay
        comparable. All ranking is done by the engine; nothing is recomputed here.
      </p>

      <div className="om-comparison__controls">
        {/*
          Sides are chosen with radio groups rather than a <select>: the shell's
          R1.2 guard forbids any combobox/listbox control (the fixed-NSW design),
          and AnalysisControls follows the same convention.
        */}
        <SideChooser
          side="A"
          legend="Scenario A"
          radioName="scenario-a"
          presets={presets}
          value={scenarioA}
          onValueChange={onScenarioAChange}
          customCriteria={customCriteriaA}
          onCustomCriteriaChange={onCustomCriteriaAChange}
          loading={loading}
        />
        <SideChooser
          side="B"
          legend="Scenario B"
          radioName="scenario-b"
          presets={presets}
          value={scenarioB}
          onValueChange={onScenarioBChange}
          customCriteria={customCriteriaB}
          onCustomCriteriaChange={onCustomCriteriaBChange}
          loading={loading}
        />

        <button type="button" onClick={onCompare} disabled={!canCompare}>
          {loading ? "Comparing…" : "Compare scenarios"}
        </button>
      </div>

      {samePreset && (
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
