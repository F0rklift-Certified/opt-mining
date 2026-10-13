"use client";

/**
 * CellPicker — a mini MapLibre map for the S3-06 scenario-comparison panel.
 *
 * The user drags a rectangle on this map to pick which cells the comparison
 * TABLE displays. This is a DISPLAY FILTER only: it never calls the comparison
 * engine, never re-ranks, re-scores or re-sorts anything, and emits only the
 * `cell_id`s whose centre falls inside the drawn rectangle (via the pure
 * {@link cellIdsInBbox} geometric test over coordinates already in memory). The
 * ranks the table shows remain the engine's GLOBAL ranks; this component owns
 * no decision logic.
 *
 * Data path: cells come through the single shared client (`service.getRunCells`),
 * joined best-effort with `service.getExclusions` for the per-cell exclusion
 * class — the SAME two calls CellMap makes — so there is NO direct `fetch` here
 * and NO new client method. The MapLibre lifecycle mirrors CellMap's
 * single-ordered-path shape (mount effect, a `mapReady` gate, a
 * `pendingDataRef` replay buffer, a `requestIdRef` staleness guard) so it tests
 * under the SAME jsdom mock.
 *
 * Visual parity (S3-06 follow-up): the mini-map draws the NSW boundary +
 * outside-NSW dimming mask and the SAME three engine-driven cell layers CellMap
 * uses (eligible score ramp / environmental rule-out / unassessed no-data) via
 * the shared {@link ./cell-layers} builders, so it reads as the shape of NSW
 * with the same colour language — not a flat rectangular block. The drawn
 * rectangle and selected-cell markers stay layered on top.
 *
 * Accessibility: the drag interaction is a convenience, NOT the only way to
 * select — the sibling search box in ScenarioComparison is a full keyboard
 * alternative, and the Apply/Clear controls are ordinary buttons. The drawn
 * rectangle and the selected-cell markers are visual aids layered over the
 * cells.
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
  type DecisionService,
  type ExcludedRow,
} from "../api/decision-service";
import { bboxFromCorners, cellIdsInBbox, type Bbox } from "./cell-geometry";
import {
  NSW_SOURCE_ID,
  clipToNsw,
  withExclusionClasses,
  nswBoundaryData,
  nswMaskLayer,
  nswBorderLayer,
  excludedNoDataLayer,
  excludedEnvLayer,
  eligibleLayer,
} from "./cell-layers";

export interface CellPickerProps {
  /** `engine.run.run_id` for the currently-loaded run, or null when none. */
  runId: string | null;
  /** The shared typed client (single integration point). */
  service: DecisionService;
  /**
   * Called when the user finishes a drag, with the `cell_id`s whose centre is
   * inside the drawn rectangle (may be empty if the box caught no cell).
   */
  onApply: (cellIds: string[]) => void;
  /** Called when the user clears the selection (table returns to all rows). */
  onClear: () => void;
  /** How many cells are currently selected (0 = showing all). */
  activeCount: number;
}

/**
 * The cell points source. The picker keeps its OWN source id (so it never
 * clashes with the big map if both ever mount) but draws the SAME three
 * engine-driven cell layers CellMap uses — eligible / excluded-environmental /
 * excluded-no-data — via the shared {@link cell-layers} builders, which take a
 * `sourceId` so only the source binding differs, never the paint.
 */
const SOURCE_ID = "picker-cells";
/** The selected-cell overlay (cells inside the applied/drawn rectangle). */
const SELECTED_SOURCE_ID = "picker-selected";
const SELECTED_LAYER_ID = "picker-selected-layer";
/** The rubber-band rectangle drawn while dragging / after apply. */
const RECT_SOURCE_ID = "picker-rect";
const RECT_FILL_LAYER_ID = "picker-rect-fill";
const RECT_LINE_LAYER_ID = "picker-rect-line";

/** NSW-framed initial view (whole-state overview), matching CellMap's framing. */
const NSW_CENTER: [number, number] = [147.0, -32.5];
const NSW_ZOOM = 5;

/** Required OSM attribution for the public basemap. */
const OSM_ATTRIBUTION = "© OpenStreetMap contributors";

/**
 * Minimal inline raster style driven by NEXT_PUBLIC_BASEMAP_TILE_URL (same as
 * CellMap). The basemap is context only: when unset the cells render over the
 * empty MapLibre background.
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
 * Build a closed rectangle ring FeatureCollection from a {@link Bbox}, or an
 * empty collection when there is no box. A pure geometric construction (no
 * decision math); returns a NEW object each call.
 */
function rectData(bbox: Bbox | null): GeoJSON.FeatureCollection {
  if (!bbox) return { type: "FeatureCollection", features: [] };
  const ring: number[][] = [
    [bbox.minLng, bbox.minLat],
    [bbox.maxLng, bbox.minLat],
    [bbox.maxLng, bbox.maxLat],
    [bbox.minLng, bbox.maxLat],
    [bbox.minLng, bbox.minLat],
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
 * Build a Point FeatureCollection for the selected-cell overlay from the fetched
 * cells filtered to a set of `cell_id`s. A pure membership filter (`Set.has`)
 * over coordinates already in memory — never `.sort`/`.reduce`.
 */
function selectedPointsData(
  collection: CellCollection | null,
  selectedIds: Set<string>,
): GeoJSON.FeatureCollection {
  if (!collection || selectedIds.size === 0) {
    return { type: "FeatureCollection", features: [] };
  }
  const features = (collection.features ?? [])
    .filter((feature) => selectedIds.has(feature.properties.cell_id))
    .map((feature) => ({
      type: "Feature" as const,
      properties: { cell_id: feature.properties.cell_id },
      geometry: feature.geometry as GeoJSON.Point,
    }));
  return { type: "FeatureCollection", features };
}

/** The highlighted selected cells (drawn above the base cells). */
function selectedLayer(): maplibregl.CircleLayerSpecification {
  return {
    id: SELECTED_LAYER_ID,
    type: "circle",
    source: SELECTED_SOURCE_ID,
    paint: {
      "circle-color": "#a50f15",
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 2, 9, 6],
      "circle-opacity": 0.95,
    },
  };
}

/** The translucent fill of the drawn rectangle. */
function rectFillLayer(): maplibregl.FillLayerSpecification {
  return {
    id: RECT_FILL_LAYER_ID,
    type: "fill",
    source: RECT_SOURCE_ID,
    paint: { "fill-color": "#111827", "fill-opacity": 0.12 },
  };
}

/** The outline of the drawn rectangle. */
function rectLineLayer(): maplibregl.LineLayerSpecification {
  return {
    id: RECT_LINE_LAYER_ID,
    type: "line",
    source: RECT_SOURCE_ID,
    paint: { "line-color": "#111827", "line-width": 1.5 },
  };
}

/** The mini-map cell picker body. */
export default function CellPicker({
  runId,
  service,
  onApply,
  onClear,
  activeCount,
}: CellPickerProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const pendingDataRef = useRef<CellCollection | null>(null);
  const requestIdRef = useRef(0);
  const fetchedRunRef = useRef<string | null>(null);
  // The current run's full cell collection, kept so the drag hit-test and the
  // selected-overlay can read coordinates already in memory.
  const cellsRef = useRef<CellCollection | null>(null);
  // Drag state: the lngLat where the drag began, held across mousemove/up.
  const dragStartRef = useRef<[number, number] | null>(null);
  // Setters wired once the sources exist (in the load handler); stable refs so
  // the mount-only effect never depends on them.
  const setRectRef = useRef<(bbox: Bbox | null) => void>(() => {});
  const setSelectedRef = useRef<(ids: Set<string>) => void>(() => {});
  // Latest callbacks held in refs so the once-run load handler always invokes
  // the current props without the mount effect depending on them.
  const onApplyRef = useRef(onApply);
  onApplyRef.current = onApply;

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
      attributionControl: {},
    });
    mapRef.current = map;

    map.on("load", () => {
      // The NSW boundary source + its mask/border layers are added FIRST so the
      // cell layers below draw on top of them (dimmed surround, traced border) —
      // the same bottom-most framing CellMap uses, so the mini-map reads as the
      // SHAPE of NSW rather than a flat rectangular block.
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
      // Draw order (bottom -> top), identical to CellMap's visual language:
      // faint no-data carpet, then genuine environmental rule-outs, then the
      // eligible score ramp on top. The shared builders take this picker's own
      // source id so only the source binding differs, never the paint.
      map.addLayer(excludedNoDataLayer(SOURCE_ID));
      map.addLayer(excludedEnvLayer(SOURCE_ID));
      map.addLayer(eligibleLayer(SOURCE_ID));
      map.addSource(SELECTED_SOURCE_ID, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      map.addLayer(selectedLayer());
      map.addSource(RECT_SOURCE_ID, {
        type: "geojson",
        data: rectData(null),
      });
      map.addLayer(rectFillLayer());
      map.addLayer(rectLineLayer());

      setRectRef.current = (bbox: Bbox | null) => {
        (map.getSource(RECT_SOURCE_ID) as GeoJSONSource | undefined)?.setData(
          rectData(bbox),
        );
      };
      setSelectedRef.current = (ids: Set<string>) => {
        (map.getSource(SELECTED_SOURCE_ID) as GeoJSONSource | undefined)?.setData(
          selectedPointsData(cellsRef.current, ids),
        );
      };

      // Drag-to-draw a rectangle. Disabling the map's own drag-pan while a
      // selection drag is in progress keeps the box crisp; it is restored on
      // mouseup. The three handlers compose: mousedown arms the drag, mousemove
      // updates the rubber-band box, mouseup finalises and emits the cell_ids.
      map.on("mousedown", (event: maplibregl.MapMouseEvent) => {
        dragStartRef.current = [event.lngLat.lng, event.lngLat.lat];
        map.dragPan?.disable?.();
        setRectRef.current(null);
      });
      map.on("mousemove", (event: maplibregl.MapMouseEvent) => {
        const start = dragStartRef.current;
        if (!start) return;
        const bbox = bboxFromCorners(start, [event.lngLat.lng, event.lngLat.lat]);
        setRectRef.current(bbox);
      });
      map.on("mouseup", (event: maplibregl.MapMouseEvent) => {
        const start = dragStartRef.current;
        if (!start) return;
        dragStartRef.current = null;
        map.dragPan?.enable?.();
        const bbox = bboxFromCorners(start, [event.lngLat.lng, event.lngLat.lat]);
        setRectRef.current(bbox);
        const cells = cellsRef.current;
        const ids = cells ? cellIdsInBbox(cells, bbox) : [];
        setSelectedRef.current(new Set(ids));
        onApplyRef.current(ids);
      });

      setMapReady(true);
      const pending = pendingDataRef.current;
      if (pending) {
        (map.getSource(SOURCE_ID) as GeoJSONSource | undefined)?.setData(
          pending as unknown as GeoJSON.FeatureCollection,
        );
        cellsRef.current = pending;
        pendingDataRef.current = null;
      }
    });

    return () => {
      mapRef.current = null;
      map.remove();
    };
  }, []);

  // Data effect: fetch the run's cells through the shared client once per run.
  useEffect(() => {
    if (runId === null) {
      setLoading(false);
      setError(null);
      return;
    }

    if (fetchedRunRef.current === runId) {
      const map = mapRef.current;
      const source = map?.getSource(SOURCE_ID) as GeoJSONSource | undefined;
      const pending = pendingDataRef.current;
      if (mapReady && source && pending) {
        source.setData(pending as unknown as GeoJSON.FeatureCollection);
        cellsRef.current = pending;
        pendingDataRef.current = null;
      }
      return;
    }

    fetchedRunRef.current = runId;
    const myId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    // A new run supersedes any prior drawn rectangle / selection overlay.
    setRectRef.current(null);
    setSelectedRef.current(new Set());
    cellsRef.current = null;

    // The cells layer is the required data path; the exclusions call enriches
    // it with the per-cell exclusion class (no-data vs environmental), exactly
    // as CellMap does. The exclusions fetch is best-effort: if it is missing or
    // fails, the cells still render (every excluded cell then falls back to the
    // environmental style). All data comes through the shared client — the
    // picker adds NO new client method; `getExclusions` already exists on it.
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
        // without touching any surviving cell's styling values). The hit-test
        // and selected overlay read the SAME enriched+clipped collection.
        const collection = clipToNsw(withExclusionClasses(cells, exclusions));
        const map = mapRef.current;
        const source = map?.getSource(SOURCE_ID) as GeoJSONSource | undefined;
        if (source) {
          source.setData(collection as unknown as GeoJSON.FeatureCollection);
          cellsRef.current = collection;
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

  function handleClear(): void {
    setRectRef.current(null);
    setSelectedRef.current(new Set());
    onClear();
  }

  return (
    <div className="om-cell-picker">
      <div
        ref={containerRef}
        className="om-cell-picker__map"
        aria-label="Mini map of NSW — drag to select cells for the comparison table"
      />
      <PickerLegend />
      {runId === null && (
        <p className="om-cell-picker__status">No run is loaded.</p>
      )}
      {runId !== null && loading && (
        <p className="om-cell-picker__status">Loading cells…</p>
      )}
      {error && (
        <p className="om-service-error" role="alert">
          Cell map unavailable: {error}
        </p>
      )}
      <div className="om-cell-picker__actions">
        <span className="om-cell-picker__count" role="status">
          {activeCount === 0
            ? "No rectangle selection — showing all cells."
            : `${activeCount.toLocaleString()} ${activeCount === 1 ? "cell" : "cells"} selected by rectangle.`}
        </span>
        <button
          type="button"
          className="om-cell-picker__clear"
          onClick={handleClear}
          disabled={activeCount === 0}
        >
          Clear selection
        </button>
      </div>
    </div>
  );
}

/**
 * A compact legend naming the cell classes the shared layers paint, mirroring
 * CellMap's legend so the mini-map is read with the same visual language. The
 * swatch colours reuse the CellMap `om-map__swatch--*` classes, which track the
 * shared layer paint, so the two maps' legends cannot drift.
 */
function PickerLegend(): JSX.Element {
  return (
    <ul className="om-cell-picker__legend" aria-label="Mini-map legend">
      <li>
        <span
          className="om-map__swatch om-map__swatch--eligible"
          aria-hidden="true"
        />
        Eligible (shade = suitability)
      </li>
      <li>
        <span
          className="om-map__swatch om-map__swatch--env"
          aria-hidden="true"
        />
        Excluded — environmental
      </li>
      <li>
        <span
          className="om-map__swatch om-map__swatch--nodata"
          aria-hidden="true"
        />
        Not assessed — no data
      </li>
    </ul>
  );
}
