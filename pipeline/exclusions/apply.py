"""
Exclusion layer stage — S1-07.

Reads the common analysis grid plus the raw geographic and wind source
datasets, computes the per-cell fields the configured exclusion rules need,
evaluates those rules, and writes:

    DATA/exclusions/optmining_exclusions_2024_nsw.gpkg    — Eligibility_Table
    DATA/exclusions/metadata/exclusion_summary.md          — method report

See pipeline/exclusions/__init__.py for why this reads raw sources directly
instead of a S1-06/S1-03 Feature_Table (neither exists in code yet).

Importable entry point:
    from pipeline.exclusions.apply import run
    result = run(verbose=False)
"""

from __future__ import annotations

import io
import os
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import shapely.geometry as shp_geom
from rasterio.warp import transform as warp_transform
from rasterio.warp import transform_geom

from . import config
from . import rules as rules_mod
from .raster_stats import zonal_mean
from ..common.geo import apply_vsicurl_env, atomic_write_text, banner


# ---------------------------------------------------------------------------
# Grid input
# ---------------------------------------------------------------------------


def read_grid_cells(grid_path: Path) -> gpd.GeoDataFrame:
    """
    Read cell_id + geometry + centroid columns from the grid GeoPackage.

    Halts loudly (rather than silently producing a partial exclusion table)
    on a missing grid, a missing cell_id column, or duplicate cell_id
    values — the same halting conditions the S1-06 design specifies for its
    (not yet implemented) grid reader, kept consistent here.
    """
    if not grid_path.exists():
        raise FileNotFoundError(
            f"Analysis grid not found: {grid_path} — run "
            f"`python -m pipeline --only grid` first."
        )
    gdf = gpd.read_file(grid_path)

    if "cell_id" not in gdf.columns:
        raise ValueError(f"Grid file has no 'cell_id' column: {grid_path}")

    dupes = gdf["cell_id"][gdf["cell_id"].duplicated()].unique().tolist()
    if dupes:
        shown = dupes[:10]
        suffix = " ..." if len(dupes) > 10 else ""
        raise ValueError(f"Grid file has duplicate cell_id values: {shown}{suffix}")

    if str(gdf.crs) != config.STORAGE_CRS:
        gdf = gdf.to_crs(config.STORAGE_CRS)

    return gdf


# ---------------------------------------------------------------------------
# Vector overlap (protected areas, urban centres) — EPSG:3577
# ---------------------------------------------------------------------------


def _load_vector(path: Path, source_label: str) -> gpd.GeoDataFrame:
    if not path.exists():
        raise RuntimeError(f"{source_label} source not found: {path}")
    try:
        gdf = gpd.read_file(path)
    except Exception as exc:  # noqa: BLE001 — re-raised as a halting error
        raise RuntimeError(f"{source_label} source could not be read: {path} ({exc})") from exc
    if gdf.crs is None:
        raise ValueError(f"{source_label} source has no declared CRS: {path}")

    n_invalid = int((~gdf.geometry.is_valid).sum())
    if n_invalid:
        # Real-world reserve/locality boundaries commonly carry small
        # self-intersections; repair with the standard buffer(0) trick
        # rather than letting an invalid geometry silently corrupt the
        # sjoin's intersection result.
        print(f"      ({source_label}: repairing {n_invalid} invalid geometr"
              f"{'y' if n_invalid == 1 else 'ies'} via buffer(0))")
        gdf["geometry"] = gdf.geometry.buffer(0)

    return gdf


def _overlap_join(
    cells: gpd.GeoDataFrame,
    features: gpd.GeoDataFrame,
    name_field: str | None,
) -> dict[str, tuple[bool, str]]:
    """
    Spatial join (intersects) of `cells` against `features`, both
    reprojected to COMPUTATION_CRS (EPSG:3577) — the intersection CRS the
    S1-06 design specifies for the same overlap test, kept consistent here
    (Constitution: CRS explicit at every boundary).

    Returns {cell_id: (overlap_bool, joined_distinct_names)}. When
    `name_field` is given, a feature with a missing/blank name contributes
    the UNNAMED_PROTECTED_AREA_PLACEHOLDER; distinct names are de-duplicated
    and joined with PROTECTED_AREA_NAME_DELIMITER, in sorted (deterministic)
    order.
    """
    cells_proj = cells[["cell_id", "geometry"]].to_crs(config.COMPUTATION_CRS)
    features_proj = features.to_crs(config.COMPUTATION_CRS)

    joined = gpd.sjoin(cells_proj, features_proj, how="inner", predicate="intersects")

    result: dict[str, tuple[bool, str]] = {cid: (False, "") for cid in cells["cell_id"]}
    if joined.empty:
        return result

    for cell_id, group in joined.groupby("cell_id"):
        if name_field and name_field in group.columns:
            names = []
            for raw in group[name_field]:
                is_blank = raw is None or (isinstance(raw, float) and np.isnan(raw))
                if not is_blank and str(raw).strip() == "":
                    is_blank = True
                names.append(config.UNNAMED_PROTECTED_AREA_PLACEHOLDER if is_blank else str(raw).strip())
            distinct = sorted(dict.fromkeys(names))
            joined_names = config.PROTECTED_AREA_NAME_DELIMITER.join(distinct)
        else:
            joined_names = ""
        result[cell_id] = (True, joined_names)

    return result


def protected_area_overlap(cells: gpd.GeoDataFrame) -> dict[str, tuple[bool, str]]:
    """CAPAD overlap — full-NSW coverage. Implements frozen decision Q6 (binary exclusion)."""
    capad = _load_vector(config.CAPAD_PATH, "CAPAD protected areas")
    return _overlap_join(cells, capad, name_field="NAME")


def urban_overlap(
    cells: gpd.GeoDataFrame,
) -> tuple[dict[str, bool], tuple[float, float, float, float]]:
    """
    ABS Urban Centre/Locality overlap — New England REZ window only. Also
    returns the source's coverage bounds (EPSG:4326) so the caller can flag
    cells outside that window rather than silently trusting a False result.

    The ABS UCL extract includes a "Remainder of State/Territory" feature
    (`sos_code_2021 == "13"`) — a catch-all polygon for everything OUTSIDE
    every actual urban centre/locality. It is not an urban area and is
    dropped before the overlap join (see config.URBAN_EXCLUDE_SOS_CODES);
    including it would flag almost the entire grid as "urban".
    """
    urban = _load_vector(config.URBAN_PATH, "ABS Urban Centres/Localities")
    if "sos_code_2021" in urban.columns:
        n_before = len(urban)
        urban = urban[~urban["sos_code_2021"].isin(config.URBAN_EXCLUDE_SOS_CODES)]
        print(f"      (dropped {n_before - len(urban)} non-urban 'Rural Balance' feature(s))")
    result = _overlap_join(cells, urban, name_field=None)
    coverage_bounds = tuple(urban.to_crs(config.STORAGE_CRS).total_bounds)
    return {cid: overlap for cid, (overlap, _name) in result.items()}, coverage_bounds


# ---------------------------------------------------------------------------
# Raster fields (slope, wind speed)
# ---------------------------------------------------------------------------


def _reproject_geom(geom, src_crs: str, dst_crs):
    mapping = transform_geom(src_crs, dst_crs, geom.__geo_interface__)
    return shp_geom.shape(mapping)


def _raster_field(
    cells: gpd.GeoDataFrame,
    raster_path: Path,
    source_label: str,
) -> dict[str, float | None]:
    """
    Per-cell zonal mean of one raster's band 1, using the coverage
    short-circuit + cell-centre mask in raster_stats.zonal_mean. Cell
    geometry/centroids are reprojected to the raster's own CRS at the read
    boundary if it differs from STORAGE_CRS (logged via the halting check
    below rather than silently assumed).
    """
    if not raster_path.exists():
        raise RuntimeError(f"{source_label} source not found: {raster_path}")

    apply_vsicurl_env()
    result: dict[str, float | None] = {}

    with rasterio.open(raster_path) as src:
        if src.crs is None:
            raise ValueError(f"{source_label} raster has no declared CRS: {raster_path}")
        needs_reproject = str(src.crs) != config.STORAGE_CRS

        for cell_id, geom, lon, lat in zip(
            cells["cell_id"], cells.geometry, cells["centroid_lon"], cells["centroid_lat"]
        ):
            cell_geom, centroid = geom, (lon, lat)
            if needs_reproject:
                cell_geom = _reproject_geom(geom, config.STORAGE_CRS, src.crs)
                (cx,), (cy,) = warp_transform(config.STORAGE_CRS, src.crs, [lon], [lat])
                centroid = (cx, cy)
            stat = zonal_mean(src, cell_geom, centroid)
            result[cell_id] = stat.value

    return result


def slope_field(cells: gpd.GeoDataFrame) -> dict[str, float | None]:
    """Mean Horn slope (degrees) — statistic frozen by decision Q3 (mean for scoring)."""
    return _raster_field(cells, config.SLOPE_RASTER_PATH, "Slope (SRTM GL3 Horn slope)")


def wind_speed_field(cells: gpd.GeoDataFrame) -> dict[str, float | None]:
    """Mean GWA v4 wind speed (m/s) at 100 m hub height — frozen decision Q2 (primary height)."""
    return _raster_field(cells, config.WIND_SPEED_RASTER_PATH, "GWA wind speed (100 m)")


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def build_cell_table(
    cells: gpd.GeoDataFrame,
    rules: list[dict],
    verbose: bool = False,
) -> gpd.GeoDataFrame:
    """Compute every per-cell field, evaluate the rules, and assemble the Eligibility_Table."""
    if verbose:
        print("    Computing protected-area overlap (CAPAD, EPSG:3577)...")
    protected = protected_area_overlap(cells)

    if verbose:
        print("    Computing urban-centre overlap (ABS UCL, EPSG:3577)...")
    urban, urban_coverage_bounds = urban_overlap(cells)

    if verbose:
        print("    Sampling slope (SRTM GL3 Horn slope, cell-centre mean)...")
    slope = slope_field(cells)

    if verbose:
        print("    Sampling wind speed (GWA v4, 100 m, cell-centre mean)...")
    wind = wind_speed_field(cells)

    u_west, u_south, u_east, u_north = urban_coverage_bounds

    rows = []
    for cell_id, lon, lat in zip(cells["cell_id"], cells["centroid_lon"], cells["centroid_lat"]):
        p_overlap, p_name = protected[cell_id]
        fields = {
            "protected_area": p_overlap,
            "protected_area_name": p_name,
            "slope_deg": slope[cell_id],
            "urban_area": urban[cell_id],
            "wind_speed_100m_ms": wind[cell_id],
        }
        eligible, exclusion_reason, triggered = rules_mod.evaluate_cell(fields, rules)

        # Non-exclusionary "soft" flag: outside the urban dataset's own
        # coverage window, `urban_area == False` is an absence of evidence,
        # not evidence of absence — flag it rather than let it pass as good.
        data_flags: list[str] = []
        in_urban_coverage = (u_west <= lon <= u_east) and (u_south <= lat <= u_north)
        if not in_urban_coverage:
            data_flags.append(
                "Urban-centre data unavailable outside New England REZ coverage "
                "(urban_area defaults to False, not confirmed)"
            )

        rows.append(
            {
                "cell_id": cell_id,
                "eligible": eligible,
                "exclusion_reason": exclusion_reason,
                "triggered_rules": rules_mod.REASON_DELIMITER.join(triggered) if triggered else None,
                "protected_area": fields["protected_area"],
                "protected_area_name": fields["protected_area_name"],
                "slope_deg": fields["slope_deg"],
                "urban_area": fields["urban_area"],
                "wind_speed_100m_ms": fields["wind_speed_100m_ms"],
                "data_flags": "; ".join(data_flags) if data_flags else None,
            }
        )

    return gpd.GeoDataFrame(rows, geometry=cells.geometry.values, crs=cells.crs)


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------


def summarise(table: gpd.GeoDataFrame) -> dict:
    """Total / eligible / excluded counts + per-rule breakdown, for logging and the report."""
    total = len(table)
    eligible = int(table["eligible"].sum())
    excluded = total - eligible

    by_rule: dict[str, int] = {}
    for reason_list in table.loc[~table["eligible"], "triggered_rules"]:
        if not reason_list:
            continue
        for name in reason_list.split(rules_mod.REASON_DELIMITER):
            by_rule[name] = by_rule.get(name, 0) + 1

    return {"total": total, "eligible": eligible, "excluded": excluded, "by_rule": by_rule}


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def _write_eligibility_table(gdf: gpd.GeoDataFrame, path: Path) -> None:
    """Atomic GeoPackage write (tmp + os.replace), mirroring grid/generate.run()."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".gpkg.tmp")
    try:
        gdf.to_file(tmp, driver="GPKG")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _write_report(
    table: gpd.GeoDataFrame,
    summary: dict,
    rules: list[dict],
    rules_path: Path,
    runtime_s: float,
    path: Path,
) -> None:
    total = summary["total"] or 1  # guard divide-by-zero for an (unexpected) empty grid
    out = io.StringIO()
    out.write("# Exclusion layer summary (S1-07)\n\n")
    out.write(banner("exclusions.apply"))
    out.write(
        "\nSee `pipeline/exclusions/__init__.py` for the scope note: this stage reads raw "
        "geographic/wind sources directly rather than a S1-06/S1-03 Feature_Table, because "
        "those stages are design-documented but not yet implemented in code.\n\n"
    )
    out.write(f"Rules config: `{rules_path}`\n\n")

    out.write("## Exclusion Summary\n\n")
    out.write(f"- Total cells: **{summary['total']:,}**\n")
    out.write(f"- Eligible: **{summary['eligible']:,}** ({100.0 * summary['eligible'] / total:.1f}%)\n")
    out.write(f"- Excluded: **{summary['excluded']:,}** ({100.0 * summary['excluded'] / total:.1f}%)\n\n")

    out.write("### By reason\n\n")
    out.write("| Rule | Description | Cells excluded | Share of total |\n|---|---|---|---|\n")
    rules_by_name = {r["name"]: r for r in rules}
    for name, count in sorted(summary["by_rule"].items(), key=lambda kv: -kv[1]):
        desc = rules_by_name.get(name, {}).get("description", "")
        out.write(f"| {name} | {desc} | {count:,} | {100.0 * count / total:.1f}% |\n")
    out.write("\n")

    n_flagged = int(table["data_flags"].notna().sum())
    out.write("### Non-exclusionary data flags\n\n")
    out.write(
        f"- Cells retained but flagged for a soft data-coverage concern (not excluded): "
        f"**{n_flagged:,}** ({100.0 * n_flagged / total:.1f}%)\n\n"
    )

    out.write("## Data-source coverage caveat\n\n")
    out.write(
        "The slope, wind-speed and urban-centre sources currently cover only the New England "
        "REZ study window, not the full NSW grid; CAPAD (protected areas) is full-NSW. Cells "
        "outside that window have `slope_deg` / `wind_speed_100m_ms` = null and are excluded "
        "by the `missing_wind_data` rule (per the Constitution: \"where critical data is "
        "missing, exclude the cell\") rather than being scored on invented data. This is a "
        "real, documented gap in Sprint 1 source coverage, not a defect in this stage — see "
        "`pipeline/exclusions/__init__.py`.\n\n"
    )

    out.write("## Rule configuration (verbatim)\n\n")
    out.write("```yaml\n")
    for r in rules:
        out.write(f"- name: {r['name']}\n")
        out.write(f"  field: {r['field']}\n")
        out.write(f"  condition: {r['condition']!r}\n")
        if r.get("threshold") is not None:
            out.write(f"  threshold: {r['threshold']}\n")
    out.write("```\n\n")

    out.write(f"## Runtime\n\n- {runtime_s:.2f}s for {summary['total']:,} cells\n")

    atomic_write_text(path, out.getvalue())


# ---------------------------------------------------------------------------
# Validation (no silent passes)
# ---------------------------------------------------------------------------


def validate(table_path: Path, grid_path: Path) -> dict:
    """No-silent-passes validation over the written Eligibility_Table."""
    checks: list[dict] = []

    def check(name, expected, observed, passed):
        checks.append({"name": name, "expected": expected, "observed": observed, "passed": bool(passed)})

    table = gpd.read_file(table_path)
    grid = gpd.read_file(grid_path)

    check("Row count == grid cell count", len(grid), len(table), len(table) == len(grid))

    grid_ids = set(grid["cell_id"])
    table_ids = set(table["cell_id"])
    missing = grid_ids - table_ids
    extra = table_ids - grid_ids
    check(
        "cell_id set matches grid exactly",
        "0 missing, 0 extra",
        f"{len(missing)} missing, {len(extra)} extra",
        not missing and not extra,
    )

    required_cols = {"cell_id", "eligible", "exclusion_reason"}
    observed_cols = set(table.columns)
    check(
        "Required output columns present",
        sorted(required_cols),
        sorted(observed_cols & required_cols),
        required_cols.issubset(observed_cols),
    )

    eligible_mask = table["eligible"].astype(bool)
    reason_present = table["exclusion_reason"].notna() & (
        table["exclusion_reason"].astype(str).str.len() > 0
    )
    inconsistent = int(((eligible_mask & reason_present) | (~eligible_mask & ~reason_present)).sum())
    check(
        "eligible/exclusion_reason are consistent (never both set, never both empty)",
        0,
        inconsistent,
        inconsistent == 0,
    )

    n_eligible = int(eligible_mask.sum())
    n_excluded = int((~eligible_mask).sum())
    check("eligible + excluded == total", len(table), n_eligible + n_excluded, n_eligible + n_excluded == len(table))

    passed = sum(1 for c in checks if c["passed"])
    return {"checks": checks, "passed": passed, "total": len(checks)}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(verbose: bool = False, rules_path: Path | None = None) -> dict:
    """
    Run the exclusion-layer stage.

    Parameters
    ----------
    verbose : bool
        Enable detailed per-field logging.
    rules_path : Path | None
        Path to the exclusion rules YAML. None uses the packaged default
        (`pipeline/exclusions/exclusion_rules.yaml`).

    Returns
    -------
    dict with keys: eligibility_table, report, n_cells, n_eligible,
    n_excluded, runtime_s, validation (the validate() result dict).

    Raises on any halting condition (missing/invalid grid, missing/
    unreadable source, malformed rules file) — no summary dict is returned
    in that case, so the orchestrator halts with a non-zero exit.
    """
    t0 = time.time()
    rules_path = rules_path or config.DEFAULT_RULES_PATH

    print("  [1/4] Loading exclusion rules...")
    rules = rules_mod.load_rules(rules_path)
    print(f"    {len(rules)} rule(s) loaded from {rules_path}")

    print("  [2/4] Reading analysis grid...")
    cells = read_grid_cells(config.GRID_PATH)
    print(f"    {len(cells):,} cells")

    print("  [3/4] Computing per-cell fields and applying rules...")
    table = build_cell_table(cells, rules, verbose=verbose)

    summary = summarise(table)
    total = summary["total"] or 1
    print(
        f"    Eligible: {summary['eligible']:,}/{summary['total']:,} "
        f"({100.0 * summary['eligible'] / total:.1f}%)"
    )
    for name, count in sorted(summary["by_rule"].items(), key=lambda kv: -kv[1]):
        print(f"      excluded by {name}: {count:,}")

    runtime_s = time.time() - t0

    print("  [4/4] Writing outputs...")
    table_path = config.EXCLUSIONS_DIR / config.OUTPUT_FILENAME
    _write_eligibility_table(table, table_path)
    print(f"    -> {table_path.relative_to(config.PROJECT_ROOT)}")

    report_path = config.EXCLUSIONS_META_DIR / config.REPORT_FILENAME
    _write_report(table, summary, rules, rules_path, runtime_s, report_path)
    print(f"    -> {report_path.relative_to(config.PROJECT_ROOT)}")

    validation = validate(table_path, config.GRID_PATH)
    print(f"    Validation: {validation['passed']}/{validation['total']} checks passed")

    return {
        "eligibility_table": table_path,
        "report": report_path,
        "n_cells": summary["total"],
        "n_eligible": summary["eligible"],
        "n_excluded": summary["excluded"],
        "runtime_s": runtime_s,
        "validation": validation,
    }
