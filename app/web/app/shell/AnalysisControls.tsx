"use client";

/**
 * AnalysisControls — weighting picker, weight display, and run action (S3-02).
 *
 * Three weighting options are offered: the S1-10/S2-01 documented Baseline
 * (editable) and the two S2-07 scenario presets (locked). There is no
 * endpoint to list scenarios or fetch a weights configuration, so all three
 * criteria sets are mirrored here from their source of truth —
 * `pipeline/scoring/scoring_weights.yaml` (Baseline) and
 * `pipeline/scoring/scenarios.yaml` (Wind-led / Grid-led) — rather than
 * invented. Selecting an option and clicking Run only changes what is sent to
 * `run_analysis` (either `{ scenario }` or `{ weights }`); every score, rank
 * and weight shown afterwards comes back from the service.
 *
 * Presets are rendered as radio buttons rather than a <select> because the
 * existing shell test forbids any combobox/listbox in the shell (the NSW
 * region is intentionally fixed with no selector).
 */
import type { Criterion, RunHandle } from "../api/decision-service";

const FEATURE_LABELS: Record<string, string> = {
  wind_speed: "Wind speed",
  dist_transmission_km: "Distance to transmission",
  demand_proxy: "Demand proxy",
  dist_substation_km: "Distance to substation",
  slope_deg: "Slope",
  inside_rez: "Inside REZ",
};

function featureLabel(feature: string): string {
  return FEATURE_LABELS[feature] ?? feature;
}

/**
 * The S1-10/S2-01 documented default weights, mirrored from
 * `pipeline/scoring/scoring_weights.yaml`. This is the Baseline option and
 * the shell's default — it must match that file's values (Requirement:
 * "Default weights match the documented S2-01 assumptions").
 */
export const BASELINE_CRITERIA: Criterion[] = [
  {
    feature: "wind_speed",
    weight: 0.35,
    direction: "higher_is_better",
    rationale:
      "Primary resource indicator; energy yield scales roughly with the cube of wind speed.",
  },
  {
    feature: "dist_transmission_km",
    weight: 0.2,
    direction: "lower_is_better",
    rationale:
      "Connection cost is a major capex component and scales with distance to the nearest ≥132 kV line.",
  },
  {
    feature: "demand_proxy",
    weight: 0.15,
    direction: "higher_is_better",
    rationale:
      "Proximity to electrical demand improves offtake prospects (a NEM-region annual mean proxy).",
  },
  {
    feature: "dist_substation_km",
    weight: 0.1,
    direction: "lower_is_better",
    rationale:
      "Substation proximity reduces interconnection complexity; weighted below transmission distance because the two are partly collinear.",
  },
  {
    feature: "slope_deg",
    weight: 0.1,
    direction: "lower_is_better",
    rationale:
      "Flatter terrain lowers civil-works and turbine-siting cost, complementing the hard slope exclusion.",
  },
  {
    feature: "inside_rez",
    weight: 0.1,
    direction: "higher_is_better",
    rationale:
      "Cells inside a declared NSW Renewable Energy Zone benefit from coordinated network planning.",
  },
];

const WIND_LED_CRITERIA: Criterion[] = [
  {
    feature: "wind_speed",
    weight: 0.55,
    direction: "higher_is_better",
    rationale:
      "Emphasised under this preference — cells with the strongest resource rise to the top even further from the grid.",
  },
  {
    feature: "dist_transmission_km",
    weight: 0.15,
    direction: "lower_is_better",
    rationale: "Down-weighted so grid proximity cannot outweigh a strong resource.",
  },
  {
    feature: "demand_proxy",
    weight: 0.1,
    direction: "higher_is_better",
    rationale:
      "Proximity to electrical demand improves offtake prospects (a NEM-region annual mean proxy).",
  },
  {
    feature: "dist_substation_km",
    weight: 0.05,
    direction: "lower_is_better",
    rationale:
      "Weighted lightly to avoid double-counting the same near-the-grid signal as transmission distance.",
  },
  {
    feature: "slope_deg",
    weight: 0.05,
    direction: "lower_is_better",
    rationale: "A continuous penalty complementing the hard slope exclusion.",
  },
  {
    feature: "inside_rez",
    weight: 0.1,
    direction: "higher_is_better",
    rationale: "A modest policy signal from coordinated network planning.",
  },
];

const GRID_LED_CRITERIA: Criterion[] = [
  {
    feature: "wind_speed",
    weight: 0.25,
    direction: "higher_is_better",
    rationale:
      "Still matters, but down-weighted relative to connection accessibility under this preference.",
  },
  {
    feature: "dist_transmission_km",
    weight: 0.35,
    direction: "lower_is_better",
    rationale:
      "The dominant discriminator under this preference — connection cost to the nearest ≥132 kV line.",
  },
  {
    feature: "demand_proxy",
    weight: 0.1,
    direction: "higher_is_better",
    rationale:
      "Proximity to electrical demand improves offtake prospects (a NEM-region annual mean proxy).",
  },
  {
    feature: "dist_substation_km",
    weight: 0.1,
    direction: "lower_is_better",
    rationale:
      "Weighted higher than Wind-led because interconnection accessibility is central to this preference.",
  },
  {
    feature: "slope_deg",
    weight: 0.05,
    direction: "lower_is_better",
    rationale: "A continuous penalty complementing the hard slope exclusion.",
  },
  {
    feature: "inside_rez",
    weight: 0.15,
    direction: "higher_is_better",
    rationale:
      "Emphasised — REZ membership brings committed transmission investment and an established access regime.",
  },
];

export interface WeightingOption {
  id: string;
  label: string;
  /** Baseline's weights are user-editable; a preset's are locked. */
  editable: boolean;
  criteria: Criterion[];
}

/** The three offered weightings. Only "baseline" is editable (AC5 "and/or"). */
export const WEIGHTING_OPTIONS: WeightingOption[] = [
  { id: "baseline", label: "Baseline (default)", editable: true, criteria: BASELINE_CRITERIA },
  { id: "wind_led", label: "Wind-led", editable: false, criteria: WIND_LED_CRITERIA },
  { id: "grid_led", label: "Grid-led", editable: false, criteria: GRID_LED_CRITERIA },
];

export const DEFAULT_OPTION_ID: string = "baseline";

/**
 * Validate a Baseline criteria set before it can be sent to `run_analysis`.
 * Every weight must be a non-negative finite number, and at least one must be
 * positive (an all-zero configuration would score nothing). Returns a
 * human-readable message naming the fault, or `null` when valid.
 */
export function validateWeights(criteria: Criterion[]): string | null {
  for (const criterion of criteria) {
    if (!Number.isFinite(criterion.weight)) {
      return `${featureLabel(criterion.feature)} weight must be a number.`;
    }
    if (criterion.weight < 0) {
      return `${featureLabel(criterion.feature)} weight cannot be negative.`;
    }
  }
  if (criteria.every((criterion) => criterion.weight === 0)) {
    return "At least one weight must be greater than zero.";
  }
  return null;
}

export interface AnalysisControlsProps {
  /** Currently selected weighting option id (not yet necessarily run). */
  optionId: string;
  onOptionChange: (optionId: string) => void;
  /** The Baseline's current (possibly user-edited) criteria. */
  baselineCriteria: Criterion[];
  onBaselineCriteriaChange: (criteria: Criterion[]) => void;
  onRun: () => void;
  /** True while a run is in flight; disables the controls. */
  running: boolean;
  /** The scenario/run/weights actually behind the results on screen, if any. */
  activeRun: RunHandle | null;
}

export default function AnalysisControls({
  optionId,
  onOptionChange,
  baselineCriteria,
  onBaselineCriteriaChange,
  onRun,
  running,
  activeRun,
}: AnalysisControlsProps): JSX.Element {
  const activeOption =
    WEIGHTING_OPTIONS.find((option) => option.id === optionId) ?? WEIGHTING_OPTIONS[0]!;
  const displayedCriteria = activeOption.editable ? baselineCriteria : activeOption.criteria;
  const validationError = activeOption.editable ? validateWeights(baselineCriteria) : null;

  function handleWeightInput(index: number, value: number): void {
    const next = baselineCriteria.map((criterion, i) =>
      i === index ? { ...criterion, weight: value } : criterion,
    );
    onBaselineCriteriaChange(next);
  }

  return (
    <div className="om-controls">
      <fieldset className="om-controls__presets" disabled={running}>
        <legend>Weighting</legend>
        {WEIGHTING_OPTIONS.map((option) => (
          <label key={option.id} className="om-controls__option">
            <input
              type="radio"
              name="weighting-option"
              value={option.id}
              checked={optionId === option.id}
              onChange={() => onOptionChange(option.id)}
            />
            {option.label}
          </label>
        ))}
      </fieldset>

      <table className="om-weights">
        <caption>{activeOption.label} weights</caption>
        <thead>
          <tr>
            <th scope="col">Criterion</th>
            <th scope="col">Weight</th>
            <th scope="col">Interpretation</th>
          </tr>
        </thead>
        <tbody>
          {displayedCriteria.map((criterion, index) => (
            <tr key={criterion.feature}>
              <td>{featureLabel(criterion.feature)}</td>
              <td>
                {activeOption.editable ? (
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    aria-label={`${featureLabel(criterion.feature)} weight`}
                    value={Number.isNaN(criterion.weight) ? "" : criterion.weight}
                    disabled={running}
                    onChange={(event) => handleWeightInput(index, event.target.valueAsNumber)}
                  />
                ) : (
                  criterion.weight.toFixed(2)
                )}
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

      <button type="button" onClick={onRun} disabled={running || Boolean(validationError)}>
        {running ? "Running…" : "Run analysis"}
      </button>
      {activeRun ? (
        <dl className="om-facts">
          <div>
            <dt>Active scenario</dt>
            <dd>{activeRun.scenario ?? activeRun.weights_id}</dd>
          </div>
          <div>
            <dt>Run</dt>
            <dd>
              <code>{activeRun.run_id}</code>
            </dd>
          </div>
          <div>
            <dt>Weights</dt>
            <dd>
              <code>{activeRun.weights_id}</code>
            </dd>
          </div>
        </dl>
      ) : (
        <p>No run is available.</p>
      )}
    </div>
  );
}
