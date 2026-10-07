import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";

import type { DecisionService } from "../api/decision-service";
import { BASELINE_CRITERIA } from "./AnalysisControls";
import AppShell from "./AppShell";

// Layer-scoped map handlers captured by `${event}:${layerId}` so a test can
// drive CellMap's click-to-inspect path (S3-03b) without a GL context.
const mapLayerHandlers: Record<string, (event: unknown) => void> = {};

/** Fire the captured map click handler for a layer with one feature. */
function mapClickOnLayer(
  layerId: string,
  properties: Record<string, unknown>,
): void {
  const handler = mapLayerHandlers[`click:${layerId}`];
  if (!handler) throw new Error(`no click handler registered for ${layerId}`);
  // The handler calls a React state setter; wrap it so the update is flushed.
  act(() => {
    handler({ features: [{ properties }] });
  });
}

// jsdom has no WebGL, so CellMap's maplibregl.Map is mocked. The mock records
// the load callback and exposes a setData spy so the map lifecycle runs without
// a GL context; see CellMap.test.tsx for the detailed assertions. The layer
// `on(event, layerId, cb)` form is captured so click-to-inspect is drivable.
jest.mock("maplibre-gl", () => {
  class MockMap {
    on(event: string, layerOrCb: unknown, maybeCb?: (event: unknown) => void) {
      if (typeof layerOrCb === "function") {
        if (event === "load") (layerOrCb as () => void)();
        return;
      }
      if (typeof maybeCb === "function") {
        mapLayerHandlers[`${event}:${layerOrCb as string}`] = maybeCb;
      }
    }
    addControl() {}
    addSource() {}
    addLayer() {}
    getSource() {
      return { setData: jest.fn() };
    }
    getCanvas() {
      return { style: { cursor: "" } };
    }
    remove() {}
  }
  return {
    __esModule: true,
    default: { Map: MockMap, NavigationControl: class {} },
    Map: MockMap,
    NavigationControl: class {},
  };
});

function serviceWithFlaggedDataset(): DecisionService {
  return {
    runAnalysis: jest.fn().mockResolvedValue({
      run_id: "run-wind-1",
      weights_id: "baseline-hash",
      scenario: null,
    }),
    getRankedResults: jest.fn().mockResolvedValue([
      { cell_id: "S30.100_E151.200", suitability_score: 0.912, rank: 1 },
      { cell_id: "S30.200_E151.300", suitability_score: 0.874, rank: 2 },
    ]),
    getSiteDetail: jest.fn().mockResolvedValue({
      cell_id: "S30.100_E151.200",
      suitability_score: 0.912,
      rank: 1,
      eligible: true,
    }),
    getExclusions: jest.fn().mockResolvedValue([
      { cell_id: "excluded-1", reason_codes: ["F1"], reason_text: "Protected" },
    ]),
    compareScenarios: jest.fn().mockResolvedValue({ labels: {}, rows: [] }),
    getDataQuality: jest.fn().mockResolvedValue({
      passed: false,
      checks: [
        { name: "baseline hash", expected: "frozen hash", observed: "different hash", passed: false },
        { name: "unique cell ids", expected: "unique", observed: "unique", passed: true },
      ],
    }),
    getRunCells: jest.fn().mockResolvedValue({
      type: "FeatureCollection",
      run_id: "run-wind-1",
      features: [],
    }),
  };
}

describe("AppShell service integration", () => {
  it("renders real service values and a flagged data-quality banner", async () => {
    const service = serviceWithFlaggedDataset();
    render(<AppShell service={service} />);

    const warning = await screen.findByRole("alert", { name: "" });
    expect(warning).toHaveTextContent("Data-quality warning");
    expect(warning).toHaveTextContent("baseline hash");

    expect(await screen.findByText("run-wind-1")).toBeInTheDocument();
    expect(screen.getAllByText("S30.100_E151.200")).toHaveLength(2);
    expect(screen.getAllByText("0.912")).toHaveLength(2);
    // The interactive-map region now renders the CellMap container (not the old
    // placeholder copy); CellMap requests the Run's cells via the shared client.
    expect(screen.getByLabelText("Interactive cell map")).toBeInTheDocument();
    await waitFor(() => {
      expect(service.getRunCells).toHaveBeenCalledWith("run-wind-1");
    });

    await waitFor(() => {
      expect(service.runAnalysis).toHaveBeenCalledWith({
        weights: { criteria: BASELINE_CRITERIA },
      });
      expect(service.getRankedResults).toHaveBeenCalledWith("run-wind-1", { top_n: 10 });
      expect(service.getSiteDetail).toHaveBeenCalledWith(
        "run-wind-1",
        "S30.100_E151.200",
      );
    });
  });

  it("keeps engine output visible when only the quality endpoint fails", async () => {
    const service = serviceWithFlaggedDataset();
    service.getDataQuality = jest.fn().mockRejectedValue(new Error("quality sidecar missing"));
    render(<AppShell service={service} />);

    expect(await screen.findByText("run-wind-1")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Data-quality status is unavailable",
    );
  });

  it("re-runs the analysis under the selected preset when Run is clicked (S3-02)", async () => {
    const service = serviceWithFlaggedDataset();
    service.runAnalysis = jest.fn().mockImplementation(
      async ({ scenario }: { scenario?: string | null }) => ({
        run_id: scenario === "grid_led" ? "run-grid-1" : "run-wind-1",
        weights_id: scenario ?? "wind_led",
        scenario,
      }),
    );
    render(<AppShell service={service} />);

    await screen.findByText("run-wind-1");

    fireEvent.click(screen.getByRole("radio", { name: "Grid-led" }));
    fireEvent.click(screen.getByRole("button", { name: /run analysis/i }));

    expect(await screen.findByText("run-grid-1")).toBeInTheDocument();
    expect(service.runAnalysis).toHaveBeenLastCalledWith({ scenario: "grid_led" });
    // The engine, not the UI, produced this run — the client sends the
    // preset id and nothing else (AC: no scoring/normalisation in the UI).
    expect(service.getRankedResults).toHaveBeenLastCalledWith("run-grid-1", { top_n: 10 });
  });

  it("sends the edited Baseline weight, unmodified, when Run is clicked (S3-02)", async () => {
    const service = serviceWithFlaggedDataset();
    render(<AppShell service={service} />);

    await screen.findByText("run-wind-1");

    fireEvent.change(screen.getByLabelText("Wind speed weight"), {
      target: { value: "0.5" },
    });
    fireEvent.click(screen.getByRole("button", { name: /run analysis/i }));

    await waitFor(() => {
      const lastCall = (service.runAnalysis as jest.Mock).mock.calls.at(-1)[0];
      expect(lastCall.weights.criteria[0]).toMatchObject({
        feature: "wind_speed",
        weight: 0.5,
      });
      // Every other criterion is carried through unchanged — the UI edits
      // only the field the user touched, never re-derives the rest.
      expect(lastCall.weights.criteria.slice(1)).toEqual(BASELINE_CRITERIA.slice(1));
    });
  });
});

describe("AppShell display filters & shared selection (S3-03b)", () => {
  it("re-queries ranked results with the new top-N and does NOT re-run analysis (AC2/AC4)", async () => {
    const service = serviceWithFlaggedDataset();
    render(<AppShell service={service} />);

    // Wait for the initial run so the ranked table (and its filter) are shown.
    await screen.findByText("run-wind-1");
    await waitFor(() =>
      expect(service.getRankedResults).toHaveBeenCalledWith("run-wind-1", { top_n: 10 }),
    );

    const runCallsBefore = (service.runAnalysis as jest.Mock).mock.calls.length;
    const cellsCallsBefore = (service.getRunCells as jest.Mock).mock.calls.length;

    fireEvent.change(screen.getByLabelText("Top N sites"), {
      target: { value: "3" },
    });

    await waitFor(() =>
      expect(service.getRankedResults).toHaveBeenLastCalledWith("run-wind-1", {
        top_n: 3,
      }),
    );

    // The filter is a display query only: no new run, no re-fetch of cells —
    // nothing that could re-trigger scoring/normalisation/ranking.
    expect((service.runAnalysis as jest.Mock).mock.calls.length).toBe(runCallsBefore);
    expect((service.getRunCells as jest.Mock).mock.calls.length).toBe(cellsCallsBefore);
  });

  it("applies a minimum-suitability filter via getRankedResults without re-running analysis", async () => {
    const service = serviceWithFlaggedDataset();
    render(<AppShell service={service} />);

    await screen.findByText("run-wind-1");
    const runCallsBefore = (service.runAnalysis as jest.Mock).mock.calls.length;

    fireEvent.change(screen.getByLabelText("Min suitability"), {
      target: { value: "0.9" },
    });

    await waitFor(() =>
      expect(service.getRankedResults).toHaveBeenLastCalledWith("run-wind-1", {
        top_n: 10,
        min_score: 0.9,
      }),
    );
    expect((service.runAnalysis as jest.Mock).mock.calls.length).toBe(runCallsBefore);
  });

  it("drives Site-detail from a clicked ranked row (shared CellSelection)", async () => {
    const service = serviceWithFlaggedDataset();
    render(<AppShell service={service} />);

    await screen.findByText("run-wind-1");

    // Default Site-detail shows the first-ranked site (rank 1 cell).
    const siteDetail = screen.getByRole("region", {
      name: "Site detail / explanation",
    });

    // Click the SECOND ranked row's cell button; Site-detail must follow it.
    fireEvent.click(screen.getByRole("button", { name: "S30.200_E151.300" }));

    await waitFor(() => {
      expect(within(siteDetail).getByText("S30.200_E151.300")).toBeInTheDocument();
    });
    // The row-sourced selection carries that row's rank/score — proving the
    // ranked table drives the shared selection, no getSiteDetail round-trip.
    expect(within(siteDetail).getByText("2")).toBeInTheDocument();
    expect(within(siteDetail).getByText("0.874")).toBeInTheDocument();
  });

  it("drives Site-detail from a map click using the SAME CellSelection shape (AC3)", async () => {
    const service = serviceWithFlaggedDataset();
    render(<AppShell service={service} />);

    await screen.findByText("run-wind-1");

    const siteDetail = screen.getByRole("region", {
      name: "Site detail / explanation",
    });

    // The map's onSelectCell is wired to the SAME setter the ranked rows use.
    // Fire the captured map click handler for an eligible cell; Site-detail
    // must update identically to a row click — proving the shapes are shared.
    mapClickOnLayer("cells-eligible", {
      cell_id: "S99.000_E150.000",
      eligible: true,
      suitability_score: 0.655,
      rank: 7,
    });

    await waitFor(() => {
      expect(within(siteDetail).getByText("S99.000_E150.000")).toBeInTheDocument();
    });
    expect(within(siteDetail).getByText("7")).toBeInTheDocument();
    expect(within(siteDetail).getByText("0.655")).toBeInTheDocument();
  });
});
