"""
Exclusion layer stage — S1-07.

Reads the common analysis grid and joins the per-cell feature tables the
upstream stages produce (S1-06 geographic.features, S1-03 wind.features,
S1-04 demand) on cell_id, evaluates the configured exclusion rules against
the joined fields, and writes:

    DATA/exclusions/optmining_exclusions_2024_nsw.gpkg    — Eligibility_Table
    DATA/exclusions/metadata/exclusion_summary.md          — method report

The stage no longer re-samples raw rasters/vectors: every per-cell field
(protected_area, protected_area_name, slope_deg, urban_area, on_land,
wind_speed_100m_ms, demand_proxy) comes from the statewide-NSW feature
tables, joined on cell_id. See pipeline/exclusions/__init__.py for the
migration note.

Importable entry point:
    from pipeline.exclusions.apply import run
    result = run(verbose=False)
"""

from __future__ import annotations

import io
import json
import os
import time
from pathlib import Path

import geopandas as gpd
import numpy as np

from . import config
from . import rules as rules_mod
from ..common.geo import atomic_write_text, banner


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
# Feature-table inputs (joined on cell_id)
# ---------------------------------------------------------------------------


def _read_feature_table(
    path: Path,
    layer: str,
    source_label: str,
    required_columns: list[str],
    n_grid_cells: int,
) -> gpd.GeoDataFrame:
    """
    Open one per-cell feature GeoPackage with its EXPLICIT layer and halt
    loudly (raise) on any condition that would otherwise produce a silently
    partial exclusion table: a missing/unreadable file, a missing cell_id or
    required column, duplicate cell_id values, or a row count that does not
    match the analysis grid.

    A silent left-join to nulls is specifically forbidden here — a null in,
    e.g., wind_speed_100m_ms or slope_deg is read by the rule engine as a
    genuine `missing_wind_data` / `missing_slope_data` exclusion, so a
    coverage mismatch must stop the run rather than mass-exclude cells.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"{source_label} feature table not found: {path} — run the "
            f"producing stage first (e.g. `python -m pipeline --only wind.features` "
            f"or `--only geographic.features`)."
        )
    try:
        gdf = gpd.read_file(path, layer=layer)
    except Exception as exc:  # noqa: BLE001 — re-raised as a halting error
        raise RuntimeError(
            f"{source_label} feature table could not be read: {path} "
            f"(layer={layer!r}; {exc})"
        ) from exc

    if "cell_id" not in gdf.columns:
        raise ValueError(f"{source_label} feature table has no 'cell_id' column: {path}")

    missing_cols = [c for c in required_columns if c not in gdf.columns]
    if missing_cols:
        raise ValueError(
            f"{source_label} feature table missing required column(s) {missing_cols}: {path}"
        )

    dupes = gdf["cell_id"][gdf["cell_id"].duplicated()].unique().tolist()
    if dupes:
        shown = dupes[:10]
        suffix = " ..." if len(dupes) > 10 else ""
        raise ValueError(
            f"{source_label} feature table has duplicate cell_id values: {shown}{suffix}"
        )

    if len(gdf) != n_grid_cells:
        raise ValueError(
            f"{source_label} feature table row count ({len(gdf):,}) does not match the "
            f"analysis grid cell count ({n_grid_cells:,}): {path}. Exclusions joins the "
            f"feature tables 1:1 on cell_id; a coverage mismatch must halt rather than "
            f"silently mass-exclude cells."
        )

    # Drop geometry — the join carries only the scalar fields; the output
    # geometry comes from the grid cells.
    return gdf[["cell_id", *required_columns]]


def read_feature_tables(
    n_grid_cells: int,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Read the geographic, wind and demand per-cell feature tables, each with
    its explicit `layer=`, selecting only the columns the exclusion rules
    need.

    Returns (geographic_df, wind_df, demand_df), all keyed on cell_id with
    exactly `n_grid_cells` rows (halt-on-mismatch, see `_read_feature_table`).
    """
    geographic = _read_feature_table(
        config.GEOGRAPHIC_FEATURE_PATH,
        config.GEOGRAPHIC_FEATURE_LAYER,
        "Geographic",
        [
            "slope_deg",
            "land_use",
            "protected_area",
            "protected_area_name",
            "urban_area",
            "on_land",
        ],
        n_grid_cells,
    )
    wind = _read_feature_table(
        config.WIND_FEATURE_PATH,
        config.WIND_FEATURE_LAYER,
        "Wind",
        ["wind_speed_100m"],
        n_grid_cells,
    )
    demand = _read_feature_table(
        config.DEMAND_FEATURE_PATH,
        config.DEMAND_FEATURE_LAYER,
        "Demand",
        ["demand_proxy"],
        n_grid_cells,
    )
    return geographic, wind, demand


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def build_cell_table(
    cells: gpd.GeoDataFrame,
    rules: list[dict],
    verbose: bool = False,
) -> gpd.GeoDataFrame:
    """
    Join the per-cell feature tables on cell_id, evaluate the rules, and
    assemble the Eligibility_Table.

    Every eligibility field is read from the statewide-NSW feature tables
    (geographic.features + wind.features + demand) via an inner 1:1 join on
    cell_id — nothing is re-sampled here and nothing depends on the grid's
    centroid columns.
    """
    n_cells = len(cells)
    if verbose:
        print("    Reading geographic + wind + demand feature tables (joined on cell_id)...")
    geographic, wind, demand = read_feature_tables(n_cells)

    # Inner-join on cell_id. The grid frame carries the output geometry; the
    # feature tables carry the scalar fields. The join must be 1:1 and cover
    # every grid cell — anything less is a halting condition (a dropped or
    # duplicated row would skew eligibility).
    joined = (
        cells[["cell_id", "geometry"]]
        .merge(geographic, on="cell_id", how="inner", validate="one_to_one")
        .merge(wind, on="cell_id", how="inner", validate="one_to_one")
        .merge(demand, on="cell_id", how="inner", validate="one_to_one")
    )
    if len(joined) != n_cells:
        matched = set(joined["cell_id"])
        unmatched = [cid for cid in cells["cell_id"] if cid not in matched][:10]
        raise ValueError(
            f"cell_id join did not cover every grid cell: grid has {n_cells:,} cells, "
            f"joined table has {len(joined):,}. Sample unmatched cell_id(s): {unmatched}. "
            f"The geographic/wind feature tables must each carry exactly one row per grid "
            f"cell_id."
        )

    rows = []
    for rec in joined.itertuples(index=False):
        fields = {
            "protected_area": rec.protected_area,
            "protected_area_name": rec.protected_area_name,
            "slope_deg": rec.slope_deg,
            "urban_area": rec.urban_area,
            # Wind feature column is `wind_speed_100m`; the rule field key is
            # `wind_speed_100m_ms` (keep the rename explicit, as the
            # integration merge does for wind_speed_100m -> wind_speed).
            "wind_speed_100m_ms": rec.wind_speed_100m,
            "on_land": rec.on_land,
            # demand_proxy is a scored criterion (S2-01); a null here must
            # exclude the cell via the `missing_demand_data` rule rather than
            # let it be scored on missing critical data.
            "demand_proxy": rec.demand_proxy,
        }
        eligible, reason_pairs = rules_mod.evaluate_cell_detailed(fields, rules)
        # Derive the backward-compatible human string + machine name list from
        # the same evaluation, so exclusion_reason / triggered_rules /
        # exclusion_reasons can never disagree (rules.evaluate_cell does the
        # same derivation; we inline it here to avoid a second evaluation).
        exclusion_reason = (
            rules_mod.REASON_DELIMITER.join(p["text"] for p in reason_pairs)
            if reason_pairs
            else None
        )
        triggered = [p["code"] for p in reason_pairs]

        rows.append(
            {
                "cell_id": rec.cell_id,
                "eligible": eligible,
                "exclusion_reason": exclusion_reason,
                "triggered_rules": rules_mod.REASON_DELIMITER.join(triggered) if triggered else None,
                # Machine+human paired reason schema (Decision_Engine_Spec §6
                # F16): a JSON list of {"code": rule_name, "text": reason}
                # pairs, consumed directly by the S2-06 explanation engine.
                # Null for eligible cells, consistent with exclusion_reason.
                "exclusion_reasons": json.dumps(reason_pairs) if reason_pairs else None,
                "protected_area": fields["protected_area"],
                "protected_area_name": fields["protected_area_name"],
                "slope_deg": fields["slope_deg"],
                "urban_area": fields["urban_area"],
                "wind_speed_100m_ms": fields["wind_speed_100m_ms"],
                # data_flags no longer carries the New-England urban
                # coverage-window note: urban_area is now statewide-definite
                # from the joined geographic feature table. It stays in the
                # output schema (null unless the geographic builder carries a
                # soft note) so OUTPUT_COLUMNS is unchanged.
                "data_flags": None,
            }
        )

    return gpd.GeoDataFrame(rows, geometry=joined.geometry.values, crs=cells.crs)


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
        "\nThis stage joins the per-cell geographic feature table "
        "(`geographic.features`) and the wind feature table (`wind.features`) on "
        "`cell_id` — both statewide-NSW over every one of the analysis grid's cells — "
        "and evaluates the configured rules against the joined fields. See "
        "`pipeline/exclusions/__init__.py` for the scope note.\n\n"
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

    out.write("## Data-source coverage\n\n")
    out.write(
        "Every per-cell field is read from the statewide-NSW feature tables joined on "
        "`cell_id`: `protected_area` / `protected_area_name` / `slope_deg` / `urban_area` / "
        "`on_land` from `geographic.features`, `wind_speed_100m_ms` from `wind.features`, and "
        "`demand_proxy` from `demand`. Each table carries a row for every one of the grid's "
        "cells, so the exclusion layer now covers the full NSW grid rather than a windowed "
        "subset. A cell is still excluded where a critical scored field is genuinely null "
        "(`missing_wind_data`, `missing_slope_data`, `missing_demand_data`) or where its "
        "centre is offshore/marine (`offshore_or_marine`), per the Constitution's \"where "
        "critical data is missing, exclude the cell\" rule.\n\n"
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

    out.write("## Exclusion reason schema (machine + human readable)\n\n")
    out.write(
        "Every excluded cell retains its reason(s) in three consistent forms, all derived "
        "from one rule evaluation so they can never drift:\n\n"
        "- `exclusion_reason` — human-readable text, reasons joined with "
        f"`{rules_mod.REASON_DELIMITER!r}` in rule-config order.\n"
        "- `triggered_rules` — machine-readable rule-name codes, same delimiter and order.\n"
        "- `exclusion_reasons` — a JSON list of `{\"code\": rule_name, \"text\": reason}` "
        "pairs (null for eligible cells), the paired form the S2-06 explanation engine "
        "consumes directly.\n\n"
        "The `code` values are the frozen exclusion reason-code vocabulary — the rule "
        "`name` values in the rules config above. This vocabulary is governed by the "
        "Decision-Engine Specification §6 (frozen decision F16); adding or renaming a code "
        "follows that document's change-control process. A cell can carry multiple reasons.\n\n"
    )

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

    # Structured machine+human reason schema (exclusion_reasons) is present and
    # consistent with eligible / triggered_rules for EVERY row. This is the
    # column the S2-06 explanation engine consumes, so a drift between it and
    # the other two reason forms must be reported, never silently passed.
    if "exclusion_reasons" not in table.columns:
        check("exclusion_reasons column present", "present", "absent", False)
    else:
        n_inconsistent = 0
        for _, row in table.iterrows():
            raw = row["exclusion_reasons"]
            is_null = raw is None or (isinstance(raw, float) and np.isnan(raw))
            if bool(row["eligible"]):
                # Eligible cells must carry no structured reasons.
                if not is_null:
                    n_inconsistent += 1
                continue
            # Excluded cells must carry a well-formed list of {code, text}
            # pairs whose codes equal the triggered_rules names, in order.
            if is_null:
                n_inconsistent += 1
                continue
            try:
                pairs = json.loads(raw)
            except (ValueError, TypeError):
                n_inconsistent += 1
                continue
            codes = [p.get("code") for p in pairs] if isinstance(pairs, list) else None
            texts_ok = isinstance(pairs, list) and all(
                isinstance(p, dict) and p.get("text") for p in pairs
            )
            triggered_raw = row["triggered_rules"]
            triggered_null = triggered_raw is None or (
                isinstance(triggered_raw, float) and np.isnan(triggered_raw)
            )
            expected_codes = (
                [] if triggered_null else str(triggered_raw).split(rules_mod.REASON_DELIMITER)
            )
            if codes != expected_codes or not texts_ok or not pairs:
                n_inconsistent += 1
        check(
            "exclusion_reasons pairs consistent with eligible/triggered_rules "
            "(codes match, texts non-empty, null iff eligible)",
            0,
            n_inconsistent,
            n_inconsistent == 0,
        )

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
