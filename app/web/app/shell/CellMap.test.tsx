/**
 * Component test for CellMap (S3-03a).
 *
 * `maplibre-gl` is mocked because jsdom has no WebGL (design §5.8). The mock
 * fires the "load" handler synchronously and exposes a shared `setData` spy, so
 * the single-path lifecycle (mapReady gate, pendingDataRef replay) runs without
 * a GL context and we can assert the served FeatureCollection reaches the source.
 *
 * Assertions (design §5.8):
 *   - a non-null runId calls service.getRunCells(runId) exactly once;
 *   - the returned FeatureCollection is passed to the mocked source's setData;
 *   - changing runId triggers a refetch;
 *   - an error renders the role="alert" "Map data unavailable" message;
 *   - CellMap reads data only via the injected service (no fetch literal) — the
 *     source file is scanned to prove the single-integration-point rule.
 *
 * NOT covered here (integration/manual, design §5.8): actual GPU rendering and
 * visual readability at ~47k features against the running stack.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen, waitFor } from "@testing-library/react";

import type { CellCollection, DecisionService } from "../api/decision-service";
import { DecisionServiceError } from "../api/decision-service";
import CellMap from "./CellMap";

const setDataSpy = jest.fn();

jest.mock("maplibre-gl", () => {
  class MockMap {
    on(event: string, cb: () => void) {
      // Fire the load handler synchronously so the "cells" source is added and
      // mapReady flips true before any fetched data is applied.
      if (event === "load") cb();
    }
    addControl() {}
    addSource() {}
    addLayer() {}
    getSource() {
      return { setData: (...args: unknown[]) => setDataSpy(...args) };
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

function featureCollection(runId: string): CellCollection {
  return {
    type: "FeatureCollection",
    run_id: runId,
    features: [
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [151.2, -30.1] },
        properties: {
          cell_id: "S30.100_E151.200",
          eligible: true,
          suitability_score: 0.9,
          rank: 1,
        },
      },
    ],
  };
}

/**
 * A collection with one eligible cell and two excluded cells — one ruled out
 * only by missing wind data (a no-data cell) and one ruled out by a protected
 * area (an environmental cell) — for the exclusion-class classification test.
 */
function mixedCollection(runId: string): CellCollection {
  return {
    type: "FeatureCollection",
    run_id: runId,
    features: [
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [151.2, -30.1] },
        properties: { cell_id: "eligible-1", eligible: true, suitability_score: 0.9, rank: 1 },
      },
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [146.0, -34.0] },
        properties: { cell_id: "nodata-1", eligible: false, suitability_score: null, rank: null },
      },
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [150.3, -33.7] },
        properties: { cell_id: "env-1", eligible: false, suitability_score: null, rank: null },
      },
    ],
  };
}

/** A minimal service that only implements getRunCells (the sole required op). */
function serviceWithCells(
  impl: DecisionService["getRunCells"],
): DecisionService {
  return { getRunCells: impl } as unknown as DecisionService;
}

/** A service implementing both getRunCells and getExclusions. */
function serviceWithCellsAndExclusions(
  cells: DecisionService["getRunCells"],
  exclusions: DecisionService["getExclusions"],
): DecisionService {
  return { getRunCells: cells, getExclusions: exclusions } as unknown as DecisionService;
}

beforeEach(() => {
  setDataSpy.mockClear();
});

describe("CellMap (S3-03a map rendering)", () => {
  it("fetches the run's cells once and applies them to the map source", async () => {
    const collection = featureCollection("run-1");
    const getRunCells = jest.fn().mockResolvedValue(collection);
    render(<CellMap runId="run-1" service={serviceWithCells(getRunCells)} />);

    await waitFor(() => {
      expect(setDataSpy).toHaveBeenCalledWith(collection);
    });
    expect(getRunCells).toHaveBeenCalledTimes(1);
    expect(getRunCells).toHaveBeenCalledWith("run-1");
  });

  it("refetches when runId changes", async () => {
    const getRunCells = jest
      .fn()
      .mockImplementation((id: string) => Promise.resolve(featureCollection(id)));
    const service = serviceWithCells(getRunCells);
    const { rerender } = render(<CellMap runId="run-1" service={service} />);

    await waitFor(() => expect(getRunCells).toHaveBeenCalledWith("run-1"));

    rerender(<CellMap runId="run-2" service={service} />);

    await waitFor(() => expect(getRunCells).toHaveBeenCalledWith("run-2"));
    expect(getRunCells).toHaveBeenCalledTimes(2);
  });

  it("shows the no-run status and fetches nothing when runId is null", () => {
    const getRunCells = jest.fn();
    render(<CellMap runId={null} service={serviceWithCells(getRunCells)} />);

    expect(screen.getByText("No run is loaded.")).toBeInTheDocument();
    expect(getRunCells).not.toHaveBeenCalled();
  });

  it("renders a role=alert message when the fetch fails", async () => {
    const getRunCells = jest
      .fn()
      .mockRejectedValue(new DecisionServiceError(503, { detail: "no output" }));
    render(<CellMap runId="run-1" service={serviceWithCells(getRunCells)} />);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Map data unavailable");
  });

  it("classifies excluded cells from engine reason codes and stamps exclusion_class", async () => {
    const getRunCells = jest.fn().mockResolvedValue(mixedCollection("run-1"));
    const getExclusions = jest.fn().mockResolvedValue([
      { cell_id: "nodata-1", reason_codes: ["missing_wind_data"], reason_text: "Missing wind data" },
      {
        cell_id: "env-1",
        reason_codes: ["protected_area", "missing_wind_data"],
        reason_text: "Protected area: Blue Mountains, Missing wind data",
      },
    ]);
    render(
      <CellMap
        runId="run-1"
        service={serviceWithCellsAndExclusions(getRunCells, getExclusions)}
      />,
    );

    await waitFor(() => expect(setDataSpy).toHaveBeenCalled());
    const applied = setDataSpy.mock.calls.at(-1)?.[0] as CellCollection;
    const byId = new Map(
      (applied.features ?? []).map(
        (f) => [f.properties.cell_id, f.properties as Record<string, unknown>] as const,
      ),
    );

    // A cell excluded ONLY by missing wind data is "nodata" (unassessed).
    expect(byId.get("nodata-1")?.exclusion_class).toBe("nodata");
    // A cell carrying a real rule (protected area) is "environmental", even
    // though missing-wind co-occurs.
    expect(byId.get("env-1")?.exclusion_class).toBe("environmental");
    // Eligible cells are left untouched (no exclusion_class).
    expect(byId.get("eligible-1")?.exclusion_class).toBeUndefined();
    expect(getExclusions).toHaveBeenCalledWith("run-1");
  });

  it("still renders cells when getExclusions is unavailable (best-effort enrichment)", async () => {
    const collection = mixedCollection("run-1");
    const getRunCells = jest.fn().mockResolvedValue(collection);
    // serviceWithCells has no getExclusions — the optional call must not throw.
    render(<CellMap runId="run-1" service={serviceWithCells(getRunCells)} />);

    await waitFor(() => expect(setDataSpy).toHaveBeenCalled());
    expect(getRunCells).toHaveBeenCalledTimes(1);
  });

  it("reads data only through the injected service — no fetch literal in source", () => {
    const source = readFileSync(join(__dirname, "CellMap.tsx"), "utf8");
    expect(source).not.toMatch(/\bfetch\s*\(/);
    expect(source).toContain("service.getRunCells");
  });
});
