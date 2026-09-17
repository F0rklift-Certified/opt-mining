import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import type { DecisionService, SiteDetail } from "../api/decision-service";
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

function serviceWithFlaggedDataset(): DecisionService {
  return {
    runAnalysis: jest.fn().mockResolvedValue({
      run_id: "run-wind-1",
      weights_id: "wind_led",
      scenario: "wind_led",
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
    // Rank 1 is selected by default: shortlist row, map selection and detail.
    await waitFor(() => {
      expect(screen.getAllByText("S30.100_E151.200")).toHaveLength(3);
      expect(screen.getAllByText("0.912")).toHaveLength(2);
    });
    expect(screen.getByText("2 ranked cells loaded from the engine; map rendering follows in S3-03a.")).toBeInTheDocument();

    await waitFor(() => {
      expect(service.runAnalysis).toHaveBeenCalledWith({ scenario: "wind_led" });
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
    expect(within(mapRegion()).getByText(RANK_2)).toBeInTheDocument();
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
    expect(within(mapRegion()).getByText(RANK_1)).toBeInTheDocument();
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
});
