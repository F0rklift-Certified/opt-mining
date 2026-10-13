"""
Explanation_Table assembly, atomic writers and the schema document (S2-06a).

The output is a fully regenerable DERIVED product: delete it, rerun the stage
against the same Scored_Table and the same templates, and the identical
artefact comes back. Nothing here is hand-edited.

Two artefacts carry the explanations:
  - a JSON array — the structured Explanation_Structure records, the primary
    artefact the service (S2-08) and S2-06b consume;
  - a flat CSV — the same records with the list fields joined, the
    deterministic artefact to diff across runs (a GeoPackage's hash drifts with
    its internal timestamp, so as in the scoring stage the CSV is the byte-
    stable comparison artefact; the explanations carry no geometry of their own,
    so there is no GeoPackage here — the cell_id joins back to the grid).

Both writes go through a temporary sibling file + `os.replace` (via
`common.geo`), so a failed write leaves any previous artefact untouched.

A third artefact, the schema document, states the eligible Explanation_Structure
as the FROZEN contract S2-06b extends (excluded path + caveats) and S2-08
`get_site_detail` / S3-05 consume.
"""

from __future__ import annotations

import csv
import io
import json
import os
from collections.abc import Sequence
from pathlib import Path

from ..common.geo import atomic_write_text, banner
from . import config
from .engine import (
    CellExplanationInput,
    ExcludedCellInput,
    explain_cell,
    explain_excluded_cell,
)
from .templates import ExplanationTemplates

# The delimiter joining a list field into one CSV cell. A pipe is chosen
# because no phrase contains one, so the CSV round-trips back to the list.
CSV_LIST_DELIMITER = " | "


def build_explanations(
    cells: Sequence[CellExplanationInput],
    templates: ExplanationTemplates,
    excluded_cells: Sequence[ExcludedCellInput] = (),
) -> list[dict]:
    """
    One Explanation_Structure record per cell (S2-06b).

    Eligible cells are explained first (in the order given — the loader hands
    them in Scored_Table order), then excluded cells (in integrated-table
    order). Each eligible record carries the S2-06a factors plus the S2-06b
    caveats; each excluded record carries the F16 exclusion reasons plus the
    same caveats. Pure: no I/O.
    """
    records = [explain_cell(cell, templates) for cell in cells]
    records.extend(explain_excluded_cell(cell, templates) for cell in excluded_cells)
    return records


def write_json(records: Sequence[dict], path: Path) -> None:
    """
    Atomic, deterministic JSON write.

    Records are already field-ordered by the engine (ELIGIBLE_FIELDS for
    eligible records, EXCLUDED_FIELDS for excluded ones); the array preserves
    input order (eligible cells, then excluded). `sort_keys=False` keeps the
    documented field order, and the fixed 2-space indent + trailing newline make
    the file byte-identical across reruns with unchanged inputs.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(list(records), indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    atomic_write_text(path, text)


def _reasons_to_cell(reasons: Sequence[dict]) -> str:
    """
    Flatten the exclusion-reason pair list into one deterministic CSV cell.

    Each pair renders as "code: text"; multiple pairs are joined with the same
    pipe delimiter as the other list fields, so the CSV stays diff-stable and a
    consumer can split it back. The JSON artefact carries the structured pairs;
    the CSV is the byte-stable comparison form.
    """
    return CSV_LIST_DELIMITER.join(
        f"{r[config.REASON_CODE_KEY]}: {r[config.REASON_TEXT_KEY]}" for r in reasons
    )


def _flatten(record: dict) -> dict:
    """
    One CSV row over the ALL_FIELDS union.

    A record carries only its own path's fields, so fields the record does not
    have render as an empty cell. List fields are joined with the delimiter;
    the exclusion-reason pairs are flattened to "code: text" entries.
    """
    row: dict = {field: "" for field in config.ALL_FIELDS}
    row[config.FIELD_CELL_ID] = record.get(config.FIELD_CELL_ID, "")
    row[config.FIELD_ELIGIBLE] = record.get(config.FIELD_ELIGIBLE, "")
    if config.FIELD_HEADLINE in record:
        row[config.FIELD_HEADLINE] = record[config.FIELD_HEADLINE]
    if config.FIELD_POSITIVE_FACTORS in record:
        row[config.FIELD_POSITIVE_FACTORS] = CSV_LIST_DELIMITER.join(
            record[config.FIELD_POSITIVE_FACTORS]
        )
    if config.FIELD_WEAKNESSES in record:
        row[config.FIELD_WEAKNESSES] = CSV_LIST_DELIMITER.join(record[config.FIELD_WEAKNESSES])
    if config.FIELD_PROXY_CAVEATS in record:
        row[config.FIELD_PROXY_CAVEATS] = CSV_LIST_DELIMITER.join(
            record[config.FIELD_PROXY_CAVEATS]
        )
    if config.FIELD_DATA_QUALITY_NOTES in record:
        row[config.FIELD_DATA_QUALITY_NOTES] = CSV_LIST_DELIMITER.join(
            record[config.FIELD_DATA_QUALITY_NOTES]
        )
    if config.FIELD_EXCLUSION_REASONS in record:
        row[config.FIELD_EXCLUSION_REASONS] = _reasons_to_cell(
            record[config.FIELD_EXCLUSION_REASONS]
        )
    return row


def write_csv(records: Sequence[dict], path: Path) -> None:
    """
    Atomic, deterministic CSV write.

    Same conventions as the scoring stage's CSV writer: no index, "\\n" line
    endings, UTF-8, so the file is byte-identical across reruns with unchanged
    inputs. The header is the ALL_FIELDS union (both paths' fields); each record
    fills only its own path's columns. List fields are joined with
    `CSV_LIST_DELIMITER`.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=list(config.ALL_FIELDS), lineterminator="\n"
    )
    writer.writeheader()
    for record in records:
        writer.writerow(_flatten(record))
    atomic_write_text(path, buffer.getvalue())


def write_explanations(
    records: Sequence[dict],
    json_path: Path,
    csv_path: Path,
) -> None:
    """Write both artefacts atomically; a failure leaves prior outputs intact."""
    write_json(records, json_path)
    write_csv(records, csv_path)


def build_schema_doc(templates: ExplanationTemplates) -> str:
    """
    The eligible Explanation_Structure contract, as markdown.

    This is the FROZEN surface: S2-06b EXTENDS it (adding exclusion_reasons,
    proxy_caveats, data_quality_notes for the excluded path) and S2-08
    `get_site_detail` / S3-05 CONSUME it. The field names and types here must
    stay stable across the sprint boundary.
    """
    lines: list[str] = []
    add = lines.append
    add("# Site Explanation — Structure (S2-06a + S2-06b)\n")
    add(banner(config.MODULE_NAME))
    add("")
    add("The deterministic explanation engine emits one record per site. S2-06a "
        "owns the **eligible-cell** fields; **S2-06b extends this structure in "
        "place** — adding the **excluded-cell** field and the **caveat** fields "
        "carried on both paths — without renaming or removing any S2-06a field. "
        "The S2-08 `get_site_detail` operation returns this structure and the "
        "S3-05 site-detail view renders it, so the contract is frozen at the "
        "Sprint 2/3 boundary.\n")

    add("## Eligible-cell fields (S2-06a)\n")
    add("| Field | Type | Description |")
    add("|-------|------|-------------|")
    add(f"| `{config.FIELD_CELL_ID}` | string | The analysis grid cell id, "
        f"joinable to the grid and the Scored_Table. |")
    add(f"| `{config.FIELD_ELIGIBLE}` | boolean | `true` on this path; `false` "
        f"for excluded cells (below). |")
    add(f"| `{config.FIELD_HEADLINE}` | string | A single screening-level "
        f"headline. Never a \"best site\" claim. |")
    add(f"| `{config.FIELD_POSITIVE_FACTORS}` | array of string | The cell's "
        f"strongest positive factors, ranked by S2-05 contribution magnitude, "
        f"each with a qualitative band, at most {config.MAX_POSITIVE_FACTORS}. |")
    add(f"| `{config.FIELD_WEAKNESSES}` | array of string | The cell's important "
        f"weaknesses (criteria it scores poorly on), worst first, at most "
        f"{config.MAX_WEAKNESSES}. |")
    add("")

    add("## Excluded-cell field (S2-06b)\n")
    add("An excluded record carries `cell_id`, `eligible: false`, the exclusion "
        "reasons below, and the two caveat fields — it does **not** carry "
        "`headline`, `positive_factors` or `weaknesses`, because an excluded "
        "cell was removed before scoring and has no rank to explain.\n")
    add("| Field | Type | Description |")
    add("|-------|------|-------------|")
    add(f"| `{config.FIELD_EXCLUSION_REASONS}` | array of {{`code`, `text`}} | "
        f"The machine- and human-readable exclusion reason(s) from the "
        f"integrated table (Decision-Engine Spec §6.5, frozen decision F16), "
        f"in rule-config order. `code` is a member of the frozen reason-code "
        f"vocabulary; `text` is the human-readable reason. Non-empty for every "
        f"excluded cell. |")
    add("")

    add("## Caveat fields (S2-06b — on both paths)\n")
    add("| Field | Type | Description |")
    add("|-------|------|-------------|")
    add(f"| `{config.FIELD_PROXY_CAVEATS}` | array of string | A caveat for "
        f"each **proxy** variable the cell used, so a proxy is never read as a "
        f"direct measurement (AC7). The MVP demand feature is a spatial proxy "
        f"allocated below the AEMO region, not measured local demand. Empty "
        f"when the cell used no proxy variable. |")
    add(f"| `{config.FIELD_DATA_QUALITY_NOTES}` | array of string | The cell's "
        f"S1-09 composite confidence level (always surfaced, including `high`), "
        f"with the reduced-confidence reasons appended when present. Exactly one "
        f"entry per record. |")
    add("")

    add("## Example — eligible cell\n")
    example = {
        config.FIELD_CELL_ID: "NSW001",
        config.FIELD_ELIGIBLE: True,
        config.FIELD_HEADLINE: templates.headline,
        config.FIELD_POSITIVE_FACTORS: [
            "Strong wind resource (top decile)",
            "Inside a Renewable Energy Zone (present)",
        ],
        config.FIELD_WEAKNESSES: ["Distant from transmission (limited)"],
        config.FIELD_PROXY_CAVEATS: [
            templates.phrases["demand_proxy"].proxy_caveat
            if "demand_proxy" in templates.phrases
            and templates.phrases["demand_proxy"].proxy_caveat
            else "Demand shown is a spatial proxy, not measured local demand"
        ],
        config.FIELD_DATA_QUALITY_NOTES: [
            templates.data_quality.level_template.format(level="high")
        ],
    }
    add("```json")
    add(json.dumps(example, indent=2, ensure_ascii=False))
    add("```\n")

    add("## Example — excluded cell\n")
    excluded_example = {
        config.FIELD_CELL_ID: "NSW002",
        config.FIELD_ELIGIBLE: False,
        config.FIELD_EXCLUSION_REASONS: [
            {config.REASON_CODE_KEY: "protected_area",
             config.REASON_TEXT_KEY: "Protected area: Oxley Wild Rivers NP"}
        ],
        config.FIELD_PROXY_CAVEATS: [
            templates.phrases["demand_proxy"].proxy_caveat
            if "demand_proxy" in templates.phrases
            and templates.phrases["demand_proxy"].proxy_caveat
            else "Demand shown is a spatial proxy, not measured local demand"
        ],
        config.FIELD_DATA_QUALITY_NOTES: [
            templates.data_quality.notes_template.format(
                level_note=templates.data_quality.level_template.format(level="medium"),
                notes="one feature interpolated",
            )
        ],
    }
    add("```json")
    add(json.dumps(excluded_example, indent=2, ensure_ascii=False))
    add("```\n")

    add("## Determinism and provenance\n")
    add("- **Deterministic, no LLM.** The same Scored_Table and the same "
        "templates always produce byte-identical records.")
    add(f"- **Templates identity:** the phrasing is data, loaded from "
        f"`{templates.path.name if templates.path else '<in-memory>'}` "
        f"(version `{templates.version}`, SHA-256 `{templates.config_id}`).")
    add("- **Screening-level language throughout.** \"Best site\"/\"optimal "
        "site\" phrasing is rejected at config load and asserted absent by "
        "validation.")
    add("")
    return "\n".join(lines) + "\n"


def write_schema_doc(templates: ExplanationTemplates, path: Path) -> None:
    atomic_write_text(Path(path), build_schema_doc(templates))
