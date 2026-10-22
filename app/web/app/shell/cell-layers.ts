/**
 * cell-layers — shared presentation helpers for the interactive CellMap (S3-03a)
 * and the S3-06 scenario-comparison mini-map (CellPicker).
 *
 * These functions build the NSW boundary source + outside-NSW dimming mask and
 * the three engine-driven cell layers (eligible / excluded-environmental /
 * excluded-no-data), classify an excluded cell from its engine reason codes,
 * and clip the served cells to the NSW shape. They were extracted VERBATIM from
 * CellMap so BOTH maps share one definition and cannot drift: same layer ids,
 * colours, radii, opacity, ramp stops, filters, and geometry construction.
 *
 * Like {@link ./cell-geometry}, everything here is a PURE read of coordinates /
 * engine-produced properties already in memory — no network call, no decision
 * math (no scoring, ranking, normalisation or weight scaling), no
 * `.sort`/`.reduce` (so the scope-guard stays satisfied). The engine owns all
 * ranking and exclusion rules; these helpers only decide how to DRAW what the
 * engine already produced.
 */
import type { CellCollection, ExcludedRow } from "../api/decision-service";
import { NSW_BOUNDARY } from "./nsw-boundary";
import type {
  CircleLayerSpecification,
  ExpressionSpecification,
  FillLayerSpecification,
  LineLayerSpecification,
} from "maplibre-gl";

/** GeoJSON source id and the three circle layers (design §5.6). */
export const CELLS_SOURCE_ID = "cells";
export const EXCLUDED_NODATA_LAYER_ID = "cells-excluded-nodata";
export const EXCLUDED_ENV_LAYER_ID = "cells-excluded-env";
export const ELIGIBLE_LAYER_ID = "cells-eligible";

/**
 * The engine exclusion-rule code marking a cell as outside the wind-resource
 * data footprint. One member of {@link NODATA_CODES}; retained as a named
 * constant because it is the canonical "no wind value" marker. The code is the
 * engine's own `reason_codes` value from `get_exclusions` (S2-03/F16
 * vocabulary), carried through unchanged; nothing here invents a code or
 * re-evaluates a rule.
 */
const MISSING_WIND_CODE = "missing_wind_data";

/**
 * The set of engine reason codes that mark a cell as UNASSESSED for want of a
 * critical input value — a data-coverage gap, not an environmental rule-out.
 * A cell carrying only these codes was never judged on its merits (no wind,
 * no slope, or no demand value), so it must read as "not assessed", not as a
 * ruled-out site. `offshore_or_marine` is deliberately NOT here: it is a real
 * geographic rule-out (the cell is in the ocean), so it classes as
 * environmental, including when it co-occurs with a missing-data code on an
 * ocean cell. The codes are the engine's own F16 vocabulary, carried through
 * unchanged.
 */
const NODATA_CODES = new Set<string>([
  MISSING_WIND_CODE,
  "missing_slope_data",
  "missing_demand_data",
]);

/**
 * Per-cell exclusion class derived from the engine's `reason_codes` (NOT
 * recomputed): a cell whose reasons are ALL no-data codes is "nodata"
 * (unassessed — a data-coverage gap); any cell carrying at least one genuine
 * rule (protected area, slope threshold, urban, offshore/marine) is
 * "environmental" — a real rule-out. The derived class is written onto each
 * excluded Feature's `properties` as `exclusion_class` so the layers can
 * style the two honestly apart.
 */
export type ExclusionClass = "nodata" | "environmental";
export const EXCLUSION_CLASS_PROP = "exclusion_class";

/**
 * Classify one excluded cell from its engine reason codes. A cell is "nodata"
 * iff it has reasons AND every reason is a no-data code ({@link NODATA_CODES});
 * otherwise it is "environmental". So a slope/wind/demand-missing-only cell is
 * unassessed, while any genuine rule — or a dual-coded ocean cell carrying
 * `offshore_or_marine` alongside a missing-data code — classes as a rule-out.
 */
export function classifyExclusion(reasonCodes: string[]): ExclusionClass {
  const allNoData =
    reasonCodes.length > 0 &&
    reasonCodes.every((code) => NODATA_CODES.has(code));
  return allNoData ? "nodata" : "environmental";
}

/**
 * Join the engine's exclusion reasons onto the served cell GeoJSON, stamping
 * `exclusion_class` on every excluded Feature. This is a pure lookup keyed on
 * `cell_id` — no decision math, no reprojection: the classes come straight
 * from `get_exclusions` reason codes. Eligible features are left untouched.
 * Returns a NEW FeatureCollection (the served data is not mutated in place).
 */
export function withExclusionClasses(
  collection: CellCollection,
  exclusions: ExcludedRow[],
): CellCollection {
  const classByCell = new Map<string, ExclusionClass>();
  for (const row of exclusions) {
    classByCell.set(row.cell_id, classifyExclusion(row.reason_codes ?? []));
  }
  const features = (collection.features ?? []).map((feature) => {
    const properties = feature.properties;
    if (properties.eligible) return feature;
    const cls = classByCell.get(properties.cell_id) ?? "environmental";
    return {
      ...feature,
      properties: { ...properties, [EXCLUSION_CLASS_PROP]: cls },
    };
  });
  return { ...collection, features };
}

/**
 * The NSW boundary source and its two presentation-only layers (S3-03a). The
 * source carries two features — a dimming mask that greys everything OUTSIDE
 * NSW, and the NSW outline for the border line — tagged with `properties.kind`
 * so each layer filters to its own feature. Both are drawn BELOW the three cell
 * layers so cells and the border stay fully visible over the dimmed surround.
 */
export const NSW_SOURCE_ID = "nsw-boundary";
export const NSW_MASK_LAYER_ID = "nsw-mask";
export const NSW_BORDER_LAYER_ID = "nsw-border";

/**
 * The x-coordinates where one linear ring (an array of `[lng, lat]` vertices)
 * crosses the horizontal line at `lat`, using the standard ray-casting edge
 * test: an edge counts when its endpoints straddle `lat`, and the crossing is
 * interpolated along it. A point `[lng, lat]` is inside the ring exactly when
 * an ODD number of these crossings lie to its right (`lng < x`). Reads
 * coordinates only — no decision math — and uses plain `for` loops (never
 * `.reduce`/`.sort`) to satisfy the scope-guard.
 */
function ringCrossingsAt(lat: number, ring: number[][]): number[] {
  const crossings: number[] = [];
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const vi = ring[i];
    const vj = ring[j];
    if (!vi || !vj) continue;
    const xi = vi[0];
    const yi = vi[1];
    const xj = vj[0];
    const yj = vj[1];
    if (
      xi === undefined ||
      yi === undefined ||
      xj === undefined ||
      yj === undefined
    ) {
      continue;
    }
    if (yi > lat !== yj > lat) {
      crossings.push(((xj - xi) * (lat - yi)) / (yj - yi) + xi);
    }
  }
  return crossings;
}

/** True when an odd number of `crossings` lie strictly right of `lng`. */
function oddCrossingsRightOf(lng: number, crossings: number[]): boolean {
  let inside = false;
  for (let k = 0; k < crossings.length; k++) {
    const x = crossings[k];
    if (x !== undefined && lng < x) inside = !inside;
  }
  return inside;
}

/** One NSW polygon's ring crossings along a single latitude. */
interface PolygonRow {
  minLng: number;
  maxLng: number;
  outer: number[];
  holes: number[][];
}

/**
 * Bounding box `[minLng, minLat, maxLng, maxLat]` of each NSW polygon's outer
 * ring, built once on first use, so a latitude row only considers the
 * polygons it can pass through. Coordinate reads only.
 */
let polygonBboxes: [number, number, number, number][] | null = null;

function nswPolygonBboxes(): [number, number, number, number][] {
  if (polygonBboxes) return polygonBboxes;
  const boxes: [number, number, number, number][] = [];
  const polygons = NSW_BOUNDARY.coordinates;
  for (let p = 0; p < polygons.length; p++) {
    const outer = polygons[p]?.[0] ?? [];
    let minLng = Infinity;
    let minLat = Infinity;
    let maxLng = -Infinity;
    let maxLat = -Infinity;
    for (let v = 0; v < outer.length; v++) {
      const vertex = outer[v];
      const x = vertex?.[0];
      const y = vertex?.[1];
      if (x === undefined || y === undefined) continue;
      if (x < minLng) minLng = x;
      if (x > maxLng) maxLng = x;
      if (y < minLat) minLat = y;
      if (y > maxLat) maxLat = y;
    }
    boxes.push([minLng, minLat, maxLng, maxLat]);
  }
  polygonBboxes = boxes;
  return boxes;
}

/**
 * Ring crossings of every NSW polygon along each latitude seen so far, keyed by
 * that exact latitude. Grid cells in one row share a latitude, so the boundary
 * (~18.7k vertices) is walked once per ROW (~190 statewide) instead of once
 * per CELL (~47k) — what keeps the statewide clip fast (S4-02). The boundary
 * is static, so the cache is safe to keep across runs.
 */
const rowCache = new Map<number, PolygonRow[]>();

function nswRowAt(lat: number): PolygonRow[] {
  const cached = rowCache.get(lat);
  if (cached) return cached;
  const rows: PolygonRow[] = [];
  const polygons = NSW_BOUNDARY.coordinates;
  const boxes = nswPolygonBboxes();
  for (let p = 0; p < polygons.length; p++) {
    const polygon = polygons[p];
    const box = boxes[p];
    if (!polygon || !box || lat < box[1] || lat > box[3]) continue;
    const holes: number[][] = [];
    for (let h = 1; h < polygon.length; h++) {
      const hole = polygon[h];
      if (hole) holes.push(ringCrossingsAt(lat, hole));
    }
    rows.push({
      minLng: box[0],
      maxLng: box[2],
      outer: ringCrossingsAt(lat, polygon[0] ?? []),
      holes,
    });
  }
  rowCache.set(lat, rows);
  return rows;
}

/**
 * True when `[lng, lat]` falls inside the NSW MultiPolygon: inside a polygon's
 * outer ring (index 0) and not inside any of that polygon's holes. Considers
 * every polygon (so islands such as Lord Howe are included). The result is
 * identical to ray-casting each ring per point; the crossings are just shared
 * across a latitude row. Reads coordinates only — a geographic test, not
 * decision math.
 */
function pointInNsw(lng: number, lat: number): boolean {
  const rows = nswRowAt(lat);
  for (let r = 0; r < rows.length; r++) {
    const row = rows[r];
    if (!row || lng < row.minLng || lng > row.maxLng) continue;
    if (!oddCrossingsRightOf(lng, row.outer)) continue;
    let inHole = false;
    for (let h = 0; h < row.holes.length; h++) {
      const hole = row.holes[h];
      if (hole && oddCrossingsRightOf(lng, hole)) {
        inHole = true;
        break;
      }
    }
    if (!inHole) return true;
  }
  return false;
}

/**
 * Clip the served cells to the NSW shape: keep only Point features whose
 * coordinate falls inside the NSW MultiPolygon. A pure transform in the data
 * path (returns a NEW FeatureCollection; never mutates served data). It removes
 * features geographically only — it does not read, recompute, or change any
 * `eligible` / `suitability_score` / `exclusion_class` value, so the styling of
 * surviving cells is untouched. Uses `.filter` only (never `.reduce`/`.sort`).
 */
export function clipToNsw(collection: CellCollection): CellCollection {
  const features = (collection.features ?? []).filter((feature) => {
    const geometry = feature.geometry;
    if (geometry.type !== "Point") return false;
    const lng = geometry.coordinates[0];
    const lat = geometry.coordinates[1];
    if (lng === undefined || lat === undefined) return false;
    return pointInNsw(lng, lat);
  });
  return { ...collection, features };
}

/**
 * World bounding box used as the outer ring of the dimming mask (lon/lat). The
 * mask polygon fills this rectangle and cuts NSW out as holes, so everything
 * outside the NSW shape is dimmed while NSW itself stays clear.
 */
const WORLD_BBOX_RING: number[][] = [
  [-180, -85],
  [180, -85],
  [180, 85],
  [-180, 85],
  [-180, -85],
];

/**
 * Build the `nsw-boundary` source data once: a FeatureCollection carrying the
 * dimming-mask Polygon (world bbox with every NSW polygon's outer ring cut out
 * as a hole, including islands) tagged `kind: "mask"`, and the raw NSW
 * MultiPolygon tagged `kind: "border"` for the outline line. Interior holes
 * (lakes) of NSW polygons are not cut into the mask — a deliberate, negligible
 * simplification at state scale.
 */
export function nswBoundaryData(): GeoJSON.FeatureCollection {
  const maskRings: number[][][] = [WORLD_BBOX_RING];
  for (let p = 0; p < NSW_BOUNDARY.coordinates.length; p++) {
    const polygon = NSW_BOUNDARY.coordinates[p];
    const outer = polygon ? polygon[0] : undefined;
    if (outer) maskRings.push(outer);
  }
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: { kind: "mask" },
        geometry: { type: "Polygon", coordinates: maskRings },
      },
      {
        type: "Feature",
        properties: { kind: "border" },
        geometry: NSW_BOUNDARY,
      },
    ],
  };
}

/**
 * The outside-NSW dimming mask (bottom-most of the boundary layers): a
 * semi-transparent dark fill of the mask Polygon feature so everything beyond
 * the NSW shape reads as out of scope.
 */
export function nswMaskLayer(): FillLayerSpecification {
  return {
    id: NSW_MASK_LAYER_ID,
    type: "fill",
    source: NSW_SOURCE_ID,
    filter: ["==", ["get", "kind"], "mask"],
    paint: {
      "fill-color": "#0b1a2b",
      "fill-opacity": 0.35,
    },
  };
}

/**
 * The NSW border line tracing the state outline, drawn above the mask and below
 * the cell layers so the shape reads clearly without obscuring any cell.
 */
export function nswBorderLayer(): LineLayerSpecification {
  return {
    id: NSW_BORDER_LAYER_ID,
    type: "line",
    source: NSW_SOURCE_ID,
    filter: ["==", ["get", "kind"], "border"],
    paint: {
      "line-color": "#1f2a37",
      "line-width": 1,
    },
  };
}

/**
 * The eligible-cell colour ramp (S4-02): ColorBrewer "Reds", one hue getting
 * steadily darker from lower to higher suitability. It starts at a mid-light
 * salmon (not near-white) so the lowest-scoring eligible cell still reads as a
 * scored candidate against the basemap and the slate/grey excluded classes. One
 * colour per served quantile (`CellCollection.score_quantiles`).
 */
export const SCORE_RAMP = [
  "#fcbba1",
  "#fc9272",
  "#fb6a4a",
  "#ef3b2c",
  "#cb181d",
  "#a50f15",
  "#67000d",
] as const;

/** The ramp's two ends: lowest and highest eligible suitability. */
const LOWEST_SCORE_COLOUR = SCORE_RAMP[0];
const HIGHEST_SCORE_COLOUR = SCORE_RAMP[6];

/** One served colour-scale point: the eligible score at a probability. */
export interface ScoreQuantile {
  quantile: number;
  suitability_score: number;
}

/**
 * The colour stops `[score, colour]` for the eligible ramp: one per served
 * quantile, in the served (ascending) order, with ramp colours spread evenly
 * over the stops. A stop whose score does not exceed the previous one is
 * skipped (MapLibre needs strictly ascending inputs; ties happen when many
 * cells share a score). Falls back to the full 0–1 score range when no
 * quantiles are served. Presentation only: the engine's scores are read, never
 * changed, and no value is sorted or re-ranked.
 */
export function scoreColorStops(
  quantiles?: readonly ScoreQuantile[] | null,
): [number, string][] {
  const last = SCORE_RAMP.length - 1;
  if (!quantiles || quantiles.length === 0) {
    return [
      [0, LOWEST_SCORE_COLOUR],
      [1, HIGHEST_SCORE_COLOUR],
    ];
  }
  const stops: [number, string][] = [];
  const span = Math.max(quantiles.length - 1, 1);
  for (let i = 0; i < quantiles.length; i++) {
    const point = quantiles[i];
    if (!point) continue;
    const previous = stops[stops.length - 1];
    if (previous && point.suitability_score <= previous[0]) continue;
    const colour = SCORE_RAMP[Math.round((i * last) / span)] ?? HIGHEST_SCORE_COLOUR;
    stops.push([point.suitability_score, colour]);
  }
  return stops;
}

/**
 * The MapLibre `circle-color` expression for eligible cells: a continuous
 * linear interpolation of `suitability_score` through {@link scoreColorStops}.
 * A single usable stop (every eligible cell has the same score) collapses to
 * that stop's colour, since an interpolation needs distinct inputs.
 */
export function scoreColorExpression(
  quantiles?: readonly ScoreQuantile[] | null,
): ExpressionSpecification | string {
  const stops = scoreColorStops(quantiles);
  if (stops.length === 1) {
    return stops[0]?.[1] ?? HIGHEST_SCORE_COLOUR;
  }
  const expression: unknown[] = [
    "interpolate",
    ["linear"],
    ["get", "suitability_score"],
  ];
  for (const [score, colour] of stops) {
    expression.push(score, colour);
  }
  return expression as ExpressionSpecification;
}

/**
 * Circle radius (px) by zoom so each 0.05° cell is drawn about its true width
 * (S4-02). MapLibre's world is 512·2^z px wide, so a 0.05° cell is
 * ≈ 0.0711 × 2^z px wide; from zoom 7 up the radius is 0.0391 × 2^z ≈ 0.55 of
 * that width, doubling per zoom level, so neighbouring circles touch (cells are
 * taller than wide in Web Mercator) and the grid reads as a surface rather than
 * dots. Below zoom 7 it is floored so the statewide view stays readable instead
 * of sub-pixel. `scale` lets a layer draw smaller than a full cell.
 */
export function cellRadius(scale = 1): ExpressionSpecification {
  return [
    "interpolate",
    ["exponential", 2],
    ["zoom"],
    5,
    1.6 * scale,
    7,
    5.0 * scale,
    12,
    160.2 * scale,
  ];
}

/**
 * The faint "no data" layer (bottom): cells excluded ONLY because a critical
 * input value was missing (wind, slope, or demand) and so were never assessed
 * on merit. Statewide this class is now rare — a small residual pocket such as
 * the demand-less ACT enclave — rather than the old state-filling carpet.
 * Drawn palest so it reads as unassessed, not a rule-out. Filtered on the
 * engine-derived `exclusion_class` (design §5.6).
 *
 * The `sourceId` lets both maps feed their OWN cell source (CellMap uses
 * {@link CELLS_SOURCE_ID}, the picker its own id) WITHOUT changing any paint —
 * only the source binding differs, never the visual language.
 */
export function excludedNoDataLayer(
  sourceId: string = CELLS_SOURCE_ID,
): CircleLayerSpecification {
  return {
    id: EXCLUDED_NODATA_LAYER_ID,
    type: "circle",
    source: sourceId,
    filter: [
      "all",
      ["==", ["get", "eligible"], false],
      ["==", ["get", EXCLUSION_CLASS_PROP], "nodata"],
    ],
    paint: {
      "circle-color": "#c7ccd1",
      "circle-radius": cellRadius(0.8),
      "circle-opacity": ["interpolate", ["linear"], ["zoom"], 5, 0.12, 9, 0.3],
    },
  };
}

/**
 * The environmental-exclusion layer (middle): cells a genuine hard rule ruled
 * out (protected area, excessive slope, urban, offshore/marine). A distinct
 * slate/blue so a real rule-out is clearly NOT the same as "unassessed/no
 * data". Filtered on the engine-derived `exclusion_class` (design §5.6).
 */
export function excludedEnvLayer(
  sourceId: string = CELLS_SOURCE_ID,
): CircleLayerSpecification {
  return {
    id: EXCLUDED_ENV_LAYER_ID,
    type: "circle",
    source: sourceId,
    filter: [
      "all",
      ["==", ["get", "eligible"], false],
      ["==", ["get", EXCLUSION_CLASS_PROP], "environmental"],
    ],
    paint: {
      "circle-color": "#5b6b8c",
      "circle-radius": cellRadius(),
      "circle-opacity": ["interpolate", ["linear"], ["zoom"], 5, 0.7, 9, 0.85],
    },
  };
}

/**
 * The primary eligible layer (top): fully opaque, full-cell radius, colour a
 * continuous ramp over `suitability_score` (S4-02). The ramp's stops sit at the
 * served `score_quantiles` when given, so the real score distribution spreads
 * across the whole ramp; without them it spans 0–1. Because `eligible` is
 * defined as "score and rank both non-null", the eligible-only filter
 * guarantees the ramp never sees a null score — no fallback is needed (design
 * §5.6).
 */
export function eligibleLayer(
  sourceId: string = CELLS_SOURCE_ID,
  quantiles?: readonly ScoreQuantile[] | null,
): CircleLayerSpecification {
  return {
    id: ELIGIBLE_LAYER_ID,
    type: "circle",
    source: sourceId,
    filter: ["==", ["get", "eligible"], true],
    paint: {
      "circle-color": scoreColorExpression(quantiles),
      "circle-radius": cellRadius(),
      "circle-opacity": [
        "interpolate",
        ["linear"],
        ["zoom"],
        5,
        0.9,
        9,
        1,
      ],
    },
  };
}
