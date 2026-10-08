#!/usr/bin/env python3
"""One-shot acquisition of the statewide ABS UCL 2021 NSW urban extract.

Queries the ABS ASGS 2021 ArcGIS FeatureServer (UCL layer) filtered to NSW
(state_code_2021 = '1'), reprojects/confirms EPSG:4326, clips to the NSW analysis
bbox, and atomically writes DATA/geographic/urban/abs_ucl_2021_nsw.geojson plus a
download_manifest entry. Temporary helper — not part of the pipeline stages.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import geopandas as gpd

from pipeline.geographic import config as geo_config
from pipeline.common.geo import (
    query_layer_geojson,
    atomic_write_text,
    atomic_write_json,
    utc_now,
)

NSW_BBOX = (141.01125, -37.51125, 153.66125, -28.16125)
UCL_LAYER_URL = f"{geo_config.ABS_ASGS_BASE}/UCL/FeatureServer/0"
WHERE = "state_code_2021 = '1'"
OUT_PATH = geo_config.GEO_DIR / "urban" / "abs_ucl_2021_nsw.geojson"


def _write_geojson(path: Path, collection: dict) -> int:
    text = json.dumps(collection, separators=(",", ":")) + "\n"
    atomic_write_text(path, text)
    return len(text.encode())


def main() -> int:
    print(f"Querying ABS UCL FeatureServer for NSW ({WHERE})...")
    collection = query_layer_geojson(UCL_LAYER_URL, where=WHERE)
    n_raw = len(collection["features"])
    print(f"  fetched {n_raw} UCL features (full resolution)")
    if n_raw == 0:
        raise SystemExit("ABS UCL query returned zero NSW features; aborting.")

    # Commit guardrail: the full-resolution statewide extract (Sydney/Newcastle
    # polygons are detailed) exceeds MAX_COMMIT_BYTES, so re-fetch with the same
    # server-side generalisation offset the project uses for oversized ABS layers
    # (download._fetch_with_size_guardrail). At the 0.05-deg (~5 km) analysis
    # resolution and cell-centre intersection, a ~0.0005-deg (~50 m) offset is
    # well within tolerance and leaves sos_code_2021 attributes untouched.
    offset = None
    from pipeline.common.geo import feature_collection_bytes

    if feature_collection_bytes(collection) > geo_config.MAX_COMMIT_BYTES:
        offset = geo_config.GENERALISE_OFFSET_DEG
        print(
            f"  full-resolution extract exceeds commit guardrail "
            f"({geo_config.MAX_COMMIT_BYTES} bytes); re-fetching generalised "
            f"(maxAllowableOffset={offset} deg)"
        )
        collection = query_layer_geojson(
            UCL_LAYER_URL, where=WHERE, max_allowable_offset=offset
        )
        n_raw = len(collection["features"])
        print(f"  fetched {n_raw} UCL features (generalised)")

    # Load into geopandas to confirm CRS (EPSG:4326, outSR explicit) and clip.
    # Carry only the native ArcGIS properties through — build the frame from the
    # raw features so no spurious geopandas roundtrip columns ("id"/"shape") leak
    # into the stored schema (keep it identical to the REZ slice's attribute set).
    gdf = gpd.GeoDataFrame.from_features(collection["features"], crs="EPSG:4326")
    if "sos_code_2021" not in gdf.columns:
        raise SystemExit(
            f"ABS UCL extract lacks sos_code_2021 attribute; got {list(gdf.columns)}"
        )
    # Drop any non-attribute roundtrip artefacts.
    for junk in ("id", "shape"):
        if junk in gdf.columns:
            gdf = gdf.drop(columns=[junk])

    # Clip to the NSW analysis bbox (intersecting features, geometries clipped).
    w, s, e, n = NSW_BBOX
    before = len(gdf)
    gdf = gdf.clip((w, s, e, n))
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()].reset_index(drop=True)
    print(f"  clipped to NSW bbox: {before} -> {len(gdf)} features")

    # Reassemble as a compact FeatureCollection in EPSG:4326 (storage CRS),
    # emitting only the real attribute properties (drop_id avoids a top-level
    # feature "id" and the geometry column is not duplicated as a property).
    gdf = gdf.to_crs("EPSG:4326")
    clipped = json.loads(gdf.to_json(drop_id=True))

    nbytes = _write_geojson(OUT_PATH, clipped)
    print(f"  wrote {OUT_PATH} ({nbytes} bytes, {len(gdf)} features)")

    # Provenance: hash + manifest entry.
    sha = hashlib.sha256(OUT_PATH.read_bytes()).hexdigest()
    dist = gdf["sos_code_2021"].value_counts().to_dict()
    bounds = tuple(round(float(x), 5) for x in gdf.total_bounds)
    print(f"  sha256={sha}")
    print(f"  sos_code_2021 distribution={dist}")
    print(f"  bounds={bounds}")

    manifest_path = geo_config.GEO_META_DIR / "download_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    urban_entry = {
        "dataset": "ABS ASGS 2021 Urban Centres and Localities (UCL), NSW statewide",
        "source": UCL_LAYER_URL,
        "query_url": f"{UCL_LAYER_URL}/query",
        "where": WHERE,
        "out_sr": 4326,
        "max_allowable_offset_deg": offset,
        "clip_bbox_epsg4326": list(NSW_BBOX),
        "output_file": str(OUT_PATH.relative_to(geo_config.PROJECT_ROOT)),
        "features": int(len(gdf)),
        "features_before_clip": int(n_raw),
        "local_bytes": int(nbytes),
        "sha256": sha,
        "retrieved_utc": utc_now(),
        "crs": "EPSG:4326 (GeoJSON, outSR explicit)",
        "sos_code_2021_distribution": {str(k): int(v) for k, v in dist.items()},
        "bbox_epsg4326": list(bounds),
        "generated_by": "scripts/_acquire_ucl_nsw.py",
    }
    manifest.setdefault("urban_nsw", {})
    manifest["urban_nsw"] = urban_entry
    atomic_write_json(manifest_path, manifest)
    print(f"  manifest updated: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
