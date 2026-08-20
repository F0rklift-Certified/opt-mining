"""
Validate every Task 4 sample against independently known ground truth.

Each check compares a sampled value against a fact that does not come from
the sample itself: gazetted protected areas, surveyed town elevations, the
ABS's own served Albers areas, the ALUM classification, and the two
operating wind farms from Task 1's validation set. A failed check is
reported, not hidden — the report carries PASS/FAIL per check and the
script exits non-zero on any FAIL.

The EPSG:3577 checks also serve as the working proof for Task 1's hand-off
that area computations happen in an equal-area projected CRS: geometries are
reprojected with rasterio.warp.transform_geom and their shoelace areas
compared against the areas the custodians serve.

Usage:
  python scripts/geo_validate_samples.py

Output: DATA/geographic/metadata/validation_geographic.md

Source: samples under DATA/geographic/; reference values cited per check
Licence: see DATA/geographic/DATA_PROVENANCE.md
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import transform as warp_transform
from rasterio.warp import transform_geom

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geo_common import (  # noqa: E402
    GEO_DIR,
    META_DIR,
    REPO_ROOT,
    atomic_write_text,
    banner,
)

CAPAD_NSW = GEO_DIR / "protected" / "dcceew_capad-terrestrial_2024_nsw.geojson"
CAPAD_WINDOW = GEO_DIR / "protected" / "dcceew_capad-terrestrial_2024_new-england-rez.geojson"
STE = GEO_DIR / "boundaries" / "abs_ste_2021_national.geojson"
NE_LAND = GEO_DIR / "coastline" / "ne_land-50m_australia.geojson"
ABS_AUS = GEO_DIR / "boundaries" / "abs_aus_2021_national.geojson"
GL3 = GEO_DIR / "elevation" / "srtm-gl3_elevation_90m_new-england-rez.tif"
GL1 = GEO_DIR / "elevation" / "srtm-gl1_elevation_30m_glen-innes.tif"
GL1_SLOPE = GEO_DIR / "elevation" / "srtm-gl1_slope-horn_30m_glen-innes.tif"
NLUM = GEO_DIR / "landuse" / "abares_nlum-alumv8_2020-21_new-england-rez.tif"
CLASS_TABLE = GEO_DIR / "landuse" / "abares_alumv8_class_table.csv"
WIND_FARMS = REPO_ROOT / "DATA" / "wind-resource" / "reference" / "nsw_wind_farms_new_england.csv"

checks: list[dict] = []


def check(name: str, expected: str, observed: str, passed: bool) -> None:
    checks.append({"name": name, "expected": expected, "observed": observed,
                   "passed": bool(passed)})
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {observed} (expected {expected})")


def shoelace_km2(geometry_3577: dict) -> float:
    """Area of a (Multi)Polygon already in EPSG:3577, exterior minus holes, km^2."""
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


def point_in_polygons(lon: float, lat: float, geometries: list[dict]) -> bool:
    """
    Exact point-in-polygon via a single-pixel rasterisation: a 1 x 1 grid
    whose pixel centre is the point; the cell-centre burn rule then answers
    containment without any geometry library.
    """
    res = 0.0025
    transform = from_origin(lon - res / 2, lat + res / 2, res, res)
    burned = rasterize(((g, 1) for g in geometries), out_shape=(1, 1),
                       transform=transform, fill=0, all_touched=False, dtype="uint8")
    return bool(burned[0, 0])


def sample_raster(path: Path, lon: float, lat: float) -> float:
    """Sample band 1 at a WGS84 point, transforming into the raster CRS."""
    with rasterio.open(path) as src:
        xs, ys = warp_transform("EPSG:4326", src.crs, [lon], [lat])
        value = next(src.sample([(xs[0], ys[0])]))[0]
        scale = src.scales[0] if src.scales else 1.0
    return float(value) * scale


def features_by(path: Path):
    return json.loads(path.read_text())["features"]


def main() -> int:
    # --- CAPAD ground truth --------------------------------------------------
    # CAPAD stores its area fields (GAZ_AREA, GIS_AREA) in HECTARES and names
    # reserves without their type suffix ("Kosciuszko", TYPE "National Park") —
    # both discovered by an earlier failing run of this script and recorded as
    # data-dictionary facts in the task document.
    print("CAPAD protected areas")
    nsw = features_by(CAPAD_NSW)
    named = [f for f in nsw
             if "kosciuszko" in (f["properties"].get("NAME") or "").lower()
             and f["properties"].get("TYPE") == "National Park"]
    check("Kosciuszko NP present in CAPAD NSW", "1+ feature",
          f"{len(named)} feature(s)", len(named) >= 1)
    if named:
        gis_area_ha = sum(float(f["properties"].get("GIS_AREA") or 0) for f in named)
        gis_area_km2 = gis_area_ha / 100.0
        iucn = {f["properties"].get("IUCN") for f in named}
        check("Kosciuszko NP extent (GIS_AREA is hectares)", "~6,900 km2 (gazetteer)",
              f"GIS_AREA {gis_area_ha:,.0f} ha = {gis_area_km2:,.0f} km2",
              6200 <= gis_area_km2 <= 7600)
        check("Kosciuszko NP IUCN category", "II (national park)",
              ", ".join(sorted(str(i) for i in iucn)), "II" in iucn)

        # EPSG:3577 shoelace vs served GIS_AREA (Task 1 hand-off: areas in
        # an equal-area projected CRS).
        area_3577 = sum(
            shoelace_km2(transform_geom("EPSG:4326", "EPSG:3577", f["geometry"]))
            for f in named)
        rel_err = 100.0 * (area_3577 - gis_area_km2) / gis_area_km2
        check("Kosciuszko area recomputed in EPSG:3577", "within 1% of served GIS_AREA",
              f"{area_3577:,.0f} km2 ({rel_err:+.2f}%)", abs(rel_err) <= 1.0)

    # In-window anchors. New England NP itself sits east of the window
    # (~152.4 E), so the checks use reserves that gazetted maps place inside it.
    window_names = " | ".join((f["properties"].get("NAME") or "")
                              for f in features_by(CAPAD_WINDOW)).lower()
    check("Mount Kaputar NP in window extract", "present",
          "present" if "mount kaputar" in window_names else "absent",
          "mount kaputar" in window_names)
    check("Oxley Wild Rivers NP in window extract", "present",
          "present" if "oxley wild rivers" in window_names else "absent",
          "oxley wild rivers" in window_names)

    # --- ABS STE served area vs recomputed -----------------------------------
    print("ABS state boundaries")
    ste = features_by(STE)
    nsw_ste = [f for f in ste if f["properties"].get("state_name_2021") == "New South Wales"]
    check("NSW polygon present in STE", "1 feature", f"{len(nsw_ste)}", len(nsw_ste) == 1)
    if nsw_ste:
        served = float(nsw_ste[0]["properties"]["area_albers_sqkm"])
        recomputed = shoelace_km2(
            transform_geom("EPSG:4326", "EPSG:3577", nsw_ste[0]["geometry"]))
        rel_err = 100.0 * (recomputed - served) / served
        check("NSW area recomputed in EPSG:3577", "within 0.5% of ABS area_albers_sqkm",
              f"{recomputed:,.0f} vs served {served:,.0f} km2 ({rel_err:+.2f}%)",
              abs(rel_err) <= 0.5)

    # --- DEM ground truth ------------------------------------------------------
    print("Elevation")
    with rasterio.open(GL3) as src:
        gl3_max = float(src.read(1).max())
    check("GL3 window maximum vs highest in-window peak",
          "1,400–1,600 m (Ben Lomond ~1,512 m)", f"{gl3_max:.0f} m",
          1400 <= gl3_max <= 1600)

    armidale = sample_raster(GL3, 151.665, -30.512)
    check("GL3 spot height at Armidale", "~980 m +/- 60 (surveyed town elevation)",
          f"{armidale:.0f} m", 920 <= armidale <= 1040)
    glen_innes = sample_raster(GL1, 151.7386, -29.7346)
    check("GL1 spot height at Glen Innes", "~1,060 m +/- 60 (surveyed town elevation)",
          f"{glen_innes:.0f} m", 1000 <= glen_innes <= 1120)

    # GL1 vs GL3 coincident agreement over the sub-window (deterministic grid
    # of sample points; no RNG so re-runs are identical).
    lons = np.linspace(151.30, 151.70, 9)
    lats = np.linspace(-29.95, -29.55, 9)
    diffs = [sample_raster(GL1, lon, lat) - sample_raster(GL3, lon, lat)
             for lon in lons for lat in lats]
    mad = float(np.mean(np.abs(diffs)))
    check("GL1 vs GL3 coincident-point agreement", "mean abs diff <= 15 m (81 points)",
          f"{mad:.1f} m", mad <= 15)

    # --- NLUM decode ------------------------------------------------------------
    print("Land use")
    with open(CLASS_TABLE) as fh:
        table = {int(row["Value"]): row["TERTV8"] for row in csv.DictReader(fh)}
    with rasterio.open(NLUM) as src:
        values = set(int(v) for v in np.unique(src.read(1)))
    unknown = values - set(table)
    check("Every NLUM window code decodes against the shipped class table",
          "0 unknown codes", f"{len(unknown)} unknown ({sorted(unknown)[:5]})",
          len(unknown) == 0)
    check("Conservation classes (1.1.x) present in window", "present",
          "present" if any(110 <= v < 120 for v in values) else "absent",
          any(110 <= v < 120 for v in values))
    check("Wind electricity generation class (563) present in window",
          "present (operating wind farms exist here)",
          "present" if 563 in values else "absent", 563 in values)

    # --- Cross-task: Task 1 wind farms survive every proposed layer -------------
    print("Cross-task wind-farm checks")
    ne_geoms = [f["geometry"] for f in features_by(NE_LAND) if f.get("geometry")]
    abs_geoms = [f["geometry"] for f in features_by(ABS_AUS) if f.get("geometry")]
    capad_geoms = [f["geometry"] for f in nsw if f.get("geometry")]

    with open(WIND_FARMS) as fh:
        farms = list(csv.DictReader(fh))
    for farm in farms:
        name = farm["name"]
        lon, lat = float(farm["longitude"]), float(farm["latitude"])
        on_ne = point_in_polygons(lon, lat, ne_geoms)
        on_abs = point_in_polygons(lon, lat, abs_geoms)
        check(f"{name}: on land in both masks", "land in NE and ABS masks",
              f"NE={on_ne}, ABS={on_abs}", on_ne and on_abs)
        in_capad = point_in_polygons(lon, lat, capad_geoms)
        check(f"{name}: outside all CAPAD NSW protected areas", "outside",
              "inside" if in_capad else "outside", not in_capad)
        code = int(sample_raster(NLUM, lon, lat))
        label = table.get(code, "?")
        ok_class = (200 <= code < 500) or code == 563
        check(f"{name}: NLUM class is agricultural or wind generation",
              "2.x/3.x/4.x or 5.6.3", f"{code} ({label})", ok_class)
        slope = sample_raster(GL1_SLOPE, lon, lat)
        check(f"{name}: derived slope at site below candidate limits",
              "< 15 deg", f"{slope:.1f} deg", slope < 15.0)

    # --- Report -------------------------------------------------------------------
    passed = sum(1 for c in checks if c["passed"])
    out = io.StringIO()
    out.write("# Ground-truth validation of geographic samples\n\n")
    out.write(banner("geo_validate_samples.py"))
    out.write(
        f"\n**{passed}/{len(checks)} checks passed.** Reference values are facts "
        "independent of the samples: gazetted areas, surveyed town elevations, "
        "ABS-served Albers areas, the ALUM v8 class table, and Task 1's operating "
        "wind farms. The EPSG:3577 rows are the working proof that area "
        "computations run in an equal-area projected CRS (Task 1 hand-off).\n\n"
    )
    out.write("| Check | Expected | Observed | Result |\n|---|---|---|---|\n")
    for c in checks:
        out.write(f"| {c['name']} | {c['expected']} | {c['observed']} "
                  f"| {'PASS' if c['passed'] else '**FAIL**'} |\n")

    report_path = META_DIR / "validation_geographic.md"
    atomic_write_text(report_path, out.getvalue())
    print(f"\nReport: {report_path.relative_to(REPO_ROOT)}")
    print(f"{passed}/{len(checks)} checks passed.")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
