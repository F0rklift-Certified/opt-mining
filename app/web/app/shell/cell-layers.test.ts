/**
 * Unit tests for the shared cell-layers presentation helpers (S3-06 mini-map
 * parity). These are the pure functions BOTH CellMap and CellPicker consume to
 * draw the NSW boundary + outside-dimming mask and the three engine-driven cell
 * layers with one shared definition, so the two maps cannot drift.
 *
 * No MapLibre / jsdom here — the builders return plain style/geometry objects,
 * so they are asserted directly. The component tests (CellMap.test.tsx /
 * CellPicker.test.tsx) prove both components actually ADD these layers.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import type { CellCollection, ExcludedRow } from "../api/decision-service";
import {
  CELLS_SOURCE_ID,
  EXCLUDED_NODATA_LAYER_ID,
  EXCLUDED_ENV_LAYER_ID,
  ELIGIBLE_LAYER_ID,
  NSW_SOURCE_ID,
  NSW_MASK_LAYER_ID,
  NSW_BORDER_LAYER_ID,
  classifyExclusion,
  withExclusionClasses,
  clipToNsw,
  nswBoundaryData,
  nswMaskLayer,
  nswBorderLayer,
  excludedNoDataLayer,
  excludedEnvLayer,
  eligibleLayer,
} from "./cell-layers";

describe("classifyExclusion (engine reason codes → class)", () => {
  it("classes a cell with ONLY no-data codes as 'nodata' (unassessed)", () => {
    expect(classifyExclusion(["missing_wind_data"])).toBe("nodata");
    expect(classifyExclusion(["missing_slope_data"])).toBe("nodata");
    expect(classifyExclusion(["missing_demand_data"])).toBe("nodata");
    expect(
      classifyExclusion(["missing_wind_data", "missing_slope_data"]),
    ).toBe("nodata");
  });

  it("classes any genuine rule as 'environmental', even co-coded with no-data", () => {
    expect(classifyExclusion(["protected_area"])).toBe("environmental");
    // offshore_or_marine is a real geographic rule-out, not a data gap.
    expect(classifyExclusion(["offshore_or_marine"])).toBe("environmental");
    expect(
      classifyExclusion(["offshore_or_marine", "missing_slope_data"]),
    ).toBe("environmental");
    expect(
      classifyExclusion(["protected_area", "missing_wind_data"]),
    ).toBe("environmental");
  });

  it("classes an empty reason list as 'environmental' (not an unassessed gap)", () => {
    expect(classifyExclusion([])).toBe("environmental");
  });
});

describe("withExclusionClasses (reason-join)", () => {
  const collection: CellCollection = {
    type: "FeatureCollection",
    run_id: "run-1",
    features: [
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [150.0, -32.0] },
        properties: { cell_id: "eligible-1", eligible: true, suitability_score: 0.8, rank: 1 },
      },
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [150.5, -32.5] },
        properties: { cell_id: "nodata-1", eligible: false, suitability_score: null, rank: null },
      },
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [151.0, -33.0] },
        properties: { cell_id: "env-1", eligible: false, suitability_score: null, rank: null },
      },
    ],
  } as CellCollection;

  const exclusions: ExcludedRow[] = [
    { cell_id: "nodata-1", reason_codes: ["missing_wind_data"], reason_text: "Missing wind data" },
    { cell_id: "env-1", reason_codes: ["protected_area"], reason_text: "Protected area" },
  ];

  it("stamps exclusion_class on excluded cells and leaves eligible cells untouched", () => {
    const out = withExclusionClasses(collection, exclusions);
    const byId = new Map(
      (out.features ?? []).map(
        (f) => [f.properties.cell_id, f.properties as Record<string, unknown>] as const,
      ),
    );
    expect(byId.get("nodata-1")?.exclusion_class).toBe("nodata");
    expect(byId.get("env-1")?.exclusion_class).toBe("environmental");
    expect(byId.get("eligible-1")?.exclusion_class).toBeUndefined();
  });

  it("falls back to 'environmental' for an excluded cell with no exclusion row", () => {
    const out = withExclusionClasses(collection, []);
    const byId = new Map(
      (out.features ?? []).map(
        (f) => [f.properties.cell_id, f.properties as Record<string, unknown>] as const,
      ),
    );
    expect(byId.get("nodata-1")?.exclusion_class).toBe("environmental");
    expect(byId.get("env-1")?.exclusion_class).toBe("environmental");
  });

  it("returns a NEW collection without mutating the input", () => {
    const out = withExclusionClasses(collection, exclusions);
    expect(out).not.toBe(collection);
    expect(collection.features?.[1]?.properties).not.toHaveProperty(
      "exclusion_class",
    );
  });
});

describe("clipToNsw (geographic clip, presentation-only)", () => {
  it("keeps a cell inside NSW and drops one well outside, without touching styling", () => {
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
    } as CellCollection;
    const out = clipToNsw(collection);
    const ids = (out.features ?? []).map((f) => f.properties.cell_id);
    expect(ids).toContain("inside-nsw");
    expect(ids).not.toContain("central-australia");
    // Surviving cell's styling values are untouched.
    expect(out.features?.[0]?.properties.suitability_score).toBe(0.5);
  });
});

describe("boundary builders (shape of NSW)", () => {
  it("builds a mask + border feature pair tagged by kind on the shared source", () => {
    const data = nswBoundaryData();
    expect(data.type).toBe("FeatureCollection");
    expect(data.features).toHaveLength(2);
    const kinds = data.features.map((f) => f.properties?.kind);
    expect(kinds).toEqual(["mask", "border"]);
    // The mask's outer ring is the world bbox (so everything outside NSW dims).
    const mask = data.features[0];
    expect(mask?.geometry.type).toBe("Polygon");
  });

  it("mask and border layers bind to the NSW source and filter by kind", () => {
    expect(nswMaskLayer()).toMatchObject({
      id: NSW_MASK_LAYER_ID,
      type: "fill",
      source: NSW_SOURCE_ID,
      filter: ["==", ["get", "kind"], "mask"],
    });
    expect(nswMaskLayer().paint).toMatchObject({
      "fill-color": "#0b1a2b",
      "fill-opacity": 0.35,
    });
    expect(nswBorderLayer()).toMatchObject({
      id: NSW_BORDER_LAYER_ID,
      type: "line",
      source: NSW_SOURCE_ID,
      filter: ["==", ["get", "kind"], "border"],
    });
  });
});

describe("cell layer builders (shared visual language)", () => {
  it("default to the shared cell source id", () => {
    expect(eligibleLayer().source).toBe(CELLS_SOURCE_ID);
    expect(excludedEnvLayer().source).toBe(CELLS_SOURCE_ID);
    expect(excludedNoDataLayer().source).toBe(CELLS_SOURCE_ID);
  });

  it("bind to a caller-supplied source id WITHOUT changing paint (so the picker can reuse them)", () => {
    const PICKER = "picker-cells";
    const shared = eligibleLayer();
    const picker = eligibleLayer(PICKER);
    expect(picker.source).toBe(PICKER);
    expect(picker.id).toBe(ELIGIBLE_LAYER_ID);
    // Only the source binding differs; paint is byte-for-byte identical.
    expect(picker.paint).toEqual(shared.paint);
    expect(picker.filter).toEqual(shared.filter);
  });

  it("filters each layer on eligible / exclusion_class as the big map does", () => {
    expect(eligibleLayer().filter).toEqual(["==", ["get", "eligible"], true]);
    expect(excludedEnvLayer().filter).toEqual([
      "all",
      ["==", ["get", "eligible"], false],
      ["==", ["get", "exclusion_class"], "environmental"],
    ]);
    expect(excludedNoDataLayer().filter).toEqual([
      "all",
      ["==", ["get", "eligible"], false],
      ["==", ["get", "exclusion_class"], "nodata"],
    ]);
    expect(excludedEnvLayer().id).toBe(EXCLUDED_ENV_LAYER_ID);
    expect(excludedNoDataLayer().id).toBe(EXCLUDED_NODATA_LAYER_ID);
  });

  it("drives the eligible colour from a suitability_score ramp with the shared stops", () => {
    const color = (eligibleLayer().paint as Record<string, unknown>)[
      "circle-color"
    ];
    expect(color).toEqual([
      "interpolate",
      ["linear"],
      ["get", "suitability_score"],
      0,
      "#fee5d9",
      0.5,
      "#fb6a4a",
      1,
      "#a50f15",
    ]);
  });
});

describe("both maps consume the SAME shared helpers (no drift)", () => {
  it("CellMap and CellPicker both import the cell layers / boundary builders from ./cell-layers", () => {
    const cellMap = readFileSync(join(__dirname, "CellMap.tsx"), "utf8");
    const cellPicker = readFileSync(join(__dirname, "CellPicker.tsx"), "utf8");
    for (const source of [cellMap, cellPicker]) {
      expect(source).toMatch(/from\s+["']\.\/cell-layers["']/);
      expect(source).toContain("eligibleLayer");
      expect(source).toContain("excludedEnvLayer");
      expect(source).toContain("excludedNoDataLayer");
      expect(source).toContain("nswMaskLayer");
      expect(source).toContain("nswBorderLayer");
    }
    // Neither component redefines the moved builders locally (they are shared).
    expect(cellMap).not.toMatch(/function\s+eligibleLayer\s*\(/);
    expect(cellPicker).not.toMatch(/function\s+eligibleLayer\s*\(/);
  });
});
