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
from .engine import CellExplanationInput, explain_cell
from .templates import ExplanationTemplates

# The delimiter joining a list field into one CSV cell. A pipe is chosen
# because no phrase contains one, so the CSV round-trips back to the list.
CSV_LIST_DELIMITER = " | "


def build_explanations(
    cells: Sequence[CellExplanationInput],
    templates: ExplanationTemplates,
) -> list[dict]:
    """
    One eligible Explanation_Structure record per cell, in the order given
    (the loader hands eligible cells in Scored_Table order). Pure: no I/O.
    """
    return [explain_cell(cell, templates) for cell in cells]


def write_json(records: Sequence[dict], path: Path) -> None:
    """
    Atomic, deterministic JSON write.

    Records are already field-ordered by the engine (ELIGIBLE_FIELDS); the
    array preserves input order. `sort_keys=False` keeps the documented field
    order, and the fixed 2-space indent + trailing newline make the file
    byte-identical across reruns with unchanged inputs.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(list(records), indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    atomic_write_text(path, text)


def _flatten(record: dict) -> dict:
    """One CSV row: list fields joined with the delimiter, scalars as-is."""
    return {
        config.FIELD_CELL_ID: record[config.FIELD_CELL_ID],
        config.FIELD_ELIGIBLE: record[config.FIELD_ELIGIBLE],
        config.FIELD_HEADLINE: record[config.FIELD_HEADLINE],
        config.FIELD_POSITIVE_FACTORS: CSV_LIST_DELIMITER.join(
            record[config.FIELD_POSITIVE_FACTORS]
        ),
        config.FIELD_WEAKNESSES: CSV_LIST_DELIMITER.join(record[config.FIELD_WEAKNESSES]),
    }


def write_csv(records: Sequence[dict], path: Path) -> None:
    """
    Atomic, deterministic CSV write.

    Same conventions as the scoring stage's CSV writer: no index, "\\n" line
    endings, UTF-8, so the file is byte-identical across reruns with unchanged
    inputs. List fields are joined with `CSV_LIST_DELIMITER`.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=list(config.ELIGIBLE_FIELDS), lineterminator="\n"
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
    add("# Site Explanation — Structure (S2-06a)\n")
    add(banner(config.MODULE_NAME))
    add("")
    add("The deterministic explanation engine emits one record per site. This "
        "document defines the **eligible-cell** fields, which S2-06a owns. "
        "**S2-06b extends this structure in place** — adding the excluded-cell "
        "and caveat fields — and must not rename or remove any field below. "
        "The S2-08 `get_site_detail` operation returns this structure and the "
        "S3-05 site-detail view renders it, so the contract is frozen at the "
        "Sprint 2/3 boundary.\n")

    add("## Eligible-cell fields\n")
    add("| Field | Type | Description |")
    add("|-------|------|-------------|")
    add(f"| `{config.FIELD_CELL_ID}` | string | The analysis grid cell id, "
        f"joinable to the grid and the Scored_Table. |")
    add(f"| `{config.FIELD_ELIGIBLE}` | boolean | `true` for every record on "
        f"this path. S2-06b emits `false` records for excluded cells. |")
    add(f"| `{config.FIELD_HEADLINE}` | string | A single screening-level "
        f"headline. Never a \"best site\" claim. |")
    add(f"| `{config.FIELD_POSITIVE_FACTORS}` | array of string | The cell's "
        f"strongest positive factors, ranked by S2-05 contribution magnitude, "
        f"each with a qualitative band, at most {config.MAX_POSITIVE_FACTORS}. |")
    add(f"| `{config.FIELD_WEAKNESSES}` | array of string | The cell's important "
        f"weaknesses (criteria it scores poorly on), worst first, at most "
        f"{config.MAX_WEAKNESSES}. |")
    add("")

    add("## Example\n")
    example = {
        config.FIELD_CELL_ID: "NSW001",
        config.FIELD_ELIGIBLE: True,
        config.FIELD_HEADLINE: templates.headline,
        config.FIELD_POSITIVE_FACTORS: [
            "Strong wind resource (top decile)",
            "Inside a Renewable Energy Zone (present)",
        ],
        config.FIELD_WEAKNESSES: ["Distant from transmission (limited)"],
    }
    add("```json")
    add(json.dumps(example, indent=2, ensure_ascii=False))
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
