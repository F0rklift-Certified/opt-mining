"""
Stage entry point for the S1-11 preliminary ranked-shortlist stage (`shortlist`,
Requirement 10).

Orchestrates the stage in the order the design specifies (design.md §"Data
flow"), wiring the already-implemented modules together and doing nothing else
of substance itself — every rule lives in the module it belongs to:

    resolve Top_N -> load Scored_Table -> select (pure) -> load grid
    -> join coordinates -> assemble -> summarise (pure) -> derive one
    Run_Timestamp + resolve versioned filenames -> write CSV + GeoJSON
    -> write Summary_Report + metadata sidecar -> record provenance

FAIL BEFORE WRITE. The effective Top_N is resolved FIRST — the cheapest thing
to get wrong — so a non-positive-integer value halts before the Scored_Table is
even opened (Requirement 3.5). The Scored_Table and the grid are then loaded and
validated (missing/unreadable file, absent required column) before any output
directory is touched, and the coordinate join halts on any unmatched
shortlisted `cell_id` (Requirement 4.5). Every fatal condition therefore raises
BEFORE `run()` writes anything, so a failed run never leaves a partial or stale
shortlist on disk (Requirement 10.3).

ONE Run_Timestamp, ONE Pipeline_Version. Both are derived exactly once and
threaded into the filenames and every metadata artefact, so the filenames, the
Summary_Report and the sidecar can never disagree about which run produced the
outputs (Requirement 7.2, 9.4).

This stage is a FILTERING and FORMATTING step: it performs no re-scoring and no
re-ranking, selects by the existing integer S1-10 `rank`, and never re-derives
the grid. It raises rather than returning on any failure, so the orchestrator
halts with a non-zero exit status.

Design reference: Sprint-1-Tasks/S1-11-Generate-Ranked-Shortlist/design.md
§1 "Stage entry point".
"""

from __future__ import annotations

import time
from pathlib import Path

from . import config
from .assemble import assemble_shortlist, optional_context_columns
from .coords import join_coordinates, load_grid
from .load import load_scored_table
from .naming import resolve_output_paths, run_timestamp
from .report import (
    pipeline_version,
    record_provenance,
    write_metadata_sidecar,
    write_summary_report,
)
from .select import eligible_cells, select_shortlist
from .summary import compute_summary
from .write import write_csv, write_geojson


def _rel(path: Path | str) -> str:
    """Path relative to the project root for log lines; absolute when it lies
    outside the project tree. Mirrors `scoring.run._rel`."""
    try:
        return str(Path(path).relative_to(config.PROJECT_ROOT))
    except ValueError:
        return str(path)


def run(
    verbose: bool = False,
    top_n: int | None = None,
    scored_path: Path | str | None = None,
    grid_path: Path | str | None = None,
    geometry: str = config.DEFAULT_GEOMETRY,
) -> dict:
    """
    Select the top-N eligible cells by their existing S1-10 `rank`, join each
    cell's `centroid_lat` / `centroid_lon` from the Analysis_Grid on `cell_id`
    in EPSG:4326, and write the Shortlist_CSV, the Shortlist_GeoJSON and the
    Summary_Report, plus the metadata sidecar and derived-product provenance.

    Parameters
    ----------
    verbose : bool
        Print the resolved eligible/included counts and the per-artefact
        output paths. The stage always prints its numbered progress lines;
        `verbose` adds the detail lines. First parameter, defaults to `False`,
        per the registered-stage contract (Requirement 10.1).
    top_n : int | None
        The requested Top_N (CLI `--shortlist-top-n`). `None` falls back to the
        pipeline-config value then `config.DEFAULT_TOP_N` (20) via
        `config.resolve_top_n` (Requirement 3.1, 3.3). A non-positive-integer
        resolved value halts before any output (Requirement 3.5).
    scored_path : Path | str | None
        The S1-10 Scored_Table. `None` defaults to `config.SCORED_PATH` inside
        the loader.
    grid_path : Path | str | None
        The S1-02 Analysis_Grid. `None` defaults to `config.GRID_PATH` inside
        the grid loader.
    geometry : str
        The documented GeoJSON geometry choice, one of
        `config.GEOMETRY_CHOICES` (`"centroid"` Point, default, or `"polygon"`
        cell) — noted for the Summary_Report (Requirement 5.4).

    Returns
    -------
    dict
        A summary of the run (design.md §1). The three output-path values
        (`shortlist_csv_path`, `shortlist_geojson_path`, `summary_report_path`)
        exist on disk when this returns (Requirement 10.2), and the single UTC
        Run_Timestamp is reused across the filenames and the metadata
        (Requirement 7.2).

    Raises
    ------
    ValueError / FileNotFoundError / RuntimeError / KeyError
        On a non-positive-integer Top_N, a missing/unreadable Scored_Table or
        grid, an absent required column, an unmatched shortlisted `cell_id`, or
        a write failure — every one raised BEFORE (or without leaving) any
        partial output, so the orchestrator halts with a non-zero exit status
        (Requirement 10.3).
    """
    t0 = time.time()

    # [1/8] Resolve the effective Top_N FIRST — halt before any output on a
    # non-positive-integer value (Requirement 3.5). No file is opened yet, so an
    # invalid Top_N leaves nothing on disk.
    effective_top_n = config.resolve_top_n(top_n, None)
    print(f"  [1/8] Effective Top_N: {effective_top_n} (geometry {geometry!r})")

    # Derive the single UTC Run_Timestamp and the Pipeline_Version exactly once,
    # then thread them into ALL outputs and metadata (Requirement 7.2, 9.4).
    ts = run_timestamp()
    pv = pipeline_version(config.PROJECT_ROOT)
    print(f"        Run timestamp (UTC) {ts}; pipeline version {pv}")

    # [2/8] The sole per-cell score input — fail-fast on missing/unreadable file
    # or an absent required column (Requirement 1.4, 1.5). `None` → the loader
    # defaults to config.SCORED_PATH.
    effective_scored_path = Path(scored_path) if scored_path is not None else config.SCORED_PATH
    print("  [2/8] Reading Scored_Table...")
    scored = load_scored_table(scored_path if scored_path is not None else None)
    print(f"        {len(scored):,} cells  ({_rel(effective_scored_path)}, "
          f"layer {config.SCORED_LAYER})")

    # [3/8] Pure selection by the existing S1-10 rank (no re-scoring/re-ranking).
    n_eligible = int(len(eligible_cells(scored)))
    shortlist = select_shortlist(scored, effective_top_n)
    n_shortlisted = int(len(shortlist))
    print(f"  [3/8] Selected {n_shortlisted:,} of {n_eligible:,} eligible "
          f"cell(s) by ascending rank"
          + (" (Top_N exceeded the eligible count — clamped, not padded)"
             if effective_top_n > n_eligible else ""))

    # [4/8] Attach centroid_lat/centroid_lon from the grid on cell_id in
    # EPSG:4326 — halt on any unmatched shortlisted cell_id (Requirement 4.5).
    effective_grid_path = Path(grid_path) if grid_path is not None else config.GRID_PATH
    print("  [4/8] Reading Analysis_Grid and joining coordinates...")
    grid = load_grid(grid_path if grid_path is not None else None)
    joined = join_coordinates(shortlist, grid)
    print(f"        {len(grid):,} grid cell(s)  ({_rel(effective_grid_path)}, "
          f"layer {config.GRID_LAYER}, CRS {config.STORAGE_CRS})")

    # [5/8] Assemble the documented schema + gather any optional context columns
    # (with their definitions/sources) for the Summary_Report.
    assembled = assemble_shortlist(joined)
    optional_context = optional_context_columns(joined)
    if verbose and optional_context:
        print("        optional context columns: "
              + ", ".join(col.name for col in optional_context))

    # [6/8] Pure summary statistics (score distribution over eligible cells
    # only; geographic spread + confidence over the shortlisted cells).
    stats = compute_summary(scored, assembled)

    # Ensure the output directories exist before writing (Requirement 10.2).
    config.SHORTLIST_DIR.mkdir(parents=True, exist_ok=True)
    config.SHORTLIST_META_DIR.mkdir(parents=True, exist_ok=True)

    # Resolve the timestamped/versioned filenames from the SAME Run_Timestamp
    # (Requirement 7.1, 7.2); the collision rule surfaces its outcome for the
    # Summary_Report (Requirement 7.4).
    resolved = resolve_output_paths(config.SHORTLIST_DIR, ts)
    if resolved.collision.occurred:
        print(f"        name collision on {resolved.collision.base_stem!r}; "
              f"resolved to {resolved.collision.resolved_stem!r} "
              f"(precision {resolved.collision.precision})")

    # [7/8] Write the two headline outputs (same cell_id set, same rank order).
    print("  [7/8] Writing outputs...")
    write_csv(assembled, resolved.csv)
    write_geojson(assembled, resolved.geojson, geometry)
    print(f"        -> {_rel(resolved.csv)}")
    print(f"        -> {_rel(resolved.geojson)}")

    # [8/8] Write the Summary_Report + metadata sidecar (disclaimer +
    # resolution), then record derived-product provenance. Pipeline_Version and
    # Run_Timestamp are recorded identically across both metadata artefacts
    # (Requirement 9.4).
    print("  [8/8] Writing metadata and provenance...")
    summary_report_path = write_summary_report(
        config.SHORTLIST_META_DIR / config.SUMMARY_REPORT_FILENAME,
        stats=stats,
        effective_top_n=effective_top_n,
        n_shortlisted=n_shortlisted,
        geometry=geometry,
        optional_context=optional_context,
        collision=resolved.collision,
        pipeline_version=pv,
        run_timestamp=ts,
    )
    metadata_sidecar_path = write_metadata_sidecar(
        config.SHORTLIST_META_DIR / config.METADATA_SIDECAR_FILENAME,
        scored_path=effective_scored_path,
        effective_top_n=effective_top_n,
        n_shortlisted=n_shortlisted,
        geometry=geometry,
        pipeline_version=pv,
        run_timestamp=ts,
    )
    manifest_path = config.SHORTLIST_META_DIR / config.MANIFEST_FILENAME
    provenance_path = config.SHORTLIST_DIR / config.PROVENANCE_FILENAME
    register_path = config.SHORTLIST_META_DIR / config.SOURCE_REGISTER_FILENAME
    record_provenance(
        csv_path=resolved.csv,
        geojson_path=resolved.geojson,
        scored_path=effective_scored_path,
        grid_path=effective_grid_path,
        effective_top_n=effective_top_n,
        n_shortlisted=n_shortlisted,
        run_timestamp=ts,
        pipeline_version=pv,
        manifest_path=manifest_path,
        provenance_path=provenance_path,
        register_path=register_path,
        scored_layer=config.SCORED_LAYER,
        grid_layer=config.GRID_LAYER,
    )
    if verbose:
        print(f"        -> {_rel(summary_report_path)}")
        print(f"        -> {_rel(metadata_sidecar_path)}")
        print(f"        -> {_rel(manifest_path)}, {_rel(provenance_path)}, "
              f"{_rel(register_path)}")

    runtime_s = time.time() - t0
    print(f"        Shortlisted {n_shortlisted:,} of {n_eligible:,} eligible "
          f"(Top_N {effective_top_n}); runtime {runtime_s:.1f}s")

    return {
        # Output paths — all three exist on disk now (Requirement 10.2).
        "shortlist_csv_path": str(resolved.csv),
        "shortlist_geojson_path": str(resolved.geojson),
        "summary_report_path": str(summary_report_path),
        "metadata_sidecar_path": str(metadata_sidecar_path),
        "manifest_path": str(manifest_path),
        "provenance_path": str(provenance_path),
        "source_register_path": str(register_path),
        # Selection sizing (Requirement 2.5, 6.5, 9.2).
        "effective_top_n": effective_top_n,
        "n_shortlisted": n_shortlisted,
        "n_eligible": n_eligible,
        "n_scored": stats.n_scored,
        "n_cells": stats.n_cells,
        # Reproducibility metadata — the single Run_Timestamp reused across
        # filenames and metadata (Requirement 7.2, 9.1).
        "run_timestamp": ts,
        "pipeline_version": pv,
        # Naming outcome (Requirement 7.4) and geometry choice (Requirement 5.4).
        "collision": {
            "occurred": resolved.collision.occurred,
            "resolved_stem": resolved.collision.resolved_stem,
        },
        "geometry": geometry,
        "runtime_seconds": runtime_s,
    }
