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
import { CELL_SIZE_DEG, cellGridIndex, type CellGridIndex } from "./cell-geometry";
import {
  CELLS_SOURCE_ID as SOURCE_ID,
  EXCLUDED_NODATA_LAYER_ID,
  EXCLUDED_ENV_LAYER_ID,
  ELIGIBLE_LAYER_ID,
  NSW_SOURCE_ID,
  NSW_MASK_LAYER_ID,
  NSW_BORDER_LAYER_ID,
  SCORE_RAMP,
  type ScoreQuantile,
  clipToNsw,
  withExclusionClasses,
  nswBoundaryData,
  nswMaskLayer,
  nswBorderLayer,
  excludedNoDataLayer,
  excludedEnvLayer,
  eligibleLayer,
  scoreColorExpression,
  scoreColorStops,
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
  /**
   * The app-wide selected cell for THIS run (S4-02), or null for none. When it
   * changes — a shortlist pick, the automatic rank-1 pick after a run, or a map
   * click echoed back — the persistent selected box moves to that cell, so the
   * map and the shortlist always show the same selection. Omitted: the box
   * only follows map clicks (S3-03b behaviour).
   */
  selectedCellId?: string | null;
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
 * Half-width (in degrees) of the highlight square around a cell's point: half
 * the 0.05° grid spacing, so the square is exactly one cell's footprint and
 * adjacent squares meet edge to edge. A fixed geographic size (not pixel-based)
 * so the square tracks the cell as the map zooms. A geometric presentation
 * value only — no decision math.
 */
const SELECTION_HALF_DEG = CELL_SIZE_DEG / 2;

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
 * Pan/zoom limits (S4-02): the view can't drift far from NSW (Lord Howe Island
 * stays reachable) or zoom out past the whole-state overview, and stops at the
 * zoom where one 0.05° cell is ~150 px wide — closer adds no information.
 */
const NSW_MAX_BOUNDS: [[number, number], [number, number]] = [
  [136.0, -40.5],
  [162.0, -25.0],
];
const MIN_ZOOM = 4.5;
const MAX_ZOOM = 12;

/**
 * Hand a run's cells to the map: replace the cell source's data and re-place
 * the eligible colour stops at this run's served `score_quantiles`. The data is
 * passed through unmodified; only the styling expression is rebuilt.
 */
function paintCells(map: MapLibreMap, collection: CellCollection): void {
  (map.getSource(SOURCE_ID) as GeoJSONSource | undefined)?.setData(
    collection as unknown as GeoJSON.FeatureCollection,
  );
  map.setPaintProperty(
    ELIGIBLE_LAYER_ID,
    "circle-color",
    scoreColorExpression(collection.score_quantiles),
  );
}

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
export default function CellMap({
  runId,
  service,
  onSelectCell,
  selectedCellId,
}: CellMapProps): JSX.Element {
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
  // The current run's cells indexed by grid slot and cell_id, so the map-wide
  // mousemove can find the cell whose SQUARE holds the cursor (not just its
  // circle) and the selection effect can find a selected cell's centre, both in
  // constant time. Rebuilt whenever cell data is applied; null on run change. A
  // ref so the mount-only handler reads the latest index without depending on it.
  const cellIndexRef = useRef<CellGridIndex | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The applied run's colour-scale points (drive the legend), and a counter
  // bumped each time cells are applied so the selection effect re-pins the
  // selected box once the selected cell's coordinates are known.
  const [scoreQuantiles, setScoreQuantiles] = useState<ScoreQuantile[]>([]);
  const [cellsVersion, setCellsVersion] = useState(0);
  // Records what was just applied: the index for lookups, the legend scale,
  // and the version bump. Only refs and state setters — stable across renders.
  const cellsAppliedRef = useRef((collection: CellCollection) => {
    cellIndexRef.current = cellGridIndex(collection);
    setScoreQuantiles(collection.score_quantiles ?? []);
    setCellsVersion((version) => version + 1);
  });

  // Mount effect: create the map once; tear it down on unmount.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const map = new maplibregl.Map({
      container,
      style: basemapStyle(),
      center: NSW_CENTER,
      zoom: NSW_ZOOM,
      minZoom: MIN_ZOOM,
      maxZoom: MAX_ZOOM,
      maxBounds: NSW_MAX_BOUNDS,
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
      // whose square contains it (a constant-time grid lookup) and draws the
      // box there, so the box appears whenever the pointer is anywhere inside a
      // cell's square — not only directly over its dot. When the cursor is
      // inside no cell's square the box clears. The pointer cursor mirrors the
      // same test. The pinned selected box is untouched by hover.
      map.on("mousemove", (event: maplibregl.MapMouseEvent) => {
        const center =
          cellIndexRef.current?.containing(event.lngLat.lng, event.lngLat.lat) ??
          null;
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
        paintCells(map, pending);
        // Seed the hover/selection index off the replayed cells.
        cellsAppliedRef.current(pending);
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
      if (mapReady && map && source && pending) {
        paintCells(map, pending);
        // Seed the hover/selection index off the replayed cells.
        cellsAppliedRef.current(pending);
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
    cellIndexRef.current = null;

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
        // The map must draw the SAME run the shortlist shows (S4-02 AC6): a
        // collection for any other run is refused, never drawn.
        if (cells.run_id !== runId) {
          throw new Error(
            `received cells for run ${cells.run_id}, expected ${runId}`,
          );
        }
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
        if (map && source) {
          paintCells(map, collection);
          // Seed the hover/selection index off the just-drawn cells.
          cellsAppliedRef.current(collection);
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

  // Selection effect (S4-02): mirror the app-wide selection onto the map. When
  // the selected cell changes, or this run's cells have just been applied (so
  // its centre is now known), move the persistent box to that cell, or clear it
  // when nothing is selected. Skipped when the prop is not wired, so the box
  // then keeps its click-only behaviour.
  useEffect(() => {
    if (selectedCellId === undefined || !mapReady) return;
    const center =
      selectedCellId === null
        ? null
        : (cellIndexRef.current?.centerOf(selectedCellId) ?? null);
    setSelectedSquareRef.current(center);
    // A selection made elsewhere (e.g. a shortlist row) may sit outside the
    // current view when zoomed in: pan to it, keeping the zoom, so the box is
    // always visible. A selection already in view never moves the map.
    const map = mapRef.current;
    if (center && map && !map.getBounds().contains(center)) {
      map.easeTo({ center });
    }
  }, [selectedCellId, mapReady, cellsVersion]);

  return (
    <div>
      <div ref={containerRef} className="om-map" aria-label="Interactive cell map" />
      {statusText(runId, loading, error)}
      <MapLegend quantiles={scoreQuantiles} />
    </div>
  );
}

/** A score for the legend: two decimals, like the shortlist. */
function formatScore(score: number): string {
  return score.toFixed(2);
}

/**
 * The map legend (S4-02): a continuous colour bar for eligible cells labelled
 * with this run's lowest, median and highest suitability scores, then the two
 * excluded classes, the selection/hover outlines and the outside-NSW mask, so
 * every style on the map is named. The bar is drawn from the SAME stops the
 * eligible layer uses, so legend and map cannot disagree. Before a run's cells
 * arrive the bar shows the ramp without numbers.
 */
function MapLegend({
  quantiles,
}: {
  quantiles: readonly ScoreQuantile[];
}): JSX.Element {
  const stops = scoreColorStops(quantiles);
  const gradient =
    quantiles.length > 0
      ? `linear-gradient(to right, ${stops.map(([, colour]) => colour).join(", ")})`
      : `linear-gradient(to right, ${SCORE_RAMP.join(", ")})`;
  const lowest = quantiles[0];
  const median = quantiles.find((point) => point.quantile === 0.5);
  const highest = quantiles[quantiles.length - 1];
  return (
    <div className="om-map__legend" aria-label="Map legend" role="group">
      <p className="om-map__legend-title">
        Eligible candidate — relative suitability score
      </p>
      <div
        className="om-map__ramp"
        style={{ backgroundImage: gradient }}
        aria-hidden="true"
      />
      {lowest && highest ? (
        <p className="om-map__ramp-labels">
          <span>Lower {formatScore(lowest.suitability_score)}</span>
          {median ? <span>Median {formatScore(median.suitability_score)}</span> : null}
          <span>Higher {formatScore(highest.suitability_score)}</span>
        </p>
      ) : null}
      <p className="om-map__legend-note">
        Darker = higher score among eligible cells (colour steps at the 10th,
        25th, 50th, 75th and 90th percentiles). Excluded cells are not scored
        and are never shown on this scale.
      </p>
      <ul className="om-map__legend-keys">
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
        <li>
          <span
            className="om-map__swatch om-map__swatch--selected"
            aria-hidden="true"
          />
          Selected site (same cell as the shortlist and site detail)
        </li>
        <li>
          <span
            className="om-map__swatch om-map__swatch--hover"
            aria-hidden="true"
          />
          Cell under the pointer — click to inspect
        </li>
        <li>
          <span
            className="om-map__swatch om-map__swatch--mask"
            aria-hidden="true"
          />
          Outside NSW (not analysed)
        </li>
      </ul>
    </div>
  );
}
