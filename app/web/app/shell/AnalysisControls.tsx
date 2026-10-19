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

export const FEATURE_LABELS: Record<string, string> = {
  wind_speed: "Wind speed",
  dist_transmission_km: "Distance to transmission",
  demand_proxy: "Demand proxy",
  dist_substation_km: "Distance to substation",
  slope_deg: "Slope",
  inside_rez: "Inside REZ",
};

export function featureLabel(feature: string): string {
  return FEATURE_LABELS[feature] ?? feature;
}

/**
 * Hover-help naming where each criterion's data came from, surfaced via the
 * native `title` tooltip on the criterion cell. Sources are taken from the
 * `DATA/**` provenance records (see `DATA/integration/DATA_PROVENANCE.md` and
 * the per-feature `DATA_PROVENANCE.md` files) so the text reflects the real
 * lineage rather than a guess.
 */
export const FEATURE_SOURCES: Record<string, string> = {
  wind_speed:
    "Source: Global Wind Atlas v4 — mean wind speed at 100 m hub height, sampled per analysis cell.",
  dist_transmission_km:
    "Source: Geoscience Australia transmission lines (≥132 kV) — straight-line distance from each cell centroid in EPSG:3577 (Australian Albers).",
  demand_proxy:
    "Source: AEMO regional annual-mean demand distributed within each NEM region by a weighting surface — ABS UCL 2021 urban footprint (default) or, under the load_weighted method, real NSW zone-substation maximum demand (DNSP DAPR, geocoded, distance-decay). A proxy for nearness to existing network load, not measured local demand and not a guarantee of spare capacity or offtake.",
  dist_substation_km:
    "Source: Geoscience Australia substations — straight-line distance from each cell centroid in EPSG:3577 (Australian Albers).",
  slope_deg:
    "Source: NASA SRTM GL3 (~90 m) elevation — Horn 3×3 slope in degrees, derived per cell.",
  inside_rez:
    "Source: EnergyCo NSW Renewable Energy Zones — whether the cell falls inside a declared REZ.",
};

/** Where a criterion's data came from, for the Criterion-cell tooltip. */
export function featureSource(feature: string): string {
  return FEATURE_SOURCES[feature] ?? "Source: see DATA provenance records.";
}

/**
 * Short, plain-language text shown in the Interpretation column. The full
 * reasoning stays in each criterion's `rationale` (sent to the service and
 * shown on hover), while the table displays this simplified one-liner. Keyed
 * by feature; falls back to a direction-based sentence for anything unmapped.
 */
export const FEATURE_INTERPRETATION: Record<string, string> = {
  wind_speed:
    "Windier sites score higher — stronger wind means more energy generated, so it's the main driver of a good site.",
  dist_transmission_km:
    "Sites closer to a transmission line score higher — a shorter connection to the grid means lower build cost.",
  demand_proxy:
    "Sites nearer to existing network load score higher — a regional demand total is spread within each NEM region by urban footprint (default) or, under load_weighted, by real zone-substation maximum demand, so cells near where power is already used rate higher. A proxy for an easier market, not a guarantee of spare capacity or offtake.",
  dist_substation_km:
    "Sites closer to a substation score higher — a nearby connection point keeps hook-up simpler and cheaper.",
  slope_deg:
    "Flatter sites score higher — gentle terrain is easier and cheaper to build turbines on than steep land.",
  inside_rez:
    "Sites inside a Renewable Energy Zone score higher — these areas have planned grid investment and clearer access.",
};

/** The simplified Interpretation text for a criterion. */
export function interpretationText(criterion: Criterion): string {
  const mapped = FEATURE_INTERPRETATION[criterion.feature];
  if (mapped) {
    return mapped;
  }
  return criterion.direction === "higher_is_better"
    ? "Higher values score higher."
    : "Lower values score higher.";
}

/**
 * Hover-help for the three weight-table column headers. Each is a short,
 * plain-language sentence explaining what the column means, surfaced via the
 * native `title` tooltip on the `<th>`.
 */
export const COLUMN_HELP: Record<"criterion" | "weight" | "interpretation", string> = {
  criterion:
    "The site characteristic being scored (e.g. wind speed or distance to transmission). Each cell is measured on every criterion.",
  weight:
    "How much this criterion counts toward the overall suitability score. Weights are relative — a larger weight pulls the ranking more strongly, and the weights sum to 1 across all criteria.",
  interpretation:
    "Why this criterion matters and which direction is favourable — whether higher or lower values make a site more suitable.",
};

/**
 * Hover-help for a single weight value. Combines the criterion's direction
 * (higher-is-better vs lower-is-better) with its share of the total so the
 * tooltip explains both how the value is measured and how heavily it counts.
 */
export function weightHelp(criterion: Criterion): string {
  const direction =
    criterion.direction === "higher_is_better"
      ? "Higher values score better — a cell is more suitable as this measure rises."
      : "Lower values score better — a cell is more suitable as this measure falls.";
  const share = `Weight ${criterion.weight.toFixed(2)}: this criterion contributes ${(
    criterion.weight * 100
  ).toFixed(0)}% of the overall score.`;
  return `${direction} ${share}`;
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
      "Proximity to existing network load improves offtake prospects (a NEM-region annual-mean total distributed within each region by urban footprint, or by real zone-substation maximum demand under load_weighted; a proxy, not measured local demand or a guarantee of spare capacity or offtake).",
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
      "Proximity to existing network load improves offtake prospects (a NEM-region annual-mean total distributed within each region by urban footprint, or by real zone-substation maximum demand under load_weighted; a proxy, not measured local demand or a guarantee of spare capacity or offtake).",
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
      "Proximity to existing network load improves offtake prospects (a NEM-region annual-mean total distributed within each region by urban footprint, or by real zone-substation maximum demand under load_weighted; a proxy, not measured local demand or a guarantee of spare capacity or offtake).",
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
            <th scope="col" title={COLUMN_HELP.criterion}>
              Criterion
            </th>
            <th scope="col" title={COLUMN_HELP.weight}>
              Weight
            </th>
            <th scope="col" title={COLUMN_HELP.interpretation}>
              Interpretation
            </th>
          </tr>
        </thead>
        <tbody>
          {displayedCriteria.map((criterion, index) => (
            <tr key={criterion.feature}>
              <td title={featureSource(criterion.feature)}>
                {featureLabel(criterion.feature)}
              </td>
              <td title={weightHelp(criterion)}>
                {activeOption.editable ? (
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    aria-label={`${featureLabel(criterion.feature)} weight`}
                    title={weightHelp(criterion)}
                    value={Number.isNaN(criterion.weight) ? "" : criterion.weight}
                    disabled={running}
                    onChange={(event) => handleWeightInput(index, event.target.valueAsNumber)}
                  />
                ) : (
                  criterion.weight.toFixed(2)
                )}
              </td>
              <td title={criterion.rationale}>{interpretationText(criterion)}</td>
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
