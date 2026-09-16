"use client";

/**
 * AnalysisControls — scenario-preset picker and run action (S3-02).
 *
 * Presets are the S2-07 scenario names (pipeline/scoring/scenarios.yaml);
 * there is no endpoint yet to list them, so the two current preset ids/labels
 * are named here rather than duplicating their weights. Selecting a preset
 * and clicking Run only changes what `scenario` is sent to `run_analysis` —
 * every score, rank and weight shown comes back from the service afterwards.
 */
import type { RunHandle } from "../api/decision-service";

export interface ScenarioPreset {
  id: string;
  label: string;
}

/** Mirrors the scenario ids in pipeline/scoring/scenarios.yaml (S2-07). */
export const SCENARIO_PRESETS: ScenarioPreset[] = [
  { id: "wind_led", label: "Wind-led" },
  { id: "grid_led", label: "Grid-led" },
];

export const DEFAULT_SCENARIO: string = SCENARIO_PRESETS[0]!.id;

export interface AnalysisControlsProps {
  /** Currently selected preset id (not yet necessarily run). */
  scenario: string;
  onScenarioChange: (scenario: string) => void;
  onRun: () => void;
  /** True while a run is in flight; disables the controls. */
  running: boolean;
  /** The scenario/run/weights actually behind the results on screen, if any. */
  activeRun: RunHandle | null;
}

export default function AnalysisControls({
  scenario,
  onScenarioChange,
  onRun,
  running,
  activeRun,
}: AnalysisControlsProps): JSX.Element {
  return (
    <div className="om-controls">
      <fieldset className="om-controls__presets" disabled={running}>
        <legend>Scenario preset</legend>
        {SCENARIO_PRESETS.map((preset) => (
          <label key={preset.id} className="om-controls__option">
            <input
              type="radio"
              name="scenario-preset"
              value={preset.id}
              checked={scenario === preset.id}
              onChange={() => onScenarioChange(preset.id)}
            />
            {preset.label}
          </label>
        ))}
      </fieldset>
      <button type="button" onClick={onRun} disabled={running}>
        {running ? "Running…" : "Run analysis"}
      </button>
      {activeRun ? (
        <dl className="om-facts">
          <div>
            <dt>Active scenario</dt>
            <dd>{activeRun.scenario}</dd>
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
