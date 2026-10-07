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
let canvasCursor = "";

jest.mock("maplibre-gl", () => {
  class MockMap {
    // Two-arg form registers the load handler (S3-03a); the three-arg form is a
    // layer-scoped handler (S3-03b) captured by `${event}:${layerId}`.
    on(event: string, layerOrCb: unknown, maybeCb?: (event: unknown) => void) {
      if (typeof layerOrCb === "function") {
        // Fire the load handler synchronously so the "cells" source is added
        // and mapReady flips true before any fetched data is applied.
        if (event === "load") (layerOrCb as () => void)();
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
    getSource() {
      return { setData: (...args: unknown[]) => setDataSpy(...args) };
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
  canvasCursor = "";
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
    features?: { properties: Record<string, unknown> }[],
  ): void {
    const handler = layerHandlers[`${event}:${layerId}`];
    expect(handler).toBeDefined();
    handler?.({ features });
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

  it("toggles the canvas pointer cursor on mouseenter/mouseleave over cells", async () => {
    const getRunCells = jest.fn().mockResolvedValue(featureCollection("run-1"));
    render(<CellMap runId="run-1" service={serviceWithCells(getRunCells)} />);
    await waitFor(() => expect(setDataSpy).toHaveBeenCalled());

    fireLayerEvent("mouseenter", "cells-eligible");
    expect(canvasCursor).toBe("pointer");
    fireLayerEvent("mouseleave", "cells-eligible");
    expect(canvasCursor).toBe("");
  });
});
