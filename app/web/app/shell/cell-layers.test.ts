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
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import type { CellCollection, ExcludedRow } from "../api/decision-service";
import { NSW_BOUNDARY } from "./nsw-boundary";
import {
  SCORE_RAMP,
  scoreColorExpression,
  scoreColorStops,
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

  it("drives the eligible colour from a suitability_score ramp spanning 0–1 when no quantiles are served", () => {
    const color = (eligibleLayer().paint as Record<string, unknown>)[
      "circle-color"
    ];
    expect(color).toEqual([
      "interpolate",
      ["linear"],
      ["get", "suitability_score"],
      0,
      "#fcbba1",
      1,
      "#67000d",
    ]);
  });

  it("places the ramp at the served quantiles when given (S4-02)", () => {
    const quantiles = [
      { quantile: 0, suitability_score: 0.42 },
      { quantile: 0.5, suitability_score: 0.72 },
      { quantile: 1, suitability_score: 0.92 },
    ];
    const color = (eligibleLayer(CELLS_SOURCE_ID, quantiles).paint as Record<string, unknown>)[
      "circle-color"
    ];
    // Three stops spread over the 7-colour ramp: first, middle, last colour.
    expect(color).toEqual([
      "interpolate",
      ["linear"],
      ["get", "suitability_score"],
      0.42,
      SCORE_RAMP[0],
      0.72,
      SCORE_RAMP[3],
      0.92,
      SCORE_RAMP[6],
    ]);
  });
});

describe("score colour stops (S4-02)", () => {
  it("keeps the ramp one hue, getting darker from low to high suitability", () => {
    // Lightness falls monotonically along the ramp (sequential encoding).
    const luminance = (hex: string): number => {
      const n = Number.parseInt(hex.slice(1), 16);
      const r = (n >> 16) & 255;
      const g = (n >> 8) & 255;
      const b = n & 255;
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    for (let i = 1; i < SCORE_RAMP.length; i++) {
      expect(luminance(SCORE_RAMP[i] as string)).toBeLessThan(
        luminance(SCORE_RAMP[i - 1] as string),
      );
    }
  });

  it("skips a quantile that ties the previous one (MapLibre needs ascending stops)", () => {
    const stops = scoreColorStops([
      { quantile: 0, suitability_score: 0.5 },
      { quantile: 0.1, suitability_score: 0.5 },
      { quantile: 0.25, suitability_score: 0.6 },
    ]);
    expect(stops.map(([score]) => score)).toEqual([0.5, 0.6]);
  });

  it("collapses to a single colour when every eligible cell has the same score", () => {
    expect(
      scoreColorExpression([
        { quantile: 0, suitability_score: 0.7 },
        { quantile: 1, suitability_score: 0.7 },
      ]),
    ).toBe(SCORE_RAMP[0]);
  });
});

/**
 * Reference point-in-NSW by ray-casting every ring for every point — the
 * original S3-03a algorithm. The fast row-cached clip must agree with it.
 */
function referenceInNsw(lng: number, lat: number): boolean {
  const inRing = (ring: number[][]): boolean => {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i] as [number, number];
      const [xj, yj] = ring[j] as [number, number];
      if (yi > lat !== yj > lat && lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) {
        inside = !inside;
      }
    }
    return inside;
  };
  for (const polygon of NSW_BOUNDARY.coordinates) {
    if (!inRing(polygon[0] as number[][])) continue;
    if (!polygon.slice(1).some((hole) => inRing(hole as number[][]))) return true;
  }
  return false;
}

function pointCollection(points: [number, number][]): CellCollection {
  return {
    type: "FeatureCollection",
    run_id: "run-clip",
    features: points.map(([lng, lat], i) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [lng, lat] },
      properties: { cell_id: `p${i}`, eligible: true, suitability_score: 0.5, rank: i + 1 },
    })),
  } as CellCollection;
}

describe("clipToNsw performance rewrite (S4-02)", () => {
  it("keeps exactly the points the reference ray-cast keeps", () => {
    // A 0.05° lattice over the whole NSW bbox (borders, coast, ACT hole) plus
    // Lord Howe Island, so every polygon/hole path is exercised.
    const points: [number, number][] = [];
    for (let lat = -37.6; lat <= -28.0; lat += 0.13) {
      for (let lng = 140.9; lng <= 153.7; lng += 0.11) {
        points.push([lng, lat]);
      }
    }
    points.push([159.08, -31.55], [149.13, -35.28], [149.0, -35.4]);
    const kept = new Set(
      (clipToNsw(pointCollection(points)).features ?? []).map((f) => f.properties.cell_id),
    );
    const expected = new Set(
      points.flatMap(([lng, lat], i) => (referenceInNsw(lng, lat) ? [`p${i}`] : [])),
    );
    expect(kept).toEqual(expected);
    expect(expected.size).toBeGreaterThan(1000);
  });

  const SCORED_CSV = join(
    __dirname,
    "../../../../DATA/scoring/optmining_suitability-score_2026_nsw.csv",
  );
  const realGrid = existsSync(SCORED_CSV) ? it : it.skip;

  realGrid("clips the full ~47k-cell baseline grid quickly and keeps every top-ranked cell", () => {
    const lines = readFileSync(SCORED_CSV, "utf8").trim().split("\n");
    const header = (lines[0] ?? "").split(",");
    const col = (name: string) => header.indexOf(name);
    const collection = {
      type: "FeatureCollection",
      run_id: "baseline",
      features: lines.slice(1).map((line) => {
        const cells = line.split(",");
        const rank = cells[col("rank")] ? Number(cells[col("rank")]) : null;
        return {
          type: "Feature",
          geometry: {
            type: "Point",
            coordinates: [Number(cells[col("centroid_lon")]), Number(cells[col("centroid_lat")])],
          },
          properties: { cell_id: cells[col("cell_id")], eligible: rank !== null, suitability_score: null, rank },
        };
      }),
    } as unknown as CellCollection;
    expect(collection.features?.length).toBeGreaterThan(40000);

    const started = performance.now();
    const clipped = clipToNsw(collection);
    const elapsed = performance.now() - started;

    // The S3-03a per-cell ray cast took ~2 s here; the row cache must keep a
    // statewide redraw well under a second on the main thread.
    expect(elapsed).toBeLessThan(750);
    // Map ≡ shortlist (AC6): no cell the shortlist can show is clipped away.
    const kept = new Set((clipped.features ?? []).map((f) => f.properties.cell_id));
    const topRanked = (collection.features ?? []).filter(
      (f) => f.properties.rank !== null && (f.properties.rank ?? Infinity) <= 100,
    );
    expect(topRanked).toHaveLength(100);
    for (const feature of topRanked) {
      expect(kept.has(feature.properties.cell_id)).toBe(true);
    }
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
