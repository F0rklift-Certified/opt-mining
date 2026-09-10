"""
Stage entry point for the S1-12 validation / sanity-check stage (`sanity`,
Requirement 9).

This is the pipeline's TERMINAL stage. It consumes the Sprint 1 outputs
READ-ONLY (the ranked Shortlist, the per-cell Scored_Table, the
Integrated_Feature_Table, the GA Wind_Generators, and the Analysis_Grid) and
produces a human-readable Validation_Report plus an optional machine-readable
Results_Sidecar. It runs four plausibility checks that ask whether the
pipeline's outputs make sense against known reality; it is a REALITY-CHECK
reporting step, NOT a modelling step and NOT the structural validation in
`pipeline/validate.py`.

Orchestrates the stage in the order the design specifies (design.md §1
"Stage entry point"), wiring the already-implemented modules together and doing
nothing else of substance itself — every rule lives in the module it belongs to:

    validate spot_cells -> resolve_shortlist + load_inputs -> split
    eligible/excluded -> join grid centroids + integrated wind_speed onto
    eligible -> check_known_wind_farms / check_exclusions / select_spot_cells +
    check_spot_values / check_distribution -> collect_issues -> render_report +
    write_report (+ write_sidecar) -> record_provenance

FAIL BEFORE WRITE. The requested `spot_cells` count is validated FIRST — the
cheapest thing to get wrong — so a value outside [SPOT_CHECK_MIN,
SPOT_CHECK_MAX] halts before any input is opened, naming the invalid count
(Requirement 4.5). The five inputs are then loaded and validated (missing /
unreadable file, absent required column, unresolvable CRS) BEFORE any output
directory is touched (1.4, 1.5). Every fatal condition therefore RAISES (never
returns a dict) before `run()` writes anything, so a failed run never leaves a
partial or stale report on disk and the orchestrator halts with a non-zero exit
status (9.3). The stage NEVER writes to any input (8.1).

ONE Run_Timestamp, ONE Pipeline_Version. Both are derived exactly once and
threaded into the report header, the sidecar, and the provenance record, so the
report, the sidecar and the manifest can never disagree about which run
produced the outputs.

Design reference: .kiro/specs/s1-12-validation-sanity-check/design.md
§1 "Stage entry point".
"""

from __future__ import annotations

import time
from pathlib import Path

from ..common.geo import utc_now
from ..shortlist.report import pipeline_version
from . import config
from .checks import (
    check_distribution,
    check_exclusions,
    check_known_wind_farms,
    check_spot_values,
    select_spot_cells,
)
from .geo import CrsTransform
from .issues import collect_issues
from .load import SanityInputs, load_inputs, resolve_shortlist
from .report import (
    RunMetadata,
    SanityResults,
    record_provenance,
    render_report,
    write_report,
)
# `run()` has a `write_sidecar` bool parameter that would shadow the writer
# function of the same name, so import the writer under a private alias.
from .report import write_sidecar as _write_sidecar

# The Integrated_Feature_Table column Check 4 correlates the score against, and
# the grid centroid columns Checks 3/4 need — both must be joined onto the
# eligible frame (which carries only cell_id/suitability_score/rank from the
# Scored_Table) BEFORE the pure checks run.
_CELL_ID = config.REQUIRED_SCORE_COLUMNS[0]  # "cell_id"
_CENTROID_LAT = config.REQUIRED_GRID_COLUMNS[1]  # "centroid_lat"
_CENTROID_LON = config.REQUIRED_GRID_COLUMNS[2]  # "centroid_lon"
_WIND_SPEED = config.REQUIRED_INTEGRATED_COLUMNS[1]  # "wind_speed"


def _rel(path: Path | str) -> str:
    """Path relative to the project root for log lines; absolute when it lies
    outside the project tree. Mirrors ``scoring.run._rel`` /
    ``shortlist.run._rel``."""
    try:
        return str(Path(path).relative_to(config.PROJECT_ROOT))
    except ValueError:
        return str(path)


def _enrich_eligible(eligible, grid, integrated):
    """
    Join the grid centroids and the integrated ``wind_speed`` onto the eligible
    frame on ``cell_id``, so Check 3 (spot values) and Check 4 (distribution)
    can read ``centroid_lat`` / ``centroid_lon`` and the wind correlation.

    The Eligible_Cell frame comes from the Scored_Table and carries only
    ``cell_id`` / ``suitability_score`` / ``rank``. ``select_spot_cells`` and
    ``check_distribution`` need each cell's centroid (from the Analysis_Grid) and
    ``wind_speed`` (from the Integrated_Feature_Table) — this is the join the
    notes left by tasks 5.1 and 6.1 expect the caller to perform.

    PURE: builds and returns a new frame; never mutates ``eligible``. A LEFT join
    keeps every eligible cell (an unmatched centroid/wind_speed becomes null and
    is handled honestly by the downstream checks — a MISSING spot value, or a
    dropped pair in the correlation). Any column already present on ``eligible``
    is not overwritten, so a re-run/re-join is a no-op on those columns.
    """
    enriched = eligible.copy()

    # Grid centroids on cell_id (only the columns not already present).
    grid_cols = [
        c for c in (_CENTROID_LAT, _CENTROID_LON)
        if c in grid.columns and c not in enriched.columns
    ]
    if grid_cols:
        centroids = grid[[_CELL_ID, *grid_cols]].drop_duplicates(subset=_CELL_ID)
        enriched = enriched.merge(centroids, on=_CELL_ID, how="left")

    # Integrated wind_speed on cell_id (for Check 4's wind-vs-score correlation).
    if _WIND_SPEED in integrated.columns and _WIND_SPEED not in enriched.columns:
        wind = integrated[[_CELL_ID, _WIND_SPEED]].drop_duplicates(subset=_CELL_ID)
        enriched = enriched.merge(wind, on=_CELL_ID, how="left")

    return enriched


def run(
    verbose: bool = False,
    spot_cells: int = config.SPOT_CHECK_DEFAULT,
    wind_generators_path: Path | str | None = None,
    shortlist_dir: Path | str | None = None,
    scored_path: Path | str | None = None,
    integrated_path: Path | str | None = None,
    grid_path: Path | str | None = None,
    containment_crs: str = config.CONTAINMENT_CRS,
    write_sidecar: bool = True,
) -> dict:
    """
    Run the four plausibility checks over the Sprint 1 outputs read-only and
    write the Validation_Report (plus, optionally, the Results_Sidecar) and its
    derived-product provenance.

    Parameters
    ----------
    verbose : bool
        Print the per-check detail lines in addition to the numbered progress
        lines. First parameter, defaults to ``False``, per the registered-stage
        contract (Requirement 9.1).
    spot_cells : int
        The requested Spot_Check_Cells count (CLI ``--sanity-spot-cells``),
        validated to the inclusive range ``[SPOT_CHECK_MIN, SPOT_CHECK_MAX]``
        (``[5, 10]``). A value outside the range halts BEFORE any output, naming
        the invalid count (Requirement 4.5). Defaults to ``SPOT_CHECK_DEFAULT``.
    wind_generators_path : Path | str | None
        Override for the GA Wind_Generators input (CLI ``--wind-generators``).
        ``None`` uses ``config.WIND_GENERATORS_PATH``.
    shortlist_dir : Path | str | None
        The directory the latest timestamped Shortlist is resolved from. ``None``
        uses ``config.SHORTLIST_DIR``.
    scored_path, integrated_path, grid_path : Path | str | None
        Overrides for the Scored_Table, Integrated_Feature_Table, and
        Analysis_Grid inputs. ``None`` uses the corresponding ``config`` default.
    containment_crs : str
        The single explicit CRS every containment operation runs in, logged in
        the report's transform log. Defaults to ``config.CONTAINMENT_CRS``
        (EPSG:3577); never assumed silently.
    write_sidecar : bool
        Whether to emit the optional machine-readable Results_Sidecar. When
        ``True`` (the default) the sidecar is written atomically and recorded in
        provenance alongside the report.

    Returns
    -------
    dict
        A summary of the run (design.md §1). The returned ``report_path`` (and
        any ``sidecar_path``) exist on disk when this returns (Requirement 9.2),
        and the single UTC ``run_timestamp`` is reused across the report, the
        sidecar, and the provenance record.

    Raises
    ------
    ValueError / FileNotFoundError / RuntimeError
        On an invalid ``spot_cells`` count, a missing / unreadable input, an
        absent required column, an unresolvable CRS, or a write failure — every
        one raised BEFORE (or without leaving) any partial output, so the
        orchestrator halts with a non-zero exit status (Requirements 1.4, 1.5,
        4.5, 7.9, 9.3). No input is ever written (8.1).
    """
    t0 = time.time()

    # [1/7] Validate the Spot_Check_Cells count FIRST — halt before any input is
    # opened or any output is written on a value outside [5, 10], naming the
    # invalid count (Requirement 4.5). Nothing is on disk yet, so an invalid
    # count leaves no partial output.
    if not (config.SPOT_CHECK_MIN <= spot_cells <= config.SPOT_CHECK_MAX):
        raise ValueError(
            f"sanity: requested Spot_Check_Cells count {spot_cells} is outside "
            f"the inclusive range [{config.SPOT_CHECK_MIN}, "
            f"{config.SPOT_CHECK_MAX}]; halting before any output."
        )
    print(f"  [1/7] Spot_Check_Cells: {spot_cells} "
          f"(range [{config.SPOT_CHECK_MIN}, {config.SPOT_CHECK_MAX}])")

    # Derive the single UTC Run_Timestamp and the Pipeline_Version exactly once,
    # then thread them into the report header, the sidecar, and provenance.
    run_timestamp = utc_now()
    pv = pipeline_version(config.PROJECT_ROOT)
    print(f"        Run timestamp (UTC) {run_timestamp}; pipeline version {pv}")

    # [2/7] Resolve the latest Shortlist and load all five inputs READ-ONLY.
    # The loader halts BEFORE any output on a missing/unreadable file, an absent
    # required column, or an unresolvable CRS, each naming the offending
    # path/column/source (Requirements 1.4, 1.5, 2.2, 3.5). No input is mutated
    # (8.1).
    print("  [2/7] Resolving Shortlist and loading inputs (read-only)...")
    resolved_shortlist_path = resolve_shortlist(
        shortlist_dir if shortlist_dir is not None else config.SHORTLIST_DIR
    )
    paths = SanityInputs(
        scored_path=Path(scored_path) if scored_path is not None else config.SCORED_PATH,
        shortlist_path=resolved_shortlist_path,
        integrated_path=(
            Path(integrated_path) if integrated_path is not None else config.INTEGRATED_PATH
        ),
        wind_generators_path=(
            Path(wind_generators_path)
            if wind_generators_path is not None
            else config.WIND_GENERATORS_PATH
        ),
        grid_path=Path(grid_path) if grid_path is not None else config.GRID_PATH,
    )
    frames = load_inputs(paths)

    n_cells = int(len(frames.grid)) if len(frames.grid) else int(len(frames.scored))
    n_eligible = int(len(frames.eligible))
    print(f"        {n_cells:,} grid cell(s); {n_eligible:,} eligible "
          f"(scored + ranked); shortlist {_rel(resolved_shortlist_path)}")
    if verbose:
        print(f"        scored     {_rel(paths.scored_path)} "
              f"(layer {config.SCORED_LAYER})")
        print(f"        integrated {_rel(paths.integrated_path)} "
              f"(layer {config.INTEGRATED_LAYER})")
        print(f"        grid       {_rel(paths.grid_path)} "
              f"(layer {config.GRID_LAYER})")
        print(f"        generators {_rel(paths.wind_generators_path)}")

    # Join the grid centroids and the integrated wind_speed onto the eligible
    # frame on cell_id (the join the notes for tasks 5.1 / 6.1 expect), so Check
    # 3 records centroid_lat/lon and Check 4 computes the wind-vs-score
    # correlation. PURE: the loader's frames are never mutated.
    eligible_enriched = _enrich_eligible(
        frames.eligible, frames.grid, frames.integrated
    )

    # A single shared transform log — every containment operation appends to it,
    # and the report renders it verbatim so no containment CRS is silently
    # assumed (2.2, 3.5).
    transform_log: list[CrsTransform] = []

    # [3/7] The four pure plausibility checks (frames in, structured results
    # out; no filesystem access, no mutation of any input).
    print("  [3/7] Running plausibility checks...")

    # Check 1 — Known Wind Farm Comparison (Requirement 2).
    wind_farms = check_known_wind_farms(
        frames.wind_generators, frames.grid, frames.scored,
        containment_crs, transform_log,
    )
    print(f"        Check 1 (Known Wind Farms): "
          f"{wind_farms.n_upper_quartile}/{wind_farms.n_known_farms} in "
          f"Upper_Quartile -> "
          f"{'PASS' if wind_farms.outcome.passed else 'FAIL'}")

    # Check 2 — Exclusion Validation (Requirement 3).
    exclusions = check_exclusions(
        config.LANDMARKS, frames.grid, frames.scored, frames.integrated,
        containment_crs, transform_log,
    )
    print(f"        Check 2 (Exclusion Validation): "
          f"{exclusions.n_passed} passed / {exclusions.n_failed} failed -> "
          f"{'PASS' if exclusions.all_passed else 'FAIL'}")

    # Check 3 — Feature-Value Spot-Checks (Requirement 4). Deterministic
    # selection over the enriched eligible frame, then record each cell's
    # feature values for INDEPENDENT reviewer verification (human-judgement
    # item; no automated pass/fail).
    spot_selection = select_spot_cells(eligible_enriched, spot_cells)
    spot_values = check_spot_values(spot_selection, frames.integrated)
    print(f"        Check 3 (Spot-Checks): recorded "
          f"{spot_values.n_spot_cells} cell(s) for verification")

    # Check 4 — Score-Distribution Plausibility (Requirement 5).
    distribution = check_distribution(eligible_enriched)
    print(f"        Check 4 (Distribution): clustering "
          f"{'PASS' if distribution.cluster_outcome.passed else 'FAIL'}, "
          f"correlation "
          f"{'PASS' if distribution.correlation_outcome.passed else 'FAIL'}")

    # [4/7] Gather every honestly-recorded Anomaly into the Sprint-2 issues
    # section — nothing is suppressed, nothing is used to adjust the model
    # (Requirement 6).
    issues = collect_issues(wind_farms, exclusions, spot_values, distribution)
    print(f"  [4/7] Issues for Sprint 2: {len(issues)} anomal"
          f"{'y' if len(issues) == 1 else 'ies'} recorded")

    # Assemble the aggregate the renderer/sidecar consume, and the run metadata.
    results = SanityResults(
        wind_farms=wind_farms,
        exclusions=exclusions,
        spot_values=spot_values,
        distribution=distribution,
        issues=issues,
        transform_log=transform_log,
    )
    meta = RunMetadata(
        run_timestamp=run_timestamp,
        pipeline_version=pv,
        n_cells=n_cells,
        n_eligible=n_eligible,
        resolved_shortlist_path=_rel(resolved_shortlist_path),
    )

    # Ensure the output directories exist before writing (Requirement 9.2, 7.9).
    config.REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.SANITY_DIR.mkdir(parents=True, exist_ok=True)
    config.SANITY_META_DIR.mkdir(parents=True, exist_ok=True)

    # [5/7] Render + atomically write the Validation_Report. A write failure
    # leaves any pre-existing report unmodified and raises (Requirements 7.7,
    # 7.9).
    print("  [5/7] Writing Validation_Report...")
    report_text = render_report(results, meta)
    write_report(report_text, config.REPORT_PATH)
    print(f"        -> {_rel(config.REPORT_PATH)}")

    # [6/7] Optionally write the machine-readable Results_Sidecar (7.8, 7.9,
    # 10.2). The single Run_Timestamp/Pipeline_Version metadata is recorded on
    # it so it never disagrees with the report.
    sidecar_path: Path | None = None
    if write_sidecar:
        sidecar_path = config.SIDECAR_PATH
        _write_sidecar(results, sidecar_path, meta)
        print(f"        -> {_rel(sidecar_path)}")

    # [7/7] Record the report (and any sidecar) as DERIVED products in all three
    # provenance artefacts, listing all five READ-ONLY inputs and the single UTC
    # Run_Timestamp (Requirement 10).
    print("  [7/7] Recording provenance...")
    manifest_path = config.SANITY_META_DIR / config.MANIFEST_FILENAME
    provenance_path = config.SANITY_DIR / config.PROVENANCE_FILENAME
    register_path = config.SANITY_META_DIR / config.SOURCE_REGISTER_FILENAME
    record_provenance(
        report_path=config.REPORT_PATH,
        sidecar_path=sidecar_path,
        shortlist_path=resolved_shortlist_path,
        scored_path=paths.scored_path,
        integrated_path=paths.integrated_path,
        wind_generators_path=paths.wind_generators_path,
        grid_path=paths.grid_path,
        run_timestamp=run_timestamp,
        pipeline_version=pv,
        manifest_path=manifest_path,
        provenance_path=provenance_path,
        register_path=register_path,
        scored_layer=config.SCORED_LAYER,
        integrated_layer=config.INTEGRATED_LAYER,
        grid_layer=config.GRID_LAYER,
    )
    if verbose:
        print(f"        -> {_rel(manifest_path)}, {_rel(provenance_path)}, "
              f"{_rel(register_path)}")

    runtime_seconds = time.time() - t0
    print(f"        Checked {n_cells:,} cell(s), {n_eligible:,} eligible; "
          f"runtime {runtime_seconds:.1f}s")

    return {
        # Output paths — report (and any sidecar) exist on disk now (9.2).
        "report_path": str(config.REPORT_PATH),
        "sidecar_path": str(sidecar_path) if sidecar_path is not None else None,
        "resolved_shortlist_path": str(resolved_shortlist_path),
        # Sizing.
        "n_cells": n_cells,
        "n_eligible": n_eligible,
        # Check 1 — Known Wind Farm Comparison.
        "n_known_farms": wind_farms.n_known_farms,
        "n_farms_upper_quartile": wind_farms.n_upper_quartile,
        "check1_pass": wind_farms.outcome.passed,
        # Check 2 — Exclusion Validation.
        "n_exclusion_checks_passed": exclusions.n_passed,
        "n_exclusion_checks_failed": exclusions.n_failed,
        "check2_pass": exclusions.all_passed,
        # Check 3 — Feature-Value Spot-Checks (human-judgement item, recorded).
        "n_spot_cells": spot_values.n_spot_cells,
        "check3_recorded": True,
        # Check 4 — Score-Distribution Plausibility.
        "check4_pass": (
            distribution.cluster_outcome.passed
            and distribution.correlation_outcome.passed
        ),
        # Reproducibility metadata — the single Run_Timestamp / Pipeline_Version.
        "run_timestamp": run_timestamp,
        "pipeline_version": pv,
        "runtime_seconds": runtime_seconds,
    }
