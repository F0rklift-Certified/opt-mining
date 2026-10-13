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
 * Ray-casting point-in-polygon over one linear ring (an array of `[lng, lat]`
 * vertices). Reads coordinates only — no decision math — so the geographic clip
 * stays inside the decision-free rule. A plain `for` loop (never `.reduce`) to
 * satisfy the scope-guard. Returns true when the point lies inside the ring.
 */
function pointInRing(lng: number, lat: number, ring: number[][]): boolean {
  let inside = false;
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
    const intersects =
      yi > lat !== yj > lat &&
      lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi;
    if (intersects) inside = !inside;
  }
  return inside;
}

/**
 * True when `[lng, lat]` falls inside the NSW MultiPolygon: inside a polygon's
 * outer ring (index 0) and not inside any of that polygon's holes. Iterates all
 * polygons/rings (so islands such as Lord Howe are included). Reads coordinates
 * only — this is a geographic test, not decision math.
 */
function pointInNsw(lng: number, lat: number): boolean {
  const polygons = NSW_BOUNDARY.coordinates;
  for (let p = 0; p < polygons.length; p++) {
    const polygon = polygons[p];
    if (!polygon) continue;
    const outer = polygon[0];
    if (!outer || !pointInRing(lng, lat, outer)) continue;
    let inHole = false;
    for (let h = 1; h < polygon.length; h++) {
      const hole = polygon[h];
      if (hole && pointInRing(lng, lat, hole)) {
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
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 1.5, 9, 4],
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
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 2, 9, 5],
      "circle-opacity": ["interpolate", ["linear"], ["zoom"], 5, 0.5, 9, 0.75],
    },
  };
}

/**
 * The primary eligible layer (top): fully opaque, larger radius, colour a
 * data-driven ramp over `suitability_score`. Because `eligible` is defined as
 * "score and rank both non-null", the eligible-only filter guarantees the ramp
 * never sees a null score — no fallback is needed (design §5.6).
 */
export function eligibleLayer(
  sourceId: string = CELLS_SOURCE_ID,
): CircleLayerSpecification {
  return {
    id: ELIGIBLE_LAYER_ID,
    type: "circle",
    source: sourceId,
    filter: ["==", ["get", "eligible"], true],
    paint: {
      "circle-color": [
        "interpolate",
        ["linear"],
        ["get", "suitability_score"],
        0,
        "#fee5d9",
        0.5,
        "#fb6a4a",
        1,
        "#a50f15",
      ],
      "circle-radius": [
        "interpolate",
        ["linear"],
        ["zoom"],
        5,
        2.5,
        9,
        7,
      ],
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
