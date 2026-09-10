"""
Wind feature-builder stage (S1-03) — per-cell wind feature table.

Aggregates the NSW-wide GWA wind-speed clip onto the common analysis grid
(DATA/grid/nsw_analysis_grid.gpkg, S1-02): one row per cell_id carrying the
mean wind speed at 100 m (frozen decisions Q1/Q2), its units, its data source,
and a confidence flag. Cells with zero valid GWA pixels are flagged
``no_data`` with a null value — never back-filled.

This stage CONSUMES the grid, so it is registered in config.STAGES AFTER the
``grid`` stage, not inline with the other wind.* stages.

Importable entry point:
    from pipeline.wind.features import run
    result = run(verbose=False)

Output:
    DATA/wind-resource/features/gwa_v4_wind-feature_<vintage>_nsw.gpkg
    DATA/wind-resource/metadata/wind_feature_method.md
    DATA/wind-resource/metadata/download_manifest.json (merged, not overwritten)
    DATA/wind-resource/DATA_PROVENANCE.md (derived-layer section)
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.errors import WindowError
from rasterio.features import geometry_mask
from rasterio.windows import Window, from_bounds

from . import config
from ..common.geo import atomic_write_text, banner, utc_now
from ..grid.config import COMPUTATION_CRS, GRID_OUTPUT_DIR, STORAGE_CRS

GRID_PATH = GRID_OUTPUT_DIR / "nsw_analysis_grid.gpkg"
GRID_LAYER = "nsw_grid"
FEATURE_LAYER = "wind_features"

_PROVENANCE_BEGIN = "<!-- BEGIN wind.features derived layer (generated) -->"
_PROVENANCE_END = "<!-- END wind.features derived layer (generated) -->"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class CellStat:
    """Zonal block result for one analysis cell (Req 3.2).

    Invariant: n_valid + n_nodata == total native pixels in the cell's
    selection (pixel-centre inclusion rule).
    """

    value: float | None  # aggregated statistic; None when n_valid == 0 (Req 2.5)
    n_valid: int         # non-NoData native pixels in the cell's block
    n_nodata: int        # NoData/masked/out-of-extent pixels in the block
    in_coverage: bool    # False -> cell centroid outside raster bounds (Req 5.3)


# ---------------------------------------------------------------------------
# Grid input (Req 2.3, 2.4, 6.6)
# ---------------------------------------------------------------------------


def read_grid_cells(grid_path: Path) -> gpd.GeoDataFrame:
    """
    Read cell_id + geometry from the analysis-grid GeoPackage (EPSG:4326).

    cell_id values are reused byte-for-byte in grid order — never modified,
    renumbered, or reordered (Req 2.4).
    """
    if not grid_path.exists():
        raise FileNotFoundError(
            f"analysis grid not found: {grid_path} — generate it first with "
            f"`python -m pipeline --only grid`"
        )
    grid = gpd.read_file(grid_path, layer=GRID_LAYER)
    if "cell_id" not in grid.columns:
        raise ValueError(f"grid {grid_path} has no 'cell_id' column")
    duplicated = grid["cell_id"][grid["cell_id"].duplicated()]
    if not duplicated.empty:
        sample = ", ".join(duplicated.head(5).tolist())
        raise ValueError(
            f"grid {grid_path} has {len(duplicated)} duplicate cell_id values "
            f"(e.g. {sample}) — refusing to build features on an ambiguous key"
        )
    return grid[["cell_id", "geometry"]]


# ---------------------------------------------------------------------------
# CRS boundary (Req 7.1, 7.4)
# ---------------------------------------------------------------------------


def _assert_storage_crs(grid: gpd.GeoDataFrame, src: "rasterio.DatasetReader") -> None:
    """
    Assert grid and raster CRS both resolve to the storage CRS (EPSG:4326).

    Raises ValueError reporting any mismatch — never silently reprojects
    (Req 7.4). Under Option A no reprojection of the GWA raster ever occurs.
    """
    expected = int(STORAGE_CRS.split(":")[1])
    if grid.crs is None:
        raise ValueError(f"grid has no declared CRS (expected {STORAGE_CRS})")
    if grid.crs.to_epsg() != expected:
        raise ValueError(
            f"grid CRS is {grid.crs} but the storage CRS is {STORAGE_CRS} — "
            f"refusing to silently reproject"
        )
    if src.crs is None:
        raise ValueError(f"raster has no declared CRS (expected {STORAGE_CRS})")
    if src.crs.to_epsg() != expected:
        raise ValueError(
            f"raster CRS is {src.crs} but the storage CRS is {STORAGE_CRS} — "
            f"reproject explicitly upstream rather than here"
        )


# ---------------------------------------------------------------------------
# Zonal block statistic (Req 2.1, 2.5, 3.1-3.4, 5.3)
# ---------------------------------------------------------------------------


def _cell_in_coverage(src: "rasterio.DatasetReader", cell_geom) -> bool:
    """Cell-centroid-in-raster-bounds fast path (Req 5.3)."""
    centroid = cell_geom.centroid
    b = src.bounds
    return (b.left <= centroid.x <= b.right) and (b.bottom <= centroid.y <= b.top)


def _zonal_block_stat(
    src: "rasterio.DatasetReader",
    cell_geom,
    stat: str = "mean",
) -> CellStat:
    """
    Aggregate the native pixels whose centre lies inside the cell polygon.

    Pixel-inclusion basis: cell-centre rule (geometry_mask, all_touched=False)
    — deterministic for a given raster + cell (Req 3.1). Valid pixels are
    finite, unmasked values; NoData/masked pixels and in-cell positions
    outside the raster's data extent count as NoData (Req 3.2, 5.3). The GWA
    clips declare NoData as NaN, so validity is NaN-aware, never an equality
    test. Applies src.scales. value is None when n_valid == 0 (Req 2.5).
    """
    if stat != "mean":
        raise ValueError(
            f"unsupported aggregation statistic {stat!r} — frozen decision Q1 "
            f"selects 'mean'; changing it requires the data-spec §8 process"
        )

    # The cell's full block in pixel space. Grid cells are axis-aligned
    # rectangles, so the bounds window is the cell's own extent even when it
    # overhangs the raster edge.
    block = from_bounds(*cell_geom.bounds, transform=src.transform)
    block = block.round_offsets().round_lengths()
    n_rows, n_cols = int(block.height), int(block.width)
    if n_rows <= 0 or n_cols <= 0:
        return CellStat(None, 0, 0, _cell_in_coverage(src, cell_geom))

    inside = geometry_mask(
        [cell_geom],
        out_shape=(n_rows, n_cols),
        transform=src.window_transform(block),
        all_touched=False,
        invert=True,
    )
    total = int(inside.sum())
    in_coverage = _cell_in_coverage(src, cell_geom)

    try:
        window = block.intersection(Window(0, 0, src.width, src.height))
    except WindowError:
        window = None
    if window is None or window.width <= 0 or window.height <= 0:
        return CellStat(None, 0, total, in_coverage)

    data = src.read(1, window=window, masked=True)
    finite = ~np.ma.getmaskarray(data) & np.isfinite(data.data)

    # Align the read window inside the cell's full block frame; positions the
    # read never covered stay invalid (out-of-extent counts as NoData).
    r0 = int(window.row_off - block.row_off)
    c0 = int(window.col_off - block.col_off)
    inside_read = inside[r0 : r0 + int(window.height), c0 : c0 + int(window.width)]
    valid = inside_read & finite

    n_valid = int(valid.sum())
    if n_valid == 0:
        return CellStat(None, 0, total, in_coverage)

    scale = src.scales[0] if src.scales else 1.0
    values = data.data[valid].astype(np.float64) * scale
    return CellStat(float(np.mean(values)), n_valid, total - n_valid, in_coverage)


# ---------------------------------------------------------------------------
# Confidence (Req 5.1, 5.2, 5.3)
# ---------------------------------------------------------------------------


def _confidence_flag(stat: CellStat) -> str:
    """valid iff the cell has at least one valid GWA pixel, else no_data."""
    return config.CONF_VALID if stat.n_valid >= 1 else config.CONF_NODATA


# ---------------------------------------------------------------------------
# Writers (Req 4.6, 9.4)
# ---------------------------------------------------------------------------


def _write_feature_table(gdf: gpd.GeoDataFrame, path: Path) -> None:
    """Atomic GeoPackage write (tmp keeps .gpkg suffix for driver inference)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.stem + "_tmp.gpkg")
    try:
        gdf.to_file(tmp_path, driver="GPKG", layer=FEATURE_LAYER)
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _write_report(report_text: str, path: Path) -> None:
    """Atomic write of the method report (banner included in the text)."""
    atomic_write_text(path, report_text)


def _build_report(
    source_raster: Path,
    n_cells: int,
    n_valid: int,
    n_nodata: int,
    stats: dict,
    checks: list[dict],
) -> str:
    """Render the method report (Req 1.2, 1.3, 3.5, 5.5, 9.1-9.4)."""
    check_rows = "\n".join(
        f"| {c['name']} | {c['expected']} | {c['observed']} | "
        f"{'PASS' if c['passed'] else '**FAIL**'} |"
        for c in checks
    )
    stats_line = (
        f"min {stats['min']:.3f} / max {stats['max']:.3f} / mean {stats['mean']:.3f} "
        f"{config.WIND_VARIABLE_UNITS}"
        if n_valid
        else "no valid cells — no statistics"
    )
    return f"""# Wind feature layer — method report (S1-03)

{banner('wind.features')}

## 1. Variable selection (Req 1)

| Item | Value |
|---|---|
| Wind_Variable | `{config.WIND_VARIABLE}` |
| Hub height | 100 m |
| Units | {config.WIND_VARIABLE_UNITS} |
| Source raster | `{source_raster.name}` |
| Data source | {config.WIND_DATA_SOURCE} |
| Vintage token | {config.WIND_FEATURE_VINTAGE} (GWA 4.0 country GeoTIFF set, published June 2025 per the download manifest) |

**Justification.** Mean wind speed at 100 m is the single most defensible MVP
wind-resource variable: the hub height implements frozen decision Q2 (100 m
primary, consistent with the GWA capacity-factor layers' hub height) and the
statistic implements frozen decision Q1 (mean — single stable statistic; the
aggregation-sensitivity evidence lives in `aggregation_sensitivity.md`). Wind
speed is preferred over power density for the MVP because it is directly
interpretable and embeds no air-density or Weibull-distribution assumptions;
the power-density layer remains available in `DATA/wind-resource/` as a
criterion input for later sprints. The value is derived exclusively from the
GWA raster — never from any suitability score (Req 1.4).

**Coverage note.** The source raster is the NSW-wide clip (deviation from the
S1-03 design.md's New-England-REZ filename, recorded in the data-spec Change
History). GWA carries real values over ocean, so offshore cells receive valid
wind speeds; land-masking is deferred to S1-06/S1-07 per the grid decision
document.

## 2. Aggregation method (Req 2, 3)

- **Statistic:** {config.WIND_AGG_STATISTIC} (frozen decision Q1).
- **Pixel-inclusion basis:** cell-centre rule — a native GWA pixel belongs to
  a cell iff the pixel centre lies within the cell polygon
  (`rasterio.features.geometry_mask`, `all_touched=False`). Deterministic:
  the same raster + cell always yields the same pixel set.
- **Partial-cell boundary rule (verbatim):** "for cells overlapping the
  raster edge, in-cell pixel positions outside the raster's data extent are
  counted as NoData; the cell-centre rule still yields a deterministic
  selection."
- **Block alignment:** the grid origin is snapped to the GWA lattice
  (Option A), so every fully-covered cell selects an exact 20×20 = 400
  native-pixel block with no reprojection or interpolation of the raster.
- **NoData rule:** the GWA clip declares NoData as NaN; valid pixels are
  finite, unmasked values (NaN-aware test, never `== nodata`). NoData pixels
  are excluded from the statistic. Invariant: n_valid + n_nodata equals the
  total pixels in the cell's selection.

## 3. NoData / zero-valid occurrences (Req 2.5, 9.2)

| Count | Value |
|---|---|
| Total cells | {n_cells:,} |
| Valid cells | {n_valid:,} |
| No-data cells (zero valid pixels) | {n_nodata:,} |
| valid + no_data == total | {str(n_valid + n_nodata == n_cells)} |

## 4. Confidence flags (Req 5)

Enumerated values: `{config.CONF_VALID}`, `{config.CONF_NODATA}`.
Assignment rule: `{config.CONF_VALID}` iff the cell has ≥ 1 valid GWA pixel;
otherwise `{config.CONF_NODATA}` with a null Wind_Variable value. The builder
never substitutes a default, interpolated, extrapolated, or hard-coded number
for a zero-valid cell (Req 5.4).

## 5. CRS handling (Req 7)

Grid, source raster, and output are all {STORAGE_CRS} (asserted at run time;
mismatches halt the stage — never silently reprojected). No reprojection of
the GWA raster occurs under Option A. This stage performs no distance or area
computation; were any added, it would use {COMPUTATION_CRS}.

## 6. Output statistics (Req 9)

{config.WIND_VARIABLE} across valid cells: {stats_line}

## 7. Validation checks (Req 10)

| Check | Expected | Observed | Result |
|---|---|---|---|
{check_rows}
"""


# ---------------------------------------------------------------------------
# Provenance (Req 8)
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_provenance(table_path: Path, source_raster: Path, manifest_path: Path) -> None:
    """
    Record the derived feature table: read-merge-write a record into
    download_manifest.json (Req 8.2) and refresh the derived-layer section of
    DATA_PROVENANCE.md (Req 8.1, 8.3). Never clobbers download records.
    """
    record = {
        "output_file": str(table_path.relative_to(config.PROJECT_ROOT)),
        "stage": "wind.features",
        "derived_from": str((config.WIND_DIR / source_raster.name).relative_to(config.PROJECT_ROOT)),
        "sha256": _sha256(table_path),
        "local_bytes": table_path.stat().st_size,
        "generated_utc": utc_now(),
    }
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    derived = [
        r for r in manifest.get("derived_features", [])
        if r.get("output_file") != record["output_file"]
    ]
    derived.append(record)
    manifest["derived_features"] = derived
    atomic_write_text(manifest_path, json.dumps(manifest, indent=2) + "\n")

    section = (
        f"{_PROVENANCE_BEGIN}\n"
        f"## Derived layer — wind feature table (S1-03)\n\n"
        f"- **File:** `{record['output_file']}`\n"
        f"- **Derived from:** `{record['derived_from']}` ({config.WIND_DATA_SOURCE})\n"
        f"- **Method:** {config.WIND_AGG_STATISTIC} of the 20×20 native GWA pixels per "
        f"0.05° analysis cell (cell-centre inclusion; NoData excluded; zero-valid "
        f"cells flagged `{config.CONF_NODATA}` with a null value).\n"
        f"- **Regenerable:** yes — fully derived from the GWA raster and the S1-02 "
        f"analysis grid via `python -m pipeline --only wind.features`.\n"
        f"- **SHA-256:** `{record['sha256']}`\n"
        f"- **Generated (UTC):** {record['generated_utc']}\n"
        f"{_PROVENANCE_END}\n"
    )
    provenance_path = config.WIND_DIR / "DATA_PROVENANCE.md"
    text = provenance_path.read_text() if provenance_path.exists() else ""
    if _PROVENANCE_BEGIN in text and _PROVENANCE_END in text:
        head, rest = text.split(_PROVENANCE_BEGIN, 1)
        _, tail = rest.split(_PROVENANCE_END, 1)
        text = head + section.rstrip("\n") + tail
    else:
        text = text.rstrip("\n") + "\n\n" + section
    atomic_write_text(provenance_path, text)


# ---------------------------------------------------------------------------
# Validation (Req 10) — no silent passes
# ---------------------------------------------------------------------------


def validate(feature_table_path: Path, grid_path: Path) -> dict:
    """
    No-silent-passes checks over the written table. Returns
    {"checks": [{name, expected, observed, passed}, ...], "passed": int,
    "total": int}. Every check reports expected vs observed (Req 10.4).
    """
    table = gpd.read_file(feature_table_path, layer=FEATURE_LAYER)
    grid = gpd.read_file(grid_path, layer=GRID_LAYER)
    values = table[config.WIND_VARIABLE]
    non_null = values.dropna()

    checks: list[dict] = []

    def check(name, expected, observed, passed):
        checks.append({"name": name, "expected": expected,
                       "observed": observed, "passed": bool(passed)})

    check(
        "row count equals grid cell count",
        f"{len(grid)} rows",
        f"{len(table)} rows",
        len(table) == len(grid),
    )
    if non_null.empty:
        check(
            "non-null values within plausible range",
            f"[{config.WIND_PLAUSIBLE_MIN}, {config.WIND_PLAUSIBLE_MAX}] "
            f"{config.WIND_VARIABLE_UNITS}",
            "no non-null values",
            True,
        )
    else:
        check(
            "non-null values within plausible range",
            f"[{config.WIND_PLAUSIBLE_MIN}, {config.WIND_PLAUSIBLE_MAX}] "
            f"{config.WIND_VARIABLE_UNITS}",
            f"min {non_null.min():.3f} / max {non_null.max():.3f}",
            bool(
                (non_null >= config.WIND_PLAUSIBLE_MIN).all()
                and (non_null <= config.WIND_PLAUSIBLE_MAX).all()
            ),
        )
    nodata_with_value = int(
        (table["confidence_flag"] == config.CONF_NODATA)[values.notna()].sum()
    )
    check(
        "no-data cells have null value",
        "0 no-data rows with a value",
        f"{nodata_with_value} no-data rows with a value",
        nodata_with_value == 0,
    )
    bad_flags = int(
        (~table["confidence_flag"].isin([config.CONF_VALID, config.CONF_NODATA])).sum()
    )
    check(
        "confidence_flag within enumerated set",
        f"all flags in {{{config.CONF_VALID}, {config.CONF_NODATA}}}",
        f"{bad_flags} rows outside the set",
        bad_flags == 0,
    )

    return {
        "checks": checks,
        "passed": sum(1 for c in checks if c["passed"]),
        "total": len(checks),
    }


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


def run(verbose: bool = False) -> dict:
    """
    Build the per-cell wind feature table on the common analysis grid.

    Reads the grid (cell_id + geometry) and the source GWA raster, derives one
    Wind_Variable per cell by block-aggregating the 20×20 native GWA pixels
    that fall in each cell, writes the Feature_Table atomically as a
    GeoPackage, writes a do-not-edit method report, and records provenance.

    Returns
    -------
    dict with keys:
        "feature_table" : Path   # output GeoPackage
        "report"        : Path   # method report
        "manifest"      : Path   # updated download manifest
        "n_cells"       : int    # rows written == grid cell_id count (Req 2.3)
        "n_valid"       : int    # cells with valid wind data (Req 9.2)
        "n_nodata"      : int    # cells flagged no-data (Req 9.2)
        "stats"         : dict   # {"min","max","mean"} over valid cells (Req 9.1)

    Raises
    ------
    FileNotFoundError / ValueError / RuntimeError on any halting condition
    (missing grid or raster, missing/duplicate cell_id, undeclared or
    non-EPSG:4326 CRS, failed validation check) so the orchestrator halts
    non-zero (Req 6.6).
    """
    source_raster = config.WIND_DIR / config.WIND_FEATURE_SOURCE
    print(f"  Building wind feature layer ({config.WIND_VARIABLE}, "
          f"{config.WIND_AGG_STATISTIC})...")
    print(f"    Grid   : {GRID_PATH.relative_to(config.PROJECT_ROOT)}")
    print(f"    Raster : {source_raster.relative_to(config.PROJECT_ROOT)}")

    if not source_raster.exists():
        raise FileNotFoundError(
            f"source GWA raster not found: {source_raster} — download it with "
            f"`python -m pipeline --only wind.download "
            f"--bbox 141.01125,-37.51125,153.66125,-28.16125 --area-name nsw "
            f"--heights 100`"
        )

    grid = read_grid_cells(GRID_PATH)
    n_cells = len(grid)

    t0 = time.time()
    cell_values: list[float] = []
    flags: list[str] = []
    n_valid_cells = 0
    with rasterio.open(source_raster) as src:
        _assert_storage_crs(grid, src)
        if verbose:
            print(f"    CRS    : grid {grid.crs}, raster {src.crs} "
                  f"(storage {STORAGE_CRS}, no reprojection)")
        for i, geom in enumerate(grid.geometry.values):
            stat = _zonal_block_stat(src, geom, config.WIND_AGG_STATISTIC)
            cell_values.append(np.nan if stat.value is None else stat.value)
            flags.append(_confidence_flag(stat))
            if stat.n_valid >= 1:
                n_valid_cells += 1
            if verbose and (i + 1) % 10000 == 0:
                print(f"    ... {i + 1:,}/{n_cells:,} cells")

    n_nodata_cells = n_cells - n_valid_cells
    elapsed = time.time() - t0

    values = np.asarray(cell_values, dtype=np.float64)
    finite = values[np.isfinite(values)]
    stats = {
        "min": float(finite.min()) if finite.size else None,
        "max": float(finite.max()) if finite.size else None,
        "mean": float(finite.mean()) if finite.size else None,
    }

    table = gpd.GeoDataFrame(
        {
            "cell_id": grid["cell_id"].values,
            config.WIND_VARIABLE: values,
            "units": config.WIND_VARIABLE_UNITS,
            "data_source": config.WIND_DATA_SOURCE,
            "confidence_flag": flags,
        },
        geometry=grid.geometry.values,
        crs=STORAGE_CRS,
    )

    table_path = (
        config.WIND_FEATURES_DIR
        / f"gwa_v4_wind-feature_{config.WIND_FEATURE_VINTAGE}_nsw.gpkg"
    )
    _write_feature_table(table, table_path)

    print(f"    {n_cells:,} cells in {elapsed:.1f}s — "
          f"{n_valid_cells:,} valid, {n_nodata_cells:,} no-data")
    if finite.size:
        print(f"    {config.WIND_VARIABLE}: min {stats['min']:.3f} / "
              f"max {stats['max']:.3f} / mean {stats['mean']:.3f} "
              f"{config.WIND_VARIABLE_UNITS}")
    print(f"    Output : {table_path.relative_to(config.PROJECT_ROOT)}")

    result = validate(table_path, GRID_PATH)
    for c in result["checks"]:
        status = "PASS" if c["passed"] else "**FAIL**"
        print(f"    [{status}] {c['name']}: expected {c['expected']}, "
              f"observed {c['observed']}")
    print(f"    {result['passed']}/{result['total']} validation checks passed")

    report_path = config.WIND_META_DIR / "wind_feature_method.md"
    report = _build_report(
        source_raster, n_cells, n_valid_cells, n_nodata_cells, stats,
        result["checks"],
    )
    _write_report(report, report_path)
    print(f"    Report : {report_path.relative_to(config.PROJECT_ROOT)}")

    manifest_path = config.WIND_META_DIR / "download_manifest.json"
    _record_provenance(table_path, source_raster, manifest_path)

    if result["passed"] != result["total"]:
        failed = [c["name"] for c in result["checks"] if not c["passed"]]
        raise RuntimeError(
            f"wind feature table failed validation: {', '.join(failed)} "
            f"(see report {report_path})"
        )

    return {
        "feature_table": table_path,
        "report": report_path,
        "manifest": manifest_path,
        "n_cells": n_cells,
        "n_valid": n_valid_cells,
        "n_nodata": n_nodata_cells,
        "stats": stats,
    }
