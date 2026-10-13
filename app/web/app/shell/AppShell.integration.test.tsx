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

function controlsRegion(): HTMLElement {
  return screen.getByRole("region", { name: "Analysis controls" });
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
    getSanityCheck: jest.fn().mockResolvedValue({
      caveat:
        "The model is not trained to reproduce the known wind/REZ locations.",
      preliminary_disclaimer: "Screening-level result — not a siting decision.",
      run_metadata: {
        run_timestamp: "2026-10-12T09:30:00Z",
        pipeline_version: "1.4.2",
        resolved_shortlist_path: "DATA/shortlist/optmining_shortlist_2026_nsw.csv",
        n_cells: 1000,
        n_eligible: 420,
      },
      checks: [
        {
          name: "Known-wind-farm top-ranked band",
          expected: "≥ 50% of farms in band",
          observed: "60% in band",
          passed: true,
        },
      ],
      contradictions: [],
      wind_farms: [],
      top_band_n: 20,
      exclusion_assertions: [],
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

    fireEvent.click(within(controlsRegion()).getByRole("radio", { name: "Grid-led" }));
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

    fireEvent.click(within(controlsRegion()).getByRole("radio", { name: "Grid-led" }));
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

describe("AppShell sanity-check panel (S3-08)", () => {
  function sanityRegion(): HTMLElement {
    return screen.getByRole("region", { name: "Sanity check / validation" });
  }

  it("fetches the sanity result once on mount and renders it in the sanity region", async () => {
    const service = serviceWithFlaggedDataset();
    render(<AppShell service={service} />);

    await screen.findByText("run-wind-1");

    const region = sanityRegion();
    // The caveat and a served check render in the mounted panel.
    await waitFor(() => {
      expect(
        within(region).getByText(/not trained to reproduce the known wind\/REZ/i),
      ).toBeInTheDocument();
    });
    expect(within(region).getByText(/Known-wind-farm top-ranked band/)).toBeInTheDocument();
    expect(within(region).getByText("PASS")).toBeInTheDocument();

    // Fetched exactly once on mount, independent of the active Run (a re-run
    // never refetches the baseline-fixed sidecar).
    expect(service.getSanityCheck).toHaveBeenCalledTimes(1);
  });

  it("asserts same-engine-output on the unmodified baseline mount run", async () => {
    const service = serviceWithFlaggedDataset();
    render(<AppShell service={service} />);

    await screen.findByText("run-wind-1");

    const region = sanityRegion();
    // The default mount run is the unmodified baseline -> single-lineage copy.
    expect(
      within(region).getByText(/same engine output as the map and shortlist/i),
    ).toBeInTheDocument();
    expect(
      within(region).queryByText(/Sanity reflects the BASELINE run, not the current scenario/),
    ).not.toBeInTheDocument();
  });

  it("flips to the baseline-vs-scenario warning when a preset scenario is selected", async () => {
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

    // Select a named preset and re-run — the single-run selector is no longer
    // the baseline, so the panel must warn that sanity reflects the baseline.
    fireEvent.click(within(controlsRegion()).getByRole("radio", { name: "Grid-led" }));
    fireEvent.click(screen.getByRole("button", { name: /run analysis/i }));

    await screen.findByText("run-grid-1");

    const region = sanityRegion();
    expect(
      within(region).getByText(/Sanity reflects the BASELINE run, not the current scenario/),
    ).toBeInTheDocument();
    expect(
      within(region).queryByText(/same engine output as the map and shortlist/i),
    ).not.toBeInTheDocument();
    // The sidecar is fetched once; selecting a scenario does not refetch it.
    expect(service.getSanityCheck).toHaveBeenCalledTimes(1);
  });

  it("flips to the warning when the baseline weights are edited (not just on a scenario)", async () => {
    const service = serviceWithFlaggedDataset();
    render(<AppShell service={service} />);

    await screen.findByText("run-wind-1");

    const region = sanityRegion();
    // Still the unmodified baseline before any edit.
    expect(
      within(region).getByText(/same engine output as the map and shortlist/i),
    ).toBeInTheDocument();

    // Edit a baseline weight so baselineCriteria diverges from BASELINE_CRITERIA
    // while the option id stays "baseline" — isBaselineRun must become false.
    fireEvent.change(screen.getByLabelText("Wind speed weight"), {
      target: { value: "0.5" },
    });

    await waitFor(() => {
      expect(
        within(sanityRegion()).getByText(
          /Sanity reflects the BASELINE run, not the current scenario/,
        ),
      ).toBeInTheDocument();
    });
    expect(
      within(sanityRegion()).queryByText(/same engine output as the map and shortlist/i),
    ).not.toBeInTheDocument();
  });

  it("keeps the engine output visible when only the sanity endpoint fails", async () => {
    const service = serviceWithFlaggedDataset();
    service.getSanityCheck = jest
      .fn()
      .mockRejectedValue(new Error("sanity sidecar missing"));
    render(<AppShell service={service} />);

    expect(await screen.findByText("run-wind-1")).toBeInTheDocument();
    const region = sanityRegion();
    expect(within(region).getByRole("alert")).toHaveTextContent(
      "Sanity-check result is unavailable. sanity sidecar missing",
    );
  });
});

describe("AppShell scenario comparison (S3-06)", () => {
  function comparisonRegion(): HTMLElement {
    return screen.getByRole("region", { name: "Scenario comparison" });
  }

  it("compares the two chosen presets through the shared client and renders engine ranks", async () => {
    const service = serviceWithFlaggedDataset();
    service.compareScenarios = jest.fn().mockResolvedValue({
      labels: { a: "wind_led", b: "grid_led" },
      rows: [
        { cell_id: "S31.186_E151.686", rank_a: 1, rank_b: 21, rank_delta: -20 },
        { cell_id: "S40.000_E150.000", rank_a: 90, rank_b: 3, rank_delta: 87 },
      ],
    });
    render(<AppShell service={service} />);

    await screen.findByText("run-wind-1");

    const region = comparisonRegion();
    // The two selectors default to the two named presets (Wind-led, Grid-led).
    fireEvent.click(
      within(region).getByRole("button", { name: /compare scenarios/i }),
    );

    // The comparison math is server-side: the UI sends only the two keys.
    await waitFor(() => {
      expect(service.compareScenarios).toHaveBeenCalledWith({
        scenario_a: "wind_led",
        scenario_b: "grid_led",
      });
    });

    // Engine-provided ranks and the rank delta render verbatim.
    expect(await within(region).findByText("S31.186_E151.686")).toBeInTheDocument();
    expect(within(region).getByText("-20")).toBeInTheDocument();
    expect(within(region).getByText("+87")).toBeInTheDocument();
  });

  it("re-compares with the newly selected presets", async () => {
    const service = serviceWithFlaggedDataset();
    service.compareScenarios = jest.fn().mockResolvedValue({
      labels: { a: "grid_led", b: "wind_led" },
      rows: [{ cell_id: "S31.000_E150.000", rank_a: 4, rank_b: 2, rank_delta: 2 }],
    });
    render(<AppShell service={service} />);

    await screen.findByText("run-wind-1");

    const region = comparisonRegion();
    const groupA = within(region).getByRole("group", { name: "Scenario A" });
    const groupB = within(region).getByRole("group", { name: "Scenario B" });
    fireEvent.click(within(groupA).getByRole("radio", { name: "Grid-led" }));
    fireEvent.click(within(groupB).getByRole("radio", { name: "Wind-led" }));
    fireEvent.click(
      within(region).getByRole("button", { name: /compare scenarios/i }),
    );

    await waitFor(() => {
      expect(service.compareScenarios).toHaveBeenLastCalledWith({
        scenario_a: "grid_led",
        scenario_b: "wind_led",
      });
    });
  });

  it("sends an edited Custom side as explicit weights through the shared client", async () => {
    const service = serviceWithFlaggedDataset();
    service.compareScenarios = jest.fn().mockResolvedValue({
      labels: { a: "custom_a", b: "grid_led" },
      rows: [{ cell_id: "S31.000_E150.000", rank_a: 1, rank_b: 5, rank_delta: -4 }],
    });
    render(<AppShell service={service} />);

    await screen.findByText("run-wind-1");

    const region = comparisonRegion();
    const groupA = within(region).getByRole("group", { name: "Scenario A" });
    // Switch side A to Custom and edit its wind-speed weight.
    fireEvent.click(within(groupA).getByRole("radio", { name: /custom weights/i }));
    const windInput = within(region).getByLabelText(/custom a wind speed weight/i);
    fireEvent.change(windInput, { target: { value: "0.8" } });

    fireEvent.click(
      within(region).getByRole("button", { name: /compare scenarios/i }),
    );

    await waitFor(() => {
      expect(service.compareScenarios).toHaveBeenCalledTimes(1);
    });
    // Side A travels as explicit weights (the edited value present, no scenario
    // key for A); side B stays its preset key. All ranking is server-side.
    const request = (service.compareScenarios as jest.Mock).mock.calls[0]![0];
    expect(request.scenario_a).toBeUndefined();
    expect(request.weights_a.criteria[0]).toMatchObject({
      feature: "wind_speed",
      weight: 0.8,
    });
    // Only the weight changed — the criteria set and directions are the seed's.
    expect(request.weights_a.criteria.map((c: { feature: string }) => c.feature)).toEqual(
      BASELINE_CRITERIA.map((c) => c.feature),
    );
    expect(request.scenario_b).toBe("grid_led");
    expect(request.weights_b).toBeUndefined();

    // The engine's returned rank/delta render verbatim.
    expect(await within(region).findByText("S31.000_E150.000")).toBeInTheDocument();
    expect(within(region).getByText("-4")).toBeInTheDocument();
  });

  it("surfaces a comparison failure without hiding the rest of the shell", async () => {
    const service = serviceWithFlaggedDataset();
    service.compareScenarios = jest
      .fn()
      .mockRejectedValue(new Error("unknown scenario"));
    render(<AppShell service={service} />);

    await screen.findByText("run-wind-1");

    const region = comparisonRegion();
    fireEvent.click(
      within(region).getByRole("button", { name: /compare scenarios/i }),
    );

    expect(await within(region).findByRole("alert")).toHaveTextContent(
      "Scenario comparison unavailable: unknown scenario",
    );
    // The ranked shortlist is still present.
    expect(screen.getByRole("button", { name: RANK_1 })).toBeInTheDocument();
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
