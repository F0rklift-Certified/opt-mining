"""
Stage entry point for the S1-10 baseline suitability model (Requirement 11).

Orchestrates the stage in the order the design specifies:

    load weights -> load integrated table -> compute bounds (eligible only)
    -> score (pure) -> rank -> assemble -> write -> report -> provenance
    -> validate

FAIL BEFORE WRITE. The weights file is loaded and validated first, before the
47,311-row feature table is even opened, and the feature table's columns are
checked before anything is computed. Every fatal condition therefore halts the
run without touching the previous outputs, so a failed run never leaves a
partial or stale scored table on disk that a later stage might read as good.

Raises rather than returning on any failure, so the orchestrator halts with a
non-zero exit status.
"""

from __future__ import annotations

import time
from pathlib import Path

from ..common.geo import atomic_write_text, sha256_file, utc_now
from . import config
from .load import load_integrated
from .normalise import compute_bounds
from .report import (
    build_method_report,
    build_validation_report,
    git_commit,
    record_provenance,
)
from .score import eligible_mask, score_and_rank, summarise
from .validate import validate as validate_scored
from .weights import load_weights
from .write import build_scored_table, output_columns, write_scored_table


def _rel(path: Path) -> str:
    try:
        return str(Path(path).relative_to(config.PROJECT_ROOT))
    except ValueError:
        return str(path)


def _print_checks(result: dict) -> None:
    for check in result["checks"]:
        status = "PASS" if check["passed"] else "**FAIL**"
        print(f"    [{status}] {check['name']}: expected {check['expected']}, "
              f"observed {check['observed']}")
    print(f"    {result['passed']}/{result['total']} checks passed "
          f"({result['failed']} failures)")


def run(
    verbose: bool = False,
    weights_path: Path | None = None,
    integrated_path: Path | None = None,
    confidence_discount: bool | None = None,
) -> dict:
    """
    Score every eligible analysis cell with a weighted MCDA over normalised
    criteria, then write the Scored_Table, the method report, the validation
    report and provenance.

    Parameters
    ----------
    verbose : bool
        Print per-criterion bounds and the full check list.
    weights_path : Path | None
        Criteria weights YAML (CLI: `--scoring-weights`). Defaults to the
        packaged `pipeline/scoring/scoring_weights.yaml`.
    integrated_path : Path | None
        Integrated feature table. Defaults to the S1-08 output.
    confidence_discount : bool | None
        Override the weights file's `confidence_discount` setting. `None`
        (the default) uses whatever the file says.

    Returns a summary dict including `scored_table_path` and
    `method_report_path`, both of which exist on disk when this returns.

    Raises ScoringConfigError / FileNotFoundError / ValueError / RuntimeError
    on a bad config, a missing or malformed input, or a failed validation
    check, so the orchestrator halts with a non-zero exit status.
    """
    t0 = time.time()
    generated_utc = utc_now()
    commit = git_commit(config.PROJECT_ROOT)

    # [1/6] Weights first — the cheapest thing to get wrong, so fail on it
    # before reading a 47k-row table.
    weights = load_weights(weights_path or config.DEFAULT_WEIGHTS_PATH)
    if confidence_discount is not None:
        from dataclasses import replace

        weights = replace(weights, confidence_discount=bool(confidence_discount))
    print(f"  [1/6] Criteria weights: {_rel(weights.path)} "
          f"(version {weights.version}, {len(weights.criteria)} criteria, "
          f"Σw = {weights.weight_sum:g}, "
          f"discount {'on' if weights.confidence_discount else 'off'})")
    for criterion in weights.criteria:
        print(f"          {criterion.feature:24s} {criterion.weight:>5g}  "
              f"{criterion.direction}")

    # [2/6] The sole feature input.
    integrated_path = Path(integrated_path or config.INTEGRATED_PATH)
    print(f"  [2/6] Reading integrated feature table...")
    features = load_integrated(integrated_path, weights.criteria)
    print(f"        {len(features):,} cells  ({_rel(integrated_path)}, "
          f"layer {config.INTEGRATED_LAYER}, CRS {features.crs.to_string()})")

    # [3/6] Bounds from the eligible population only, computed once so the
    # method report and the scores can never disagree.
    mask = eligible_mask(features)
    bounds = compute_bounds(features.loc[mask], weights.criteria)
    print(f"  [3/6] Normalisation bounds from {int(mask.sum()):,} eligible cells")
    constant = [f for f, b in bounds.items() if b.is_constant]
    if verbose or constant:
        for criterion in weights.criteria:
            b = bounds[criterion.feature]
            note = "  <- CONSTANT, cannot discriminate" if b.is_constant else ""
            print(f"          {criterion.feature:24s} "
                  f"[{b.lo:.4f}, {b.hi:.4f}]  n={b.n_observed:,}{note}")
    if constant:
        print(f"        NOTE: {len(constant)} criterion/criteria constant over the "
              f"eligible population; each adds a flat offset to every score and "
              f"cannot change the ranking (see the method report).")

    # [4/6] The pure core.
    print("  [4/6] Scoring (weighted MCDA) and ranking...")
    scored = score_and_rank(features, weights, bounds=bounds)
    summary = summarise(scored, features)
    print(f"        scored {summary['n_scored']:,}; "
          f"excluded (null score) {summary['n_excluded']:,}; "
          f"score range [{summary['score_min']:.4f}, {summary['score_max']:.4f}]"
          if summary["n_scored"]
          else f"        scored 0; excluded {summary['n_excluded']:,}")

    table = build_scored_table(features, scored, weights)

    # [5/6] Write, then report. The validation report is written even when
    # validation fails, so a failed run still leaves the evidence behind.
    print("  [5/6] Writing outputs...")
    gpkg_path = config.SCORING_DIR / config.OUTPUT_FILENAME
    csv_path = config.SCORING_DIR / config.CSV_FILENAME
    write_scored_table(table, gpkg_path, csv_path)
    print(f"        -> {_rel(gpkg_path)} (layer {config.OUTPUT_LAYER})")
    print(f"        -> {_rel(csv_path)}")

    meta_dir = config.SCORING_META_DIR
    validation_path = meta_dir / config.VALIDATION_REPORT_FILENAME
    report_path = meta_dir / config.METHOD_REPORT_FILENAME
    manifest_path = meta_dir / config.MANIFEST_FILENAME
    register_path = meta_dir / config.SOURCE_REGISTER_FILENAME
    provenance_path = config.SCORING_DIR / config.PROVENANCE_FILENAME

    # [6/6] Validate — no silent passes.
    print("  [6/6] Validating (no silent passes)...")
    result = validate_scored(table, features, weights)
    atomic_write_text(validation_path,
                      build_validation_report(result, generated_utc, commit))
    if verbose or result["failed"]:
        _print_checks(result)
    else:
        print(f"        {result['passed']}/{result['total']} checks passed")
    print(f"        -> {_rel(validation_path)}")

    inputs = {
        "integrated_path": integrated_path,
        "integrated_layer": config.INTEGRATED_LAYER,
        "integrated_rows": int(len(features)),
        "integrated_crs": features.crs.to_string(),
        "integrated_sha256": sha256_file(integrated_path),
        "integrated_bytes": integrated_path.stat().st_size,
    }
    runtime_s = time.time() - t0
    outputs = {
        "Scored table (GeoPackage)": gpkg_path,
        "Scored table (CSV)": csv_path,
        "Method report": report_path,
        "Validation report": validation_path,
        "Manifest": manifest_path,
        "Provenance": provenance_path,
        "Source register": register_path,
    }
    atomic_write_text(report_path, build_method_report(
        weights=weights, bounds=bounds, summary=summary, result=result,
        inputs=inputs, outputs=outputs, runtime_s=runtime_s,
        generated_utc=generated_utc, commit=commit,
    ))
    record_provenance(
        gpkg_path=gpkg_path, csv_path=csv_path,
        columns=output_columns(weights), n_rows=len(table),
        weights=weights, inputs=inputs, summary=summary,
        generated_utc=generated_utc, commit=commit,
        manifest_path=manifest_path, provenance_path=provenance_path,
        register_path=register_path,
    )
    print(f"        -> {_rel(report_path)}")
    print(f"        -> {_rel(manifest_path)}, {_rel(provenance_path)}, "
          f"{_rel(register_path)}")

    if result["failed"]:
        raise RuntimeError(
            f"scored table failed validation: {', '.join(result['failed_names'])} "
            f"(see {validation_path})"
        )

    print(f"        Cells {summary['n_cells']:,}; scored {summary['n_scored']:,}; "
          f"runtime {runtime_s:.1f}s")

    return {
        "scored_table_path": str(gpkg_path),
        "method_report_path": str(report_path),
        "csv_path": str(csv_path),
        "validation_report_path": str(validation_path),
        "manifest_path": str(manifest_path),
        "provenance_path": str(provenance_path),
        "source_register_path": str(register_path),
        "n_cells": summary["n_cells"],
        "n_scored": summary["n_scored"],
        "n_excluded": summary["n_excluded"],
        "n_eligible": summary["n_eligible"],
        "n_unscorable_eligible": summary["n_unscorable_eligible"],
        "confidence_counts": summary["confidence_counts"],
        "scored_confidence_counts": summary["scored_confidence_counts"],
        "n_high_confidence": summary["scored_confidence_counts"].get("high", 0),
        "n_low_confidence": summary["scored_confidence_counts"].get("low", 0),
        "score_min": summary["score_min"],
        "score_max": summary["score_max"],
        "score_mean": summary["score_mean"],
        "constant_criteria": constant,
        "weights_config_id": weights.config_id,
        "weights_path": str(weights.path) if weights.path else None,
        "confidence_discount": weights.confidence_discount,
        "validation": result,
        "runtime_seconds": runtime_s,
        "generated_utc": generated_utc,
        "git_commit": commit,
    }
