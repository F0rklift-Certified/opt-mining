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

/** A minimal service that only implements getRunCells (the sole op CellMap uses). */
function serviceWithCells(
  impl: DecisionService["getRunCells"],
): DecisionService {
  return { getRunCells: impl } as unknown as DecisionService;
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

  it("reads data only through the injected service — no fetch literal in source", () => {
    const source = readFileSync(join(__dirname, "CellMap.tsx"), "utf8");
    expect(source).not.toMatch(/\bfetch\s*\(/);
    expect(source).toContain("service.getRunCells");
  });
});
