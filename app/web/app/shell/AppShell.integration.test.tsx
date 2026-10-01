import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { DecisionService } from "../api/decision-service";
import { BASELINE_CRITERIA } from "./AnalysisControls";
import AppShell from "./AppShell";

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
    expect(screen.getByText("2 ranked cells loaded from the engine; map rendering follows in S3-03a.")).toBeInTheDocument();

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
