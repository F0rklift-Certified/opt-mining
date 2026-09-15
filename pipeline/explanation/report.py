"""
Method report, validation report and provenance for the explanation stage
(S2-06a).

The method report is the document a reviewer reads to understand HOW the
explanations were produced: the rule (rank by contribution, band by normalised
value), the band thresholds, the screening-language guarantee, the templates
identity, and the counts. The validation report lists every check. Provenance
mirrors `scoring.report.record_provenance`: a manifest record keyed by output
file, a generated block in `DATA_PROVENANCE.md` between markers, and a
source-register row. The Explanation_Table is labelled a DERIVED product
throughout so it is never mistaken for custodial source data.
"""

from __future__ import annotations

import csv
import io
import json
import subprocess
from pathlib import Path

from ..common.geo import atomic_write_json, atomic_write_text, banner, sha256_file
from . import config
from .templates import ExplanationTemplates

PROVENANCE_BEGIN = "<!-- BEGIN explanation.run derived layer (generated) -->"
PROVENANCE_END = "<!-- END explanation.run derived layer (generated) -->"


def _rel(path: Path) -> str:
    path = Path(path)
    try:
        return str(path.relative_to(config.PROJECT_ROOT))
    except ValueError:
        return str(path)


def git_commit(cwd: Path | None = None) -> str:
    """
    HEAD commit for the report and manifest, '-dirty' when tracked files are
    modified; 'unknown' on any failure. Never raises — reproducibility metadata
    must not be able to fail the stage. (Same helper as scoring.report.)
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


# ---------------------------------------------------------------------------
# Method report
# ---------------------------------------------------------------------------


def build_method_report(
    *,
    templates: ExplanationTemplates,
    weights,
    summary: dict,
    result: dict,
    inputs: dict,
    outputs: dict,
    runtime_s: float,
    generated_utc: str,
    commit: str,
) -> str:
    """Render the explanation method report as markdown."""
    lines: list[str] = []
    add = lines.append

    add("# Site Explanations — Method (S2-06a + S2-06b)\n")
    add(banner(config.MODULE_NAME))
    add("")
    add("This is a **deterministic, template/rule-based** explanation of every "
        "site — eligible and excluded — with **no language model involved**. The "
        "same Scored_Table, integrated table and templates always produce "
        "byte-identical explanations, which is more auditable than a generative "
        "model and cannot invent a factor the data does not support. Eligible "
        "cells are explained by their strongest factors and weaknesses (S2-06a); "
        "excluded cells state their machine- and human-readable exclusion "
        "reason(s) (S2-06b). Every record — both paths — also carries any **proxy** "
        "caveat and the cell's **data-quality / confidence** note (S2-06b, AC7).\n")

    # 1. Rule
    add("## 1. How factors are chosen\n")
    add("For every **eligible** cell:\n")
    add(f"- **Positive factors** are the criteria contributing the most to the "
        f"cell's S2-05 suitability score, ranked by the persisted "
        f"`{config.CONTRIBUTION_PREFIX}{{feature}}` value (the score is **never** "
        f"recomputed here), at most {config.MAX_POSITIVE_FACTORS}. Only criteria "
        f"the cell scores favourably on (normalised value above "
        f"{config.WEAKNESS_NORM_CEILING}) are offered as strengths.")
    add(f"- **Weaknesses** are the criteria the cell scores poorly on (normalised "
        f"value at or below {config.WEAKNESS_NORM_CEILING}), worst first, at most "
        f"{config.MAX_WEAKNESSES}.")
    add("- A **qualitative band** is derived from the cell's normalised value for "
        "the criterion and appended to the phrase. Because the Scored_Table does "
        "not persist the normalised intermediates, they are **recomputed** from "
        "the integrated table using the scoring stage's own normaliser "
        "(`pipeline.scoring.normalise`) with the same weights, and a "
        "reconciliation guard asserts the recomputed contributions reproduce the "
        "persisted ones within the shared tolerance before any explanation is "
        "written.\n")

    # 2. Bands
    add("## 2. Qualitative bands\n")
    add("| Band | Minimum normalised value |")
    add("|------|--------------------------:|")
    for band in templates.bands:
        add(f"| {band.label} | {band.min_norm:g} |")
    add("")
    add(f"Boolean criteria use the labels "
        f"`{templates.boolean_true_label}` / `{templates.boolean_false_label}` "
        f"rather than a decile band. A criterion that is constant over the "
        f"eligible population carries no discriminating information and is never "
        f"surfaced as a factor.\n")

    # 3. Screening language
    add("## 3. Screening-level language\n")
    add(f"Every headline reads: *\"{templates.headline}\"*. This is a strategic "
        f"screening output — it indicates a **higher-ranked candidate under the "
        f"selected assumptions and criteria**, never a \"best\" or \"optimal\" "
        f"site. Non-screening superlatives are rejected when the templates load "
        f"and asserted absent by validation.\n")

    # 4. Templates identity
    add("## 4. Templates (phrasing as data)\n")
    add(f"Phrasing is **user input** loaded at runtime from "
        f"`{_rel(templates.path) if templates.path else '<in-memory>'}` "
        f"(version `{templates.version}`, SHA-256 `{templates.config_id}`). No "
        f"phrase or band label appears in `pipeline/explanation/` source.\n")
    add("| Criterion | Positive phrase | Weakness phrase |")
    add("|-----------|-----------------|-----------------|")
    order = [c.feature for c in weights.criteria] if weights else list(templates.phrases)
    for feature in order:
        if feature in templates.phrases:
            cp = templates.phrases[feature]
            add(f"| `{feature}` | {cp.positive} | {cp.weakness} |")
    add("")

    # 4b. Excluded path + caveats (S2-06b)
    add("## 4b. Excluded cells and caveats (S2-06b)\n")
    add("- **Excluded cells** carry their machine- and human-readable exclusion "
        "reason(s) — a JSON list of `{code, text}` pairs from the integrated "
        "table's `exclusion_reasons` (Decision-Engine Spec §6.5, frozen decision "
        "F16), carried through verbatim in rule-config order. Eligibility and "
        "scores are **not** recomputed here.")
    add("- **Proxy caveats** flag any proxy variable a cell used, so a proxy is "
        "never read as a direct measurement. A criterion is a proxy when the "
        "templates mark it `proxy: true`; the caveat is surfaced only when the "
        "cell had a value for that criterion. The MVP demand feature is a "
        "spatial proxy allocated below the AEMO region, not measured local "
        "demand.")
    add(f"- **Data-quality notes** always surface the cell's S1-09 composite "
        f"confidence level (including `high`), appending the reduced-confidence "
        f"reasons from `{config.CONFIDENCE_NOTES_COLUMN}` when present. Exactly "
        f"one note per record.\n")

    # 5. Counts
    add("## 5. What was explained\n")
    add("| Measure | Cells |")
    add("|---------|------:|")
    add(f"| Eligible cells in the Scored_Table | {summary['n_eligible_cells']:,} |")
    add(f"| Excluded cells in the integrated table | {summary.get('n_excluded_cells', 0):,} |")
    add(f"| **Explained (both paths)** | **{summary['n_explained']:,}** |")
    add(f"| Excluded cells explained | {summary.get('n_excluded_explained', 0):,} |")
    add(f"| Eligible records with at least one weakness | {summary['n_with_weaknesses']:,} |")
    add(f"| Records carrying a proxy caveat | {summary.get('n_with_proxy_caveat', 0):,} |")
    add("")

    # 6. Inputs / outputs
    add("## 6. Inputs, outputs and reproduction\n")
    add("| Input | Path | Detail |")
    add("|-------|------|--------|")
    add(f"| Scored_Table (S2-05) | `{_rel(inputs['scored_table_path'])}` | "
        f"layer `{config.SCORED_TABLE_LAYER}`, SHA-256 "
        f"`{inputs['scored_table_sha256']}` |")
    add(f"| Integrated table (S1-08) | `{_rel(inputs['integrated_path'])}` | "
        f"read only to recompute normalisation bounds |")
    add(f"| Criteria weights | `{_rel(inputs['weights_path']) if inputs['weights_path'] else '—'}` | "
        f"version `{inputs['weights_version']}`, SHA-256 `{inputs['weights_config_id']}` |")
    add(f"| Explanation templates | `{_rel(templates.path) if templates.path else '—'}` | "
        f"version `{templates.version}`, SHA-256 `{templates.config_id}` |")
    add("")
    add("| Output | Path |")
    add("|--------|------|")
    for label, path in outputs.items():
        add(f"| {label} | `{_rel(path)}` |")
    add("")
    add(f"- **Regenerable:** yes — `python -m pipeline --only explanation` (after "
        f"`scoring`). Reproducible from the Scored_Table, the integrated table and "
        f"the two config files alone, with no manual editing.")
    add(f"- **Validation:** {result['passed']}/{result['total']} checks passed "
        f"({result['failed']} failures).")
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
    add("# Site Explanations — Validation (S2-06a)\n")
    add(banner(config.MODULE_NAME))
    add("")
    add(f"{result['passed']}/{result['total']} checks passed "
        f"({result['failed']} failures). Every check is listed whether it passed "
        f"or not — no silent passes.\n")
    add("| Check | Expected | Observed | Result |")
    add("|-------|----------|----------|--------|")
    for check in result["checks"]:
        status = "PASS" if check["passed"] else "**FAIL**"
        add(f"| {check['name']} | {check['expected']} | {check['observed']} | {status} |")
    add("")
    add(f"*Generated {generated_utc}; git commit `{commit}`.*")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def record_provenance(
    *,
    json_path: Path,
    csv_path: Path,
    n_records: int,
    templates: ExplanationTemplates,
    inputs: dict,
    summary: dict,
    generated_utc: str,
    commit: str,
    manifest_path: Path,
    provenance_path: Path,
    register_path: Path,
) -> dict:
    """
    Record the Explanation_Table as a DERIVED product in all three provenance
    artefacts: the manifest, `DATA_PROVENANCE.md` and the source register.
    Mirrors `scoring.report.record_provenance`.
    """
    record = {
        "output_file": _rel(json_path),
        "csv_file": _rel(csv_path),
        "stage": config.STAGE_NAME,
        "product_type": "derived",
        "generated_utc": generated_utc,
        "git_commit": commit,
        "records": int(n_records),
        "sha256_json": sha256_file(json_path),
        "sha256_csv": sha256_file(csv_path),
        "bytes_json": Path(json_path).stat().st_size,
        "bytes_csv": Path(csv_path).stat().st_size,
        "inputs": [
            {
                "name": "scored_table",
                "path": _rel(inputs["scored_table_path"]),
                "layer": config.SCORED_TABLE_LAYER,
                "sha256": inputs["scored_table_sha256"],
            },
            {
                "name": "integrated_feature_table",
                "path": _rel(inputs["integrated_path"]),
            },
        ],
        "templates_config": {
            "path": _rel(templates.path) if templates.path else None,
            "templates_config_id": templates.config_id,
            "version": templates.version,
        },
        "weights_config": {
            "path": _rel(inputs["weights_path"]) if inputs["weights_path"] else None,
            "weights_config_id": inputs["weights_config_id"],
            "version": inputs["weights_version"],
        },
        "counts": {
            "n_eligible_cells": summary["n_eligible_cells"],
            "n_excluded_cells": summary.get("n_excluded_cells", 0),
            "n_explained": summary["n_explained"],
            "n_excluded_explained": summary.get("n_excluded_explained", 0),
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

    section = (
        f"{PROVENANCE_BEGIN}\n"
        f"## Derived layer — Site Explanations (S2-06a)\n\n"
        f"- **DERIVED PRODUCT — not custodial source data.** Fully regenerable "
        f"from the inputs below; contains no data of its own.\n"
        f"- **File:** `{record['output_file']}` (JSON array of "
        f"Explanation_Structure records)\n"
        f"- **CSV:** `{record['csv_file']}` (list fields joined; the "
        f"deterministic artefact)\n"
        f"- **Derived from:**\n"
        f"  - Scored_Table (S2-05): `{_rel(inputs['scored_table_path'])}` "
        f"(layer `{config.SCORED_TABLE_LAYER}`, SHA-256 "
        f"`{inputs['scored_table_sha256']}`)\n"
        f"  - integrated feature table (S1-08): `{_rel(inputs['integrated_path'])}` "
        f"(read only, to recompute normalisation bounds)\n"
        f"  - explanation templates (user input): "
        f"`{_rel(templates.path) if templates.path else '—'}` (version "
        f"`{templates.version}`, SHA-256 `{templates.config_id}`)\n"
        f"  - criteria weights (user input): "
        f"`{_rel(inputs['weights_path']) if inputs['weights_path'] else '—'}` "
        f"(SHA-256 `{inputs['weights_config_id']}`)\n"
        f"- **Method:** deterministic template/rule engine (NO LLM); eligible "
        f"cells: positive factors ranked by S2-05 contribution, weaknesses by "
        f"normalised value, qualitative bands recomputed via the scoring "
        f"normaliser and reconciled to the persisted contributions; excluded "
        f"cells: F16 exclusion reason pairs carried through; every record also "
        f"carries proxy and data-quality caveats; screening-level language only.\n"
        f"- **Records:** {summary['n_eligible_cells']:,} eligible + "
        f"{summary.get('n_excluded_cells', 0):,} excluded cells; "
        f"{summary['n_explained']:,} explained "
        f"({summary.get('n_excluded_explained', 0):,} excluded)\n"
        f"- **Regenerable:** yes — `python -m pipeline --only explanation` (after "
        f"`scoring`).\n"
        f"- **SHA-256 (JSON):** `{record['sha256_json']}`\n"
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
            "# Data Provenance — Explanations (S2-06a)\n\n"
            "Everything in `DATA/explanation/` is a DERIVED product generated by "
            "the `explanation` stage. Nothing here is custodial source data; the "
            "generated block below is rewritten on every run.\n\n"
        )
        text = (text.rstrip("\n") + "\n\n" + section) if text else (header + section)
    atomic_write_text(provenance_path, text)

    _write_source_register(register_path, record, inputs, templates, generated_utc)
    return record


def _write_source_register(
    register_path: Path,
    record: dict,
    inputs: dict,
    templates: ExplanationTemplates,
    generated_utc: str,
) -> None:
    """Append/replace this product's row in the explanation source register."""
    row = {
        "dataset_id": "optmining_site_explanations",
        "category": "derived-explanation",
        "custodian": "Opt-Mining (DERIVED — not custodial data)",
        "endpoint": _rel(inputs["scored_table_path"]),
        "access_method": f"generated by pipeline stage `{config.STAGE_NAME}`",
        "format": "JSON array + CSV",
        "native_crs": "n/a (cell_id join; no geometry)",
        "licence": "derived from the licensed inputs listed in each source layer's register",
        "vintage": config.EXPLANATION_VINTAGE,
        "size_or_count": f"{record['records']:,} records",
        "intended_use": (
            "Deterministic site explanations for eligible and excluded cells with "
            "proxy and data-quality caveats (S2-06a + S2-06b); consumed by S2-08 "
            "get_site_detail and S3-05 site detail"
        ),
        "notes": (
            f"templates_config_id {templates.config_id}; "
            f"weights_config_id {inputs['weights_config_id']}; "
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
