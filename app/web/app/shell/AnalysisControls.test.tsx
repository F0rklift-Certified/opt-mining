/**
 * Render/interaction tests for the S3-02 scenario preset controls.
 *
 * Covers the ticket's deliverables directly: a preset selector, a run
 * action, and a display of what's actually behind the results on screen —
 * without any scoring/normalisation logic living in this component.
 */
import { fireEvent, render, screen } from "@testing-library/react";

import AnalysisControls, { SCENARIO_PRESETS } from "./AnalysisControls";

describe("AnalysisControls", () => {
  it("renders one radio per scenario preset, none as a combobox/listbox", () => {
    render(
      <AnalysisControls
        scenario="wind_led"
        onScenarioChange={jest.fn()}
        onRun={jest.fn()}
        running={false}
        activeRun={null}
      />,
    );

    for (const preset of SCENARIO_PRESETS) {
      expect(screen.getByRole("radio", { name: preset.label })).toBeInTheDocument();
    }
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("marks the current scenario's radio as checked", () => {
    render(
      <AnalysisControls
        scenario="grid_led"
        onScenarioChange={jest.fn()}
        onRun={jest.fn()}
        running={false}
        activeRun={null}
      />,
    );

    expect(screen.getByRole("radio", { name: "Grid-led" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Wind-led" })).not.toBeChecked();
  });

  it("calls onScenarioChange with the preset id when a different preset is picked", () => {
    const onScenarioChange = jest.fn();
    render(
      <AnalysisControls
        scenario="wind_led"
        onScenarioChange={onScenarioChange}
        onRun={jest.fn()}
        running={false}
        activeRun={null}
      />,
    );

    fireEvent.click(screen.getByRole("radio", { name: "Grid-led" }));

    expect(onScenarioChange).toHaveBeenCalledWith("grid_led");
  });

  it("calls onRun when the run button is clicked", () => {
    const onRun = jest.fn();
    render(
      <AnalysisControls
        scenario="wind_led"
        onScenarioChange={jest.fn()}
        onRun={onRun}
        running={false}
        activeRun={null}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /run analysis/i }));

    expect(onRun).toHaveBeenCalledTimes(1);
  });

  it("disables the presets and the run button while running", () => {
    render(
      <AnalysisControls
        scenario="wind_led"
        onScenarioChange={jest.fn()}
        onRun={jest.fn()}
        running
        activeRun={null}
      />,
    );

    expect(screen.getByRole("radio", { name: "Wind-led" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /running/i })).toBeDisabled();
  });

  it("shows no active run until one exists, then displays it", () => {
    const { rerender } = render(
      <AnalysisControls
        scenario="wind_led"
        onScenarioChange={jest.fn()}
        onRun={jest.fn()}
        running={false}
        activeRun={null}
      />,
    );
    expect(screen.getByText(/no run is available/i)).toBeInTheDocument();

    rerender(
      <AnalysisControls
        scenario="wind_led"
        onScenarioChange={jest.fn()}
        onRun={jest.fn()}
        running={false}
        activeRun={{ run_id: "run-1", scenario: "wind_led", weights_id: "wind_led" }}
      />,
    );

    expect(screen.queryByText(/no run is available/i)).not.toBeInTheDocument();
    expect(screen.getByText("run-1")).toBeInTheDocument();
  });
});
