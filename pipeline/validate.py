"""
Cross-domain integration validation — checks that span multiple subpackages.

These checks validate wind farm siting against geographic layers:
- Wind farms are on land (NE + ABS masks)
- Wind farms are outside protected areas (CAPAD)
- Wind farms have acceptable slope
- Land-mask assessment: NE vs ABS coastline on the analysis grid

It also holds the cross-domain checks that compare one stage's output against
another's:
- scoring (S1-10) vs the analysis grid and the integrated table
- shortlist (S1-11) vs the Scored_Table and the analysis grid

Domain-specific validation lives in each subpackage's own validate.py:
- pipeline.wind.validate — GWA raster sampling, crosscheck
- pipeline.geographic.validate — CAPAD area, DEM elevation, NLUM decode
- pipeline.scoring.validate — score range, rank contiguity, contribution reconcile
- pipeline.shortlist.validate — row count vs Top_N, eligible-only, ordering,
  coordinates, CSV/GeoJSON equality, disclaimer/resolution presence

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

# Siting constraint defaults
DEFAULT_MAX_SLOPE_DEG = 15.0


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


def _run_cross_domain_checks(verbose: bool, max_slope: float = DEFAULT_MAX_SLOPE_DEG) -> list[dict]:
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
            check(f"{name}: slope < {max_slope:.0f} deg", f"< {max_slope:.0f} deg",
                  f"{slope:.1f} deg", slope < max_slope)

    return checks


# ---------------------------------------------------------------------------
# Scoring cross-domain checks (S1-10)
# ---------------------------------------------------------------------------


def _run_scoring_cross_checks(verbose: bool = False) -> list[dict]:
    """
    Cross-domain checks on the S1-10 Scored_Table.

    These live here rather than in `pipeline/scoring/validate.py` because they
    span domains: they compare the scored table against the S1-02 analysis
    grid and the S1-08 integrated table, which the scoring stage's own
    validation tier does not load. Within-stage checks (score range, rank
    contiguity, contribution reconciliation) stay in the scoring package.

    Returns [] when the scored table has not been generated yet, so a partial
    pipeline run does not fail on a stage that has not been run.
    """
    checks: list[dict] = []

    def check(name, expected, observed, passed):
        checks.append({"name": name, "expected": expected,
                       "observed": observed, "passed": bool(passed)})

    from .scoring import config as scoring_config

    scored_path = scoring_config.SCORING_DIR / scoring_config.OUTPUT_FILENAME
    grid_path = scoring_config.PROJECT_ROOT / "DATA" / "grid" / "nsw_analysis_grid.gpkg"
    if not scored_path.exists():
        return checks

    import geopandas as gpd

    scored = gpd.read_file(scored_path, layer=scoring_config.OUTPUT_LAYER)
    cell_column = scoring_config.CELL_ID_COLUMN

    # 1. The scored table covers exactly the analysis grid.
    if grid_path.exists():
        grid_ids = set(gpd.read_file(grid_path, layer="nsw_grid")[cell_column])
        scored_ids = set(scored[cell_column])
        missing = grid_ids - scored_ids
        extra = scored_ids - grid_ids
        check("Scored table cell_id set equals the analysis grid",
              "0 missing, 0 extra",
              f"{len(missing):,} missing, {len(extra):,} extra",
              not missing and not extra)

    # 2. Eligibility agrees with the integrated table that gated it. A cell
    #    the exclusion layer rejected must not carry a score here.
    integrated_path = scoring_config.INTEGRATED_PATH
    if integrated_path.exists():
        integrated = gpd.read_file(
            integrated_path, layer=scoring_config.INTEGRATED_LAYER,
            columns=[cell_column, scoring_config.ELIGIBLE_COLUMN],
        )
        merged = scored[[cell_column, scoring_config.SCORE_COLUMN]].merge(
            integrated, on=cell_column, how="left", validate="one_to_one",
        )
        eligible = merged[scoring_config.ELIGIBLE_COLUMN].fillna(False).astype(bool)
        has_score = merged[scoring_config.SCORE_COLUMN].notna()
        violations = int((~eligible & has_score).sum()) + int((eligible & ~has_score).sum())
        check("Scored cells match the S1-07 eligibility flag in the integrated table",
              "0 mismatches",
              f"{violations:,} mismatches "
              f"({int(eligible.sum()):,} eligible, {int(has_score.sum()):,} scored)",
              violations == 0)

    if verbose:
        for entry in checks:
            print(f"    [{'PASS' if entry['passed'] else 'FAIL'}] {entry['name']}")
    return checks


# ---------------------------------------------------------------------------
# Shortlist cross-domain checks (S1-11)
# ---------------------------------------------------------------------------


def _latest_shortlist_outputs(shortlist_config) -> tuple[Path | None, Path | None]:
    """
    Discover the most recent written Shortlist_CSV / Shortlist_GeoJSON pair.

    The shortlist filenames are timestamped (`sprint1_shortlist_<UTCdate>.{csv,
    geojson}`), so rather than assuming a fixed name we glob the shortlist
    directory for the `OUTPUT_PREFIX` pattern and take the most recently
    modified pair — the same "find the latest output" discipline the other
    stages' validators use. Returns (None, None) when no output exists yet, so
    a partial pipeline run does not fail on a stage that has not been run.
    """
    out_dir = shortlist_config.SHORTLIST_DIR
    if not out_dir.exists():
        return None, None
    prefix = shortlist_config.OUTPUT_PREFIX
    csvs = sorted(out_dir.glob(f"{prefix}_*.csv"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    if not csvs:
        return None, None
    csv_path = csvs[0]
    geojson_path = csv_path.with_suffix(".geojson")
    return csv_path, (geojson_path if geojson_path.exists() else None)


def _run_shortlist_cross_checks(verbose: bool = False) -> list[dict]:
    """
    Cross-domain checks on the S1-11 shortlist (Requirement 12.7).

    These live here rather than in `pipeline/shortlist/validate.py` because
    they span domains: they compare the written shortlist against the S1-10
    Scored_Table and the S1-02 Analysis_Grid, which the shortlist stage's own
    validation tier does not load. Within-stage checks (row count vs Top_N,
    eligible-only, ascending rank, non-null coordinates, CSV/GeoJSON equality,
    disclaimer presence) stay in the shortlist package.

    Every check reports expected vs observed vs an explicit pass/fail — no
    silent passes. Returns [] when the shortlist has not been generated yet, so
    a partial pipeline run does not fail on a stage that has not been run.

    Checks:
      1. shortlisted cell_id set ⊆ Scored_Table cell_id set;
      2. shortlisted cell_id set ⊆ Analysis_Grid cell_id set;
      3. each shortlisted cell's suitability_score AND rank equal the
         Scored_Table values for that cell_id (no re-scoring / re-ranking);
      4. each shortlisted cell's centroid_lat / centroid_lon equal the grid
         values for that cell_id (coordinates consistent across stages).
    """
    checks: list[dict] = []

    def check(name, expected, observed, passed):
        checks.append({"name": name, "expected": expected,
                       "observed": observed, "passed": bool(passed)})

    from .shortlist import config as shortlist_config

    csv_path, geojson_path = _latest_shortlist_outputs(shortlist_config)
    if csv_path is None:
        return checks

    import pandas as pd

    shortlist = pd.read_csv(csv_path)
    cell_col = "cell_id"
    if cell_col not in shortlist.columns:
        check("Shortlist_CSV carries a cell_id column",
              "cell_id present", "cell_id MISSING", False)
        return checks

    shortlisted_ids = set(shortlist[cell_col])

    # --- 1 & 3. Against the Scored_Table (subset + scores/ranks unchanged). ---
    scored_path = shortlist_config.SCORED_PATH
    if scored_path.exists():
        import geopandas as gpd

        scored = gpd.read_file(scored_path, layer=shortlist_config.SCORED_LAYER)
        scored_ids = set(scored[cell_col])
        not_in_scored = shortlisted_ids - scored_ids
        check("Shortlisted cell_id set is a subset of the Scored_Table cell_id set",
              "0 shortlisted cells absent from the Scored_Table",
              f"{len(not_in_scored):,} absent",
              not not_in_scored)

        # Scores/ranks match the Scored_Table for the shortlisted cells: this is
        # a FILTERING stage, so no re-scoring and no re-ranking (1.3, 4.6).
        merged = shortlist[[cell_col, "suitability_score", "rank"]].merge(
            scored[[cell_col, "suitability_score", "rank"]],
            on=cell_col, how="left", suffixes=("_shortlist", "_scored"),
        )
        score_mismatch = int(
            (~_close(merged["suitability_score_shortlist"],
                     merged["suitability_score_scored"])).sum()
        )
        rank_mismatch = int(
            (merged["rank_shortlist"].astype("Int64")
             != merged["rank_scored"].astype("Int64")).sum()
        )
        check("Shortlist scores and ranks equal the Scored_Table "
              "(no re-scoring / re-ranking)",
              "0 score mismatches, 0 rank mismatches",
              f"{score_mismatch:,} score mismatches, {rank_mismatch:,} rank mismatches",
              score_mismatch == 0 and rank_mismatch == 0)

    # --- 2 & 4. Against the Analysis_Grid (subset + coordinates equal). ---
    grid_path = shortlist_config.GRID_PATH
    if grid_path.exists():
        import geopandas as gpd

        grid = gpd.read_file(grid_path, layer=shortlist_config.GRID_LAYER)
        grid_ids = set(grid[cell_col])
        not_in_grid = shortlisted_ids - grid_ids
        check("Shortlisted cell_id set is a subset of the Analysis_Grid cell_id set",
              "0 shortlisted cells absent from the grid",
              f"{len(not_in_grid):,} absent",
              not not_in_grid)

        coords = shortlist[[cell_col, "centroid_lat", "centroid_lon"]].merge(
            grid[[cell_col, "centroid_lat", "centroid_lon"]],
            on=cell_col, how="left", suffixes=("_shortlist", "_grid"),
        )
        coord_mismatch = int(
            (
                ~_close(coords["centroid_lat_shortlist"], coords["centroid_lat_grid"])
                | ~_close(coords["centroid_lon_shortlist"], coords["centroid_lon_grid"])
            ).sum()
        )
        check("Shortlist coordinates equal the Analysis_Grid values for each cell_id",
              "0 coordinate mismatches",
              f"{coord_mismatch:,} coordinate mismatches",
              coord_mismatch == 0)

    if verbose:
        for entry in checks:
            print(f"    [{'PASS' if entry['passed'] else 'FAIL'}] {entry['name']}")
    return checks


def _close(a, b, tol: float = 1e-9):
    """
    Element-wise closeness for the cross-domain numeric comparisons, treating
    two nulls as equal and null-vs-value as unequal, so a missing join value is
    reported as a mismatch (a FAIL) rather than silently passing.
    """
    both_null = a.isna() & b.isna()
    return both_null | ((a - b).abs() <= tol)


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
    max_slope: float = DEFAULT_MAX_SLOPE_DEG,
) -> dict:
    """
    Run cross-domain integration validation.

    Parameters
    ----------
    verbose : bool
        Enable detailed logging.
    skip_land_sea : bool
        Skip the land-mask assessment (requires network access).
    max_slope : float
        Maximum allowable slope in degrees for wind farm siting checks.
        Default: 15.0 degrees.

    Returns a summary dict with output paths and check results.
    """
    results: dict[str, object] = {}

    print("  [1/2] Cross-domain wind farm checks (land, CAPAD, slope)...")
    checks = _run_cross_domain_checks(verbose, max_slope=max_slope)
    passed = sum(1 for c in checks if c["passed"])
    print(f"    {passed}/{len(checks)} checks passed")
    results["cross_domain_checks"] = checks

    scoring_checks = _run_scoring_cross_checks(verbose)
    if scoring_checks:
        scoring_passed = sum(1 for c in scoring_checks if c["passed"])
        print(f"    Scoring (S1-10) cross-checks: "
              f"{scoring_passed}/{len(scoring_checks)} passed")
    results["scoring_cross_checks"] = scoring_checks

    shortlist_checks = _run_shortlist_cross_checks(verbose)
    if shortlist_checks:
        shortlist_passed = sum(1 for c in shortlist_checks if c["passed"])
        print(f"    Shortlist (S1-11) cross-checks: "
              f"{shortlist_passed}/{len(shortlist_checks)} passed")
    results["shortlist_cross_checks"] = shortlist_checks

    if not skip_land_sea:
        print("  [2/2] Land-mask assessment...")
        results["landmask"] = _run_landmask_assessment(verbose)
        print(f"    → {results['landmask'].relative_to(config.PROJECT_ROOT)}")
    else:
        print("  [2/2] Land-mask assessment... [skipped]")
        results["landmask"] = None

    return results
