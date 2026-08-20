"""
Fetch the Task 4 raster samples into DATA/geographic/.

Elevation comes from the SRTM GL1 (1 arc-second, ~30 m) and GL3 (3 arc-second,
~90 m) mosaics on OpenTopography's public S3 mirror, read as /vsicurl/ windows
so the national mosaics are never downloaded (Geoscience Australia's own DEM
services return HTTP 403 to scripted clients — recorded in the source
register). GL3 covers the full study window; GL1 covers a 0.5 deg sub-window
around the two operating wind farms from Task 1's validation set, which is
enough for the GL1-vs-GL3 slope-noise comparison without committing a
100 MB raster.

Land use comes from the ABARES NLUM 250 m national GeoTIFF (ALUM v8 classes,
GDA94 Australian Albers). The 64 MB zip is downloaded once into the
gitignored raw/ area, the raster is opened through /vsizip/ without
extraction, and only the study-window clip is committed — kept in the native
EPSG:3577 so no resampling is introduced. Any class table shipped inside the
zip is machine-extracted alongside.

Usage:
  python scripts/geo_fetch_rasters.py

Output: DATA/geographic/elevation/srtm-gl3_elevation_90m_new-england-rez.tif
        DATA/geographic/elevation/srtm-gl1_elevation_30m_glen-innes.tif
        DATA/geographic/landuse/abares_nlum-alumv8_2020-21_new-england-rez.tif
        DATA/geographic/landuse/abares_alumv8_class_table.csv (if shipped)
        DATA/geographic/metadata/download_manifest.json (raster section)

Source: https://opentopography.org/ (SRTM), https://www.agriculture.gov.au/abares/aclump (NLUM)
Licence: see DATA/geographic/DATA_PROVENANCE.md
"""

from __future__ import annotations

import json
import os
import sys
import zipfile
from pathlib import Path

import rasterio
import requests
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geo_common import (  # noqa: E402
    DEFAULT_AREA,
    DEFAULT_BBOX,
    GEO_DIR,
    META_DIR,
    RAW_DIR,
    REPO_ROOT,
    TIMEOUT,
    atomic_write_json,
    human_bytes,
    utc_now,
)

SRTM_BASE = "https://opentopography.s3.sdsc.edu/raster"
SRTM_GL3_VRT = f"{SRTM_BASE}/SRTM_GL3/SRTM_GL3_srtm.vrt"
SRTM_GL1_VRT = f"{SRTM_BASE}/SRTM_GL1/SRTM_GL1_srtm.vrt"

NLUM_URL = (
    "https://www.agriculture.gov.au/sites/default/files/documents/"
    "NLUM_v7_1_250m_ALUMV8_2020_21_alb_20260814.zip"
)

# GL1 at 1" over the full 2x2 deg window is ~104 MB raw — beyond the commit
# guardrail. This 0.5 x 0.5 deg sub-window contains both Task 1 wind farms
# (White Rock 151.544,-29.762; Sapphire 151.412,-29.700).
GL1_BBOX = (151.25, -30.0, 151.75, -29.5)
GL1_AREA = "glen-innes"


def apply_geo_vsicurl_env() -> None:
    """
    GDAL env for remote reads. Unlike Task 1 (bare .tif URLs), the SRTM
    mosaics are .vrt indexes referencing .tif tiles, and NLUM is read through
    /vsizip/, so the allowed-extension list must cover all three.
    """
    os.environ["GDAL_DISABLE_READDIR_ON_OPEN"] = "EMPTY_DIR"
    os.environ["CPL_VSIL_CURL_ALLOWED_EXTENSIONS"] = ".tif,.vrt,.zip"
    os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "3")
    os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")


def clip_to_file(src: rasterio.DatasetReader, bbox_native, out_path: Path) -> dict:
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
        "output_file": str(out_path.relative_to(REPO_ROOT)),
        "local_bytes": out_path.stat().st_size,
        "window_px": {"width": int(window.width), "height": int(window.height)},
        "crs": str(src.crs),
        "pixel_size": [abs(src.res[0]), abs(src.res[1])],
        "dtype": src.dtypes[0],
        "nodata": None if src.nodata is None else float(src.nodata),
    }


def fetch_srtm(vrt_url: str, bbox, out_path: Path, label: str) -> dict:
    print(f"\n{label}")
    print(f"  source : {vrt_url} (windowed /vsicurl/ read; mosaic not downloaded)")
    with rasterio.open(f"/vsicurl/{vrt_url}") as src:
        info = clip_to_file(src, bbox, out_path)
    print(f"  wrote  : {info['output_file']} ({human_bytes(info['local_bytes'])}, "
          f"{info['window_px']['width']} x {info['window_px']['height']} px)")
    info.update(dataset=label, source=vrt_url, bbox_epsg4326=list(bbox),
                access="GDAL /vsicurl/ windowed read")
    return info


def download_nlum_zip() -> Path:
    """Download the NLUM zip into raw/ once; re-runs reuse the existing file."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = RAW_DIR / NLUM_URL.rsplit("/", 1)[1]
    if zip_path.exists():
        print(f"  reusing: {zip_path.relative_to(REPO_ROOT)} "
              f"({human_bytes(zip_path.stat().st_size)})")
        return zip_path
    print(f"  downloading {NLUM_URL}")
    with requests.get(NLUM_URL, stream=True, timeout=TIMEOUT) as resp:
        resp.raise_for_status()
        tmp = zip_path.with_suffix(".zip.tmp")
        try:
            with open(tmp, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    fh.write(chunk)
            os.replace(tmp, zip_path)
        finally:
            tmp.unlink(missing_ok=True)
    print(f"  saved  : {zip_path.relative_to(REPO_ROOT)} "
          f"({human_bytes(zip_path.stat().st_size)}, gitignored)")
    return zip_path


def fetch_nlum(bbox) -> tuple[dict, list[str]]:
    print("\nABARES NLUM 250 m land use (ALUM v8), 2020-21")
    zip_path = download_nlum_zip()

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
    tifs = [n for n in names if n.lower().endswith(".tif")]
    if not tifs:
        raise RuntimeError(f"no .tif inside {zip_path.name}; contents: {names[:20]}")
    inner_tif = tifs[0]
    print(f"  raster : {inner_tif} (opened via /vsizip/, not extracted)")

    vsizip = f"/vsizip/{zip_path}/{inner_tif}"
    with rasterio.open(vsizip) as src:
        # The window arrives in EPSG:4326; NLUM is EPSG:3577. Transform the
        # bounds and clip in the native CRS so no resampling is introduced.
        bbox_native = transform_bounds("EPSG:4326", src.crs, *bbox)
        out_path = GEO_DIR / "landuse" / f"abares_nlum-alumv8_2020-21_{DEFAULT_AREA}.tif"
        info = clip_to_file(src, bbox_native, out_path)
    print(f"  wrote  : {info['output_file']} ({human_bytes(info['local_bytes'])}, "
          f"{info['window_px']['width']} x {info['window_px']['height']} px, native {info['crs']})")
    info.update(
        dataset="ABARES NLUM v7.1 250 m ALUM v8 land use, 2020-21 (window clip)",
        source=NLUM_URL,
        bbox_epsg4326=list(bbox),
        bbox_native_epsg3577=list(bbox_native),
        access="zip download to raw/ (gitignored) + /vsizip/ window clip",
        zip_bytes=zip_path.stat().st_size,
        zip_member=inner_tif,
    )
    return info, names


def extract_class_table(zip_path: Path, names: list[str]) -> dict | None:
    """
    Machine-extract the ALUM class table if the zip ships one (csv preferred,
    else a .tif.vat.dbf raster attribute table parsed with stdlib struct).
    """
    out_csv = GEO_DIR / "landuse" / "abares_alumv8_class_table.csv"
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
        print(f"  class table: {out_csv.relative_to(REPO_ROOT)} (from {csvs[0]})")
        return {"output_file": str(out_csv.relative_to(REPO_ROOT)), "zip_member": csvs[0]}

    dbfs = [n for n in names if n.lower().endswith(".vat.dbf")]
    if not dbfs:
        print("  class table: none shipped in zip (finding — decode via ALUM v8 "
              "documentation instead)")
        return None

    import csv as csv_mod
    import struct

    with zipfile.ZipFile(zip_path) as zf:
        raw = zf.read(dbfs[0])
    # dBASE III header: byte 8-9 header size, 10-11 record size; field
    # descriptors are 32 bytes each, terminated by 0x0D.
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
        if not rec or rec[0:1] == b"*":  # deleted record
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
    print(f"  class table: {out_csv.relative_to(REPO_ROOT)} "
          f"({len(rows)} classes, from {dbfs[0]})")
    return {"output_file": str(out_csv.relative_to(REPO_ROOT)), "zip_member": dbfs[0],
            "records": len(rows)}


def main() -> int:
    apply_geo_vsicurl_env()
    bbox = DEFAULT_BBOX
    print(f"Study window : {bbox}  ({DEFAULT_AREA})")

    records: list[dict] = []
    failures: list[dict] = []

    try:
        records.append(fetch_srtm(
            SRTM_GL3_VRT, bbox,
            GEO_DIR / "elevation" / f"srtm-gl3_elevation_90m_{DEFAULT_AREA}.tif",
            "SRTM GL3 elevation, 3 arc-second (~90 m), study window"))
    except Exception as exc:
        print(f"  FAILED: {exc}")
        failures.append({"dataset": "SRTM GL3", "error": str(exc)})

    try:
        records.append(fetch_srtm(
            SRTM_GL1_VRT, GL1_BBOX,
            GEO_DIR / "elevation" / f"srtm-gl1_elevation_30m_{GL1_AREA}.tif",
            "SRTM GL1 elevation, 1 arc-second (~30 m), wind-farm sub-window"))
    except Exception as exc:
        print(f"  FAILED: {exc}")
        failures.append({"dataset": "SRTM GL1", "error": str(exc)})

    try:
        nlum_info, zip_names = fetch_nlum(bbox)
        records.append(nlum_info)
        table_info = extract_class_table(RAW_DIR / NLUM_URL.rsplit("/", 1)[1], zip_names)
        if table_info:
            records.append({"dataset": "ALUM v8 class table (machine-extracted)",
                            "source": NLUM_URL, **table_info})
    except Exception as exc:
        print(f"  FAILED: {exc}")
        failures.append({"dataset": "ABARES NLUM", "error": str(exc)})

    manifest_path = META_DIR / "download_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest.setdefault("study_window", {"name": DEFAULT_AREA, "bbox_epsg4326": list(bbox)})
    manifest["rasters"] = {
        "retrieved_utc": utc_now(),
        "generated_by": "scripts/geo_fetch_rasters.py",
        "gl1_subwindow": {"name": GL1_AREA, "bbox_epsg4326": list(GL1_BBOX),
                          "reason": "full-window GL1 (~104 MB raw) exceeds the commit "
                                    "guardrail; sub-window covers both Task 1 wind farms"},
        "samples": records,
        "failures": failures,
    }
    atomic_write_json(manifest_path, manifest)
    print(f"\nManifest: {manifest_path.relative_to(REPO_ROOT)}")
    print(f"Retrieved {len(records)} sample(s); {len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
