"""
Geographic validate stage — domain-specific ground-truth checks.

Validates geographic data samples against known facts:
- CAPAD area checks (Kosciuszko NP extent)
- DEM elevation spot-checks (Armidale, Glen Innes)
- NLUM class decode completeness
- ABS state area cross-check

Cross-domain checks (wind-farm-on-land, wind-farm slope, land-mask
assessment) live in the top-level pipeline/validate.py integration stage.

Importable entry point:
    from pipeline.geographic.validate import run
    result = run(verbose=False)

Output:
    DATA/geographic/metadata/validation_geographic.md
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform as warp_transform
from rasterio.warp import transform_geom

from . import config
from ..common.geo import atomic_write_text, banner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _shoelace_km2(geometry_3577: dict) -> float:
    """Area via shoelace formula on EPSG:3577 geometry, in km2."""
    def ring_area(ring) -> float:
        pts = np.asarray(ring)
        x, y = pts[:, 0], pts[:, 1]
        return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
    polys = (geometry_3577["coordinates"] if geometry_3577["type"] == "MultiPolygon"
             else [geometry_3577["coordinates"]])
    total = 0.0
    for poly in polys:
        total += ring_area(poly[0])
        for hole in poly[1:]:
            total -= ring_area(hole)
    return total / 1e6


def _sample_raster_at(path: Path, lon: float, lat: float) -> float:
    """Sample band 1 at a WGS84 point, handling CRS transform and scale."""
    with rasterio.open(path) as src:
        xs, ys = warp_transform("EPSG:4326", src.crs, [lon], [lat])
        value = next(src.sample([(xs[0], ys[0])]))[0]
        scale = src.scales[0] if src.scales else 1.0
    return float(value) * scale


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(verbose: bool = False) -> dict:
    """
    Run geographic ground-truth validation checks.

    Returns a summary dict with the report path and pass/fail counts.
    """
    checks: list[dict] = []

    def check(name, expected, observed, passed):
        checks.append({"name": name, "expected": expected,
                       "observed": observed, "passed": bool(passed)})

    # --- CAPAD checks ---
    capad_nsw_path = config.GEO_DIR / "protected" / "dcceew_capad-terrestrial_2024_nsw.geojson"
    capad_window_path = (config.GEO_DIR / "protected" /
                         f"dcceew_capad-terrestrial_2024_{config.DEFAULT_AREA}.geojson")

    nsw_features = json.loads(capad_nsw_path.read_text())["features"]
    named = [f for f in nsw_features
             if "kosciuszko" in (f["properties"].get("NAME") or "").lower()
             and f["properties"].get("TYPE") == "National Park"]
    check("Kosciuszko NP present in CAPAD NSW", "1+ feature",
          f"{len(named)} feature(s)", len(named) >= 1)
    if named:
        gis_area_ha = sum(float(f["properties"].get("GIS_AREA") or 0) for f in named)
        gis_area_km2 = gis_area_ha / 100.0
        check("Kosciuszko NP extent", "~6,900 km2",
              f"{gis_area_km2:,.0f} km2", 6200 <= gis_area_km2 <= 7600)
        area_3577 = sum(
            _shoelace_km2(transform_geom("EPSG:4326", "EPSG:3577", f["geometry"]))
            for f in named)
        rel_err = 100.0 * (area_3577 - gis_area_km2) / gis_area_km2
        check("Kosciuszko EPSG:3577 area", "within 1% of GIS_AREA",
              f"{area_3577:,.0f} km2 ({rel_err:+.2f}%)", abs(rel_err) <= 1.0)

    # --- Window reserves ---
    window_names = " | ".join(
        (f["properties"].get("NAME") or "")
        for f in json.loads(capad_window_path.read_text())["features"]
    ).lower()
    check("Mount Kaputar NP in window", "present",
          "present" if "mount kaputar" in window_names else "absent",
          "mount kaputar" in window_names)

    # --- ABS area ---
    ste_path = config.GEO_DIR / "boundaries" / "abs_ste_2021_national.geojson"
    ste = json.loads(ste_path.read_text())["features"]
    nsw_ste = [f for f in ste if f["properties"].get("state_name_2021") == "New South Wales"]
    if nsw_ste:
        served = float(nsw_ste[0]["properties"]["area_albers_sqkm"])
        recomputed = _shoelace_km2(
            transform_geom("EPSG:4326", "EPSG:3577", nsw_ste[0]["geometry"]))
        rel_err = 100.0 * (recomputed - served) / served
        check("NSW EPSG:3577 area", "within 0.5% of ABS",
              f"{recomputed:,.0f} vs {served:,.0f} km2 ({rel_err:+.2f}%)",
              abs(rel_err) <= 0.5)

    # --- DEM checks ---
    gl3_path = config.GEO_DIR / "elevation" / f"srtm-gl3_elevation_90m_{config.DEFAULT_AREA}.tif"
    gl1_path = config.GEO_DIR / "elevation" / f"srtm-gl1_elevation_30m_{config.GL1_AREA}.tif"
    with rasterio.open(gl3_path) as src:
        gl3_max = float(src.read(1).max())
    check("GL3 window max", "1,400–1,600 m", f"{gl3_max:.0f} m", 1400 <= gl3_max <= 1600)

    armidale = _sample_raster_at(gl3_path, 151.665, -30.512)
    check("GL3 Armidale elevation", "~980 m +/-60", f"{armidale:.0f} m", 920 <= armidale <= 1040)
    glen_innes = _sample_raster_at(gl1_path, 151.7386, -29.7346)
    check("GL1 Glen Innes elevation", "~1,060 m +/-60", f"{glen_innes:.0f} m",
          1000 <= glen_innes <= 1120)

    # --- NLUM decode check ---
    class_table_path = config.GEO_DIR / "landuse" / "abares_alumv8_class_table.csv"
    nlum_path = config.GEO_DIR / "landuse" / f"abares_nlum-alumv8_2020-21_{config.DEFAULT_AREA}.tif"
    if class_table_path.exists() and nlum_path.exists():
        with open(class_table_path) as fh:
            table = {int(row["Value"]): row["TERTV8"] for row in csv.DictReader(fh)}
        with rasterio.open(nlum_path) as src:
            values = set(int(v) for v in np.unique(src.read(1)))
        unknown = values - set(table)
        check("NLUM codes decode", "0 unknown", f"{len(unknown)} unknown", len(unknown) == 0)

    # --- Write report ---
    passed = sum(1 for c in checks if c["passed"])
    out = io.StringIO()
    out.write("# Ground-truth validation of geographic samples\n\n")
    out.write(banner("geographic.validate"))
    out.write(f"\n**{passed}/{len(checks)} checks passed.**\n\n")
    out.write("| Check | Expected | Observed | Result |\n|---|---|---|---|\n")
    for c in checks:
        out.write(f"| {c['name']} | {c['expected']} | {c['observed']} "
                  f"| {'PASS' if c['passed'] else '**FAIL**'} |\n")

    report_path = config.GEO_META_DIR / "validation_geographic.md"
    atomic_write_text(report_path, out.getvalue())

    print(f"    {passed}/{len(checks)} checks passed")
    print(f"    → {report_path.relative_to(config.PROJECT_ROOT)}")
    return {"report": report_path, "passed": passed, "total": len(checks)}
