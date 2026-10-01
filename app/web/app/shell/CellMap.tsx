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
  type DecisionService,
} from "../api/decision-service";

export interface CellMapProps {
  /** `engine.run.run_id` for the currently-loaded run, or null when none. */
  runId: string | null;
  /** The shared typed client (single integration point). */
  service: DecisionService;
}

/** GeoJSON source id and the two circle layers (design §5.6). */
const SOURCE_ID = "cells";
const EXCLUDED_LAYER_ID = "cells-excluded";
const ELIGIBLE_LAYER_ID = "cells-eligible";

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
 * The muted, low-opacity excluded layer (bottom). Styling reads only the served
 * `eligible` property; zoom LOD keeps the state-wide view legible (design §5.6).
 */
function excludedLayer(): maplibregl.CircleLayerSpecification {
  return {
    id: EXCLUDED_LAYER_ID,
    type: "circle",
    source: SOURCE_ID,
    filter: ["==", ["get", "eligible"], false],
    paint: {
      "circle-color": "#9aa0a6",
      "circle-radius": [
        "interpolate",
        ["linear"],
        ["zoom"],
        5,
        1.5,
        9,
        4,
      ],
      "circle-opacity": [
        "interpolate",
        ["linear"],
        ["zoom"],
        5,
        0.15,
        9,
        0.4,
      ],
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
export default function CellMap({ runId, service }: CellMapProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const pendingDataRef = useRef<CellCollection | null>(null);
  const requestIdRef = useRef(0);
  // The run currently fetched; prevents a `mapReady` re-run from refetching.
  const fetchedRunRef = useRef<string | null>(null);
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
      map.addSource(SOURCE_ID, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      // Excluded is added first so it sits beneath the eligible layer.
      map.addLayer(excludedLayer());
      map.addLayer(eligibleLayer());
      setMapReady(true);
      const pending = pendingDataRef.current;
      if (pending) {
        (map.getSource(SOURCE_ID) as GeoJSONSource | undefined)?.setData(
          pending as unknown as GeoJSON.FeatureCollection,
        );
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
        pendingDataRef.current = null;
      }
      return;
    }

    fetchedRunRef.current = runId;
    const myId = ++requestIdRef.current;
    setLoading(true);
    setError(null);

    // `requestIdRef` is the single staleness guard (design §5.3): a response is
    // dropped iff a newer run has superseded it. The effect does not use a
    // separate "active" flag, so a `mapReady` re-run of the same run does not
    // cancel the in-flight fetch for that run.
    service
      .getRunCells(runId)
      .then((collection) => {
        if (myId !== requestIdRef.current) return; // stale run superseded
        // The "cells" source exists iff the load handler has run (it adds the
        // source and sets mapReady together), so source presence is the live
        // readiness signal — robust to the mapReady value captured at effect
        // creation. If the map is not yet ready, buffer for the load handler.
        const map = mapRef.current;
        const source = map?.getSource(SOURCE_ID) as GeoJSONSource | undefined;
        if (source) {
          source.setData(collection as unknown as GeoJSON.FeatureCollection);
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
    </div>
  );
}
