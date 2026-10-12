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
 *
 * CELL SELECTION (S3-06 extension) — a DISPLAY FILTER, never a re-rank. The user
 * can narrow WHICH cells the table lists via (a) a text search over `cell_id`
 * and (b) a mini-map ({@link CellPicker}) on which they drag a rectangle to pick
 * every cell whose centre falls inside it. The engine still ranks the FULL
 * population and `compareScenarios` is called UNCHANGED; the shown
 * rank_a/rank_b/rank_delta remain the engine's GLOBAL ranks and rows stay in the
 * engine's returned order — this component only OMITS rows the user filtered
 * out. The two controls COMPOSE as an intersection: a row is shown iff it is in
 * the rectangle selection (when one is active) AND its `cell_id` contains the
 * search substring (when one is typed). An empty rectangle selection + empty
 * search = all rows, exactly as before. Clear resets the rectangle selection;
 * clearing the search box removes the substring filter. There is NO scoring,
 * ranking, normalisation, re-sorting or delta arithmetic here — only `.filter`
 * / `.includes` / `Set` membership over the already-ranked rows.
 */
import { useState } from "react";

import type {
  Criterion,
  DecisionService,
  ScenarioComparison,
} from "../api/decision-service";
import {
  featureLabel,
  validateWeights,
  type WeightingOption,
} from "./AnalysisControls";
import CellPicker from "./CellPicker";

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
  /** The current run id, used by the mini-map cell picker (null = no run). */
  runId: string | null;
  /** The shared typed client, injected into the mini-map cell picker. */
  service: DecisionService | null;
  /**
   * The rectangle-selected cell ids scoping the TABLE (a DISPLAY FILTER). `null`
   * (or empty) means no rectangle selection is active, so all engine rows show.
   */
  selectedCellIds: string[] | null;
  /** Report a new rectangle selection (null clears it, returning to all rows). */
  onSelectedCellIdsChange: (ids: string[] | null) => void;
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
  runId,
  service,
  selectedCellIds,
  onSelectedCellIdsChange,
}: ScenarioComparisonProps): JSX.Element {
  // Live text filter over `cell_id` (case-insensitive substring). Local to the
  // view — it only narrows which already-ranked rows render, never the request.
  const [searchText, setSearchText] = useState("");
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

  // DISPLAY FILTER (not a re-rank): keep the engine's row order, drop only the
  // rows the user filtered out. A rectangle selection (membership in
  // `selectedSet`) AND the search substring must BOTH match. An inactive
  // selection (null/empty) or empty search simply doesn't constrain. No
  // `.sort`/`.reduce`/scoring — only `.filter`/`.includes`/`Set.has`.
  const hasSelection = selectedCellIds !== null && selectedCellIds.length > 0;
  const selectedSet = new Set(selectedCellIds ?? []);
  const search = searchText.trim().toLowerCase();
  const filteredRows =
    !hasSelection && search === ""
      ? rows
      : rows.filter(
          (row) =>
            (!hasSelection || selectedSet.has(row.cell_id)) &&
            (search === "" || row.cell_id.toLowerCase().includes(search)),
        );
  const filterActive = hasSelection || search !== "";
  const shownRows = filteredRows.slice(0, DISPLAY_ROW_LIMIT);
  // A filter that empties a non-empty engine result (so the user sees why).
  const filteredToEmpty =
    comparison !== null && rows.length > 0 && filteredRows.length === 0;
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

      {/*
        Cell selection (S3-06 extension) — a DISPLAY FILTER over the engine's
        rows, never a re-rank. The search box is the keyboard-operable
        alternative to the mouse-only drag, so selection is never mouse-only.
        Shown once there is a result to filter.
      */}
      {!error && comparison && rows.length > 0 && (
        <div className="om-comparison__selection">
          <p className="om-comparison__hint">
            Narrow which cells the table lists below. This is a{" "}
            <strong>display filter only</strong> — the engine still ranks every
            eligible cell, so the ranks shown stay global and comparable. An
            empty selection means all cells.
          </p>
          <label className="om-comparison__search">
            <span>Search by Site ID</span>
            <input
              type="search"
              value={searchText}
              placeholder="e.g. S31.186"
              aria-label="Filter comparison rows by Site ID"
              onChange={(event) => setSearchText(event.target.value)}
            />
          </label>
          {service ? (
            <CellPicker
              runId={runId}
              service={service}
              onApply={(ids) => onSelectedCellIdsChange(ids)}
              onClear={() => onSelectedCellIdsChange(null)}
              activeCount={selectedCellIds?.length ?? 0}
            />
          ) : (
            <p className="om-comparison__hint">
              The map picker is unavailable until the service connects. You can
              still filter by Site ID above.
            </p>
          )}
        </div>
      )}

      {error && (
        <p className="om-service-error" role="alert">
          Scenario comparison unavailable: {error}
        </p>
      )}

      {!error && comparison && rows.length === 0 && (
        <p className="om-comparison__hint">
          The engine returned no comparable cells for this pair.
        </p>
      )}

      {!error && filteredToEmpty && (
        <p className="om-comparison__hint" role="status">
          No cells match this selection. Clear the search box or the rectangle
          selection to show all {rows.length.toLocaleString()} ranked cells.
        </p>
      )}

      {!error && shownRows.length > 0 && (
        <div className="om-comparison__results">
          <p className="om-comparison__caption">
            Per-cell ranks under each preference, in engine order (showing{" "}
            {shownRows.length} of{" "}
            {filterActive
              ? `${filteredRows.length.toLocaleString()} selected (${rows.length.toLocaleString()} ranked)`
              : `${rows.length.toLocaleString()}`}{" "}
            cells). Ranks are the engine's global ranks across all cells — the
            filter only changes which rows are listed, not their ranking. A
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
