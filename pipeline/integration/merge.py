"""
S1-08 — Integrated NSW Feature Table (pipeline stage `integration`).

Left-joins the five per-cell layers produced by S1-03..S1-07 onto the S1-02
analysis grid by `cell_id` and writes one integrated table:

    DATA/integration/optmining_integrated-features_2026_nsw.gpkg  (with geometry)
    DATA/integration/optmining_integrated-features_2026_nsw.csv   (without)
    DATA/integration/metadata/integration_method.md                — method report
    DATA/integration/metadata/merge_validation.md                  — every check
    DATA/integration/metadata/integration_manifest.json            — hashes, inputs
    DATA/integration/DATA_PROVENANCE.md                            — generated block

Design rules (Constitution + pipeline/README.md "Design Principles"):
  * Left joins from the grid; the row count is asserted after every join, so
    no cell is ever dropped or duplicated. Excluded cells are retained and
    marked `eligible = False`.
  * Nothing is computed, reprojected or back-filled here: every input must
    already be in the storage CRS (EPSG:4326) or the stage halts; upstream
    nulls stay null and their counts are checked to be unchanged after the
    join ("no NaN inflation").
  * `data_confidence` is NOT derived here — that is S1-09's job. The five
    per-layer confidence flags are carried through under per-layer names and
    an objective `n_missing_features` count is added.
  * Every validation check reports its expected and observed values, even
    when it passes (no silent passes).

Usage:
    from pipeline.integration.merge import run
    run(verbose=True)
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import geopandas as gpd
import pandas as pd
import pyogrio
from pyproj import CRS

from . import config
from ..common.geo import atomic_write_json, atomic_write_text, sha256_file


# ---------------------------------------------------------------------------
# Layer specifications
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LayerSpec:
    """
    One upstream per-cell layer to join.

    columns maps TARGET column name (in the integrated table) -> SOURCE column
    name (in the upstream layer). `cell_id` is the implicit join key and is
    never listed. `stage` is the CLI stage that regenerates the layer, quoted
    in the error when the file is missing. `enum_checks` maps target columns
    to their permitted vocabulary (used by validate()).
    """

    name: str
    path: Path
    layer: str | None
    stage: str
    columns: dict[str, str]
    enum_checks: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def source_columns(self) -> tuple[str, ...]:
        return tuple(self.columns.values())


def layer_specs() -> list[LayerSpec]:
    """The five layers in join order, built at call time from config."""
    return [
        LayerSpec(
            name="wind",
            path=config.WIND_PATH,
            layer=config.WIND_LAYER,
            stage="wind.features",
            columns={
                "wind_speed": "wind_speed_100m",
                "wind_confidence": "confidence_flag",
            },
            enum_checks={"wind_confidence": config.WIND_CONFIDENCE_LEVELS},
        ),
        LayerSpec(
            name="geographic",
            path=config.GEOGRAPHIC_PATH,
            layer=config.GEOGRAPHIC_LAYER,
            stage="geographic.features",
            columns={
                "elevation_m": "elevation_m",
                "slope_deg": "slope_deg",
                "tri": "tri",
                "land_use": "land_use",
                "protected_area": "protected_area",
                "protected_area_name": "protected_area_name",
                "geo_confidence": "confidence_flag",
            },
            enum_checks={"geo_confidence": config.GEO_CONFIDENCE_LEVELS},
        ),
        LayerSpec(
            name="infrastructure",
            path=config.INFRA_PATH,
            layer=config.INFRA_LAYER,
            stage="infrastructure.features",
            columns={
                "dist_transmission_km": "dist_transmission_km",
                "dist_substation_km": "dist_substation_km",
                "dist_connection_km": "dist_connection_km",
                "inside_rez": "inside_rez",
                "rez_name": "rez_name",
                "infra_confidence": "confidence_flag",
            },
            enum_checks={"infra_confidence": config.INFRA_CONFIDENCE_LEVELS},
        ),
        LayerSpec(
            name="demand",
            path=config.DEMAND_PATH,
            layer=config.DEMAND_LAYER,
            stage="demand.feature",
            columns={
                "demand_proxy": "demand_proxy",
                "source_region": "source_region",
                "demand_confidence": "confidence_flag",
            },
            enum_checks={"demand_confidence": config.DEMAND_CONFIDENCE_LEVELS},
        ),
        LayerSpec(
            name="exclusions",
            path=config.EXCLUSIONS_PATH,
            layer=config.EXCLUSIONS_LAYER,
            stage="exclusions",
            columns={
                "eligible": "eligible",
                "exclusion_reason": "exclusion_reason",
                "triggered_rules": "triggered_rules",
                "data_flags": "data_flags",
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Input readers — halt loudly, never repair
# ---------------------------------------------------------------------------


def _crs_string(crs) -> str:
    """Normalise a CRS to 'AUTHORITY:CODE' where possible (else WKT/PROJ string)."""
    parsed = CRS.from_user_input(crs)
    authority = parsed.to_authority()
    return f"{authority[0]}:{authority[1]}" if authority else parsed.to_string()


def _resolve_layer(path: Path, layer: str | None) -> str:
    """Return the layer to read; auto-detect only when the file has exactly one."""
    names = [str(row[0]) for row in pyogrio.list_layers(path)]
    if layer is None:
        if len(names) != 1:
            raise ValueError(
                f"{path} has {len(names)} layers ({names}); cannot auto-detect — "
                f"expected exactly one layer"
            )
        return names[0]
    if layer not in names:
        raise ValueError(f"{path} has no layer {layer!r} (found {names})")
    return layer


def read_layer(
    path: Path,
    layer: str | None,
    *,
    stage: str,
    required_columns: Sequence[str] = (),
    read_geometry: bool = False,
) -> tuple[pd.DataFrame | gpd.GeoDataFrame, dict]:
    """
    Read one per-cell layer and return (frame, info).

    Halts (rather than producing a partial or silently reprojected join) on:
    a missing file (naming the stage that regenerates it), an ambiguous or
    absent layer, an undeclared CRS, a CRS other than the storage CRS, a
    missing/null/duplicate `cell_id`, or a missing required column.

    info = {path, layer, rows, crs, sha256, bytes} for the method report and
    manifest. With read_geometry=False only attributes are loaded, so the
    grid's polygons are the only geometry held in memory during the merge.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{stage} output not found: {path} — run "
            f"`python -m pipeline --only {stage}` first."
        )
    layer_name = _resolve_layer(path, layer)

    declared = pyogrio.read_info(path, layer=layer_name).get("crs")
    if not declared:
        raise ValueError(
            f"{path} layer {layer_name!r} has no declared CRS; refusing to assume "
            f"{config.STORAGE_CRS} (Constitution: never convert silently)"
        )
    crs = _crs_string(declared)
    if crs != config.STORAGE_CRS:
        raise ValueError(
            f"{path} layer {layer_name!r} is stored in {crs} but the storage CRS is "
            f"{config.STORAGE_CRS} — refusing to silently reproject; regenerate it "
            f"upstream with `python -m pipeline --only {stage}`"
        )

    if read_geometry:
        frame = gpd.read_file(path, layer=layer_name)
    else:
        frame = pyogrio.read_dataframe(path, layer=layer_name, read_geometry=False)

    if "cell_id" not in frame.columns:
        raise ValueError(
            f"{path} layer {layer_name!r} has no 'cell_id' column "
            f"(found columns: {list(frame.columns)})"
        )
    n_null = int(frame["cell_id"].isna().sum())
    if n_null:
        raise ValueError(f"{path} layer {layer_name!r} has {n_null} null cell_id value(s)")
    duplicates = frame["cell_id"][frame["cell_id"].duplicated()].unique().tolist()
    if duplicates:
        raise ValueError(
            f"{path} layer {layer_name!r} has {len(duplicates)} duplicate cell_id "
            f"value(s) (e.g. {duplicates[:5]}) — refusing to join on an ambiguous key"
        )
    missing = [c for c in required_columns if c not in frame.columns]
    if missing:
        raise ValueError(
            f"{path} layer {layer_name!r} lacks required column(s) {missing} "
            f"(found columns: {list(frame.columns)})"
        )

    info = {
        "path": path,
        "layer": layer_name,
        "rows": int(len(frame)),
        "crs": crs,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }
    return frame, info


GRID_REQUIRED_COLUMNS = ("centroid_lat", "centroid_lon", "area_km2")


def read_grid(path: Path, layer: str) -> tuple[gpd.GeoDataFrame, dict]:
    """Read the S1-02 grid with geometry; the only layer whose polygons are kept."""
    return read_layer(
        path, layer, stage="grid",
        required_columns=GRID_REQUIRED_COLUMNS, read_geometry=True,
    )


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------

# Grid identity columns carried verbatim (S1-02); geometry is appended last.
GRID_COLUMNS = ("cell_id", "centroid_lat", "centroid_lon", "area_km2")

# Column order of the integrated table. Names follow the S1-08 ticket (and the
# S1-10 weights config); the source of each is in LayerSpec.columns and is
# tabulated in the method report.
OUTPUT_COLUMNS = [
    "cell_id", "centroid_lat", "centroid_lon", "area_km2",
    "wind_speed", "wind_confidence",
    "demand_proxy", "source_region", "demand_confidence",
    "dist_transmission_km", "dist_substation_km", "dist_connection_km",
    "inside_rez", "rez_name", "infra_confidence",
    "elevation_m", "slope_deg", "tri", "land_use", "protected_area",
    "protected_area_name", "geo_confidence",
    "eligible", "exclusion_reason", "triggered_rules", "data_flags",
    "n_missing_features",
]

# The ten feature columns downstream scoring consumes (the ticket's feature
# rows). n_missing_features counts nulls over exactly these. `tri` is excluded
# for the same reason S1-06 keeps it out of its confidence flag (Glen-Innes
# only by design); names, regions and confidence flags are not features.
SCORED_FEATURE_COLUMNS = (
    "wind_speed", "demand_proxy", "dist_transmission_km", "dist_substation_km",
    "dist_connection_km", "inside_rez", "elevation_m", "slope_deg", "land_use",
    "protected_area",
)

# Boolean columns: numpy bool when null-free, pandas nullable boolean otherwise
# (so a null is a null in both the GeoPackage and the CSV, never "<NA>").
BOOL_COLUMNS = ("inside_rez", "protected_area", "eligible")


def compute_n_missing_features(frame: pd.DataFrame) -> pd.Series:
    """Row-wise count of nulls over SCORED_FEATURE_COLUMNS (int64)."""
    return frame[list(SCORED_FEATURE_COLUMNS)].isna().sum(axis=1).astype("int64")


def _normalise_bool(series: pd.Series) -> pd.Series:
    if series.isna().any():
        return series.astype("boolean")
    return series.astype(bool)


# ---------------------------------------------------------------------------
# Merge core (pure)
# ---------------------------------------------------------------------------


def merge_layers(
    grid: gpd.GeoDataFrame,
    layers: dict[str, pd.DataFrame],
    specs: Sequence[LayerSpec],
) -> tuple[gpd.GeoDataFrame, list[dict]]:
    """
    Left-join every layer onto the grid by `cell_id`, in spec order.

    Returns (integrated GeoDataFrame in OUTPUT_COLUMNS + geometry order,
    join_log). The row count is asserted unchanged after every join and the
    join is validated one-to-one, so a duplicated upstream key or a row
    inflation halts with a RuntimeError naming the layer. Nothing is
    back-filled: a grid cell absent from a layer simply gets nulls, and the
    join_log records upstream vs post-join null counts per column so
    validate() can flag that inflation.
    """
    geometry_name = grid.geometry.name
    table = grid[list(GRID_COLUMNS) + [geometry_name]].reset_index(drop=True)
    grid_ids = set(table["cell_id"])
    join_log: list[dict] = []

    for spec in specs:
        if spec.name not in layers:
            raise KeyError(f"no frame supplied for layer {spec.name!r}")
        upstream = layers[spec.name]
        absent = [c for c in spec.source_columns if c not in upstream.columns]
        if absent:
            raise ValueError(f"{spec.name} layer lacks column(s) {absent}")

        selected = upstream[["cell_id", *spec.source_columns]].rename(
            columns={source: target for target, source in spec.columns.items()}
        )
        upstream_ids = set(upstream["cell_id"])
        null_upstream = {t: int(selected[t].isna().sum()) for t in spec.columns}

        rows_before = len(table)
        try:
            table = table.merge(selected, on="cell_id", how="left", validate="one_to_one")
        except pd.errors.MergeError as exc:
            raise RuntimeError(
                f"{spec.name} layer cannot be joined one-to-one on cell_id: {exc}"
            ) from exc
        if len(table) != rows_before:
            raise RuntimeError(
                f"{spec.name} join changed the row count {rows_before} -> {len(table)}"
            )

        join_log.append({
            "layer": spec.name,
            "rows_before": rows_before,
            "rows_after": int(len(table)),
            "upstream_rows": int(len(upstream)),
            "cell_ids_missing_from_upstream": len(grid_ids - upstream_ids),
            "cell_ids_extra_in_upstream": len(upstream_ids - grid_ids),
            "null_counts_upstream": null_upstream,
            "null_counts_after": {t: int(table[t].isna().sum()) for t in spec.columns},
        })

    for column in BOOL_COLUMNS:
        table[column] = _normalise_bool(table[column])
    table["n_missing_features"] = compute_n_missing_features(table)

    table = table[OUTPUT_COLUMNS + [geometry_name]]
    return gpd.GeoDataFrame(table, geometry=geometry_name, crs=grid.crs), join_log


# ---------------------------------------------------------------------------
# Validation — no silent passes
# ---------------------------------------------------------------------------

FATAL = "fatal"
WARN = "warn"

# S1-07 recomputes these from the rasters with its own zonal code; they are
# read (not carried) so the WARN checks below can compare them with the
# geographic and wind layers' values for the same cells.
EXCLUSIONS_CROSS_CHECK_COLUMNS = (
    "protected_area", "protected_area_name", "slope_deg", "wind_speed_100m_ms",
)


def _name_set(value) -> frozenset:
    """'A; B' -> {A, B}; ''/null -> {} (both layers join names with '; ')."""
    if value is None or (not isinstance(value, str) and pd.isna(value)) or value == "":
        return frozenset()
    return frozenset(part.strip() for part in str(value).split(";") if part.strip())


def validate(
    table: gpd.GeoDataFrame,
    grid: gpd.GeoDataFrame,
    layers: dict[str, pd.DataFrame],
    join_log: list[dict],
    specs: Sequence[LayerSpec],
    infos: dict[str, dict] | None = None,
) -> dict:
    """
    Every check reports expected vs observed, even when it passes.

    Returns {"checks": [{name, expected, observed, passed, severity}],
    "passed", "total", "failed" (fatal checks that failed), "warnings"
    (warn checks that failed)}. Fatal failures halt run(); WARN checks are
    documentation of known upstream divergence and never halt.
    """
    checks: list[dict] = []

    def check(name, expected, observed, passed, severity=FATAL):
        checks.append({
            "name": name, "expected": str(expected), "observed": str(observed),
            "passed": bool(passed), "severity": severity,
        })

    # --- input CRS assertions (the loaders already halted on a mismatch;
    #     recorded so the report shows the assertion per input) ---
    if infos:
        for name in ["grid", *(s.name for s in specs)]:
            info = infos.get(name)
            if info is not None:
                check(f"{name}: CRS equals storage CRS", config.STORAGE_CRS,
                      info["crs"], info["crs"] == config.STORAGE_CRS)

    # --- per-layer join accounting ---
    for entry in join_log:
        layer = entry["layer"]
        missing = entry["cell_ids_missing_from_upstream"]
        extra = entry["cell_ids_extra_in_upstream"]
        check(f"{layer}: cell_id set matches grid", "0 missing, 0 extra",
              f"{missing} missing, {extra} extra", missing == 0 and extra == 0)
        check(f"{layer}: row count unchanged after left join",
              f"{entry['rows_before']} rows", f"{entry['rows_after']} rows",
              entry["rows_before"] == entry["rows_after"])
        before, after = entry["null_counts_upstream"], entry["null_counts_after"]
        diffs = [f"{c} {before[c]}->{after[c]}" for c in before if before[c] != after[c]]
        check(f"{layer}: null counts preserved for joined columns",
              f"identical to upstream for {len(before)} columns",
              "0 columns differ" if not diffs
              else f"{len(diffs)} columns differ: {', '.join(diffs)}",
              not diffs)

    # --- table-level structure ---
    n_grid, n_table = len(grid), len(table)
    check("row count equals grid cell count", f"{n_grid} rows", f"{n_table} rows",
          n_grid == n_table)

    n_dup = int(table["cell_id"].duplicated().sum())
    check("cell_id unique", "0 duplicates", f"{n_dup} duplicates", n_dup == 0)

    grid_ids, table_ids = list(grid["cell_id"]), list(table["cell_id"])
    divergence = next(
        (i for i, (a, b) in enumerate(zip(grid_ids, table_ids)) if a != b), None,
    )
    if divergence is None and len(grid_ids) != len(table_ids):
        divergence = min(len(grid_ids), len(table_ids))
    check("cell_id order preserved from grid", "grid order",
          "identical" if divergence is None else f"first divergence at row {divergence}",
          divergence is None)

    if n_grid == n_table:
        same = table.geometry.reset_index(drop=True).geom_equals(
            grid.geometry.reset_index(drop=True)
        )
        n_geom_diff = int((~same).sum())
        geom_observed = f"{n_geom_diff} differing cells"
    else:
        n_geom_diff = abs(n_grid - n_table)
        geom_observed = f"row counts differ ({n_grid} vs {n_table}); geometry not compared"
    check("geometry identical to grid", "0 differing cells", geom_observed, n_geom_diff == 0)

    table_crs = _crs_string(table.crs) if table.crs else "undeclared"
    check("output CRS is storage CRS", config.STORAGE_CRS, table_crs,
          table_crs == config.STORAGE_CRS)

    expected_cols = OUTPUT_COLUMNS + ["geometry"]
    actual_cols = list(table.columns)
    missing_cols = [c for c in expected_cols if c not in actual_cols]
    unexpected_cols = [c for c in actual_cols if c not in expected_cols]
    if not missing_cols and not unexpected_cols:
        cols_observed = "identical" if actual_cols == expected_cols else "same columns, different order"
    else:
        cols_observed = f"missing {missing_cols}, unexpected {unexpected_cols}"
    check("output columns match OUTPUT_COLUMNS",
          f"{len(OUTPUT_COLUMNS)} columns + geometry, in order",
          cols_observed, actual_cols == expected_cols)

    # --- eligibility semantics (mirrors pipeline/exclusions/apply.py validate) ---
    if "eligible" in table.columns and "exclusion_reason" in table.columns:
        elig = table["eligible"]
        n_null = int(elig.isna().sum())
        is_bool = str(elig.dtype) in ("bool", "boolean")
        check("eligible is boolean with no nulls", "0 nulls, boolean dtype",
              f"{n_null} nulls, dtype {elig.dtype}", n_null == 0 and is_bool)
        eligible = elig.fillna(False).astype(bool)
        reason = table["exclusion_reason"]
        reason_present = reason.notna() & (reason.fillna("").astype(str).str.len() > 0)
        inconsistent = int(((eligible & reason_present) | (~eligible & ~reason_present)).sum())
        check("eligible/exclusion_reason consistent", "0 inconsistent rows",
              f"{inconsistent} inconsistent rows", inconsistent == 0)

    # --- derived column ---
    if "n_missing_features" in table.columns and set(SCORED_FEATURE_COLUMNS) <= set(table.columns):
        recount = compute_n_missing_features(table)
        n_diff = int((recount.to_numpy() != table["n_missing_features"].to_numpy()).sum())
        check("n_missing_features equals recount over scored columns", "0 rows differ",
              f"{n_diff} rows differ", n_diff == 0)

    # --- confidence vocabularies (a null is outside every vocabulary) ---
    for spec in specs:
        for column, levels in spec.enum_checks.items():
            if column not in table.columns:
                continue
            outside = int((~table[column].isin(levels)).sum())
            check(f"{column} within vocabulary", f"all in {levels}",
                  f"{outside} rows outside {levels}", outside == 0)

    # --- cross-layer consistency (WARN): S1-07's own recomputation vs the
    #     geographic and wind layers, joined on cell_id ---
    exclusions = layers.get("exclusions")
    if exclusions is not None and all(c in exclusions.columns for c in EXCLUSIONS_CROSS_CHECK_COLUMNS):
        aligned = table[["cell_id", "protected_area", "protected_area_name", "slope_deg",
                         "wind_speed"]].merge(
            exclusions[["cell_id", *EXCLUSIONS_CROSS_CHECK_COLUMNS]],
            on="cell_id", how="left", suffixes=("", "_excl"),
        )

        both = aligned["protected_area"].notna() & aligned["protected_area_excl"].notna()
        mismatches = int((aligned.loc[both, "protected_area"].astype(bool)
                          != aligned.loc[both, "protected_area_excl"].astype(bool)).sum())
        check("cross-layer: exclusions.protected_area == geographic.protected_area",
              "0 mismatches", f"{mismatches} mismatches of {int(both.sum())} compared",
              mismatches == 0, WARN)

        def numeric_pair(name, ours, theirs, tolerance, unit):
            ours_null, theirs_null = ours.isna(), theirs.isna()
            null_pattern = int((ours_null != theirs_null).sum())
            both_present = ~ours_null & ~theirs_null
            n_both = int(both_present.sum())
            value_mism = int(((ours[both_present] - theirs[both_present]).abs() > tolerance).sum())
            check(name, "0 value mismatches, 0 null-pattern mismatches",
                  f"{value_mism} value mismatches of {n_both} both-non-null "
                  f"(tol {tolerance}{unit}); {null_pattern} null-pattern mismatches",
                  value_mism == 0 and null_pattern == 0, WARN)

        numeric_pair("cross-layer: exclusions.slope_deg ~ geographic.slope_deg",
                     aligned["slope_deg"], aligned["slope_deg_excl"],
                     config.SLOPE_TOLERANCE_DEG, "°")
        numeric_pair("cross-layer: exclusions.wind_speed_100m_ms ~ wind.wind_speed",
                     aligned["wind_speed"], aligned["wind_speed_100m_ms"],
                     config.WIND_TOLERANCE_MS, " m/s")

        name_mism = int((aligned["protected_area_name"].map(_name_set)
                         != aligned["protected_area_name_excl"].map(_name_set)).sum())
        check("cross-layer: exclusions.protected_area_name == geographic.protected_area_name",
              "0 mismatches", f"{name_mism} mismatches of {len(aligned)} compared",
              name_mism == 0, WARN)
    else:
        check("cross-layer: exclusions comparison columns present",
              str(list(EXCLUSIONS_CROSS_CHECK_COLUMNS)),
              "absent — cross-layer checks skipped", False, WARN)

    passed = sum(1 for c in checks if c["passed"])
    failed = sum(1 for c in checks if not c["passed"] and c["severity"] == FATAL)
    warnings = sum(1 for c in checks if not c["passed"] and c["severity"] == WARN)
    return {"checks": checks, "passed": passed, "total": len(checks),
            "failed": failed, "warnings": warnings}


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def write_gpkg(table: gpd.GeoDataFrame, path: Path) -> None:
    """Atomic GeoPackage write (tmp keeps the .gpkg suffix for driver inference)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + "_tmp.gpkg")
    try:
        table.to_file(tmp, driver="GPKG", layer=config.OUTPUT_LAYER)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def write_csv(table: gpd.GeoDataFrame, path: Path) -> None:
    """
    Atomic CSV write without geometry. index=False, nulls empty, booleans
    True/False, floats in pandas' shortest round-trip repr, "\\n" line ends —
    byte-identical across reruns with unchanged inputs.
    """
    path = Path(path)
    frame = pd.DataFrame(table.drop(columns=[table.geometry.name]))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + "_tmp.csv")
    try:
        frame.to_csv(tmp, index=False, na_rep="", lineterminator="\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def verify_written(gpkg_path: Path, csv_path: Path, n_expected: int) -> list[dict]:
    """Read-back checks on the two written products (same check shape as validate())."""
    checks: list[dict] = []

    def check(name, expected, observed, passed):
        checks.append({"name": name, "expected": str(expected), "observed": str(observed),
                       "passed": bool(passed), "severity": FATAL})

    n_gpkg = int(pyogrio.read_info(gpkg_path, layer=config.OUTPUT_LAYER)["features"])
    check("GeoPackage read-back row count", f"{n_expected} rows", f"{n_gpkg} rows",
          n_gpkg == n_expected)

    header = list(pd.read_csv(csv_path, nrows=0).columns)
    n_csv = int(len(pd.read_csv(csv_path, usecols=[header[0]])))
    check("CSV read-back row count", f"{n_expected} rows", f"{n_csv} rows", n_csv == n_expected)
    check("CSV columns match OUTPUT_COLUMNS without geometry",
          f"{len(OUTPUT_COLUMNS)} columns, no geometry",
          "identical" if header == OUTPUT_COLUMNS else f"got {header}",
          header == OUTPUT_COLUMNS)
    return checks


def git_commit(cwd: Path | None = None) -> str:
    """
    HEAD commit for the report/manifest ('-dirty' when the tree has changes);
    'unknown' on any failure. Never raises — reproducibility metadata must not
    be able to fail the stage.
    """
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if head.returncode != 0 or not head.stdout.strip():
            return "unknown"
        commit = head.stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        dirty = status.returncode == 0 and status.stdout.strip() != ""
        return f"{commit}-dirty" if dirty else commit
    except Exception:  # noqa: BLE001 — any failure degrades to "unknown"
        return "unknown"


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

STAGE_NAME = "integration"
MODULE_NAME = "integration.merge"

# Units / type of every output column, for the column map (ticket AC: "all
# columns retain their units, documented in metadata").
COLUMN_UNITS = {
    "cell_id": "str — grid identifier, byte-for-byte from S1-02",
    "centroid_lat": "degrees (EPSG:4326)",
    "centroid_lon": "degrees (EPSG:4326)",
    "area_km2": "km² (computed in EPSG:3577 by the grid stage)",
    "wind_speed": "m/s — GWA v4 mean wind speed at 100 m hub height",
    "wind_confidence": "flag: valid | no_data",
    "demand_proxy": "normalised 0–1 (uniform allocation of NEM-region annual mean MW)",
    "source_region": "NEM region id, null outside every region",
    "demand_confidence": "flag: high | medium | low",
    "dist_transmission_km": "km — EPSG:3577 centroid distance to nearest ≥132 kV line",
    "dist_substation_km": "km — EPSG:3577 centroid distance to nearest substation",
    "dist_connection_km": "km — EPSG:3577 centroid distance to nearest connection point",
    "inside_rez": "bool — cell intersects an EnergyCo REZ",
    "rez_name": "str, null when not in a REZ ('; '-joined if several)",
    "infra_confidence": "flag: high | low",
    "elevation_m": "m AMSL — mean of valid SRTM GL3 pixels",
    "slope_deg": "degrees — mean of valid Horn-slope pixels",
    "tri": "m — Riley terrain ruggedness index (Glen-Innes sub-window only)",
    "land_use": "ALUM v8 tertiary class name of the modal NLUM code",
    "protected_area": "bool — any CAPAD intersection (frozen decision Q6)",
    "protected_area_name": "'; '-joined CAPAD names, '' when none",
    "geo_confidence": "flag: high | low",
    "eligible": "bool — no exclusion rule triggered (S1-07)",
    "exclusion_reason": "text — ', '-joined reasons, null when eligible",
    "triggered_rules": "text — ', '-joined rule names, null when eligible",
    "data_flags": "text — '; '-joined non-exclusionary coverage flags",
    "n_missing_features": "int 0–10 — nulls among the ten scored feature columns",
}


def _banner(generated_utc: str) -> str:
    """Same wording as common.geo.banner(), stamped with the run's timestamp."""
    return (f"*Generated by `pipeline.{MODULE_NAME}` on {generated_utc}. "
            f"Do not edit by hand.*\n")


def _column_source_map(specs: Sequence[LayerSpec]) -> dict[str, str]:
    sources = {c: f"grid.{c}" for c in GRID_COLUMNS}
    for spec in specs:
        for target, source in spec.columns.items():
            sources[target] = f"{spec.name}.{source}"
    sources["n_missing_features"] = "derived — count of nulls over " + ", ".join(SCORED_FEATURE_COLUMNS)
    return sources


def _rel(path: Path) -> str:
    path = Path(path)
    try:
        return str(path.relative_to(config.PROJECT_ROOT))
    except ValueError:
        return str(path)


def build_method_report(
    *,
    table: gpd.GeoDataFrame,
    infos: dict[str, dict],
    specs: Sequence[LayerSpec],
    join_log: list[dict],
    result: dict,
    runtime_s: float,
    generated_utc: str,
    git_commit: str,
    outputs: dict[str, Path],
) -> str:
    """Render integration_method.md."""
    n_cells = len(table)
    n_eligible = int(table["eligible"].fillna(False).astype(bool).sum())
    n_excluded = n_cells - n_eligible

    input_rows = "\n".join(
        f"| {name} | `{_rel(info['path'])}` | `{info['layer']}` | {info['rows']:,} | "
        f"{info['crs']} (asserted == {config.STORAGE_CRS}) | `{info['sha256']}` |"
        for name, info in infos.items()
    )

    sources = _column_source_map(specs)
    column_rows = "\n".join(
        f"| {column} | {sources.get(column, '—')} | {COLUMN_UNITS.get(column, '—')} |"
        for column in OUTPUT_COLUMNS
    )

    upstream_nulls: dict[str, int] = {}
    for entry in join_log:
        upstream_nulls.update(entry["null_counts_upstream"])
    null_rows = "\n".join(
        f"| {column} | {upstream_nulls[column] if column in upstream_nulls else '—'} | "
        f"{int(table[column].isna().sum())} |"
        for column in OUTPUT_COLUMNS
    )

    histogram = table["n_missing_features"].value_counts().sort_index()
    histogram_rows = "\n".join(f"| {int(k)} | {int(v)} |" for k, v in histogram.items())

    dropped = (
        "`wind.units`, `wind.data_source` (constants: m/s, GWA v4), "
        "`demand.allocation_method` (constant: uniform), and S1-07's own "
        "`protected_area`, `protected_area_name`, `slope_deg`, `urban_area`, "
        "`wind_speed_100m_ms` (recomputed from rasters; compared in the WARN "
        "checks, never carried — the geographic and wind layers are canonical)."
    )

    return f"""# Integrated NSW Feature Table — method report (S1-08)

{_banner(generated_utc)}

## 1. Method

The S1-02 analysis grid (`cell_id`, centroids, `area_km2`, geometry) is the
left side of five sequential **left joins on `cell_id`**, in this order:
wind (S1-03), geographic (S1-06), infrastructure (S1-05), demand (S1-04),
exclusions (S1-07). Each join is validated one-to-one and the row count is
asserted unchanged afterwards, so no cell is dropped or duplicated. Excluded
cells are **retained** with `eligible = False`.

Nothing is computed, reprojected or back-filled here: every input must already
be stored in {config.STORAGE_CRS} (the loaders halt otherwise), and upstream
nulls stay null (the per-column null counts are checked to be identical after
the join). Distances and areas were computed upstream in {config.COMPUTATION_CRS}.

Columns dropped on purpose: {dropped}

**`data_confidence` is not emitted by this stage.** Deriving a composite
confidence is S1-09's job; this table carries the five upstream flags under
per-layer names (`wind_confidence`, `demand_confidence`, `infra_confidence`,
`geo_confidence`; exclusions has none) plus the objective `n_missing_features`
count for S1-09 to build on.

## 2. Reproducibility

- Generated (UTC): {generated_utc}
- Git commit: `{git_commit}`
- Stage: `python -m pipeline --only {STAGE_NAME}` (or the full `python -m pipeline`)
- The **CSV is the deterministic artefact**: with unchanged inputs a rerun
  reproduces it byte-for-byte. The GeoPackage embeds a
  `gpkg_contents.last_change` timestamp, so its SHA-256 changes on every
  regeneration even when the data does not.
- Input fingerprints are listed below and in `metadata/{config.MANIFEST_FILENAME}`.

## 3. Inputs

| Layer | File | Layer name | Rows | CRS | SHA-256 |
|-------|------|------------|------|-----|---------|
{input_rows}

## 4. Column map

| Column | Source (layer.column) | Units / type |
|--------|-----------------------|--------------|
{column_rows}

## 5. Null accounting

Upstream vs integrated null counts per column (`—` = grid or derived column):

| Column | Upstream nulls | Integrated nulls |
|--------|----------------|------------------|
{null_rows}

`n_missing_features` histogram (nulls among the ten scored feature columns):

| n_missing_features | Cells |
|--------------------|-------|
{histogram_rows}

- Cells: **{n_cells:,}**
- Eligible: **{n_eligible:,}** — Excluded: **{n_excluded:,}** (rows retained)

## 6. Validation

{result['passed']}/{result['total']} checks passed; {result['failed']} fatal
failure(s); {result['warnings']} warning(s). Every check, with its expected and
observed values, is in `{_rel(outputs['validation_report'])}`
(`merge_validation.md`). WARN checks compare S1-07's own raster recomputation
with the geographic and wind layers; a non-zero count there documents known
upstream divergence and does not fail the stage.

## 7. Outputs

- GeoPackage (with geometry, layer `{config.OUTPUT_LAYER}`): `{_rel(outputs['gpkg'])}`
- CSV (without geometry): `{_rel(outputs['csv'])}`

## 8. Runtime

- Total wall-clock runtime: {runtime_s:.3f} s
"""


def build_validation_report(result: dict, generated_utc: str) -> str:
    """Render merge_validation.md: one row per check, PASS / **FAIL** / WARN."""
    rows = []
    for check in result["checks"]:
        if check["passed"]:
            status = "PASS"
        elif check["severity"] == WARN:
            status = "WARN"
        else:
            status = "**FAIL**"
        rows.append(
            f"| {check['name']} | {check['severity']} | {check['expected']} | "
            f"{check['observed']} | {status} |"
        )
    body = "\n".join(rows)
    return f"""# Integrated NSW Feature Table — merge validation (S1-08)

{_banner(generated_utc)}

**{result['passed']}/{result['total']} checks passed** — {result['failed']} fatal
failure(s), {result['warnings']} warning(s). Fatal failures halt the stage; WARN
rows record known divergence between S1-07's raster recomputation and the
canonical feature layers.

| Check | Severity | Expected | Observed | Result |
|-------|----------|----------|----------|--------|
{body}
"""


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

PROVENANCE_BEGIN = "<!-- BEGIN integration.merge derived layer (generated) -->"
PROVENANCE_END = "<!-- END integration.merge derived layer (generated) -->"


def record_provenance(
    *,
    gpkg_path: Path,
    csv_path: Path,
    table: gpd.GeoDataFrame,
    infos: dict[str, dict],
    generated_utc: str,
    git_commit: str,
    manifest_path: Path,
    provenance_path: Path,
) -> dict:
    """
    Read-merge-write one record into the manifest (keyed by output_file, so a
    rerun replaces rather than appends) and splice the generated block into
    DATA_PROVENANCE.md between the BEGIN/END markers (handwritten text above
    is never touched). Returns the manifest record.
    """
    record = {
        "output_file": _rel(gpkg_path),
        "csv_file": _rel(csv_path),
        "stage": STAGE_NAME,
        "generated_utc": generated_utc,
        "git_commit": git_commit,
        "rows": int(len(table)),
        "columns": list(OUTPUT_COLUMNS),
        "sha256_gpkg": sha256_file(gpkg_path),
        "sha256_csv": sha256_file(csv_path),
        "bytes_gpkg": Path(gpkg_path).stat().st_size,
        "bytes_csv": Path(csv_path).stat().st_size,
        "inputs": [
            {
                "name": name,
                "path": _rel(info["path"]),
                "layer": info["layer"],
                "rows": info["rows"],
                "crs": info["crs"],
                "sha256": info["sha256"],
                "bytes": info["bytes"],
            }
            for name, info in infos.items()
        ],
    }

    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    derived = [
        r for r in manifest.get("derived_features", [])
        if r.get("output_file") != record["output_file"]
    ]
    derived.append(record)
    manifest["derived_features"] = derived
    atomic_write_json(manifest_path, manifest)

    inputs_md = "\n".join(
        f"  - {i['name']}: `{i['path']}` (layer `{i['layer']}`, {i['rows']:,} rows, "
        f"SHA-256 `{i['sha256']}`)"
        for i in record["inputs"]
    )
    section = (
        f"{PROVENANCE_BEGIN}\n"
        f"## Derived layer — Integrated NSW Feature Table (S1-08)\n\n"
        f"- **File:** `{record['output_file']}` (GeoPackage, layer `{config.OUTPUT_LAYER}`)\n"
        f"- **CSV:** `{record['csv_file']}` (no geometry; the deterministic artefact)\n"
        f"- **Derived from:**\n{inputs_md}\n"
        f"- **Method:** left joins on `cell_id` from the S1-02 grid; row count asserted "
        f"after every join; excluded cells retained with `eligible = False`; no "
        f"reprojection, no back-filling; `data_confidence` deferred to S1-09.\n"
        f"- **Regenerable:** yes — `python -m pipeline --only {STAGE_NAME}` "
        f"(after the five feature stages and `exclusions`).\n"
        f"- **SHA-256 (GeoPackage):** `{record['sha256_gpkg']}`\n"
        f"- **SHA-256 (CSV):** `{record['sha256_csv']}`\n"
        f"- **Rows:** {record['rows']:,}\n"
        f"- **Generated (UTC):** {generated_utc}\n"
        f"- **Git commit:** `{git_commit}`\n"
        f"{PROVENANCE_END}\n"
    )
    provenance_path = Path(provenance_path)
    text = provenance_path.read_text(encoding="utf-8") if provenance_path.exists() else ""
    if PROVENANCE_BEGIN in text and PROVENANCE_END in text:
        head, rest = text.split(PROVENANCE_BEGIN, 1)
        _, tail = rest.split(PROVENANCE_END, 1)
        text = head + section.rstrip("\n") + tail
    else:
        text = text.rstrip("\n") + "\n\n" + section if text else section
    atomic_write_text(provenance_path, text)
    return record
