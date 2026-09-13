"""
Stage entry point for the S2-06a deterministic explanation engine (stage
`explanation`).

Orchestrates the stage in the order the design specifies:

    load templates -> load Scored_Table + integrated table (recompute norms,
    reconcile) -> explain each eligible cell -> assemble -> write (JSON + CSV)
    -> schema doc -> method + validation reports -> provenance -> validate

FAIL BEFORE WRITE. The templates file is loaded and validated first, then the
Scored_Table and integrated table are read and the recomputed contributions are
reconciled against the persisted ones — all before any explanation is written.
Every fatal condition halts the run without touching the previous outputs, so a
failed run never leaves a partial or stale explanation artefact on disk.

Raises rather than returning on any failure, so the orchestrator halts with a
non-zero exit status.
"""

from __future__ import annotations

import time
from pathlib import Path

from ..common.geo import atomic_write_text, sha256_file, utc_now
from . import config
from .load import load_explanation_inputs
from .report import (
    build_method_report,
    build_validation_report,
    git_commit,
    record_provenance,
)
from .templates import load_templates
from .validate import validate as validate_explanations
from .write import (
    build_explanations,
    write_explanations,
    write_schema_doc,
)


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
    templates_path: Path | None = None,
    scored_table_path: Path | None = None,
    integrated_path: Path | None = None,
    weights_path: Path | None = None,
) -> dict:
    """
    Explain every eligible cell with the deterministic template/rule engine,
    then write the Explanation_Table (JSON + CSV), the schema document, the
    method and validation reports, and provenance.

    Parameters
    ----------
    verbose : bool
        Print the full check list and a sample explanation.
    templates_path : Path | None
        Explanation templates YAML (CLI: `--explanation-templates`). Defaults
        to the packaged `pipeline/explanation/explanation_templates.yaml`.
    scored_table_path : Path | None
        The S2-05 Scored_Table. Defaults to the scoring stage's output.
    integrated_path : Path | None
        The S1-08 integrated table (read only to recompute norms). Defaults to
        the scoring stage's input.
    weights_path : Path | None
        Criteria weights YAML (CLI: reuses `--scoring-weights`). Must be the
        SAME weights the Scored_Table was produced from; defaults to the
        packaged scoring weights.

    Returns a summary dict including `explanations_path` and
    `method_report_path`, both of which exist on disk when this returns.

    Raises ExplanationConfigError / ScoringConfigError / FileNotFoundError /
    ValueError / RuntimeError on a bad config, a missing or malformed input, a
    failed reconciliation, or a failed validation check, so the orchestrator
    halts with a non-zero exit status.
    """
    t0 = time.time()
    generated_utc = utc_now()
    commit = git_commit(config.PROJECT_ROOT)

    # [1/5] Templates first — the cheapest thing to get wrong.
    templates = load_templates(templates_path or config.DEFAULT_TEMPLATES_PATH)
    print(f"  [1/5] Explanation templates: {_rel(templates.path)} "
          f"(version {templates.version}, {len(templates.phrases)} criteria, "
          f"{len(templates.bands)} bands)")

    # [2/5] Load inputs, recompute norms, reconcile against persisted contribs.
    print("  [2/5] Reading Scored_Table + integrated table (recomputing norms)...")
    inputs = load_explanation_inputs(
        scored_table_path=scored_table_path,
        integrated_path=integrated_path,
        weights_path=weights_path,
    )
    # Every configured criterion must have phrasing before we render anything.
    for criterion in inputs.weights.criteria:
        templates.phrases_for(criterion.feature)
    print(f"        {inputs.n_eligible_cells:,} eligible cells "
          f"({_rel(inputs.scored_table_path)}); reconciliation passed")

    # [3/5] The pure engine, per eligible cell.
    print("  [3/5] Generating deterministic explanations...")
    records = build_explanations(inputs.cells, templates)
    n_with_weaknesses = sum(1 for r in records if r[config.FIELD_WEAKNESSES])
    summary = {
        "n_eligible_cells": inputs.n_eligible_cells,
        "n_explained": len(records),
        "n_with_weaknesses": n_with_weaknesses,
    }
    print(f"        explained {len(records):,}; "
          f"{n_with_weaknesses:,} carry at least one weakness")

    # [4/5] Write outputs, then reports. The validation report is written even
    # when validation fails, so a failed run still leaves the evidence behind.
    print("  [4/5] Writing outputs...")
    json_path = config.EXPLANATION_DIR / config.OUTPUT_FILENAME
    csv_path = config.EXPLANATION_DIR / config.CSV_FILENAME
    write_explanations(records, json_path, csv_path)
    print(f"        -> {_rel(json_path)}")
    print(f"        -> {_rel(csv_path)}")

    meta_dir = config.EXPLANATION_META_DIR
    schema_path = meta_dir / config.SCHEMA_FILENAME
    validation_path = meta_dir / config.VALIDATION_REPORT_FILENAME
    report_path = meta_dir / config.METHOD_REPORT_FILENAME
    manifest_path = meta_dir / config.MANIFEST_FILENAME
    register_path = meta_dir / config.SOURCE_REGISTER_FILENAME
    provenance_path = config.EXPLANATION_DIR / config.PROVENANCE_FILENAME

    write_schema_doc(templates, schema_path)
    print(f"        -> {_rel(schema_path)}")

    # [5/5] Validate — no silent passes.
    print("  [5/5] Validating (no silent passes)...")
    result = validate_explanations(
        records, templates, n_eligible_cells=inputs.n_eligible_cells
    )
    atomic_write_text(validation_path,
                      build_validation_report(result, generated_utc, commit))
    if verbose or result["failed"]:
        _print_checks(result)
    else:
        print(f"        {result['passed']}/{result['total']} checks passed")
    print(f"        -> {_rel(validation_path)}")

    report_inputs = {
        "scored_table_path": inputs.scored_table_path,
        "scored_table_sha256": sha256_file(inputs.scored_table_path),
        "integrated_path": inputs.integrated_path,
        "weights_path": inputs.weights.path,
        "weights_config_id": inputs.weights.config_id,
        "weights_version": inputs.weights.version,
    }
    runtime_s = time.time() - t0
    outputs = {
        "Explanations (JSON)": json_path,
        "Explanations (CSV)": csv_path,
        "Schema": schema_path,
        "Method report": report_path,
        "Validation report": validation_path,
        "Manifest": manifest_path,
        "Provenance": provenance_path,
        "Source register": register_path,
    }
    atomic_write_text(report_path, build_method_report(
        templates=templates, weights=inputs.weights, summary=summary,
        result=result, inputs=report_inputs, outputs=outputs, runtime_s=runtime_s,
        generated_utc=generated_utc, commit=commit,
    ))
    record_provenance(
        json_path=json_path, csv_path=csv_path, n_records=len(records),
        templates=templates, inputs=report_inputs, summary=summary,
        generated_utc=generated_utc, commit=commit,
        manifest_path=manifest_path, provenance_path=provenance_path,
        register_path=register_path,
    )
    print(f"        -> {_rel(report_path)}")
    print(f"        -> {_rel(manifest_path)}, {_rel(provenance_path)}, "
          f"{_rel(register_path)}")

    if result["failed"]:
        raise RuntimeError(
            f"explanations failed validation: {', '.join(result['failed_names'])} "
            f"(see {validation_path})"
        )

    if verbose and records:
        sample = records[0]
        print(f"        sample [{sample[config.FIELD_CELL_ID]}]: "
              f"+{sample[config.FIELD_POSITIVE_FACTORS]} "
              f"-{sample[config.FIELD_WEAKNESSES]}")

    print(f"        Eligible {inputs.n_eligible_cells:,}; explained {len(records):,}; "
          f"runtime {runtime_s:.1f}s")

    return {
        "explanations_path": str(json_path),
        "csv_path": str(csv_path),
        "schema_path": str(schema_path),
        "method_report_path": str(report_path),
        "validation_report_path": str(validation_path),
        "manifest_path": str(manifest_path),
        "provenance_path": str(provenance_path),
        "source_register_path": str(register_path),
        "n_eligible_cells": inputs.n_eligible_cells,
        "n_explained": len(records),
        "n_with_weaknesses": n_with_weaknesses,
        "templates_config_id": templates.config_id,
        "templates_path": str(templates.path) if templates.path else None,
        "weights_config_id": inputs.weights.config_id,
        "validation": result,
        "runtime_seconds": runtime_s,
        "generated_utc": generated_utc,
        "git_commit": commit,
    }
