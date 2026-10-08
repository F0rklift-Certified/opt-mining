"use client";

/**
 * CellMap — the interactive-map region body (S3-03a).
 *
 * Drives a `maplibregl.Map` imperatively (MapLibre is not React-rendered) and
 * paints the currently-loaded Run's cells over an env-driven basemap. The
 * component fetches nothing on its own beyond `service.getRunCells`; all browser
 * HTTP stays in the single integration point (`app/api/decision-service.ts`).
 *
 * No decision math and no reprojection happen here (design §5.7): the served
 * GeoJSON is handed to MapLibre unmodified, and every style expression reads only
 * the engine-produced `eligible` / `suitability_score` properties. There is no
 * coordinate transform and no `cell_id` parsing anywhere in this component.
 *
 * Lifecycle (design §5.3) is a single ordered path with four single-purpose
 * refs/state, none overlapping:
 *   - `mapRef`         — the Map instance.
 *   - `mapReady`       — state boolean; the ONLY gate on calling `setData`.
 *   - `pendingDataRef` — replay buffer for data that arrived before load.
 *   - `requestIdRef`   — monotonic counter; the ONLY staleness guard.
 */
import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import type {
  GeoJSONSource,
  Map as MapLibreMap,
  StyleSpecification,
} from "maplibre-gl";

import {
  DecisionServiceError,
  type CellCollection,
  type CellSelection,
  type DecisionService,
  type ExcludedRow,
} from "../api/decision-service";
import { NSW_BOUNDARY } from "./nsw-boundary";

export interface CellMapProps {
  /** `engine.run.run_id` for the currently-loaded run, or null when none. */
  runId: string | null;
  /** The shared typed client (single integration point). */
  service: DecisionService;
  /**
   * Surfaced when a cell is clicked, carrying the clicked feature's own
   * properties as a {@link CellSelection} (S3-03b). Optional — the map renders
   * and the lifecycle runs unchanged when no handler is wired.
   */
  onSelectCell?: (selection: CellSelection) => void;
}

/** GeoJSON source id and the three circle layers (design §5.6). */
const SOURCE_ID = "cells";
const EXCLUDED_NODATA_LAYER_ID = "cells-excluded-nodata";
const EXCLUDED_ENV_LAYER_ID = "cells-excluded-env";
const ELIGIBLE_LAYER_ID = "cells-eligible";

/**
 * The two highlight sources and their outline layers (S3-03b). Each source
 * holds either an empty FeatureCollection or one square-ring Polygon built
 * around a cell's point, traced by a `line` layer so the square reads as an
 * outline, not a fill. Both are drawn ABOVE every cell layer so a highlight is
 * never hidden behind a cell.
 *
 *   - SELECTED: set on CLICK and PERSISTS — the black box stays on the cell you
 *     selected until you click another cell (or the run changes). Drawn on top.
 *   - HOVER: follows the pointer on `mousemove` and is cleared on `mouseleave`,
 *     so it is only a transient affordance under the cursor. Drawn beneath the
 *     selected box so the persistent selection always reads clearly.
 */
const SELECTED_SOURCE_ID = "cell-selected";
const SELECTED_LAYER_ID = "cell-selected-outline";
const HOVER_SOURCE_ID = "cell-hover";
const HOVER_LAYER_ID = "cell-hover-outline";

/**
 * Half-width (in degrees) of the highlight square around a cell's point. The
 * analysis grid is ~5 km, i.e. roughly 0.045° of latitude; half of that frames
 * one cell snugly without overlapping its neighbours. A fixed geographic size
 * (not pixel-based) so the square tracks the cell as the map zooms. A geometric
 * presentation value only — no decision math.
 */
const SELECTION_HALF_DEG = 0.0225;

/**
 * Build a highlight source's data from a cell's point, or an empty
 * FeatureCollection when there is no point. The square is a closed ring centred
 * on `[lng, lat]`, inset by {@link SELECTION_HALF_DEG} on each side. A pure
 * geometric read of coordinates already in memory — no decision math, no
 * network call. Returns a NEW object each call (never mutates shared state).
 */
function selectionSquareData(
  point: [number, number] | null,
): GeoJSON.FeatureCollection {
  if (!point) {
    return { type: "FeatureCollection", features: [] };
  }
  const lng = point[0];
  const lat = point[1];
  const d = SELECTION_HALF_DEG;
  const ring: number[][] = [
    [lng - d, lat - d],
    [lng + d, lat - d],
    [lng + d, lat + d],
    [lng - d, lat + d],
    [lng - d, lat - d],
  ];
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {},
        geometry: { type: "Polygon", coordinates: [ring] },
      },
    ],
  };
}

/**
 * Find the cell centre whose highlight square CONTAINS the cursor `[lng, lat]`,
 * or null when the cursor is inside no cell's square. "Inside the square" means
 * within {@link SELECTION_HALF_DEG} of a centre on BOTH axes — the same box the
 * outline draws — so the hover box appears whenever the pointer is anywhere in
 * a cell's footprint, not only over its small circle. When squares of adjacent
 * centres overlap the cursor, the nearest centre (by Chebyshev distance) wins,
 * so exactly one cell is highlighted. A pure geometric read of coordinates
 * already in memory — no decision math; a plain `for` loop (never `.reduce`).
 */
function cellSquareContaining(
  lng: number,
  lat: number,
  centers: [number, number][],
): [number, number] | null {
  const d = SELECTION_HALF_DEG;
  let best: [number, number] | null = null;
  let bestDist = Infinity;
  for (let i = 0; i < centers.length; i++) {
    const center = centers[i];
    if (!center) continue;
    const dx = Math.abs(lng - center[0]);
    const dy = Math.abs(lat - center[1]);
    if (dx > d || dy > d) continue; // cursor outside this cell's square
    const dist = Math.max(dx, dy);
    if (dist < bestDist) {
      bestDist = dist;
      best = center;
    }
  }
  return best;
}

/**
 * The persistent SELECTED-cell outline (top-most): a solid black box tracing
 * the square around the clicked cell. Stays until another cell is clicked.
 */
function selectedLayer(): maplibregl.LineLayerSpecification {
  return {
    id: SELECTED_LAYER_ID,
    type: "line",
    source: SELECTED_SOURCE_ID,
    paint: {
      "line-color": "#111827",
      "line-width": 2.5,
    },
  };
}

/**
 * The transient HOVER outline: a thinner, lighter box around the cell under the
 * pointer, drawn beneath the selected box so the persistent selection wins.
 */
function hoverLayer(): maplibregl.LineLayerSpecification {
  return {
    id: HOVER_LAYER_ID,
    type: "line",
    source: HOVER_SOURCE_ID,
    paint: {
      "line-color": "#374151",
      "line-width": 1.5,
      "line-dasharray": [2, 1],
    },
  };
}

/**
 * The three cell layers click/hover handling is scoped to (S3-03b): every
 * class of cell — eligible, environmental rule-out, unassessed no-data — can be
 * inspected, so an excluded cell surfaces a selection too (its score/rank null).
 */
const CELL_LAYER_IDS = [
  ELIGIBLE_LAYER_ID,
  EXCLUDED_ENV_LAYER_ID,
  EXCLUDED_NODATA_LAYER_ID,
];

/**
 * Build the stable {@link CellSelection} from a clicked feature's own
 * `properties` (S3-03b). A pure read of the engine-produced values already in
 * memory — no decision math, no network call: `suitability_score` / `rank` fall
 * back to null for an excluded cell, exactly as the contract specifies.
 */
function selectionFromProperties(
  properties: {
    cell_id: string;
    eligible: boolean;
    suitability_score?: number | null;
    rank?: number | null;
  },
): CellSelection {
  return {
    cell_id: properties.cell_id,
    eligible: properties.eligible,
    suitability_score: properties.suitability_score ?? null,
    rank: properties.rank ?? null,
  };
}

/**
 * The engine exclusion-rule code marking a cell as outside the wind-resource
 * data footprint. One member of {@link NODATA_CODES}; retained as a named
 * constant because it is the canonical "no wind value" marker referenced in
 * the component's documentation. The code is the engine's own `reason_codes`
 * value from `get_exclusions` (S2-03/F16 vocabulary), carried through
 * unchanged; this component invents no code and re-evaluates no rule.
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
type ExclusionClass = "nodata" | "environmental";
const EXCLUSION_CLASS_PROP = "exclusion_class";

/**
 * Classify one excluded cell from its engine reason codes. A cell is "nodata"
 * iff it has reasons AND every reason is a no-data code ({@link NODATA_CODES});
 * otherwise it is "environmental". So a slope/wind/demand-missing-only cell is
 * unassessed, while any genuine rule — or a dual-coded ocean cell carrying
 * `offshore_or_marine` alongside a missing-data code — classes as a rule-out.
 */
function classifyExclusion(reasonCodes: string[]): ExclusionClass {
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
function withExclusionClasses(
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
const NSW_SOURCE_ID = "nsw-boundary";
const NSW_MASK_LAYER_ID = "nsw-mask";
const NSW_BORDER_LAYER_ID = "nsw-border";

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
function clipToNsw(collection: CellCollection): CellCollection {
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
 * Extract the `[lng, lat]` centre of every Point feature in a cell collection.
 * Used to seed the hover test (which cell's square contains the cursor) off the
 * same clipped data the map draws. A pure coordinate read — no decision math; a
 * plain `for` loop, never `.reduce`/`.sort`.
 */
function cellCenters(collection: CellCollection): [number, number][] {
  const centers: [number, number][] = [];
  const features = collection.features ?? [];
  for (let i = 0; i < features.length; i++) {
    const geometry = features[i]?.geometry;
    if (geometry?.type !== "Point") continue;
    const lng = geometry.coordinates[0];
    const lat = geometry.coordinates[1];
    if (lng !== undefined && lat !== undefined) centers.push([lng, lat]);
  }
  return centers;
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
function nswBoundaryData(): GeoJSON.FeatureCollection {
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
function nswMaskLayer(): maplibregl.FillLayerSpecification {
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
function nswBorderLayer(): maplibregl.LineLayerSpecification {
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
 * Required OSM attribution for the public basemap (design §5.1). The default
 * tile URL itself is NOT baked into source — it lives in `.env.example` and
 * flows in via NEXT_PUBLIC_BASEMAP_TILE_URL, per the project's "no host literal
 * in source" rule (app README; enforced by the scope-guard test).
 */
const OSM_ATTRIBUTION = "© OpenStreetMap contributors";

/** NSW-framed initial view (whole-state overview). */
const NSW_CENTER: [number, number] = [147.0, -32.5];
const NSW_ZOOM = 5;

/**
 * Minimal inline raster style driven by NEXT_PUBLIC_BASEMAP_TILE_URL (design
 * §5.1). The basemap is context only: when the env var is unset the style has
 * no raster source and the cell layer renders over MapLibre's empty background
 * (non-blocking, graceful degradation).
 */
function basemapStyle(): StyleSpecification {
  const tileUrl = process.env.NEXT_PUBLIC_BASEMAP_TILE_URL?.trim();
  if (!tileUrl) {
    return { version: 8, sources: {}, layers: [] };
  }
  return {
    version: 8,
    sources: {
      basemap: {
        type: "raster",
        tiles: [tileUrl],
        tileSize: 256,
        attribution: OSM_ATTRIBUTION,
      },
    },
    layers: [{ id: "basemap", type: "raster", source: "basemap" }],
  };
}

/**
 * The faint "no data" layer (bottom): cells excluded ONLY because a critical
 * input value was missing (wind, slope, or demand) and so were never assessed
 * on merit. Statewide this class is now rare — a small residual pocket such as
 * the demand-less ACT enclave — rather than the old state-filling carpet.
 * Drawn palest so it reads as unassessed, not a rule-out. Filtered on the
 * engine-derived `exclusion_class` (design §5.6).
 */
function excludedNoDataLayer(): maplibregl.CircleLayerSpecification {
  return {
    id: EXCLUDED_NODATA_LAYER_ID,
    type: "circle",
    source: SOURCE_ID,
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
function excludedEnvLayer(): maplibregl.CircleLayerSpecification {
  return {
    id: EXCLUDED_ENV_LAYER_ID,
    type: "circle",
    source: SOURCE_ID,
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
function eligibleLayer(): maplibregl.CircleLayerSpecification {
  return {
    id: ELIGIBLE_LAYER_ID,
    type: "circle",
    source: SOURCE_ID,
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

/** Render one labelled status line (loading / no-run / error). */
function statusText(runId: string | null, loading: boolean, error: string | null) {
  if (error) {
    return (
      <p className="om-map__status" role="alert">
        Map data unavailable: {error}
      </p>
    );
  }
  if (runId === null) {
    return <p className="om-map__status">No run is loaded.</p>;
  }
  if (loading) {
    return <p className="om-map__status">Loading cells…</p>;
  }
  return null;
}

/** The interactive-map region body: a MapLibre map of the Run's cells. */
export default function CellMap({ runId, service, onSelectCell }: CellMapProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const pendingDataRef = useRef<CellCollection | null>(null);
  const requestIdRef = useRef(0);
  // The run currently fetched; prevents a `mapReady` re-run from refetching.
  const fetchedRunRef = useRef<string | null>(null);
  // The latest selection callback, held in a ref so the once-run `load` handler
  // (registered in a mount-only effect) always invokes the current prop without
  // the mount effect depending on it — keeping the S3-03a lifecycle untouched.
  const onSelectCellRef = useRef<CellMapProps["onSelectCell"]>(onSelectCell);
  onSelectCellRef.current = onSelectCell;
  // Paints/clears the PERSISTENT selected-cell square from the click handler.
  // Set in the load handler once the source exists; a stable ref so the
  // mount-only effect never depends on it. `null` clears the box.
  const setSelectedSquareRef = useRef<(point: [number, number] | null) => void>(
    () => {},
  );
  // Paints/clears the TRANSIENT hover square from the mousemove/leave handlers.
  const setHoverSquareRef = useRef<(point: [number, number] | null) => void>(
    () => {},
  );
  // The current run's cell centre points, kept so the map-wide mousemove can
  // test whether the cursor is INSIDE a cell's square (not just over its
  // circle) and draw the hover box there. Refreshed whenever cell data is
  // applied; emptied on run change. A ref so the mount-only handler reads the
  // latest centres without the effect depending on them.
  const cellCentersRef = useRef<[number, number][]>([]);
  const [mapReady, setMapReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Mount effect: create the map once; tear it down on unmount.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const map = new maplibregl.Map({
      container,
      style: basemapStyle(),
      center: NSW_CENTER,
      zoom: NSW_ZOOM,
      // An options object enables the AttributionControl (which surfaces the
      // required OSM attribution); `true` is not a valid value in maplibre 4.x.
      attributionControl: {},
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl());

    map.on("load", () => {
      // The NSW boundary source + its mask/border layers are added FIRST so the
      // cell layers below draw on top of them (dimmed surround, traced border).
      map.addSource(NSW_SOURCE_ID, {
        type: "geojson",
        data: nswBoundaryData(),
      });
      map.addLayer(nswMaskLayer());
      map.addLayer(nswBorderLayer());
      map.addSource(SOURCE_ID, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      // Draw order (bottom -> top): faint no-data carpet, then the genuine
      // environmental rule-outs, then the eligible score layer on top.
      map.addLayer(excludedNoDataLayer());
      map.addLayer(excludedEnvLayer());
      map.addLayer(eligibleLayer());
      // The two highlight sources + their outline layers go on top of every
      // cell layer so neither box is obscured. The hover box is added first so
      // the persistent selected box draws above it.
      map.addSource(HOVER_SOURCE_ID, {
        type: "geojson",
        data: selectionSquareData(null),
      });
      map.addLayer(hoverLayer());
      map.addSource(SELECTED_SOURCE_ID, {
        type: "geojson",
        data: selectionSquareData(null),
      });
      map.addLayer(selectedLayer());
      // Expose setters the handlers use to paint/clear each box. The sources
      // exist from here on, so these never race their layers.
      setSelectedSquareRef.current = (point: [number, number] | null) => {
        (map.getSource(SELECTED_SOURCE_ID) as GeoJSONSource | undefined)?.setData(
          selectionSquareData(point),
        );
      };
      setHoverSquareRef.current = (point: [number, number] | null) => {
        (map.getSource(HOVER_SOURCE_ID) as GeoJSONSource | undefined)?.setData(
          selectionSquareData(point),
        );
      };
      // Click-to-inspect (S3-03b): scope click handling to the three cell
      // layers so any cell — eligible or excluded — surfaces a selection. The
      // handler reads the clicked feature's own `properties` (already in
      // memory) and invokes the current `onSelectCell`; no network call, no
      // decision math. The CLICK also pins the persistent black box onto the
      // clicked cell, where it STAYS until another cell is clicked.
      for (const layerId of CELL_LAYER_IDS) {
        map.on("click", layerId, (event: maplibregl.MapLayerMouseEvent) => {
          const feature = event.features?.[0];
          const properties = feature?.properties;
          if (!properties) return;
          // Pin the persistent box onto the clicked cell's own point.
          const geometry = feature?.geometry;
          if (geometry?.type === "Point") {
            const lng = geometry.coordinates[0];
            const lat = geometry.coordinates[1];
            if (lng !== undefined && lat !== undefined) {
              setSelectedSquareRef.current([lng, lat]);
            }
          }
          onSelectCellRef.current?.(
            selectionFromProperties(
              properties as Parameters<typeof selectionFromProperties>[0],
            ),
          );
        });
      }

      // The HOVER box follows the pointer based on the SQUARE footprint, not
      // the small circle: a map-wide `mousemove` snaps the cursor to the cell
      // whose square contains it (via `cellSquareContaining`) and draws the box
      // there, so the box appears whenever the pointer is anywhere inside a
      // cell's square — not only directly over its dot. When the cursor is
      // inside no cell's square the box clears. The pointer cursor mirrors the
      // same test. The pinned selected box is untouched by hover.
      map.on("mousemove", (event: maplibregl.MapMouseEvent) => {
        const center = cellSquareContaining(
          event.lngLat.lng,
          event.lngLat.lat,
          cellCentersRef.current,
        );
        setHoverSquareRef.current(center);
        map.getCanvas().style.cursor = center ? "pointer" : "";
      });
      // Clear the hover box when the pointer leaves the map canvas entirely.
      map.on("mouseout", () => {
        setHoverSquareRef.current(null);
        map.getCanvas().style.cursor = "";
      });
      setMapReady(true);
      const pending = pendingDataRef.current;
      if (pending) {
        (map.getSource(SOURCE_ID) as GeoJSONSource | undefined)?.setData(
          pending as unknown as GeoJSON.FeatureCollection,
        );
        // Seed the hover-containment test off the replayed cells.
        cellCentersRef.current = cellCenters(pending);
        pendingDataRef.current = null;
      }
    });

    return () => {
      mapRef.current = null;
      map.remove();
    };
  }, []);

  // Data effect (design §5.3), keyed [runId, service, mapReady]. The fetch is
  // issued once per run (guarded by fetchedRunRef) so a later `mapReady` flip
  // re-runs the effect to replay any pending data via setData without a second
  // network call; `requestIdRef` drops stale responses when the run changes.
  useEffect(() => {
    if (runId === null) {
      setLoading(false);
      setError(null);
      return;
    }

    // The effect re-ran but the run is unchanged (e.g. `mapReady` just flipped):
    // don't refetch — flush any buffered data now that the source may exist.
    if (fetchedRunRef.current === runId) {
      const map = mapRef.current;
      const source = map?.getSource(SOURCE_ID) as GeoJSONSource | undefined;
      const pending = pendingDataRef.current;
      if (mapReady && source && pending) {
        source.setData(pending as unknown as GeoJSON.FeatureCollection);
        // Seed the hover-containment test off the replayed cells.
        cellCentersRef.current = cellCenters(pending);
        pendingDataRef.current = null;
      }
      return;
    }

    fetchedRunRef.current = runId;
    const myId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    // A new run supersedes any prior selection: clear both highlight boxes and
    // the hover-containment centres so a stale square never lingers over a cell
    // that belongs to the previous run.
    setSelectedSquareRef.current(null);
    setHoverSquareRef.current(null);
    cellCentersRef.current = [];

    // `requestIdRef` is the single staleness guard (design §5.3): a response is
    // dropped iff a newer run has superseded it. The effect does not use a
    // separate "active" flag, so a `mapReady` re-run of the same run does not
    // cancel the in-flight fetch for that run.
    //
    // The cells layer is the required data path; the exclusions call enriches
    // it with the per-cell exclusion class (no-data vs environmental). The
    // exclusions fetch is best-effort: if it is unavailable or fails, the cells
    // still render (every excluded cell then falls back to the environmental
    // style), so the map never fails for want of the enrichment.
    Promise.all([
      service.getRunCells(runId),
      Promise.resolve()
        .then(() => service.getExclusions?.(runId) ?? [])
        .catch(() => [] as ExcludedRow[]),
    ])
      .then(([cells, exclusions]) => {
        if (myId !== requestIdRef.current) return; // stale run superseded
        // Enrich with exclusion classes, then clip the drawn cells to the NSW
        // shape (presentation-only: removes out-of-state features geographically
        // without touching any surviving cell's styling values).
        const collection = clipToNsw(withExclusionClasses(cells, exclusions));
        // The "cells" source exists iff the load handler has run (it adds the
        // source and sets mapReady together), so source presence is the live
        // readiness signal — robust to the mapReady value captured at effect
        // creation. If the map is not yet ready, buffer for the load handler.
        const map = mapRef.current;
        const source = map?.getSource(SOURCE_ID) as GeoJSONSource | undefined;
        if (source) {
          source.setData(collection as unknown as GeoJSON.FeatureCollection);
          // Seed the hover-containment test off the just-drawn cells.
          cellCentersRef.current = cellCenters(collection);
          pendingDataRef.current = null;
        } else {
          pendingDataRef.current = collection;
        }
        setLoading(false);
      })
      .catch((reason: unknown) => {
        if (myId !== requestIdRef.current) return;
        const message =
          reason instanceof DecisionServiceError || reason instanceof Error
            ? reason.message
            : "Unexpected service error.";
        setError(message);
        setLoading(false);
      });
  }, [runId, service, mapReady]);

  return (
    <div>
      <div ref={containerRef} className="om-map" aria-label="Interactive cell map" />
      {statusText(runId, loading, error)}
      <MapLegend />
    </div>
  );
}

/**
 * A static legend naming the three cell classes the layers paint, so the
 * statewide (NSW-wide) map is read honestly: eligible candidates vs genuine
 * environmental rule-outs vs the few cells left unassessed for want of a
 * critical input value. The swatch colours mirror the layer paint above.
 */
function MapLegend(): JSX.Element {
  return (
    <ul className="om-map__legend" aria-label="Map legend">
      <li>
        <span
          className="om-map__swatch om-map__swatch--eligible"
          aria-hidden="true"
        />
        Eligible candidate (shade = suitability score)
      </li>
      <li>
        <span
          className="om-map__swatch om-map__swatch--env"
          aria-hidden="true"
        />
        Excluded — environmental rule (protected area, slope, urban, offshore)
      </li>
      <li>
        <span
          className="om-map__swatch om-map__swatch--nodata"
          aria-hidden="true"
        />
        Not assessed — missing input data (e.g. no demand value)
      </li>
    </ul>
  );
}
