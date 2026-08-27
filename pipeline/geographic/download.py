"""
Geographic download stage — fetch vector and raster samples.

Part 1 (Vectors): ABS ASGS boundaries, DCCEEW CAPAD protected areas,
Natural Earth land mask, and derived NEM regions via ArcGIS REST.

Part 2 (Rasters): SRTM GL1/GL3 elevation via OpenTopography S3 and
ABARES NLUM land use (zip download + /vsizip/ window clip).

Importable entry point:
    from pipeline.geographic.download import run
    result = run(bbox=(...), area_name="...", verbose=False)

Output:
    DATA/geographic/{boundaries,protected,urban,coastline,derived}/*.geojson
    DATA/geographic/elevation/*.tif
    DATA/geographic/landuse/*.tif + class table
    DATA/geographic/metadata/download_manifest.json
"""

from __future__ import annotations

import csv as csv_mod
import json
import os
import struct
import zipfile
from pathlib import Path

import rasterio
import requests
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

from . import config
from ..common.geo import (
    apply_vsicurl_env,
    atomic_write_json,
    atomic_write_text,
    feature_collection_bytes,
    query_layer_geojson,
    utc_now,
)
from ..common.geo import human_bytes


# ---------------------------------------------------------------------------
# Shared raster helpers
# ---------------------------------------------------------------------------


def _clip_to_file(src: rasterio.DatasetReader, bbox_native, out_path: Path) -> dict:
    """Read the bbox window (in the source CRS) and write it as a small GTiff."""
    window = from_bounds(*bbox_native, transform=src.transform).round_offsets().round_lengths()
    window = window.intersection(Window(0, 0, src.width, src.height))
    if window.width <= 0 or window.height <= 0:
        raise RuntimeError(f"bbox {bbox_native} does not intersect the raster")

    data = src.read(1, window=window)
    profile = src.profile.copy()
    profile.update(
        height=int(window.height),
        width=int(window.width),
        transform=src.window_transform(window),
        driver="GTiff",
        tiled=True,
        blockxsize=256,
        blockysize=256,
        compress="deflate",
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".tif.tmp")
    try:
        with rasterio.open(tmp_path, "w", **profile) as dst:
            dst.write(data, 1)
        os.replace(tmp_path, out_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    return {
        "output_file": str(out_path.relative_to(config.PROJECT_ROOT)),
        "local_bytes": out_path.stat().st_size,
        "window_px": {"width": int(window.width), "height": int(window.height)},
        "crs": str(src.crs),
        "pixel_size": [abs(src.res[0]), abs(src.res[1])],
        "dtype": src.dtypes[0],
        "nodata": None if src.nodata is None else float(src.nodata),
    }


# ---------------------------------------------------------------------------
# Vector download
# ---------------------------------------------------------------------------


def _write_geojson(path: Path, collection: dict) -> int:
    """Write a FeatureCollection compactly; return bytes written."""
    text = json.dumps(collection, separators=(",", ":")) + "\n"
    atomic_write_text(path, text)
    return len(text.encode())


def _fetch_with_size_guardrail(layer_url: str, **query_kwargs) -> tuple[dict, float | None]:
    """
    Query at full resolution; if the result exceeds the commit guardrail,
    re-query with server-side generalisation.
    """
    collection = query_layer_geojson(layer_url, **query_kwargs)
    if feature_collection_bytes(collection) <= config.MAX_COMMIT_BYTES:
        return collection, None
    collection = query_layer_geojson(
        layer_url, max_allowable_offset=config.GENERALISE_OFFSET_DEG, **query_kwargs
    )
    return collection, config.GENERALISE_OFFSET_DEG


def _derive_nem_regions(ste: dict) -> dict:
    """Build NEM region geometries from state polygons."""
    by_code: dict[str, dict] = {}
    for feature in ste["features"]:
        code = str(feature["properties"].get("state_code_2021"))
        by_code[code] = feature

    features = []
    for region, codes in config.NEM_REGIONS.items():
        polygons: list = []
        member_names, member_area = [], 0.0
        for code in codes:
            feature = by_code.get(code)
            if feature is None or feature.get("geometry") is None:
                raise RuntimeError(f"state code {code} missing from STE layer")
            geom = feature["geometry"]
            if geom["type"] == "Polygon":
                polygons.append(geom["coordinates"])
            elif geom["type"] == "MultiPolygon":
                polygons.extend(geom["coordinates"])
            else:
                raise RuntimeError(f"unexpected geometry {geom['type']} for state {code}")
            member_names.append(feature["properties"].get("state_name_2021"))
            member_area += float(feature["properties"].get("area_albers_sqkm") or 0)
        features.append({
            "type": "Feature",
            "geometry": {"type": "MultiPolygon", "coordinates": polygons},
            "properties": {
                "nem_region": region,
                "member_states": member_names,
                "member_state_codes": codes,
                "area_albers_sqkm_sum": round(member_area, 4),
                "derivation": ("DERIVED from ABS ASGS 2021 STE polygons; "
                               "not an authoritative AEMO boundary"),
            },
        })
    return {"type": "FeatureCollection", "features": features}


def _fetch_natural_earth_australia() -> dict:
    """Download NE 1:50m land and keep landmasses touching Australia."""
    resp = requests.get(config.NE_LAND_URL, timeout=config.TIMEOUT)
    resp.raise_for_status()
    land = resp.json()
    w, s, e, n = config.AUS_BBOX

    def bbox_intersects(geom: dict) -> bool:
        coords = geom["coordinates"]
        if geom["type"] == "Polygon":
            coords = [coords]
        xs, ys = [], []
        for poly in coords:
            for x, y in poly[0]:
                xs.append(x)
                ys.append(y)
        return min(xs) <= e and max(xs) >= w and min(ys) <= n and max(ys) >= s

    kept = [f for f in land["features"] if f.get("geometry") and bbox_intersects(f["geometry"])]
    return {"type": "FeatureCollection", "features": kept}


def _run_vector_download(bbox, area_name, verbose=False) -> dict:
    """Fetch all geographic vector samples."""
    records: list[dict] = []
    failures: list[dict] = []
    ste_collection: dict | None = None

    def _record(dataset, source, path, collection, **extra):
        size = path.stat().st_size
        if verbose:
            print(f"      {path.relative_to(config.PROJECT_ROOT)} "
                  f"({len(collection['features'])} features, {human_bytes(size)})")
        records.append({
            "dataset": dataset, "source": source,
            "output_file": str(path.relative_to(config.PROJECT_ROOT)),
            "features": len(collection["features"]),
            "local_bytes": size,
            "crs": "EPSG:4326 (GeoJSON, outSR explicit)",
            **extra,
        })

    def fetch_ste():
        nonlocal ste_collection
        url = f"{config.ABS_ASGS_BASE}/STE/FeatureServer/0"
        collection, offset = _fetch_with_size_guardrail(
            url, where="state_name_2021 <> 'Outside Australia'")
        path = config.GEO_DIR / "boundaries" / "abs_ste_2021_national.geojson"
        _write_geojson(path, collection)
        _record("ABS ASGS 2021 State/Territory (STE)", url, path, collection,
                max_allowable_offset_deg=offset,
                filter="state_name_2021 <> 'Outside Australia'")
        ste_collection = collection

    def fetch_aus():
        url = f"{config.ABS_ASGS_BASE}/AUS/FeatureServer/0"
        collection, offset = _fetch_with_size_guardrail(
            url, where="aus_code_2021 = 'AUS'")
        path = config.GEO_DIR / "boundaries" / "abs_aus_2021_national.geojson"
        _write_geojson(path, collection)
        _record("ABS ASGS 2021 Australia outline (AUS)", url, path, collection,
                max_allowable_offset_deg=offset, filter="aus_code_2021 = 'AUS'")

    def fetch_lga():
        url = f"{config.ABS_ASGS_BASE}/LGA/FeatureServer/0"
        collection, offset = _fetch_with_size_guardrail(url, geometry_bbox=bbox)
        path = config.GEO_DIR / "boundaries" / f"abs_lga_2021_{area_name}.geojson"
        _write_geojson(path, collection)
        _record("ABS ASGS 2021 LGA (window extract)", url, path, collection,
                max_allowable_offset_deg=offset,
                spatial_filter=f"envelope {bbox} EPSG:4326")

    def fetch_ucl():
        url = f"{config.ABS_ASGS_BASE}/UCL/FeatureServer/0"
        collection, offset = _fetch_with_size_guardrail(url, geometry_bbox=bbox)
        path = config.GEO_DIR / "urban" / f"abs_ucl_2021_{area_name}.geojson"
        _write_geojson(path, collection)
        _record("ABS ASGS 2021 UCL (window extract)", url, path, collection,
                max_allowable_offset_deg=offset,
                spatial_filter=f"envelope {bbox} EPSG:4326")

    def fetch_capad_nsw():
        url = f"{config.CAPAD_BASE}/0"
        collection, offset = _fetch_with_size_guardrail(
            url, where="STATE = 'NSW'", page_size=1000)
        path = config.GEO_DIR / "protected" / "dcceew_capad-terrestrial_2024_nsw.geojson"
        _write_geojson(path, collection)
        _record("CAPAD 2024 terrestrial, NSW", url, path, collection,
                max_allowable_offset_deg=offset, filter="STATE = 'NSW'")

    def fetch_capad_window():
        url = f"{config.CAPAD_BASE}/0"
        collection = query_layer_geojson(url, geometry_bbox=bbox, page_size=1000)
        path = config.GEO_DIR / "protected" / f"dcceew_capad-terrestrial_2024_{area_name}.geojson"
        _write_geojson(path, collection)
        _record("CAPAD 2024 terrestrial, study-window extract (full resolution)",
                url, path, collection, max_allowable_offset_deg=None,
                spatial_filter=f"envelope {bbox} EPSG:4326")

    def fetch_ne_land():
        collection = _fetch_natural_earth_australia()
        path = config.GEO_DIR / "coastline" / "ne_land-50m_australia.geojson"
        _write_geojson(path, collection)
        _record("Natural Earth 1:50m land, Australia-region landmasses",
                config.NE_LAND_URL, path, collection,
                filter=f"landmass bbox intersects {config.AUS_BBOX}")

    def fetch_nem():
        if ste_collection is None:
            raise RuntimeError("STE fetch failed; cannot derive NEM regions")
        collection = _derive_nem_regions(ste_collection)
        path = config.GEO_DIR / "derived" / "nem_regions_asgs2021_national.geojson"
        _write_geojson(path, collection)
        _record("NEM regions (derived from ABS STE; not authoritative)",
                f"{config.ABS_ASGS_BASE}/STE/FeatureServer/0", path, collection,
                derivation="derived by pipeline.geographic.download")

    jobs = [
        ("ABS STE", fetch_ste),
        ("ABS AUS outline", fetch_aus),
        ("ABS LGA (window)", fetch_lga),
        ("ABS UCL (window)", fetch_ucl),
        ("CAPAD NSW", fetch_capad_nsw),
        ("CAPAD window extract", fetch_capad_window),
        ("Natural Earth land", fetch_ne_land),
        ("NEM regions (derived)", fetch_nem),
    ]

    for label, job in jobs:
        if verbose:
            print(f"    {label}")
        try:
            job()
        except Exception as exc:
            print(f"    {label} FAILED: {exc}")
            failures.append({"dataset": label, "error": str(exc)})

    # Update manifest (vector section)
    manifest_path = config.GEO_META_DIR / "download_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest.setdefault("study_window", {"name": area_name, "bbox_epsg4326": list(bbox)})
    manifest["vectors"] = {
        "retrieved_utc": utc_now(),
        "generated_by": "pipeline.geographic.download",
        "commit_guardrail_bytes": config.MAX_COMMIT_BYTES,
        "samples": records,
        "failures": failures,
    }
    atomic_write_json(manifest_path, manifest)

    return {"records": len(records), "failures": len(failures), "manifest": manifest_path}


# ---------------------------------------------------------------------------
# Raster download
# ---------------------------------------------------------------------------


def _fetch_srtm(vrt_url: str, bbox, out_path: Path, label: str, verbose=False) -> dict:
    """Clip a SRTM mosaic to a study window via /vsicurl/."""
    if verbose:
        print(f"    {label}")
        print(f"      source : {vrt_url}")
    with rasterio.open(f"/vsicurl/{vrt_url}") as src:
        info = _clip_to_file(src, bbox, out_path)
    if verbose:
        print(f"      wrote  : {info['output_file']} ({human_bytes(info['local_bytes'])}, "
              f"{info['window_px']['width']} x {info['window_px']['height']} px)")
    info.update(dataset=label, source=vrt_url, bbox_epsg4326=list(bbox),
                access="GDAL /vsicurl/ windowed read")
    return info


def _download_nlum_zip() -> Path:
    """Download the NLUM zip into raw/ once; re-runs reuse existing."""
    config.GEO_RAW_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = config.GEO_RAW_DIR / config.NLUM_ZIP_URL.rsplit("/", 1)[1]
    if zip_path.exists():
        return zip_path
    print(f"    downloading NLUM zip ({config.NLUM_ZIP_URL.rsplit('/', 1)[1]})")
    with requests.get(config.NLUM_ZIP_URL, stream=True, timeout=config.TIMEOUT) as resp:
        resp.raise_for_status()
        tmp = zip_path.with_suffix(".zip.tmp")
        try:
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    fh.write(chunk)
            os.replace(tmp, zip_path)
        finally:
            tmp.unlink(missing_ok=True)
    return zip_path


def _fetch_nlum(bbox, area_name, verbose=False) -> tuple[dict, list[str]]:
    """Download NLUM zip and clip the study window."""
    if verbose:
        print("    ABARES NLUM 250 m land use (ALUM v8), 2020-21")
    zip_path = _download_nlum_zip()

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    tifs = [n for n in names if n.lower().endswith(".tif")]
    if not tifs:
        raise RuntimeError(f"no .tif inside {zip_path.name}")
    inner_tif = tifs[0]

    vsizip = f"/vsizip/{zip_path}/{inner_tif}"
    with rasterio.open(vsizip) as src:
        bbox_native = transform_bounds("EPSG:4326", src.crs, *bbox)
        out_path = config.GEO_DIR / "landuse" / f"abares_nlum-alumv8_2020-21_{area_name}.tif"
        info = _clip_to_file(src, bbox_native, out_path)
    if verbose:
        print(f"      wrote  : {info['output_file']} ({human_bytes(info['local_bytes'])})")
    info.update(
        dataset="ABARES NLUM v7.1 250 m ALUM v8 land use, 2020-21 (window clip)",
        source=config.NLUM_ZIP_URL,
        bbox_epsg4326=list(bbox),
        bbox_native_epsg3577=list(bbox_native),
        access="zip download to raw/ (gitignored) + /vsizip/ window clip",
        zip_bytes=zip_path.stat().st_size,
        zip_member=inner_tif,
    )
    return info, names


def _extract_class_table(zip_path: Path, names: list[str]) -> dict | None:
    """Extract the ALUM class table (csv or .vat.dbf) from the NLUM zip."""
    out_csv = config.GEO_DIR / "landuse" / "abares_alumv8_class_table.csv"
    csvs = [n for n in names if n.lower().endswith(".csv")]
    if csvs:
        with zipfile.ZipFile(zip_path) as zf:
            data = zf.read(csvs[0])
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_csv.with_suffix(".csv.tmp")
        try:
            tmp.write_bytes(data)
            os.replace(tmp, out_csv)
        finally:
            tmp.unlink(missing_ok=True)
        return {"output_file": str(out_csv.relative_to(config.PROJECT_ROOT)),
                "zip_member": csvs[0]}

    dbfs = [n for n in names if n.lower().endswith(".vat.dbf")]
    if not dbfs:
        return None

    with zipfile.ZipFile(zip_path) as zf:
        raw = zf.read(dbfs[0])
    n_records = struct.unpack_from("<I", raw, 4)[0]
    header_size, record_size = struct.unpack_from("<HH", raw, 8)
    fields = []
    off = 32
    while raw[off] != 0x0D:
        name = raw[off:off + 11].split(b"\x00")[0].decode("ascii")
        length = raw[off + 16]
        fields.append((name, length))
        off += 32
    rows = []
    pos = header_size
    for _ in range(n_records):
        rec = raw[pos:pos + record_size]
        pos += record_size
        if not rec or rec[0:1] == b"*":
            continue
        values, fpos = [], 1
        for _, length in fields:
            values.append(rec[fpos:fpos + length].decode("ascii", "replace").strip())
            fpos += length
        rows.append(values)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_csv.with_suffix(".csv.tmp")
    try:
        with open(tmp, "w", newline="") as fh:
            writer = csv_mod.writer(fh)
            writer.writerow([f[0] for f in fields])
            writer.writerows(rows)
        os.replace(tmp, out_csv)
    finally:
        tmp.unlink(missing_ok=True)
    return {"output_file": str(out_csv.relative_to(config.PROJECT_ROOT)),
            "zip_member": dbfs[0], "records": len(rows)}


def _run_raster_download(bbox, area_name, verbose=False) -> dict:
    """Fetch geographic raster samples (elevation + land use)."""
    apply_vsicurl_env()
    records: list[dict] = []
    failures: list[dict] = []

    try:
        records.append(_fetch_srtm(
            config.SRTM_GL3_VRT, bbox,
            config.GEO_DIR / "elevation" / f"srtm-gl3_elevation_90m_{area_name}.tif",
            "SRTM GL3 elevation, 3 arc-second (~90 m), study window", verbose))
    except Exception as exc:
        print(f"    SRTM GL3 FAILED: {exc}")
        failures.append({"dataset": "SRTM GL3", "error": str(exc)})

    try:
        records.append(_fetch_srtm(
            config.SRTM_GL1_VRT, config.GL1_BBOX,
            config.GEO_DIR / "elevation" / f"srtm-gl1_elevation_30m_{config.GL1_AREA}.tif",
            "SRTM GL1 elevation, 1 arc-second (~30 m), wind-farm sub-window", verbose))
    except Exception as exc:
        print(f"    SRTM GL1 FAILED: {exc}")
        failures.append({"dataset": "SRTM GL1", "error": str(exc)})

    try:
        nlum_info, zip_names = _fetch_nlum(bbox, area_name, verbose)
        records.append(nlum_info)
        zip_path = config.GEO_RAW_DIR / config.NLUM_ZIP_URL.rsplit("/", 1)[1]
        table_info = _extract_class_table(zip_path, zip_names)
        if table_info:
            records.append({"dataset": "ALUM v8 class table (machine-extracted)",
                            "source": config.NLUM_ZIP_URL, **table_info})
    except Exception as exc:
        print(f"    NLUM FAILED: {exc}")
        failures.append({"dataset": "ABARES NLUM", "error": str(exc)})

    # Update manifest (raster section)
    manifest_path = config.GEO_META_DIR / "download_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest.setdefault("study_window", {"name": area_name, "bbox_epsg4326": list(bbox)})
    manifest["rasters"] = {
        "retrieved_utc": utc_now(),
        "generated_by": "pipeline.geographic.download",
        "gl1_subwindow": {
            "name": config.GL1_AREA,
            "bbox_epsg4326": list(config.GL1_BBOX),
            "reason": "full-window GL1 (~104 MB raw) exceeds the commit guardrail; "
                      "sub-window covers both Task 1 wind farms",
        },
        "samples": records,
        "failures": failures,
    }
    atomic_write_json(manifest_path, manifest)

    return {"records": len(records), "failures": len(failures), "manifest": manifest_path}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    bbox: tuple[float, ...] = config.DEFAULT_BBOX,
    area_name: str = config.DEFAULT_AREA,
    verbose: bool = False,
) -> dict:
    """
    Run the geographic download stage: vectors + rasters.

    Returns a summary dict with record counts and manifest paths.
    """
    results = {}

    print("  [1/2] Downloading geographic vector samples...")
    results["vectors"] = _run_vector_download(bbox, area_name, verbose)
    print(f"    {results['vectors']['records']} samples, "
          f"{results['vectors']['failures']} failures")

    print("  [2/2] Downloading geographic raster samples...")
    results["rasters"] = _run_raster_download(bbox, area_name, verbose)
    print(f"    {results['rasters']['records']} samples, "
          f"{results['rasters']['failures']} failures")

    return results
