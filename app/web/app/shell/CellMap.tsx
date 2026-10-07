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
  type ExcludedRow,
} from "../api/decision-service";

export interface CellMapProps {
  /** `engine.run.run_id` for the currently-loaded run, or null when none. */
  runId: string | null;
  /** The shared typed client (single integration point). */
  service: DecisionService;
}

/** GeoJSON source id and the three circle layers (design §5.6). */
const SOURCE_ID = "cells";
const EXCLUDED_NODATA_LAYER_ID = "cells-excluded-nodata";
const EXCLUDED_ENV_LAYER_ID = "cells-excluded-env";
const ELIGIBLE_LAYER_ID = "cells-eligible";

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
      // Draw order (bottom -> top): faint no-data carpet, then the genuine
      // environmental rule-outs, then the eligible score layer on top.
      map.addLayer(excludedNoDataLayer());
      map.addLayer(excludedEnvLayer());
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
        const collection = withExclusionClasses(cells, exclusions);
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
