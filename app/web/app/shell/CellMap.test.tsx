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

import type {
  CellCollection,
  CellSelection,
  DecisionService,
} from "../api/decision-service";
import { DecisionServiceError } from "../api/decision-service";
import CellMap from "./CellMap";

const setDataSpy = jest.fn();
const addSourceSpy = jest.fn();
const addLayerSpy = jest.fn();

/**
 * Layer-scoped handlers (click / mouseenter / mouseleave) the component
 * registers inside the load handler, captured keyed by `${event}:${layerId}`
 * so a test can fire a synthetic event at a given layer (S3-03b). Also records
 * the mock canvas cursor so the pointer-cursor wiring is assertable.
 */
let layerHandlers: Record<string, (event: unknown) => void> = {};
/** Map-wide (non-load) handlers keyed by event name, e.g. mousemove/mouseout. */
let mapHandlers: Record<string, (event: unknown) => void> = {};
let canvasCursor = "";
/**
 * Records the last `setData` payload per source id so tests can assert the
 * persistent `cell-selected` box and the transient `cell-hover` box
 * independently (both route through the shared `setDataSpy` too). Keyed by the
 * source id passed to `getSource`.
 */
let lastSetDataBySource: Record<string, unknown> = {};

jest.mock("maplibre-gl", () => {
  class MockMap {
    // Two-arg form is a map-wide handler: `load` fires synchronously (so the
    // sources are added and mapReady flips before data is applied); any other
    // map-wide handler (e.g. mousemove/mouseout, S3-03b hover) is captured by
    // `${event}` so a test can fire it. The three-arg form is a layer-scoped
    // handler captured by `${event}:${layerId}`.
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
        layerHandlers[`${event}:${layerOrCb as string}`] = maybeCb;
      }
    }
    addControl() {}
    addSource(id: string) {
      addSourceSpy(id);
    }
    addLayer(layer: { id: string }) {
      addLayerSpy(layer.id);
    }
    getSource(id: string) {
      return {
        setData: (...args: unknown[]) => {
          lastSetDataBySource[id] = args[0];
          setDataSpy(...args);
        },
      };
    }
    getCanvas() {
      return {
        get style() {
          return {
            get cursor() {
              return canvasCursor;
            },
            set cursor(value: string) {
              canvasCursor = value;
            },
          };
        },
      };
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
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [149.0, -35.3] },
        properties: { cell_id: "demand-nodata-1", eligible: false, suitability_score: null, rank: null },
      },
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [153.4, -30.0] },
        properties: { cell_id: "offshore-1", eligible: false, suitability_score: null, rank: null },
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
  addSourceSpy.mockClear();
  addLayerSpy.mockClear();
  layerHandlers = {};
  mapHandlers = {};
  canvasCursor = "";
  lastSetDataBySource = {};
});

describe("CellMap (S3-03a map rendering)", () => {
  it("fetches the run's cells once and applies the NSW-clipped collection to the map source", async () => {
    const collection = featureCollection("run-1");
    const getRunCells = jest.fn().mockResolvedValue(collection);
    render(<CellMap runId="run-1" service={serviceWithCells(getRunCells)} />);

    await waitFor(() => expect(setDataSpy).toHaveBeenCalled());
    // The clip returns a NEW FeatureCollection, so we assert on its shape rather
    // than object identity. The single cell [151.2, -30.1] is inside NSW, so it
    // survives the clip and the applied collection has exactly one feature.
    const applied = setDataSpy.mock.calls.at(-1)?.[0] as CellCollection;
    expect(applied.type).toBe("FeatureCollection");
    expect(applied.features).toHaveLength(1);
    expect(applied.features?.[0]?.properties.cell_id).toBe("S30.100_E151.200");
    expect(getRunCells).toHaveBeenCalledTimes(1);
    expect(getRunCells).toHaveBeenCalledWith("run-1");
  });

  it("adds the NSW boundary source and the mask/border layers on load", () => {
    const getRunCells = jest.fn().mockResolvedValue(featureCollection("run-1"));
    render(<CellMap runId="run-1" service={serviceWithCells(getRunCells)} />);

    expect(addSourceSpy).toHaveBeenCalledWith("nsw-boundary");
    expect(addLayerSpy).toHaveBeenCalledWith("nsw-mask");
    expect(addLayerSpy).toHaveBeenCalledWith("nsw-border");
    // The three cell layers are still added above the boundary layers.
    expect(addLayerSpy).toHaveBeenCalledWith("cells-excluded-nodata");
    expect(addLayerSpy).toHaveBeenCalledWith("cells-excluded-env");
    expect(addLayerSpy).toHaveBeenCalledWith("cells-eligible");
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
      {
        cell_id: "demand-nodata-1",
        reason_codes: ["missing_demand_data"],
        reason_text: "Missing demand data",
      },
      {
        cell_id: "offshore-1",
        reason_codes: ["offshore_or_marine", "missing_slope_data"],
        reason_text: "Offshore or marine (not on land), Missing slope data",
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

    // The clip keeps only cells inside the NSW shape. The exclusion-class logic
    // is unchanged and still exercised by the surviving cells:
    // A cell excluded ONLY by missing wind data is "nodata" (unassessed).
    expect(byId.get("nodata-1")?.exclusion_class).toBe("nodata");
    // A cell carrying a real rule (protected area) is "environmental", even
    // though missing-wind co-occurs.
    expect(byId.get("env-1")?.exclusion_class).toBe("environmental");
    // Eligible cells are left untouched by the clip (no exclusion_class added).
    expect(byId.get("eligible-1")?.exclusion_class).toBeUndefined();
    // Cells outside NSW are dropped by the geographic clip before reaching the
    // source: `demand-nodata-1` (south of the border) and `offshore-1` (ocean
    // east of the coast) never appear in the applied collection.
    expect(byId.has("demand-nodata-1")).toBe(false);
    expect(byId.has("offshore-1")).toBe(false);
    expect(getExclusions).toHaveBeenCalledWith("run-1");
  });

  it("clips cells geographically to NSW — a far-outside cell is dropped, an inside cell is kept", async () => {
    const collection: CellCollection = {
      type: "FeatureCollection",
      run_id: "run-1",
      features: [
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [151.2, -30.1] },
          properties: { cell_id: "inside-nsw", eligible: true, suitability_score: 0.5, rank: 1 },
        },
        {
          type: "Feature",
          geometry: { type: "Point", coordinates: [135.0, -25.0] },
          properties: { cell_id: "central-australia", eligible: true, suitability_score: 0.5, rank: 2 },
        },
      ],
    };
    const getRunCells = jest.fn().mockResolvedValue(collection);
    render(<CellMap runId="run-1" service={serviceWithCells(getRunCells)} />);

    await waitFor(() => expect(setDataSpy).toHaveBeenCalled());
    const applied = setDataSpy.mock.calls.at(-1)?.[0] as CellCollection;
    const ids = (applied.features ?? []).map((f) => f.properties.cell_id);
    expect(ids).toContain("inside-nsw");
    expect(ids).not.toContain("central-australia");
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

describe("CellMap click-to-inspect (S3-03b)", () => {
  /** Fire the captured layer handler with a synthetic MapLibre event. */
  function fireLayerEvent(
    event: string,
    layerId: string,
    features?: {
      properties: Record<string, unknown>;
      geometry?: { type: string; coordinates: number[] };
    }[],
  ): void {
    const handler = layerHandlers[`${event}:${layerId}`];
    expect(handler).toBeDefined();
    handler?.({ features });
  }

  /** Fire a captured map-wide handler (e.g. mousemove) with a lngLat point. */
  function fireMapMove(lng: number, lat: number): void {
    const handler = mapHandlers["mousemove"];
    expect(handler).toBeDefined();
    handler?.({ lngLat: { lng, lat } });
  }

  /** Fire the captured map-wide mouseout handler. */
  function fireMapOut(): void {
    const handler = mapHandlers["mouseout"];
    expect(handler).toBeDefined();
    handler?.({});
  }

  it("invokes onSelectCell with the clicked eligible cell's typed selection", async () => {
    const getRunCells = jest.fn().mockResolvedValue(featureCollection("run-1"));
    const onSelectCell = jest.fn();
    render(
      <CellMap
        runId="run-1"
        service={serviceWithCells(getRunCells)}
        onSelectCell={onSelectCell}
      />,
    );
    await waitFor(() => expect(setDataSpy).toHaveBeenCalled());

    fireLayerEvent("click", "cells-eligible", [
      {
        properties: {
          cell_id: "S30.100_E151.200",
          eligible: true,
          suitability_score: 0.9,
          rank: 1,
        },
      },
    ]);

    expect(onSelectCell).toHaveBeenCalledTimes(1);
    const selection = onSelectCell.mock.calls[0]?.[0] as CellSelection;
    expect(selection).toEqual({
      cell_id: "S30.100_E151.200",
      eligible: true,
      suitability_score: 0.9,
      rank: 1,
    });
  });

  it("yields null score/rank when an excluded cell is clicked", async () => {
    const getRunCells = jest.fn().mockResolvedValue(featureCollection("run-1"));
    const onSelectCell = jest.fn();
    render(
      <CellMap
        runId="run-1"
        service={serviceWithCells(getRunCells)}
        onSelectCell={onSelectCell}
      />,
    );
    await waitFor(() => expect(setDataSpy).toHaveBeenCalled());

    // An excluded feature carries no score/rank (null in the GeoJSON); the
    // selection reports eligible:false with both coerced to null.
    fireLayerEvent("click", "cells-excluded-env", [
      {
        properties: {
          cell_id: "env-1",
          eligible: false,
          suitability_score: null,
          rank: null,
        },
      },
    ]);

    const selection = onSelectCell.mock.calls[0]?.[0] as CellSelection;
    expect(selection).toEqual({
      cell_id: "env-1",
      eligible: false,
      suitability_score: null,
      rank: null,
    });
  });

  it("does not throw when a cell is clicked and no onSelectCell is wired", async () => {
    const getRunCells = jest.fn().mockResolvedValue(featureCollection("run-1"));
    render(<CellMap runId="run-1" service={serviceWithCells(getRunCells)} />);
    await waitFor(() => expect(setDataSpy).toHaveBeenCalled());

    expect(() =>
      fireLayerEvent("click", "cells-eligible", [
        {
          properties: {
            cell_id: "S30.100_E151.200",
            eligible: true,
            suitability_score: 0.9,
            rank: 1,
          },
        },
      ]),
    ).not.toThrow();
  });

  it("ignores a click that carries no feature", async () => {
    const getRunCells = jest.fn().mockResolvedValue(featureCollection("run-1"));
    const onSelectCell = jest.fn();
    render(
      <CellMap
        runId="run-1"
        service={serviceWithCells(getRunCells)}
        onSelectCell={onSelectCell}
      />,
    );
    await waitFor(() => expect(setDataSpy).toHaveBeenCalled());

    fireLayerEvent("click", "cells-eligible", []);
    expect(onSelectCell).not.toHaveBeenCalled();
  });

  it("sets the pointer cursor while the cursor is inside a cell's square and resets it outside", async () => {
    const getRunCells = jest.fn().mockResolvedValue(featureCollection("run-1"));
    render(<CellMap runId="run-1" service={serviceWithCells(getRunCells)} />);
    await waitFor(() => expect(setDataSpy).toHaveBeenCalled());

    fireMapMove(151.2, -30.1); // inside the one cell's square
    expect(canvasCursor).toBe("pointer");
    fireMapMove(151.2 + 0.1, -30.1); // outside every square
    expect(canvasCursor).toBe("");
  });

  it("adds the selected and hover highlight sources and outline layers on load", async () => {
    const getRunCells = jest.fn().mockResolvedValue(featureCollection("run-1"));
    render(<CellMap runId="run-1" service={serviceWithCells(getRunCells)} />);
    await waitFor(() => expect(setDataSpy).toHaveBeenCalled());

    expect(addSourceSpy).toHaveBeenCalledWith("cell-selected");
    expect(addLayerSpy).toHaveBeenCalledWith("cell-selected-outline");
    expect(addSourceSpy).toHaveBeenCalledWith("cell-hover");
    expect(addLayerSpy).toHaveBeenCalledWith("cell-hover-outline");
  });

  const d = 0.0225; // SELECTION_HALF_DEG — half-width of the highlight square

  /** The expected closed square ring centred on [lng, lat], inset by d. */
  function expectedRing(lng: number, lat: number): number[][] {
    return [
      [lng - d, lat - d],
      [lng + d, lat - d],
      [lng + d, lat + d],
      [lng - d, lat + d],
      [lng - d, lat - d],
    ];
  }

  /** The square ring last applied to a given highlight source, or null. */
  function ringForSource(sourceId: string): number[][] | null {
    const fc = lastSetDataBySource[sourceId] as
      | GeoJSON.FeatureCollection
      | undefined;
    const feature = fc?.features[0];
    if (!feature || feature.geometry.type !== "Polygon") return null;
    return (feature.geometry as GeoJSON.Polygon).coordinates[0] ?? null;
  }

  it("draws the hover box when the cursor is anywhere INSIDE a cell's square, not just over its circle", async () => {
    const getRunCells = jest.fn().mockResolvedValue(featureCollection("run-1"));
    render(<CellMap runId="run-1" service={serviceWithCells(getRunCells)} />);
    await waitFor(() => expect(setDataSpy).toHaveBeenCalled());

    // The one cell's centre is [151.2, -30.1]. Move the cursor OFF the centre
    // but still well inside the ±d square (offset 0.01 < d=0.0225 on each axis):
    // the box must appear, snapped to the cell centre, and the cursor becomes a
    // pointer. The persistent selected box stays empty.
    const cx = 151.2;
    const cy = -30.1;
    fireMapMove(cx + 0.01, cy - 0.01);

    expect(ringForSource("cell-hover")).toEqual(expectedRing(cx, cy));
    expect(canvasCursor).toBe("pointer");
    expect(
      (lastSetDataBySource["cell-selected"] as GeoJSON.FeatureCollection)
        .features,
    ).toHaveLength(0);
  });

  it("clears the hover box (and pointer) when the cursor is OUTSIDE every cell's square", async () => {
    const getRunCells = jest.fn().mockResolvedValue(featureCollection("run-1"));
    render(<CellMap runId="run-1" service={serviceWithCells(getRunCells)} />);
    await waitFor(() => expect(setDataSpy).toHaveBeenCalled());

    // First land inside the square so a box exists, then move far away: the
    // box must clear and the pointer cursor reset.
    fireMapMove(151.2, -30.1);
    expect(ringForSource("cell-hover")).not.toBeNull();

    fireMapMove(151.2 + 0.1, -30.1); // 0.1 > d: outside the square
    expect(
      (lastSetDataBySource["cell-hover"] as GeoJSON.FeatureCollection).features,
    ).toHaveLength(0);
    expect(canvasCursor).toBe("");
  });

  it("pins the persistent selected box on the clicked cell and keeps it through hover", async () => {
    // mixedCollection has NSW-inside cells at [151.2,-30.1] (eligible-1) and
    // [150.3,-33.7] (env-1), so the hover-containment test can find cell B.
    const getRunCells = jest.fn().mockResolvedValue(mixedCollection("run-1"));
    const onSelectCell = jest.fn();
    render(
      <CellMap
        runId="run-1"
        service={serviceWithCells(getRunCells)}
        onSelectCell={onSelectCell}
      />,
    );
    await waitFor(() => expect(setDataSpy).toHaveBeenCalled());

    const selLng = 151.2;
    const selLat = -30.1;
    // Click cell A: the selected box is pinned there and the inspect callback fires.
    fireLayerEvent("click", "cells-eligible", [
      {
        properties: {
          cell_id: "eligible-1",
          eligible: true,
          suitability_score: 0.9,
          rank: 1,
        },
        geometry: { type: "Point", coordinates: [selLng, selLat] },
      },
    ]);
    expect(onSelectCell).toHaveBeenCalledTimes(1);
    expect(ringForSource("cell-selected")).toEqual(expectedRing(selLng, selLat));

    // Now hover INSIDE a DIFFERENT cell B's square (centre [150.3,-33.7]): the
    // hover box snaps there, but the pinned selected box stays on A.
    const hovLng = 150.3;
    const hovLat = -33.7;
    fireMapMove(hovLng + 0.005, hovLat + 0.005);
    expect(ringForSource("cell-hover")).toEqual(expectedRing(hovLng, hovLat));
    expect(ringForSource("cell-selected")).toEqual(expectedRing(selLng, selLat));
  });

  it("clears only the hover box when the cursor leaves the map; the pinned selected box persists", async () => {
    const getRunCells = jest.fn().mockResolvedValue(featureCollection("run-1"));
    render(<CellMap runId="run-1" service={serviceWithCells(getRunCells)} />);
    await waitFor(() => expect(setDataSpy).toHaveBeenCalled());

    const selLng = 151.2;
    const selLat = -30.1;
    fireLayerEvent("click", "cells-eligible", [
      {
        properties: {
          cell_id: "S30.100_E151.200",
          eligible: true,
          suitability_score: 0.9,
          rank: 1,
        },
        geometry: { type: "Point", coordinates: [selLng, selLat] },
      },
    ]);
    fireMapMove(selLng, selLat); // hover the same cell to draw a hover box
    fireMapOut();

    // Hover box emptied; selected box still pinned on the clicked cell.
    expect(
      (lastSetDataBySource["cell-hover"] as GeoJSON.FeatureCollection).features,
    ).toHaveLength(0);
    expect(ringForSource("cell-selected")).toEqual(expectedRing(selLng, selLat));
  });

  it("does not move a box when the event feature has no point geometry", async () => {
    const getRunCells = jest.fn().mockResolvedValue(featureCollection("run-1"));
    const onSelectCell = jest.fn();
    render(
      <CellMap
        runId="run-1"
        service={serviceWithCells(getRunCells)}
        onSelectCell={onSelectCell}
      />,
    );
    await waitFor(() => expect(setDataSpy).toHaveBeenCalled());

    setDataSpy.mockClear();
    // Click with no geometry: the inspect callback still fires, but the pinned
    // box is not moved (no setData to either highlight source).
    fireLayerEvent("click", "cells-eligible", [
      {
        properties: {
          cell_id: "S30.100_E151.200",
          eligible: true,
          suitability_score: 0.9,
          rank: 1,
        },
      },
    ]);
    expect(onSelectCell).toHaveBeenCalledTimes(1);
    expect(setDataSpy).not.toHaveBeenCalled();
  });

  it("does not draw a hover box when the cursor is over no cell", async () => {
    // featureCollection has a single cell at [151.2,-30.1]; a cursor far from
    // it (and from any other cell) is inside no square, so no hover box.
    const getRunCells = jest.fn().mockResolvedValue(featureCollection("run-1"));
    render(<CellMap runId="run-1" service={serviceWithCells(getRunCells)} />);
    await waitFor(() => expect(setDataSpy).toHaveBeenCalled());

    setDataSpy.mockClear();
    fireMapMove(145.0, -32.0); // nowhere near the one cell's square
    const applied = lastSetDataBySource["cell-hover"] as
      | GeoJSON.FeatureCollection
      | undefined;
    // Either no setData at all, or an empty collection — never a square.
    if (applied) expect(applied.features).toHaveLength(0);
    expect(canvasCursor).toBe("");
  });
});
