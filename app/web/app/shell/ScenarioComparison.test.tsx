/**
 * Render/interaction tests for the S3-06 scenario-comparison panel.
 *
 * The panel is a pure view over the S2-07 engine's `compare_scenarios` output.
 * It must: let the user choose two WEIGHTING presets and trigger a comparison;
 * render the engine's per-cell ranks and rank delta exactly as served, in
 * engine order (never re-sorting or recomputing); and frame the scenarios as
 * preference-based, not probabilistic uncertainty.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { ScenarioComparison as ScenarioComparisonResult } from "../api/decision-service";
import type { WeightingOption } from "./AnalysisControls";
import ScenarioComparison from "./ScenarioComparison";

const PRESETS: WeightingOption[] = [
  { id: "wind_led", label: "Wind-led", editable: false, criteria: [] },
  { id: "grid_led", label: "Grid-led", editable: false, criteria: [] },
];

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

  it("offers two scenario groups populated from the provided weighting presets", () => {
    renderPanel();

    const groupA = screen.getByRole("group", { name: "Scenario A" });
    const groupB = screen.getByRole("group", { name: "Scenario B" });
    for (const group of [groupA, groupB]) {
      const options = within(group)
        .getAllByRole("radio")
        .map((radio) => radio.getAttribute("value"));
      expect(options).toEqual(["wind_led", "grid_led"]);
    }
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
});
