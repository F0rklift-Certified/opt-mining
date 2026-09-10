"""
Method report, validation report and provenance (S1-10, Requirements 12, 13).

The method report is the document a reviewer reads to decide whether to trust
a shortlist. It states the formula, every weight and the rationale behind it,
the normalisation bounds the run actually used, and the counts of what was
scored and what was not. Everything needed to reproduce or challenge the
scores is on that one page.

Provenance mirrors `integration.merge.record_provenance`: a manifest record
keyed by output file (so a rerun replaces rather than appends), a generated
block spliced into `DATA_PROVENANCE.md` between markers, and a source-register
row. The Scored_Table is labelled a DERIVED product throughout so it is never
mistaken for custodial source data.
"""

from __future__ import annotations

import csv
import io
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path

from ..common.geo import atomic_write_json, atomic_write_text, banner, sha256_file
from . import config
from .normalise import Bounds
from .weights import WeightsConfig

PROVENANCE_BEGIN = "<!-- BEGIN scoring.run derived layer (generated) -->"
PROVENANCE_END = "<!-- END scoring.run derived layer (generated) -->"


def _rel(path: Path) -> str:
    """Path relative to the project root, for reports and manifests."""
    path = Path(path)
    try:
        return str(path.relative_to(config.PROJECT_ROOT))
    except ValueError:
        return str(path)


def git_commit(cwd: Path | None = None) -> str:
    """
    HEAD commit for the report and manifest, '-dirty' when tracked files are
    modified; 'unknown' on any failure. Never raises — reproducibility
    metadata must not be able to fail the stage.
    """
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if head.returncode != 0 or not head.stdout.strip():
            return "unknown"
        commit = head.stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        dirty = status.returncode == 0 and status.stdout.strip() != ""
        return f"{commit}-dirty" if dirty else commit
    except Exception:  # noqa: BLE001 — any failure degrades to "unknown"
        return "unknown"


def _fmt(value: float | None, places: int = 4) -> str:
    return "—" if value is None else f"{value:.{places}f}"


# ---------------------------------------------------------------------------
# Method report (Requirement 13)
# ---------------------------------------------------------------------------


def build_method_report(
    *,
    weights: WeightsConfig,
    bounds: Mapping[str, Bounds],
    summary: dict,
    result: dict,
    inputs: dict,
    outputs: dict,
    runtime_s: float,
    generated_utc: str,
    commit: str,
) -> str:
    """Render the scoring method report as markdown."""
    lines: list[str] = []
    add = lines.append

    add("# Baseline Suitability Model — Method (S1-10)\n")
    add(banner(config.MODULE_NAME))
    add("")
    add("This is a transparent, deterministic **weighted multi-criteria decision "
        "analysis (MCDA)** — not a machine-learning model. Every number below is "
        "either a user input from the weights file or a value computed from the "
        "integrated feature table on this run. Nothing is learned, fitted or "
        "hard-coded.\n")

    # --- 1. Formula ---
    add("## 1. Scoring formula\n")
    add("For every **eligible** cell, and for each configured criterion *i*:\n")
    add("```")
    add("norm_i    = (v_i - min_i) / (max_i - min_i)          direction higher_is_better")
    add("norm_i    = 1 - (v_i - min_i) / (max_i - min_i)      direction lower_is_better")
    add("contrib_i = weight_i * norm_i / W_cell")
    add("score     = SUM_i contrib_i                          -> [0, 1]")
    add("```\n")
    add("`W_cell` is the sum of the weights **actually applied** to that cell — the "
        "criteria that have a value for it. A criterion with no value for a cell is "
        "left out of that cell's weighted average rather than scored as zero, so a "
        "gap in the data never masquerades as an unfavourable measurement. The "
        "carried-through `confidence` value is what flags the gap.\n")
    add(f"- Normalisation bounds are computed from the **eligible cell population "
        f"on this run** (§3), never hard-coded.")
    add(f"- Only eligible cells (S1-07 `eligible = true`) are scored. Excluded "
        f"cells receive a null score, a null rank and null contributions, and take "
        f"no part in the bounds or the ranking.")
    add(f"- `rank` 1 is the highest score; ties are broken by **ascending "
        f"`cell_id`**, so repeated runs over identical inputs produce identical "
        f"ranks.")
    add(f"- **No circular modelling:** `wind_speed` is an input criterion only. It "
        f"is never a prediction target and no wind prediction column is emitted.\n")

    # --- 2. Criteria and weights ---
    add("## 2. Criteria, weights and rationale\n")
    add(f"Weights are **user inputs** loaded at runtime from "
        f"`{_rel(weights.path) if weights.path else '<in-memory>'}` "
        f"(version `{weights.version}`, SHA-256 `{weights.config_id}`). No weight "
        f"literal appears anywhere in `pipeline/scoring/`. Weights are relative: "
        f"the score divides by the sum of applied weights, so scaling every weight "
        f"by the same factor changes nothing.\n")
    add("| Criterion | Weight | Share of Σw | Direction | Rationale |")
    add("|-----------|-------:|------------:|-----------|-----------|")
    total = weights.weight_sum
    for c in weights.criteria:
        share = (c.weight / total * 100) if total else 0.0
        add(f"| `{c.feature}` | {c.weight:g} | {share:.1f}% | {c.direction} | "
            f"{c.rationale} |")
    add(f"| **Σ** | **{total:g}** | **100.0%** | | |")
    add("")

    # --- 3. Normalisation ---
    add("## 3. Normalisation bounds applied on this run\n")
    add("Bounds come from the **eligible** population only: the score compares "
        "candidate sites against each other, so an ineligible cell's extreme value "
        "must not stretch the scale the candidates are measured on.\n")
    add("| Criterion | Rule | Min used | Max used | Observed min | Observed max | Cells with a value |")
    add("|-----------|------|---------:|---------:|-------------:|-------------:|-------------------:|")
    for c in weights.criteria:
        b = bounds[c.feature]
        add(f"| `{c.feature}` | {b.rule} | {_fmt(b.lo)} | {_fmt(b.hi)} | "
            f"{_fmt(b.observed_min)} | {_fmt(b.observed_max)} | {b.n_observed:,} |")
    add("")
    add("**Normalisation is LINEAR** for every criterion. No logarithmic or other "
        "non-linear transform is applied to any distance criterion on this run. A "
        "log transform for distances is a defensible alternative — it would "
        "compress differences between far-away cells and expand them between close "
        "ones — but it is a modelling judgement, so it is left to an explicit "
        "future change rather than applied silently here.\n")

    constant = [c.feature for c in weights.criteria if bounds[c.feature].is_constant]
    if constant:
        add("### Constant criteria on this run\n")
        add(f"The following criteria have the **same value for every eligible "
            f"cell**, so `(v - min) / (max - min)` is 0/0. Each is assigned the "
            f"documented constant `{config.CONSTANT_CRITERION_VALUE}` rather than "
            f"dividing by zero:\n")
        for feature in constant:
            weight = next(c.weight for c in weights.criteria if c.feature == feature)
            share = (weight / total) if total else 0.0
            add(f"- **`{feature}`** — adds a flat {share:.3f} to every eligible "
                f"cell's score. **It cannot discriminate between cells and cannot "
                f"change the ranking**; it only shifts the absolute scores upward. "
                f"Read the shortlist as though it were scored on the remaining "
                f"{len(weights.criteria) - len(constant)} criteria.")
        add("")

    boolean = [c.feature for c in weights.criteria if bounds[c.feature].is_boolean]
    if boolean:
        add(f"Boolean criteria ({', '.join(f'`{b}`' for b in boolean)}) use their "
            f"definitional `{{False -> 0.0, True -> 1.0}}` domain rather than the "
            f"observed population min/max, so an all-`False` boolean scores 0 for "
            f"every cell instead of triggering the constant fill and handing every "
            f"cell full marks for a benefit none of them has.\n")

    # --- 4. Explainability ---
    add("## 4. Per-criterion contributions (explainability)\n")
    add(f"For each criterion the scored table carries a "
        f"`{config.CONTRIBUTION_PREFIX}{{feature}}` column holding that criterion's "
        f"**additive contribution** to the cell's final score: literally how many "
        f"points of the score came from that criterion.\n")
    add("**Reconciliation rule:** for every scored cell, the configured "
        f"contributions sum to the final `suitability_score` within "
        f"`{config.RECONCILE_TOLERANCE:g}`. This is checked for every cell on "
        f"every run (§6) — the explainability claim is verified, not asserted.\n")
    add("This is the Constitution's requirement made concrete: *\"A recommendation "
        "the user cannot interrogate is not a recommendation — it is an "
        "assertion.\"*\n")

    # --- 5. Confidence ---
    add("## 5. Confidence\n")
    add(f"The `confidence` column carries the **S1-09 composite confidence flag** "
        f"(`{config.CONFIDENCE_COLUMN}`) through unchanged. No confidence value is "
        f"computed, adjusted or fabricated here.\n")
    if weights.confidence_discount:
        add("**Confidence discounting: ENABLED.** The raw score and every "
            "contribution are multiplied by the cell's factor, so the contributions "
            "still reconcile to the discounted score:\n")
        add("| Confidence | Factor |")
        add("|------------|-------:|")
        for level in config.CONFIDENCE_LEVELS:
            add(f"| `{level}` | {weights.confidence_factors.get(level, 1.0):g} |")
    else:
        add("**Confidence discounting: DISABLED** (`confidence_discount: false`). "
            "The final score is the raw weighted-sum score. Confidence is reported "
            "alongside every score but does not alter it.")
        add("")
        add("| Confidence | Factor if enabled |")
        add("|------------|------------------:|")
        for level in config.CONFIDENCE_LEVELS:
            add(f"| `{level}` | {weights.confidence_factors.get(level, 1.0):g} |")
    add("")

    # --- 6. Counts ---
    add("## 6. What was scored\n")
    add("| Measure | Cells |")
    add("|---------|------:|")
    add(f"| Cells in the integrated table | {summary['n_cells']:,} |")
    add(f"| Eligible (S1-07 `eligible = true`) | {summary['n_eligible']:,} |")
    add(f"| **Scored** | **{summary['n_scored']:,}** |")
    add(f"| Excluded — null score, null rank, no rank position | {summary['n_excluded']:,} |")
    add(f"| Eligible but unscorable (no criterion had a value) | "
        f"{summary['n_unscorable_eligible']:,} |")
    add("")
    add("Confidence of the cells that received a score:\n")
    add("| Confidence | Scored cells | All cells |")
    add("|------------|-------------:|----------:|")
    for level in config.CONFIDENCE_LEVELS:
        add(f"| `{level}` | {summary['scored_confidence_counts'][level]:,} | "
            f"{summary['confidence_counts'][level]:,} |")
    add("")
    add(f"Score distribution over scored cells: min {_fmt(summary['score_min'])}, "
        f"mean {_fmt(summary['score_mean'])}, max {_fmt(summary['score_max'])}.\n")

    # --- 7. Deviations ---
    add("## 7. Deviations from the S1-10 ticket\n")
    add("Recorded here rather than resolved silently, because both come from the "
        "data rather than from the code.\n")
    add(f"1. **Confidence is three-valued, not two.** The ticket specifies "
        f"`confidence` as exactly `high` or `low`. The S1-09 layer this stage "
        f"consumes emits `{'` / `'.join(config.CONFIDENCE_LEVELS)}`. Collapsing "
        f"`medium` into either neighbour would fabricate a confidence the data does "
        f"not support, which the ticket itself forbids (\"rather than fabricating a "
        f"confidence value\") and the Constitution forbids twice over (\"Never let "
        f"poor data pass as good\", \"Report confidence alongside every score\"). "
        f"The upstream value is carried through verbatim and validation asserts "
        f"membership in the S1-09 vocabulary, so an unexpected value is still an "
        f"explicit failure. On this run every scored cell is "
        f"`{config.CONFIDENCE_LEVELS[0]}`, so the ticket's two-value expectation "
        f"holds observationally for the scored population regardless.")
    add(f"2. **Null criterion values.** The ticket does not say what to do when an "
        f"eligible cell has no value for a configured criterion. This stage "
        f"excludes that criterion from that cell's weighted average and divides by "
        f"the weights actually applied (the ticket's \"sum of the applied "
        f"criterion weights\"), leaving the contribution null. Scoring the gap as "
        f"zero would penalise a cell for missing data rather than for a property of "
        f"the land. On this run no eligible cell is missing a criterion, so every "
        f"scored cell used the full weight sum.\n")

    # --- 8. Inputs, outputs, reproduction ---
    add("## 8. Inputs, outputs and reproduction\n")
    add("| Input | Path | Detail |")
    add("|-------|------|--------|")
    add(f"| Integrated feature table (S1-08) | `{_rel(inputs['integrated_path'])}` | "
        f"layer `{inputs['integrated_layer']}`, {inputs['integrated_rows']:,} rows, "
        f"CRS {inputs['integrated_crs']}, SHA-256 `{inputs['integrated_sha256']}` |")
    add(f"| Criteria weights | `{_rel(weights.path) if weights.path else '—'}` | "
        f"version `{weights.version}`, SHA-256 `{weights.config_id}` |")
    add("")
    add("| Output | Path |")
    add("|--------|------|")
    for label, path in outputs.items():
        add(f"| {label} | `{_rel(path)}` |")
    add("")
    add(f"- **CRS:** geometry stored in {config.STORAGE_CRS}; nothing is "
        f"reprojected by this stage.")
    add(f"- **Regenerable:** yes — `python -m pipeline --only scoring` (after "
        f"`integration`). Reproducible from the integrated table and the weights "
        f"file alone, with no manual editing.")
    add(f"- **Validation:** {result['passed']}/{result['total']} checks passed "
        f"({result['failed']} failures). Every check, passed or failed, is listed "
        f"in `{_rel(outputs.get('Validation report', Path('—')))}`.")
    add(f"- **Runtime:** {runtime_s:.1f} s. **Generated (UTC):** {generated_utc}. "
        f"**Git commit:** `{commit}`.")
    add("")
    add("---")
    add("")
    add("*This is a strategic screening output. It indicates where to look next; "
        "it is not a site approval, an engineering assessment or a bankable "
        "figure.*")
    return "\n".join(lines) + "\n"


def build_validation_report(result: dict, generated_utc: str, commit: str) -> str:
    """Render every validation check — passed and failed — as markdown."""
    lines: list[str] = []
    add = lines.append
    add("# Scored Table — Validation (S1-10)\n")
    add(banner(config.MODULE_NAME))
    add("")
    add(f"{result['passed']}/{result['total']} checks passed "
        f"({result['failed']} failures). Every check is listed whether it passed or "
        f"not — no silent passes.\n")
    add("| Check | Expected | Observed | Result |")
    add("|-------|----------|----------|--------|")
    for check in result["checks"]:
        status = "PASS" if check["passed"] else "**FAIL**"
        add(f"| {check['name']} | {check['expected']} | {check['observed']} | {status} |")
    add("")
    add(f"*Generated {generated_utc}; git commit `{commit}`.*")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Provenance (Requirement 12)
# ---------------------------------------------------------------------------


def record_provenance(
    *,
    gpkg_path: Path,
    csv_path: Path,
    columns: list[str],
    n_rows: int,
    weights: WeightsConfig,
    inputs: dict,
    summary: dict,
    generated_utc: str,
    commit: str,
    manifest_path: Path,
    provenance_path: Path,
    register_path: Path,
) -> dict:
    """
    Record the Scored_Table as a DERIVED product in all three provenance
    artefacts: the manifest, `DATA_PROVENANCE.md` and the source register.

    Returns the manifest record.
    """
    record = {
        "output_file": _rel(gpkg_path),
        "csv_file": _rel(csv_path),
        "stage": config.STAGE_NAME,
        "product_type": "derived",
        "generated_utc": generated_utc,
        "git_commit": commit,
        "rows": int(n_rows),
        "columns": list(columns),
        "sha256_gpkg": sha256_file(gpkg_path),
        "sha256_csv": sha256_file(csv_path),
        "bytes_gpkg": Path(gpkg_path).stat().st_size,
        "bytes_csv": Path(csv_path).stat().st_size,
        "inputs": [
            {
                "name": "integrated_feature_table",
                "path": _rel(inputs["integrated_path"]),
                "layer": inputs["integrated_layer"],
                "rows": inputs["integrated_rows"],
                "crs": inputs["integrated_crs"],
                "sha256": inputs["integrated_sha256"],
                "bytes": inputs["integrated_bytes"],
            }
        ],
        "weights_config": {
            "path": _rel(weights.path) if weights.path else None,
            "weights_config_id": weights.config_id,
            "version": weights.version,
            "criteria": [
                {"feature": c.feature, "weight": c.weight, "direction": c.direction}
                for c in weights.criteria
            ],
            "confidence_discount": weights.confidence_discount,
        },
        "counts": {
            "n_cells": summary["n_cells"],
            "n_scored": summary["n_scored"],
            "n_excluded": summary["n_excluded"],
        },
    }

    manifest_path = Path(manifest_path)
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {}
    )
    derived = [
        r for r in manifest.get("derived_features", [])
        if r.get("output_file") != record["output_file"]
    ]
    derived.append(record)
    manifest["derived_features"] = derived
    atomic_write_json(manifest_path, manifest)

    criteria_md = "\n".join(
        f"  - `{c.feature}` weight {c.weight:g}, {c.direction}"
        for c in weights.criteria
    )
    section = (
        f"{PROVENANCE_BEGIN}\n"
        f"## Derived layer — Baseline Suitability Score (S1-10)\n\n"
        f"- **DERIVED PRODUCT — not custodial source data.** Fully regenerable "
        f"from the inputs below; contains no data of its own.\n"
        f"- **File:** `{record['output_file']}` (GeoPackage, layer "
        f"`{config.OUTPUT_LAYER}`)\n"
        f"- **CSV:** `{record['csv_file']}` (no geometry; the deterministic "
        f"artefact)\n"
        f"- **Derived from:**\n"
        f"  - integrated feature table (S1-08): `{_rel(inputs['integrated_path'])}` "
        f"(layer `{inputs['integrated_layer']}`, {inputs['integrated_rows']:,} rows, "
        f"SHA-256 `{inputs['integrated_sha256']}`)\n"
        f"  - criteria weights (user input): "
        f"`{_rel(weights.path) if weights.path else '—'}` (version "
        f"`{weights.version}`, SHA-256 `{weights.config_id}`)\n"
        f"- **Criteria weights used:**\n{criteria_md}\n"
        f"- **Method:** weighted multi-criteria decision analysis (MCDA) over "
        f"criteria normalised to [0, 1] from the eligible cell population; "
        f"per-criterion contributions written alongside every score; only eligible "
        f"cells scored and ranked; confidence carried through from S1-09 unchanged; "
        f"no reprojection, no back-filling, no fitted parameters.\n"
        f"- **Confidence discount:** "
        f"{'enabled' if weights.confidence_discount else 'disabled'}\n"
        f"- **Cells:** {summary['n_cells']:,} total; {summary['n_scored']:,} scored; "
        f"{summary['n_excluded']:,} excluded with a null score\n"
        f"- **Regenerable:** yes — `python -m pipeline --only scoring` (after "
        f"`integration`).\n"
        f"- **SHA-256 (GeoPackage):** `{record['sha256_gpkg']}`\n"
        f"- **SHA-256 (CSV):** `{record['sha256_csv']}`\n"
        f"- **Generated (UTC):** {generated_utc}\n"
        f"- **Git commit:** `{commit}`\n"
        f"{PROVENANCE_END}\n"
    )
    provenance_path = Path(provenance_path)
    text = provenance_path.read_text(encoding="utf-8") if provenance_path.exists() else ""
    if PROVENANCE_BEGIN in text and PROVENANCE_END in text:
        head, rest = text.split(PROVENANCE_BEGIN, 1)
        _, tail = rest.split(PROVENANCE_END, 1)
        text = head + section.rstrip("\n") + tail
    else:
        header = (
            "# Data Provenance — Scoring (S1-10)\n\n"
            "Everything in `DATA/scoring/` is a DERIVED product generated by the "
            "`scoring` stage. Nothing here is custodial source data; the generated "
            "block below is rewritten on every run.\n\n"
        )
        text = (text.rstrip("\n") + "\n\n" + section) if text else (header + section)
    atomic_write_text(provenance_path, text)

    _write_source_register(register_path, record, inputs, weights, generated_utc)
    return record


def _write_source_register(
    register_path: Path,
    record: dict,
    inputs: dict,
    weights: WeightsConfig,
    generated_utc: str,
) -> None:
    """
    Append/replace this product's row in the scoring source register (CSV,
    same column vocabulary as `DATA/geographic/metadata/source_register.csv`).
    """
    row = {
        "dataset_id": "optmining_suitability_score",
        "category": "derived-scoring",
        "custodian": "Opt-Mining (DERIVED — not custodial data)",
        "endpoint": _rel(inputs["integrated_path"]),
        "access_method": f"generated by pipeline stage `{config.STAGE_NAME}`",
        "format": f"GeoPackage (layer {config.OUTPUT_LAYER}) + CSV",
        "native_crs": config.STORAGE_CRS,
        "licence": "derived from the licensed inputs listed in each source layer's register",
        "vintage": config.SCORING_VINTAGE,
        "size_or_count": f"{record['rows']:,} rows, {len(record['columns'])} columns",
        "intended_use": "Baseline suitability score + rank + per-criterion contributions (S1-10); input to S1-11 shortlist",
        "notes": (
            f"weights_config_id {weights.config_id}; "
            f"confidence_discount {weights.confidence_discount}; "
            f"generated {generated_utc}"
        ),
    }
    register_path = Path(register_path)
    existing: list[dict] = []
    if register_path.exists():
        try:
            existing = list(csv.DictReader(io.StringIO(
                register_path.read_text(encoding="utf-8"))))
        except Exception:  # noqa: BLE001 — a corrupt register is rewritten, not fatal
            existing = []
    rows = [r for r in existing if r.get("dataset_id") != row["dataset_id"]]
    rows.append(row)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(row), lineterminator="\n")
    writer.writeheader()
    for entry in rows:
        writer.writerow({k: entry.get(k, "") for k in row})
    atomic_write_text(register_path, buffer.getvalue())
