"""
Clip a Global Wind Atlas country raster to a study window and save it locally.

The full Australia rasters are ~600 MB each. This script never downloads them:
it opens the remote GeoTIFF through GDAL's /vsicurl/ driver, reads only the
pixel window covering the requested bounding box, and writes that window out
as a small GeoTIFF with the source CRS, transform and nodata preserved.

Usage:
  python scripts/download_gwa_sample.py                       # default sample set
  python scripts/download_gwa_sample.py --variable wind-speed --height 100
  python scripts/download_gwa_sample.py --bbox 150.0,-31.5,152.0,-29.5 --area-name my-area

Default study window: New England Renewable Energy Zone, NSW. NSW-first matches
the Product Knowledge Base fallback scope, and the window overlaps the NSW REZ
boundaries sampled in Task 3, so Task 5 can cross-check the two datasets.

Output: DATA/wind-resource/gwa_v4_<variable>_<height>m_<area>.tif
        DATA/wind-resource/metadata/download_manifest.json

Source: https://globalwindatlas.info/
Licence: see DATA/wind-resource/DATA_PROVENANCE.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import rasterio
from rasterio.windows import Window, from_bounds

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gwa_common import apply_vsicurl_env, human_bytes, resolve_source  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "DATA" / "wind-resource"
META_DIR = OUT_DIR / "metadata"

# New England REZ, NSW — approx. 2 deg x 2 deg (~190 km E-W x ~222 km N-S).
DEFAULT_BBOX = (150.0, -31.5, 152.0, -29.5)
DEFAULT_AREA = "new-england-rez"

# (variable, height) pairs retrieved by default.
#   wind-speed at three heights -> evidence for the hub-height recommendation
#   power-density               -> the checklist's second required variable
#   capacity-factor_IEC2        -> the most directly interpretable resource measure
DEFAULT_SAMPLES = [
    ("wind-speed", 50),
    ("wind-speed", 100),
    ("wind-speed", 150),
    ("power-density", 100),
    ("capacity-factor_IEC2", None),
]


def output_name(variable: str, height: int | None, area: str) -> str:
    suffix = f"_{height}m" if height is not None else ""
    return f"gwa_v4_{variable}{suffix}_{area}.tif"


def clip_sample(variable, height, bbox, area, out_dir):
    """Read the bbox window from the remote raster and write it locally."""
    provenance = resolve_source(variable, height)
    label = f"{variable}" + (f" @ {height}m" if height is not None else "")
    print(f"\n{label}")
    print(f"  source : {provenance['source_url']}")
    print(f"  remote : {human_bytes(provenance['remote_bytes'])} (not downloaded in full)")

    remote = f"/vsicurl/{provenance['signed_url']}"
    with rasterio.open(remote) as src:
        window = from_bounds(*bbox, transform=src.transform).round_offsets().round_lengths()
        # Keep the window inside the raster so a bbox partly outside Australia
        # still yields a valid clip rather than a silent pad of nodata.
        window = window.intersection(Window(0, 0, src.width, src.height))
        if window.width <= 0 or window.height <= 0:
            raise RuntimeError(f"bbox {bbox} does not intersect {provenance['source_url']}")

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
        source_grid = {
            "crs": str(src.crs),
            "width": src.width,
            "height": src.height,
            "pixel_size_deg": [abs(src.res[0]), abs(src.res[1])],
            "bounds": list(src.bounds),
            "dtype": src.dtypes[0],
            "nodata": None if src.nodata is None else float(src.nodata),
        }

    # Write to a sibling temporary file and rename into place. Opening the target
    # directly makes GDAL delete any existing file first, which turns a re-run into
    # a failure wherever that delete is not permitted, and leaves a half-written
    # raster if the write is interrupted. Rename is atomic and needs no delete.
    out_path = out_dir / output_name(variable, height, area)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".tif.tmp")
    try:
        with rasterio.open(tmp_path, "w", **profile) as dst:
            dst.write(data, 1)
        os.replace(tmp_path, out_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    local_bytes = out_path.stat().st_size
    print(f"  window : col {int(window.col_off)} row {int(window.row_off)} "
          f"-> {int(window.width)} x {int(window.height)} px")
    print(f"  wrote  : {out_path.relative_to(REPO_ROOT)} ({human_bytes(local_bytes)})")

    provenance.pop("signed_url")  # expires; not useful as a provenance record
    provenance.update(
        output_file=str(out_path.relative_to(REPO_ROOT)),
        local_bytes=local_bytes,
        bbox=list(bbox),
        area_name=area,
        window={
            "col_off": int(window.col_off),
            "row_off": int(window.row_off),
            "width": int(window.width),
            "height": int(window.height),
        },
        source_grid=source_grid,
    )
    return provenance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--variable", help="GWA variable, e.g. wind-speed, power-density")
    parser.add_argument("--height", type=int, help="Measurement height in metres, where applicable")
    parser.add_argument("--bbox", default=",".join(str(v) for v in DEFAULT_BBOX),
                        help="Study window as W,S,E,N in EPSG:4326")
    parser.add_argument("--area-name", default=DEFAULT_AREA, help="Short slug used in file names")
    parser.add_argument("--out-dir", default=str(OUT_DIR), help="Output directory")
    args = parser.parse_args()

    bbox = tuple(float(v) for v in args.bbox.split(","))
    if len(bbox) != 4:
        parser.error("--bbox must be W,S,E,N")

    samples = [(args.variable, args.height)] if args.variable else DEFAULT_SAMPLES
    out_dir = Path(args.out_dir)

    apply_vsicurl_env()
    print(f"Study window : {bbox}  ({args.area_name})")

    records, failures = [], []
    for variable, height in samples:
        try:
            records.append(clip_sample(variable, height, bbox, args.area_name, out_dir))
        except Exception as exc:  # report and continue; a missing layer is a finding, not a crash
            label = f"{variable}" + (f" @ {height}m" if height is not None else "")
            print(f"\n{label}\n  FAILED: {exc}")
            failures.append({"variable": variable, "height_m": height, "error": str(exc)})

    manifest = {
        "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": "Global Wind Atlas v4 (country GeoTIFF set)",
        "country": "AUS",
        "study_window": {"name": args.area_name, "bbox_epsg4326": list(bbox)},
        "samples": records,
        "failures": failures,
    }
    META_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = META_DIR / "download_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"\nManifest: {manifest_path.relative_to(REPO_ROOT)}")
    print(f"Retrieved {len(records)} sample(s); {len(failures)} failure(s).")
    return 1 if failures and not records else 0


if __name__ == "__main__":
    raise SystemExit(main())
