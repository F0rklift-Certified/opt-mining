/** @jest-environment node */

import { createDecisionServiceClient } from "./decision-service";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("generated-contract decision service client", () => {
  it("wraps all six frozen operations with their HTTP paths and methods", async () => {
    const requests: Request[] = [];
    const fakeFetch: typeof globalThis.fetch = async (input, init) => {
      const request = input instanceof Request ? input : new Request(input, init);
      requests.push(request);
      const url = new URL(request.url);

      if (request.method === "POST" && url.pathname === "/runs") {
        return json({ run_id: "run-1", weights_id: "wind_led", scenario: "wind_led" });
      }
      if (request.method === "GET" && url.pathname === "/runs/run-1/results") {
        return json([{ cell_id: "cell-1", suitability_score: 0.91, rank: 1 }]);
      }
      if (request.method === "GET" && url.pathname === "/runs/run-1/sites/cell-1") {
        return json({
          cell_id: "cell-1",
          suitability_score: 0.91,
          rank: 1,
          eligible: true,
        });
      }
      if (request.method === "GET" && url.pathname === "/runs/run-1/exclusions") {
        return json([{ cell_id: "cell-x", reason_codes: ["F1"], reason_text: "Protected" }]);
      }
      if (request.method === "POST" && url.pathname === "/scenario-comparison") {
        return json({ labels: { a: "Wind-led", b: "Grid-led" }, rows: [] });
      }
      if (request.method === "GET" && url.pathname === "/data-quality") {
        return json({ passed: true, checks: [] });
      }
      return json({ detail: "unexpected request" }, 500);
    };

    const service = createDecisionServiceClient({
      baseUrl: "https://decision.example.test/",
      fetch: fakeFetch,
    });

    const run = await service.runAnalysis({ scenario: "wind_led" });
    await service.getRankedResults(run.run_id, { top_n: 10, min_score: 0.5 });
    await service.getSiteDetail(run.run_id, "cell-1");
    await service.getExclusions(run.run_id);
    await service.compareScenarios({ scenario_a: "wind_led", scenario_b: "grid_led" });
    await service.getDataQuality();

    expect(requests.map((request) => request.method)).toEqual([
      "POST", "GET", "GET", "GET", "POST", "GET",
    ]);
    expect(requests.map((request) => new URL(request.url).pathname)).toEqual([
      "/runs",
      "/runs/run-1/results",
      "/runs/run-1/sites/cell-1",
      "/runs/run-1/exclusions",
      "/scenario-comparison",
      "/data-quality",
    ]);
    expect(new URL(requests[1]!.url).searchParams.get("top_n")).toBe("10");
    expect(new URL(requests[1]!.url).searchParams.get("min_score")).toBe("0.5");
    await expect(requests[0]!.json()).resolves.toEqual({ scenario: "wind_led" });
  });

  it("surfaces a non-success response consistently", async () => {
    const service = createDecisionServiceClient({
      baseUrl: "https://decision.example.test",
      fetch: async () => json({ detail: "missing validation output" }, 503),
    });

    await expect(service.getDataQuality()).rejects.toMatchObject({
      name: "DecisionServiceError",
      status: 503,
    });
  });
});
