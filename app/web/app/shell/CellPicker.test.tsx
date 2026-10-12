/**
 * Component test for CellPicker (S3-06 cell-selection mini-map).
 *
 * `maplibre-gl` is mocked (jsdom has no WebGL), reusing the CellMap mock shape:
 * the "load" handler fires synchronously, map-wide handlers are captured by
 * event name so a test can fire a synthetic drag, and `getRunCells` is faked.
 *
 * Assertions:
 *   - the picker fetches the run's cells once through the injected service;
 *   - firing mousedown -> mousemove -> mouseup framing a known subset calls
 *     onApply with exactly those cell_ids (the pure hit-test), in cell order;
 *   - a drag that frames no cell calls onApply with an empty array;
 *   - Clear calls onClear;
 *   - the picker reads data only through the injected service (no fetch literal).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { CellCollection, DecisionService } from "../api/decision-service";
import CellPicker from "./CellPicker";

const setDataSpy = jest.fn();
let mapHandlers: Record<string, (event: unknown) => void> = {};

jest.mock("maplibre-gl", () => {
  class MockMap {
    on(event: string, layerOrCb: unknown, maybeCb?: (event: unknown) => void) {
      if (typeof layerOrCb === "function") {
        if (event === "load") {
          (layerOrCb as () => void)();
        } else {
          mapHandlers[event] = layerOrCb as (event: unknown) => void;
        }
        return;
      }
      if (typeof maybeCb === "function") {
        mapHandlers[`${event}:${layerOrCb as string}`] = maybeCb;
      }
    }
    addControl() {}
    addSource() {}
    addLayer() {}
    getSource() {
      return { setData: (...args: unknown[]) => setDataSpy(...args) };
    }
    getCanvas() {
      return { style: { cursor: "" } };
    }
    dragPan = { enable() {}, disable() {} };
    remove() {}
  }
  return {
    __esModule: true,
    default: { Map: MockMap, NavigationControl: class {} },
    Map: MockMap,
    NavigationControl: class {},
  };
});

function collection(runId: string): CellCollection {
  return {
    type: "FeatureCollection",
    run_id: runId,
    features: [
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [150.0, -32.0] },
        properties: { cell_id: "inside-1", eligible: true, suitability_score: 0.9, rank: 1 },
      },
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [150.5, -31.5] },
        properties: { cell_id: "inside-2", eligible: true, suitability_score: 0.8, rank: 2 },
      },
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [145.0, -32.0] },
        properties: { cell_id: "outside-1", eligible: true, suitability_score: 0.7, rank: 3 },
      },
    ],
  } as CellCollection;
}

function serviceWithCells(impl: DecisionService["getRunCells"]): DecisionService {
  return { getRunCells: impl } as unknown as DecisionService;
}

/** Fire a map-wide handler captured by event name with a lngLat point. */
function fireMap(event: string, lng: number, lat: number): void {
  const handler = mapHandlers[event];
  expect(handler).toBeDefined();
  handler?.({ lngLat: { lng, lat } });
}

/** Simulate a full drag framing the box [swLng,swLat] -> [neLng,neLat]. */
function drag(
  swLng: number,
  swLat: number,
  neLng: number,
  neLat: number,
): void {
  fireMap("mousedown", swLng, swLat);
  fireMap("mousemove", neLng, neLat);
  fireMap("mouseup", neLng, neLat);
}

beforeEach(() => {
  setDataSpy.mockClear();
  mapHandlers = {};
});

describe("CellPicker (S3-06 cell-selection mini-map)", () => {
  it("fetches the run's cells once through the injected service", async () => {
    const getRunCells = jest.fn().mockResolvedValue(collection("run-1"));
    render(
      <CellPicker
        runId="run-1"
        service={serviceWithCells(getRunCells)}
        onApply={jest.fn()}
        onClear={jest.fn()}
        activeCount={0}
      />,
    );
    await waitFor(() => expect(getRunCells).toHaveBeenCalledTimes(1));
    expect(getRunCells).toHaveBeenCalledWith("run-1");
  });

  it("calls onApply with the cell_ids whose centre is inside the dragged rectangle", async () => {
    const getRunCells = jest.fn().mockResolvedValue(collection("run-1"));
    const onApply = jest.fn();
    render(
      <CellPicker
        runId="run-1"
        service={serviceWithCells(getRunCells)}
        onApply={onApply}
        onClear={jest.fn()}
        activeCount={0}
      />,
    );
    await waitFor(() => expect(getRunCells).toHaveBeenCalled());

    // A box over [149..151] x [-33..-31] captures inside-1 and inside-2 but
    // not outside-1 (at lng 145).
    drag(149.0, -33.0, 151.0, -31.0);

    expect(onApply).toHaveBeenCalledTimes(1);
    expect(onApply).toHaveBeenCalledWith(["inside-1", "inside-2"]);
  });

  it("calls onApply with an empty array when the rectangle frames no cell", async () => {
    const getRunCells = jest.fn().mockResolvedValue(collection("run-1"));
    const onApply = jest.fn();
    render(
      <CellPicker
        runId="run-1"
        service={serviceWithCells(getRunCells)}
        onApply={onApply}
        onClear={jest.fn()}
        activeCount={0}
      />,
    );
    await waitFor(() => expect(getRunCells).toHaveBeenCalled());

    drag(100.0, -10.0, 101.0, -9.0); // nowhere near any cell
    expect(onApply).toHaveBeenCalledWith([]);
  });

  it("does not emit a selection on a stray mousemove without a mousedown", async () => {
    const getRunCells = jest.fn().mockResolvedValue(collection("run-1"));
    const onApply = jest.fn();
    render(
      <CellPicker
        runId="run-1"
        service={serviceWithCells(getRunCells)}
        onApply={onApply}
        onClear={jest.fn()}
        activeCount={0}
      />,
    );
    await waitFor(() => expect(getRunCells).toHaveBeenCalled());

    fireMap("mousemove", 150.0, -32.0);
    fireMap("mouseup", 150.0, -32.0);
    expect(onApply).not.toHaveBeenCalled();
  });

  it("calls onClear when the Clear button is pressed", async () => {
    const getRunCells = jest.fn().mockResolvedValue(collection("run-1"));
    const onClear = jest.fn();
    render(
      <CellPicker
        runId="run-1"
        service={serviceWithCells(getRunCells)}
        onApply={jest.fn()}
        onClear={onClear}
        activeCount={2}
      />,
    );
    await waitFor(() => expect(getRunCells).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: /clear selection/i }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it("reports the active count and disables Clear when nothing is selected", () => {
    const getRunCells = jest.fn().mockResolvedValue(collection("run-1"));
    render(
      <CellPicker
        runId="run-1"
        service={serviceWithCells(getRunCells)}
        onApply={jest.fn()}
        onClear={jest.fn()}
        activeCount={0}
      />,
    );
    expect(screen.getByRole("button", { name: /clear selection/i })).toBeDisabled();
    expect(screen.getByText(/showing all cells/i)).toBeInTheDocument();
  });

  it("shows the no-run status and fetches nothing when runId is null", () => {
    const getRunCells = jest.fn();
    render(
      <CellPicker
        runId={null}
        service={serviceWithCells(getRunCells)}
        onApply={jest.fn()}
        onClear={jest.fn()}
        activeCount={0}
      />,
    );
    expect(screen.getByText("No run is loaded.")).toBeInTheDocument();
    expect(getRunCells).not.toHaveBeenCalled();
  });

  it("reads data only through the injected service — no fetch literal in source", () => {
    const source = readFileSync(join(__dirname, "CellPicker.tsx"), "utf8");
    expect(source).not.toMatch(/\bfetch\s*\(/);
    expect(source).toContain("service.getRunCells");
  });
});
