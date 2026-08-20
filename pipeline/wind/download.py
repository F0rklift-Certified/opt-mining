"""
Wind download stage — fetch Global Wind Atlas raster clips.

Clips GWA country rasters to the study window via /vsicurl/ — the full
Australia rasters (~600 MB each) are never downloaded in full.

Importable entry point:
    from pipeline.wind.download import run
    result = run(bbox=(...), area_name="...", verbose=False)

Output:
    DATA/wind-resource/gwa_v4_<variable>_<height>m_<area>.tif
    DATA/wind-resource/metadata/download_manifest.json
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import rasterio
from rasterio.windows import Window, from_bounds

from . import config
from .gwa import apply_vsicurl_env, human_bytes, resolve_source
from ..common.geo import atomic_write_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _output_name(variable: str, height: int | None, area: str) -> str:
    suffix = f"_{height}m" if height is not None else ""
    return f"gwa_v4_{variable}{suffix}_{area}.tif"


def _clip_gwa_sample(variable, height, bbox, area, out_dir, verbose=False):
    """Read the bbox window from the remote GWA raster and write it locally."""
    provenance = resolve_source(variable, height)
    label = f"{variable}" + (f" @ {height}m" if height is not None else "")
    if verbose:
        print(f"    {label}")
        print(f"      source : {provenance['source_url']}")
        print(f"      remote : {human_bytes(provenance['remote_bytes'])} (not downloaded in full)")

    remote = f"/vsicurl/{provenance['signed_url']}"
    with rasterio.open(remote) as src:
        window = from_bounds(*bbox, transform=src.transform).round_offsets().round_lengths()
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

    out_path = out_dir / _output_name(variable, height, area)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".tif.tmp")
    try:
        with rasterio.open(tmp_path, "w", **profile) as dst:
            dst.write(data, 1)
        os.replace(tmp_path, out_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    local_bytes = out_path.stat().st_size
    if verbose:
        print(f"      window : {int(window.width)} x {int(window.height)} px")
        print(f"      wrote  : {out_path.relative_to(config.PROJECT_ROOT)} "
              f"({human_bytes(local_bytes)})")

    provenance.pop("signed_url")
    provenance.update(
        output_file=str(out_path.relative_to(config.PROJECT_ROOT)),
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


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    bbox: tuple[float, ...] = config.DEFAULT_BBOX,
    area_name: str = config.DEFAULT_AREA,
    heights: list[int] | None = None,
    turbine_classes: list[str] | None = None,
    verbose: bool = False,
) -> dict:
    """
    Download GWA samples for the study window.

    Parameters
    ----------
    bbox : tuple
        Study window (W, S, E, N) in EPSG:4326.
    area_name : str
        Short slug for filenames.
    heights : list[int] | None
        Hub heights to download wind-speed layers for. None uses defaults.
    turbine_classes : list[str] | None
        IEC turbine classes for capacity-factor layers. None uses defaults.
    verbose : bool
        Enable detailed logging.

    Returns a summary dict with record counts and the manifest path.
    """
    apply_vsicurl_env()
    records, failures = [], []

    samples = config.build_samples(heights=heights, turbine_classes=turbine_classes)

    for variable, height in samples:
        try:
            records.append(
                _clip_gwa_sample(variable, height, bbox, area_name, config.WIND_DIR, verbose)
            )
        except Exception as exc:
            label = f"{variable}" + (f" @ {height}m" if height is not None else "")
            print(f"    {label} FAILED: {exc}")
            failures.append({"variable": variable, "height_m": height, "error": str(exc)})

    manifest = {
        "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": "Global Wind Atlas v4 (country GeoTIFF set)",
        "country": config.GWA_COUNTRY,
        "study_window": {"name": area_name, "bbox_epsg4326": list(bbox)},
        "samples": records,
        "failures": failures,
    }
    config.WIND_META_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = config.WIND_META_DIR / "download_manifest.json"
    atomic_write_text(manifest_path, json.dumps(manifest, indent=2) + "\n")

    print(f"    {len(records)} samples, {len(failures)} failures")
    return {"records": len(records), "failures": len(failures), "manifest": manifest_path}
