/**
 * Render/interaction tests for the S3-06 scenario-comparison panel.
 *
 * The panel is a pure view over the S2-07 engine's `compare_scenarios` output.
 * It must: let the user choose two WEIGHTING presets and trigger a comparison;
 * render the engine's per-cell ranks and rank delta exactly as served, in
 * engine order (never re-sorting or recomputing); and frame the scenarios as
 * preference-based, not probabilistic uncertainty.
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";

import type {
  Criterion,
  ScenarioComparison as ScenarioComparisonResult,
} from "../api/decision-service";
import { BASELINE_CRITERIA, type WeightingOption } from "./AnalysisControls";
import ScenarioComparison from "./ScenarioComparison";

const PRESETS: WeightingOption[] = [
  { id: "wind_led", label: "Wind-led", editable: false, criteria: BASELINE_CRITERIA },
  { id: "grid_led", label: "Grid-led", editable: false, criteria: BASELINE_CRITERIA },
];

const SEED: Criterion[] = BASELINE_CRITERIA.map((c) => ({ ...c }));

const COMPARISON: ScenarioComparisonResult = {
  labels: { a: "wind_led", b: "grid_led" },
  rows: [
    { cell_id: "S31.186_E151.686", rank_a: 1, rank_b: 21, rank_delta: -20 },
    { cell_id: "S31.186_E151.736", rank_a: 2, rank_b: 49, rank_delta: -47 },
    { cell_id: "S40.000_E150.000", rank_a: 90, rank_b: 3, rank_delta: 87 },
  ],
};

function renderPanel(
  overrides: Partial<React.ComponentProps<typeof ScenarioComparison>> = {},
) {
  const props = {
    presets: PRESETS,
    scenarioA: "wind_led",
    onScenarioAChange: jest.fn(),
    scenarioB: "grid_led",
    onScenarioBChange: jest.fn(),
    customCriteriaA: SEED.map((c) => ({ ...c })),
    onCustomCriteriaAChange: jest.fn(),
    customCriteriaB: SEED.map((c) => ({ ...c })),
    onCustomCriteriaBChange: jest.fn(),
    onCompare: jest.fn(),
    loading: false,
    error: null,
    comparison: null as ScenarioComparisonResult | null,
    ...overrides,
  };
  render(<ScenarioComparison {...props} />);
  return props;
}

function bodyRows(): HTMLElement[] {
  const [, body] = screen.getAllByRole("rowgroup");
  return within(body!).getAllByRole("row");
}

describe("ScenarioComparison", () => {
  it("frames the scenarios as preference-based, not probabilistic uncertainty", () => {
    renderPanel();

    // The whole note paragraph must carry the preference framing AND the
    // explicit rejection of a probabilistic/uncertainty reading.
    const note = screen.getByText(/weighting \/ preference/i).closest("p");
    expect(note).not.toBeNull();
    expect(note).toHaveTextContent(/weighting \/ preference/i);
    expect(note).toHaveTextContent(/\bnot\b/i);
    expect(note).toHaveTextContent(/probabilistic/i);
    expect(note).toHaveTextContent(/no scenario is more or less likely/i);
  });

  it("offers two scenario groups populated from the presets plus a Custom option", () => {
    renderPanel();

    const groupA = screen.getByRole("group", { name: "Scenario A" });
    const groupB = screen.getByRole("group", { name: "Scenario B" });
    for (const group of [groupA, groupB]) {
      const options = within(group)
        .getAllByRole("radio")
        .map((radio) => radio.getAttribute("value"));
      // The two named presets are kept, with a Custom-weights option appended.
      expect(options).toEqual(["wind_led", "grid_led", "custom"]);
    }
  });

  it("keeps the two named presets selectable (presets kept)", () => {
    const props = renderPanel({ scenarioA: "grid_led" });
    const groupA = screen.getByRole("group", { name: "Scenario A" });

    expect(
      within(groupA).getByRole("radio", { name: "Wind-led" }),
    ).toBeInTheDocument();
    expect(
      within(groupA).getByRole("radio", { name: "Grid-led" }),
    ).toBeChecked();

    fireEvent.click(within(groupA).getByRole("radio", { name: "Wind-led" }));
    expect(props.onScenarioAChange).toHaveBeenCalledWith("wind_led");
  });

  it("reports the chosen scenario when a selector changes", () => {
    const props = renderPanel();
    const groupB = screen.getByRole("group", { name: "Scenario B" });

    fireEvent.click(within(groupB).getByRole("radio", { name: "Wind-led" }));
    expect(props.onScenarioBChange).toHaveBeenCalledWith("wind_led");
  });

  it("triggers the comparison for the chosen pair", () => {
    const props = renderPanel();

    fireEvent.click(screen.getByRole("button", { name: /compare scenarios/i }));
    expect(props.onCompare).toHaveBeenCalledTimes(1);
  });

  it("disables comparing and hints when both scenarios are the same", () => {
    renderPanel({ scenarioA: "wind_led", scenarioB: "wind_led" });

    expect(screen.getByRole("button", { name: /compare scenarios/i })).toBeDisabled();
    expect(
      screen.getByText(/choose two different scenarios/i),
    ).toBeInTheDocument();
  });

  it("renders the engine's ranks and rank delta exactly as served, in engine order", () => {
    renderPanel({ comparison: COMPARISON });

    const headers = screen
      .getAllByRole("columnheader")
      .map((header) => header.textContent);
    expect(headers).toEqual([
      "Site ID",
      "Rank — Wind-led",
      "Rank — Grid-led",
      "Rank delta",
    ]);

    const rendered = bodyRows();
    expect(rendered).toHaveLength(3);
    // Row order is the engine's served order — a UI that re-sorted by delta
    // would reorder these. The panel must trust the engine.
    expect(within(rendered[0]!).getByRole("rowheader")).toHaveTextContent(
      "S31.186_E151.686",
    );
    expect(
      within(rendered[0]!).getAllByRole("cell").map((cell) => cell.textContent),
    ).toEqual(["1", "21", "-20"]);
    expect(
      within(rendered[2]!).getAllByRole("cell").map((cell) => cell.textContent),
    ).toEqual(["90", "3", "+87"]);
  });

  it("shows a missing rank as a dash rather than zero", () => {
    renderPanel({
      comparison: {
        labels: { a: "wind_led", b: "grid_led" },
        rows: [{ cell_id: "S50.000_E150.000", rank_a: 5, rank_b: null, rank_delta: null }],
      },
    });

    const [row] = bodyRows();
    expect(
      within(row!).getAllByRole("cell").map((cell) => cell.textContent),
    ).toEqual(["5", "—", "—"]);
  });

  it("surfaces a comparison failure as an alert", () => {
    renderPanel({ error: "scenario config error" });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Scenario comparison unavailable: scenario config error",
    );
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("prompts for a comparison before any result is loaded", () => {
    renderPanel();

    expect(
      screen.getByText(/pick two preference scenarios and compare/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("switches a side to Custom and reveals an editable six-criterion weight editor", () => {
    const props = renderPanel();

    const groupA = screen.getByRole("group", { name: "Scenario A" });
    fireEvent.click(within(groupA).getByRole("radio", { name: /custom weights/i }));
    expect(props.onScenarioAChange).toHaveBeenCalledWith("custom");

    // Re-render with side A set to custom to see the editor appear.
    cleanup();
    renderPanel({ scenarioA: "custom" });

    // One editable number input per frozen criterion (six), labelled for A.
    const windInput = screen.getByLabelText(/custom a wind speed weight/i);
    expect(windInput).toHaveAttribute("type", "number");
    expect(
      screen.getByLabelText(/custom a inside rez weight/i),
    ).toBeInTheDocument();
  });

  it("edits only the touched custom weight, carrying the rest through unchanged", () => {
    const props = renderPanel({ scenarioA: "custom" });

    const windInput = screen.getByLabelText(/custom a wind speed weight/i);
    fireEvent.change(windInput, { target: { value: "0.9" } });

    const onChange = props.onCustomCriteriaAChange as jest.Mock;
    expect(onChange).toHaveBeenCalledTimes(1);
    const next = onChange.mock.calls[0]![0] as Criterion[];
    // The touched criterion changed; the rest are the seed values unchanged.
    expect(next[0]!.weight).toBe(0.9);
    expect(next.slice(1)).toEqual(SEED.slice(1));
    // The criteria set and directions are untouched — only the weight changed.
    expect(next.map((c) => c.feature)).toEqual(SEED.map((c) => c.feature));
    expect(next.map((c) => c.direction)).toEqual(SEED.map((c) => c.direction));
  });

  it("compares two different custom sides (two Custom sides are a valid pair)", () => {
    const props = renderPanel({ scenarioA: "custom", scenarioB: "custom" });

    const button = screen.getByRole("button", { name: /compare scenarios/i });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    expect(props.onCompare).toHaveBeenCalledTimes(1);
  });

  it("blocks comparing while a custom side has an invalid (all-zero) weight set", () => {
    const zeroed: Criterion[] = SEED.map((c) => ({ ...c, weight: 0 }));
    renderPanel({ scenarioA: "custom", customCriteriaA: zeroed });

    expect(
      screen.getByRole("button", { name: /compare scenarios/i }),
    ).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent(/at least one weight/i);
  });
});
