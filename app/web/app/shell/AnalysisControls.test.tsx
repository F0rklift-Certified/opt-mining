/**
 * Render/interaction tests for the S3-02 weighting controls.
 *
 * Covers the ticket's deliverables directly: a Baseline/preset selector, the
 * ability to adjust weights (AC5), the active weights and their
 * interpretation being visible, a run action, graceful handling of invalid
 * weight input, and a display of what's actually behind the results on
 * screen — without any scoring/normalisation logic living in this component.
 */
import { fireEvent, render, screen } from "@testing-library/react";

import AnalysisControls, {
  BASELINE_CRITERIA,
  WEIGHTING_OPTIONS,
  validateWeights,
} from "./AnalysisControls";

type ControlsProps = Parameters<typeof AnalysisControls>[0];

function renderControls(overrides: Partial<ControlsProps> = {}) {
  const props: ControlsProps = {
    optionId: "baseline",
    onOptionChange: jest.fn(),
    baselineCriteria: BASELINE_CRITERIA,
    onBaselineCriteriaChange: jest.fn(),
    onRun: jest.fn(),
    running: false,
    activeRun: null,
    ...overrides,
  };
  render(<AnalysisControls {...props} />);
  return props;
}

describe("AnalysisControls", () => {
  it("renders one radio per weighting option, none as a combobox/listbox", () => {
    renderControls();

    for (const option of WEIGHTING_OPTIONS) {
      expect(screen.getByRole("radio", { name: option.label })).toBeInTheDocument();
    }
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("marks the current option's radio as checked", () => {
    renderControls({ optionId: "grid_led" });

    expect(screen.getByRole("radio", { name: "Grid-led" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Baseline (default)" })).not.toBeChecked();
  });

  it("calls onOptionChange with the option id when a different option is picked", () => {
    const onOptionChange = jest.fn();
    renderControls({ onOptionChange });

    fireEvent.click(screen.getByRole("radio", { name: "Grid-led" }));

    expect(onOptionChange).toHaveBeenCalledWith("grid_led");
  });

  it("defaults to the Baseline option matching the documented S2-01 weights", () => {
    renderControls();

    expect(screen.getByRole("radio", { name: "Baseline (default)" })).toBeChecked();
    expect(screen.getByLabelText("Wind speed weight")).toHaveValue(0.35);
    expect(screen.getByLabelText("Distance to transmission weight")).toHaveValue(0.2);
  });

  it("shows editable weight inputs and each criterion's interpretation for the Baseline", () => {
    renderControls();

    expect(screen.getByLabelText("Wind speed weight")).toBeInTheDocument();
    expect(
      screen.getByText(/energy yield scales roughly with the cube of wind speed/i),
    ).toBeInTheDocument();
  });

  it("shows locked, read-only weights (no inputs) for a preset", () => {
    renderControls({ optionId: "wind_led" });

    expect(screen.queryByLabelText("Wind speed weight")).not.toBeInTheDocument();
    expect(screen.getByText("0.55")).toBeInTheDocument();
  });

  it("calls onBaselineCriteriaChange with the edited weight", () => {
    const onBaselineCriteriaChange = jest.fn();
    renderControls({ onBaselineCriteriaChange });

    fireEvent.change(screen.getByLabelText("Wind speed weight"), {
      target: { value: "0.5" },
    });

    expect(onBaselineCriteriaChange).toHaveBeenCalledWith([
      expect.objectContaining({ feature: "wind_speed", weight: 0.5 }),
      ...BASELINE_CRITERIA.slice(1),
    ]);
  });

  it("shows an error and disables Run for a negative weight, without calling onRun", () => {
    const onRun = jest.fn();
    const negative = BASELINE_CRITERIA.map((c, i) => (i === 0 ? { ...c, weight: -1 } : c));
    renderControls({ baselineCriteria: negative, onRun });

    expect(screen.getByRole("alert")).toHaveTextContent(/cannot be negative/i);
    const runButton = screen.getByRole("button", { name: /run analysis/i });
    expect(runButton).toBeDisabled();
    fireEvent.click(runButton);
    expect(onRun).not.toHaveBeenCalled();
  });

  it("shows an error when every weight is zero", () => {
    const allZero = BASELINE_CRITERIA.map((c) => ({ ...c, weight: 0 }));
    renderControls({ baselineCriteria: allZero });

    expect(screen.getByRole("alert")).toHaveTextContent(/at least one weight/i);
  });

  it("calls onRun when the run button is clicked with valid weights", () => {
    const onRun = jest.fn();
    renderControls({ onRun });

    fireEvent.click(screen.getByRole("button", { name: /run analysis/i }));

    expect(onRun).toHaveBeenCalledTimes(1);
  });

  it("disables the options and the run button while running", () => {
    renderControls({ running: true });

    expect(screen.getByRole("radio", { name: "Baseline (default)" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /running/i })).toBeDisabled();
  });

  it("shows no active run until one exists, then displays it", () => {
    const { rerender } = render(
      <AnalysisControls
        optionId="baseline"
        onOptionChange={jest.fn()}
        baselineCriteria={BASELINE_CRITERIA}
        onBaselineCriteriaChange={jest.fn()}
        onRun={jest.fn()}
        running={false}
        activeRun={null}
      />,
    );
    expect(screen.getByText(/no run is available/i)).toBeInTheDocument();

    rerender(
      <AnalysisControls
        optionId="baseline"
        onOptionChange={jest.fn()}
        baselineCriteria={BASELINE_CRITERIA}
        onBaselineCriteriaChange={jest.fn()}
        onRun={jest.fn()}
        running={false}
        activeRun={{ run_id: "run-1", scenario: null, weights_id: "baseline-hash" }}
      />,
    );

    expect(screen.queryByText(/no run is available/i)).not.toBeInTheDocument();
    expect(screen.getByText("run-1")).toBeInTheDocument();
  });
});

describe("validateWeights", () => {
  it("accepts the Baseline defaults", () => {
    expect(validateWeights(BASELINE_CRITERIA)).toBeNull();
  });

  it("rejects a non-finite weight", () => {
    const criteria = BASELINE_CRITERIA.map((c, i) => (i === 0 ? { ...c, weight: NaN } : c));
    expect(validateWeights(criteria)).toMatch(/must be a number/i);
  });

  it("rejects a negative weight", () => {
    const criteria = BASELINE_CRITERIA.map((c, i) => (i === 0 ? { ...c, weight: -0.1 } : c));
    expect(validateWeights(criteria)).toMatch(/cannot be negative/i);
  });

  it("rejects all-zero weights", () => {
    const criteria = BASELINE_CRITERIA.map((c) => ({ ...c, weight: 0 }));
    expect(validateWeights(criteria)).toMatch(/at least one weight/i);
  });
});
