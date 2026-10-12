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
import { cellCenters } from "./cell-geometry";
import {
  CELLS_SOURCE_ID as SOURCE_ID,
  EXCLUDED_NODATA_LAYER_ID,
  EXCLUDED_ENV_LAYER_ID,
  ELIGIBLE_LAYER_ID,
  NSW_SOURCE_ID,
  NSW_MASK_LAYER_ID,
  NSW_BORDER_LAYER_ID,
  clipToNsw,
  withExclusionClasses,
  nswBoundaryData,
  nswMaskLayer,
  nswBorderLayer,
  excludedNoDataLayer,
  excludedEnvLayer,
  eligibleLayer,
} from "./cell-layers";

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
