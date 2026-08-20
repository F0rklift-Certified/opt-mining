"""
Cross-domain integration validation — checks that span multiple subpackages.

These checks validate wind farm siting against geographic layers:
- Wind farms are on land (NE + ABS masks)
- Wind farms are outside protected areas (CAPAD)
- Wind farms have acceptable slope
- Land-mask assessment: NE vs ABS coastline on the analysis grid

Domain-specific validation lives in each subpackage's own validate.py:
- pipeline.wind.validate — GWA raster sampling, crosscheck
- pipeline.geographic.validate — CAPAD area, DEM elevation, NLUM decode

Importable entry point:
    from pipeline.validate import run
    result = run(verbose=False, skip_land_sea=False)

Output:
    DATA/geographic/metadata/landmask_assessment.md
    (wind-farm geographic checks are appended to validation_geographic.md
     or reported standalone)
"""

from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import transform as warp_transform
from rasterio.windows import from_bounds

from . import config
from .common.geo import apply_vsicurl_env, atomic_write_text, banner
from .geographic import config as geo_config
from .wind import config as wind_config
from .wind.gwa import resolve_source


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GWA_ORIGIN_LON = 109.21125
GWA_ORIGIN_LAT = -8.86125
GWA_PIXEL_DEG = 0.0025
CELL_DEG = 0.05
PX_PER_CELL = int(round(CELL_DEG / GWA_PIXEL_DEG))
STRIP_BBOX = config.COAST_BBOX


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _point_in_polygons(lon: float, lat: float, geometries: list[dict]) -> bool:
    """Containment via single-pixel rasterisation (cell-centre rule)."""
    res = 0.0025
    transform = from_origin(lon - res / 2, lat + res / 2, res, res)
    burned = rasterize(((g, 1) for g in geometries), out_shape=(1, 1),
                       transform=transform, fill=0, all_touched=False, dtype="uint8")
    return bool(burned[0, 0])


def _sample_raster_at(path: Path, lon: float, lat: float) -> float:
    """Sample band 1 at a WGS84 point, handling CRS transform and scale."""
    with rasterio.open(path) as src:
        xs, ys = warp_transform("EPSG:4326", src.crs, [lon], [lat])
        value = next(src.sample([(xs[0], ys[0])]))[0]
        scale = src.scales[0] if src.scales else 1.0
    return float(value) * scale


# ---------------------------------------------------------------------------
# Wind farm geographic checks
# ---------------------------------------------------------------------------


def _run_cross_domain_checks(verbose: bool) -> list[dict]:
    """Check wind farms against geographic layers."""
    checks: list[dict] = []

    def check(name, expected, observed, passed):
        checks.append({"name": name, "expected": expected,
                       "observed": observed, "passed": bool(passed)})

    wind_farms_path = wind_config.WIND_REF_DIR / "nsw_wind_farms_new_england.csv"
    if not wind_farms_path.exists():
        return checks

    # Load geographic layers
    capad_nsw_path = geo_config.GEO_DIR / "protected" / "dcceew_capad-terrestrial_2024_nsw.geojson"
    ne_path = geo_config.GEO_DIR / "coastline" / "ne_land-50m_australia.geojson"
    abs_path = geo_config.GEO_DIR / "boundaries" / "abs_aus_2021_national.geojson"
    gl1_slope_path = (geo_config.GEO_DIR / "elevation" /
                      f"srtm-gl1_slope-horn_30m_{geo_config.GL1_AREA}.tif")

    ne_geoms = [f["geometry"] for f in
                json.loads(ne_path.read_text())["features"] if f.get("geometry")]
    abs_geoms = [f["geometry"] for f in
                 json.loads(abs_path.read_text())["features"] if f.get("geometry")]
    capad_geoms = [f["geometry"] for f in
                   json.loads(capad_nsw_path.read_text())["features"] if f.get("geometry")]

    with open(wind_farms_path) as fh:
        farms = list(csv.DictReader(fh))

    for farm in farms:
        name = farm["name"]
        lon, lat = float(farm["longitude"]), float(farm["latitude"])
        on_ne = _point_in_polygons(lon, lat, ne_geoms)
        on_abs = _point_in_polygons(lon, lat, abs_geoms)
        check(f"{name}: on land", "both masks", f"NE={on_ne}, ABS={on_abs}",
              on_ne and on_abs)
        in_capad = _point_in_polygons(lon, lat, capad_geoms)
        check(f"{name}: outside CAPAD", "outside",
              "inside" if in_capad else "outside", not in_capad)
        if gl1_slope_path.exists():
            slope = _sample_raster_at(gl1_slope_path, lon, lat)
            check(f"{name}: slope < 15 deg", "< 15 deg", f"{slope:.1f} deg", slope < 15.0)

    return checks


# ---------------------------------------------------------------------------
# Land mask assessment
# ---------------------------------------------------------------------------


def _anchored_grid(bbox):
    """Snap a bbox outward onto the Atlas-anchored 0.05 deg lattice."""
    w, s, e, n = bbox
    k_w = math.floor((w - GWA_ORIGIN_LON) / CELL_DEG)
    k_e = math.ceil((e - GWA_ORIGIN_LON) / CELL_DEG)
    k_n = math.floor((GWA_ORIGIN_LAT - n) / CELL_DEG)
    k_s = math.ceil((GWA_ORIGIN_LAT - s) / CELL_DEG)
    west = GWA_ORIGIN_LON + k_w * CELL_DEG
    east = GWA_ORIGIN_LON + k_e * CELL_DEG
    north = GWA_ORIGIN_LAT - k_n * CELL_DEG
    south = GWA_ORIGIN_LAT - k_s * CELL_DEG
    cols = k_e - k_w
    rows = k_s - k_n
    transform = from_origin(west, north, CELL_DEG, CELL_DEG)
    return (west, south, east, north), rows, cols, transform


def _mask_from_polygons(path: Path, rows: int, cols: int, transform) -> np.ndarray:
    """Rasterise polygons with cell-centre rule."""
    geoms = [f["geometry"] for f in
             json.loads(path.read_text())["features"] if f.get("geometry")]
    return rasterize(
        ((g, 1) for g in geoms), out_shape=(rows, cols),
        transform=transform, fill=0, all_touched=False, dtype="uint8",
    ).astype(bool)


def _run_landmask_assessment(verbose: bool) -> Path:
    """Assess NE vs ABS land mask on the analysis grid."""
    apply_vsicurl_env()
    grid_bounds, rows, cols, transform = _anchored_grid(STRIP_BBOX)

    ne_path = geo_config.GEO_DIR / "coastline" / "ne_land-50m_australia.geojson"
    abs_path = geo_config.GEO_DIR / "boundaries" / "abs_aus_2021_national.geojson"
    ne_land = _mask_from_polygons(ne_path, rows, cols, transform)
    abs_land = _mask_from_polygons(abs_path, rows, cols, transform)

    both = ne_land & abs_land
    ne_only = ne_land & ~abs_land
    abs_only = abs_land & ~ne_land
    neither = ~ne_land & ~abs_land

    # Read GWA wind over the strip
    provenance = resolve_source("wind-speed", 100)
    with rasterio.open(f"/vsicurl/{provenance['signed_url']}") as src:
        window = from_bounds(*grid_bounds, transform=src.transform)
        window = window.round_offsets().round_lengths()
        raw = src.read(1, window=window)

    # Average to cells
    expected_shape = (rows * PX_PER_CELL, cols * PX_PER_CELL)
    if raw.shape[0] >= expected_shape[0] and raw.shape[1] >= expected_shape[1]:
        trimmed = raw[:expected_shape[0], :expected_shape[1]]
    else:
        trimmed = raw
    blocks = trimmed.reshape(rows, PX_PER_CELL, cols, PX_PER_CELL).transpose(0, 2, 1, 3)
    blocks = blocks.reshape(rows, cols, -1).astype(np.float64)
    blocks[~np.isfinite(blocks)] = np.nan
    with np.errstate(invalid="ignore"):
        wind = np.nanmean(blocks, axis=2)

    def wind_stats(mask):
        vals = wind[mask]
        vals = vals[~np.isnan(vals)]
        if vals.size == 0:
            return {"n": 0, "mean": 0, "p90": 0, "max": 0}
        return {"n": int(vals.size), "mean": float(vals.mean()),
                "p90": float(np.percentile(vals, 90)), "max": float(vals.max())}

    s_land = wind_stats(both)
    s_ne_only = wind_stats(ne_only)
    s_ocean = wind_stats(neither)

    ne_only_vals = wind[ne_only]
    ne_only_vals = ne_only_vals[~np.isnan(ne_only_vals)]
    land_p90 = s_land["p90"]
    ne_only_hot = int((ne_only_vals > land_p90).sum()) if ne_only_vals.size else 0

    out = io.StringIO()
    out.write("# Land-mask assessment: Natural Earth 1:50m vs ABS ASGS boundary\n\n")
    out.write(banner("validate"))
    out.write(f"\nGrid: {rows} x {cols} cells of {CELL_DEG} deg over strip {STRIP_BBOX}.\n\n")
    out.write("## Cell classification\n\n")
    out.write("| Class | Cells | Share |\n|---|---|---|\n")
    total = rows * cols
    for label, mask in [("Land (both)", both), ("NE-only", ne_only),
                        ("ABS-only", abs_only), ("Ocean (both)", neither)]:
        out.write(f"| {label} | {int(mask.sum())} | {100.0 * mask.sum() / total:.2f}% |\n")
    out.write(f"\n## Leakage\n\n"
              f"- NE-only cells: **{int(ne_only.sum())}**\n"
              f"- Of those exceeding land P90 ({land_p90:.2f} m/s): **{ne_only_hot}**\n"
              f"- Ocean mean wind: {s_ocean['mean']:.2f} m/s vs land: {s_land['mean']:.2f} m/s\n"
              f"- A land mask is mandatory.\n")

    report_path = geo_config.GEO_META_DIR / "landmask_assessment.md"
    atomic_write_text(report_path, out.getvalue())
    return report_path


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    verbose: bool = False,
    skip_land_sea: bool = False,
) -> dict:
    """
    Run cross-domain integration validation.

    Returns a summary dict with output paths and check results.
    """
    results: dict[str, object] = {}

    print("  [1/2] Cross-domain wind farm checks (land, CAPAD, slope)...")
    checks = _run_cross_domain_checks(verbose)
    passed = sum(1 for c in checks if c["passed"])
    print(f"    {passed}/{len(checks)} checks passed")
    results["cross_domain_checks"] = checks

    if not skip_land_sea:
        print("  [2/2] Land-mask assessment...")
        results["landmask"] = _run_landmask_assessment(verbose)
        print(f"    → {results['landmask'].relative_to(config.PROJECT_ROOT)}")
    else:
        print("  [2/2] Land-mask assessment... [skipped]")
        results["landmask"] = None

    return results
