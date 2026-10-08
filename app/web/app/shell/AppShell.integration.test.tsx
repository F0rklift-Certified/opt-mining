import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import type { DecisionService, SiteDetail } from "../api/decision-service";
import { BASELINE_CRITERIA } from "./AnalysisControls";
import AppShell from "./AppShell";

const RANK_1 = "S30.100_E151.200";
const RANK_2 = "S30.200_E151.300";

const SITE_DETAILS: Record<string, SiteDetail> = {
  [RANK_1]: { cell_id: RANK_1, suitability_score: 0.912, rank: 1, eligible: true },
  [RANK_2]: { cell_id: RANK_2, suitability_score: 0.874, rank: 2, eligible: true },
};

function detailRegion(): HTMLElement {
  return screen.getByRole("region", { name: "Site detail / explanation" });
}

function mapRegion(): HTMLElement {
  return screen.getByRole("region", { name: "Interactive map" });
}

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
    // Rank 1 is selected by default: it shows in the shortlist row and in the
    // getSiteDetail-backed detail panel. The map (CellMap) renders a container,
    // not the cell-id text, so the id appears exactly twice.
    await waitFor(() => {
      expect(screen.getAllByText("S30.100_E151.200")).toHaveLength(2);
      expect(screen.getAllByText("0.912")).toHaveLength(2);
    });
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

  it("opens the selected row's site detail and mirrors it on the map (S3-04)", async () => {
    const service = serviceWithFlaggedDataset();
    service.getSiteDetail = jest.fn().mockImplementation(
      async (_runId: string, cellId: string) => SITE_DETAILS[cellId],
    );
    render(<AppShell service={service} />);

    expect(await within(detailRegion()).findByText(RANK_1)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: RANK_2 }));

    expect(await within(detailRegion()).findByText(RANK_2)).toBeInTheDocument();
    expect(within(detailRegion()).queryByText(RANK_1)).not.toBeInTheDocument();
    // The map region now renders the CellMap container; the selection is
    // mirrored on the map through the shared SiteSelection (the pinned
    // highlight square), not as cell-id text in the DOM.
    expect(within(mapRegion()).getByLabelText("Interactive cell map")).toBeInTheDocument();
    expect(service.getSiteDetail).toHaveBeenLastCalledWith("run-wind-1", RANK_2);
    expect(screen.getByRole("button", { name: RANK_2 })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: RANK_1 })).toHaveAttribute("aria-pressed", "false");
  });

  it("does not refetch detail when the already-selected row is clicked again", async () => {
    const service = serviceWithFlaggedDataset();
    render(<AppShell service={service} />);

    expect(await within(detailRegion()).findByText(RANK_1)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: RANK_1 }));

    expect(service.getSiteDetail).toHaveBeenCalledTimes(1);
  });

  it("ignores a slow detail response for a site that is no longer selected", async () => {
    const service = serviceWithFlaggedDataset();
    let releaseRank2: (detail: SiteDetail) => void = () => undefined;
    service.getSiteDetail = jest.fn().mockImplementation(
      (_runId: string, cellId: string) =>
        cellId === RANK_2
          ? new Promise<SiteDetail>((resolve) => { releaseRank2 = resolve; })
          : Promise.resolve(SITE_DETAILS[cellId]),
    );
    render(<AppShell service={service} />);

    expect(await within(detailRegion()).findByText(RANK_1)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: RANK_2 }));
    expect(within(detailRegion()).getByText("Loading site detail…")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: RANK_1 }));
    expect(await within(detailRegion()).findByText(RANK_1)).toBeInTheDocument();

    await act(async () => {
      releaseRank2(SITE_DETAILS[RANK_2]!);
    });

    expect(within(detailRegion()).getByText(RANK_1)).toBeInTheDocument();
    expect(within(detailRegion()).queryByText(RANK_2)).not.toBeInTheDocument();
    // The map renders the CellMap container throughout; it tracks the active
    // selection via the shared SiteSelection, not as cell-id text.
    expect(within(mapRegion()).getByLabelText("Interactive cell map")).toBeInTheDocument();
  });

  it("reports a site-detail failure without hiding the shortlist", async () => {
    const service = serviceWithFlaggedDataset();
    service.getSiteDetail = jest.fn().mockRejectedValue(new Error("cell not found"));
    render(<AppShell service={service} />);

    expect(await within(detailRegion()).findByRole("alert")).toHaveTextContent(
      "Site detail unavailable: cell not found",
    );
    expect(screen.getByRole("button", { name: RANK_1 })).toBeInTheDocument();
  });

  it("resets the selection to the new run's rank 1 after a re-run", async () => {
    const service = serviceWithFlaggedDataset();
    service.runAnalysis = jest.fn().mockImplementation(
      async ({ scenario }: { scenario?: string | null }) => ({
        run_id: scenario === "grid_led" ? "run-grid-1" : "run-wind-1",
        weights_id: scenario ?? "wind_led",
        scenario,
      }),
    );
    service.getRankedResults = jest.fn().mockImplementation(async (runId: string) =>
      runId === "run-grid-1"
        ? [
            { cell_id: "S31.500_E150.500", suitability_score: 0.801, rank: 1 },
            { cell_id: RANK_2, suitability_score: 0.799, rank: 2 },
          ]
        : [
            { cell_id: RANK_1, suitability_score: 0.912, rank: 1 },
            { cell_id: RANK_2, suitability_score: 0.874, rank: 2 },
          ],
    );
    render(<AppShell service={service} />);

    await within(detailRegion()).findByText(RANK_1);
    fireEvent.click(screen.getByRole("button", { name: RANK_2 }));
    await waitFor(() => {
      expect(service.getSiteDetail).toHaveBeenLastCalledWith("run-wind-1", RANK_2);
    });

    fireEvent.click(screen.getByRole("radio", { name: "Grid-led" }));
    fireEvent.click(screen.getByRole("button", { name: /run analysis/i }));

    await waitFor(() => {
      expect(service.getSiteDetail).toHaveBeenLastCalledWith("run-grid-1", "S31.500_E150.500");
    });
    expect(screen.getByRole("button", { name: "S31.500_E150.500" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: RANK_2 })).toHaveAttribute("aria-pressed", "false");
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

describe("AppShell shared selection: map click (S3-03b + S3-04)", () => {
  it("drives Site-detail from a map click through the SAME shared SiteSelection", async () => {
    // The merged shell keeps the S3-04 ranked panel and getSiteDetail-backed
    // detail, and ADDS the S3-03b CellMap. A map click adapts the emitted
    // CellSelection to the shared SiteSelection ({runId, cellId}) via
    // handleSelectSite, driving the SAME HTTP getSiteDetail detail a row click
    // drives — proving map and shortlist resolve to one selection contract.
    const service = serviceWithFlaggedDataset();
    service.getSiteDetail = jest.fn().mockImplementation(
      async (_runId: string, cellId: string) => ({
        cell_id: cellId,
        suitability_score: 0.655,
        rank: 7,
        eligible: true,
      }),
    );
    render(<AppShell service={service} />);

    await screen.findByText("run-wind-1");

    const siteDetail = screen.getByRole("region", {
      name: "Site detail / explanation",
    });

    // Fire the captured map click handler for an eligible cell. The map's
    // onSelectCell adapts the CellSelection into the shared SiteSelection and
    // calls getSiteDetail with the active run id and the clicked cell id.
    mapClickOnLayer("cells-eligible", {
      cell_id: "S99.000_E150.000",
      eligible: true,
      suitability_score: 0.655,
      rank: 7,
    });

    await waitFor(() => {
      expect(within(siteDetail).getByText("S99.000_E150.000")).toBeInTheDocument();
    });
    expect(service.getSiteDetail).toHaveBeenLastCalledWith(
      "run-wind-1",
      "S99.000_E150.000",
    );
    expect(within(siteDetail).getByText("7")).toBeInTheDocument();
    expect(within(siteDetail).getByText("0.655")).toBeInTheDocument();
  });
});
