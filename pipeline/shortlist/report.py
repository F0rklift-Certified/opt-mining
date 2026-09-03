"""
Disclaimer, metadata and Summary_Report for the S1-11 shortlist stage
(Requirements 8, 9, 11).

Every shortlist output is a preliminary screening artefact, and the pipeline's
Constitution forbids emitting a result that a downstream reader could mistake
for a site approval. This module is where that guarantee is discharged for the
two artefacts that carry no in-band metadata of their own — the human-readable
Summary_Report and the machine-readable metadata sidecar:

  * :func:`write_summary_report` writes
    ``DATA/shortlist/metadata/shortlist_summary.md`` via
    ``common.geo.atomic_write_text``, stamped with ``common.geo.banner`` (11.4).
    It records the Summary_Statistics (6), the effective Top_N and the
    eligible-vs-included counts (2.5), the geometry choice (5.4), any optional
    context-column definitions (4.3), the name-collision outcome if any (7.4),
    the Preliminary_Disclaimer (8.1) and the Analysis_Resolution statement
    (8.2).

  * :func:`write_metadata_sidecar` writes a JSON sidecar via
    ``common.geo.atomic_write_json`` recording ``pipeline_version`` and the UTC
    ``run_timestamp`` (9.1), ``effective_top_n`` and ``n_shortlisted`` (9.2),
    the ``scored_table_id`` (Scored_Table path + ``sha256_file`` digest, so the
    exact scores are traceable) (9.3), the ``geometry`` choice (5.4), and the
    Preliminary_Disclaimer and Analysis_Resolution statement (8.1, 8.2, 8.4).

The two writers are handed the SAME ``pipeline_version`` and ``run_timestamp``
by ``run()`` and record them identically, so the Summary_Report and the sidecar
never disagree about which run produced the outputs (9.4).

The stage NEVER emits any output that omits BOTH the disclaimer and the
resolution statement (8.4, 8.5). The Shortlist_GeoJSON carries them in
file-level foreign members (``write.write_geojson``, 8.3); the Shortlist_CSV has
no metadata rows, so its disclaimer travels via this Summary_Report and the
metadata sidecar (8.4).

``record_provenance`` (the derived-product ``DATA_PROVENANCE.md`` row, manifest
and source_register — Requirement 11.1–11.3, task 10.2) also lives in this
module but is implemented separately; this file is written so it can be added
below without touching the two functions here.

Design reference: design.md §10 "Disclaimer & metadata".
"""

from __future__ import annotations

import csv
import io
import json
import subprocess
from pathlib import Path

from ..common.geo import atomic_write_json, atomic_write_text, banner, sha256_file
from . import config
from .assemble import OptionalContextColumn
from .naming import CollisionOutcome
from .summary import SummaryStats


def _rel(path: Path | str) -> str:
    """Path relative to the project root for reports and manifests; absolute
    when it lies outside the project tree."""
    path = Path(path)
    try:
        return str(path.relative_to(config.PROJECT_ROOT))
    except ValueError:
        return str(path)


def pipeline_version(cwd: Path | None = None) -> str:
    """
    The Pipeline_Version recorded in the Summary_Report and the metadata
    sidecar (Requirement 9.1).

    Mirrors the established ``scoring.report.git_commit`` / ``integration``
    convention: the HEAD commit, suffixed ``-dirty`` when TRACKED files are
    modified (untracked files — this stage's own first-run outputs among them —
    do not count), and ``"unknown"`` on any failure. It NEVER raises:
    reproducibility metadata must not be able to fail the stage. ``run()`` calls
    this once and threads the single value into BOTH writers so the two records
    agree (9.4).
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


def scored_table_id(scored_path: Path | str) -> dict:
    """
    A traceable identifier for the Scored_Table input: its project-relative
    path plus its SHA-256 digest, so a reviewer can confirm the exact scores the
    shortlist was drawn from (Requirement 9.3).

    Shared by the Summary_Report and the sidecar so both name the same input
    fingerprint.
    """
    return {"path": _rel(scored_path), "sha256": sha256_file(Path(scored_path))}


# ---------------------------------------------------------------------------
# Summary_Report (Requirements 2.5, 4.3, 5.4, 6, 7.4, 8.1, 8.2, 11.4)
# ---------------------------------------------------------------------------


def _fmt(value: float | None, places: int = 4) -> str:
    """Render an optional numeric statistic; an em dash for ``None`` (an empty
    eligible population) rather than a fabricated number."""
    return "—" if value is None else f"{value:.{places}f}"


def _fmt_range(bounds: tuple, places: int = 4) -> str:
    """Render a ``(min, max)`` range, ``—`` when either bound is ``None``."""
    lo, hi = bounds
    if lo is None or hi is None:
        return "—"
    return f"{lo:.{places}f} … {hi:.{places}f}"


def build_summary_report(
    *,
    stats: SummaryStats,
    effective_top_n: int,
    n_shortlisted: int,
    geometry: str,
    optional_context: tuple[OptionalContextColumn, ...],
    collision: CollisionOutcome | None,
    pipeline_version: str,
    run_timestamp: str,
) -> str:
    """
    Render the Summary_Report markdown (Requirements 2.5, 4.3, 5.4, 6, 7.4,
    8.1, 8.2, 9.4, 11.4).

    Pure: builds the report text from the run's already-computed values; no file
    I/O. :func:`write_summary_report` stamps and writes it.
    """
    sd = stats.score_dist
    conf = stats.confidence_dist

    lines: list[str] = []
    add = lines.append

    add("# Preliminary Ranked Shortlist — Summary Report (S1-11)")
    add("")
    # Banner (11.4): identical wording to common.geo.banner, so the report is
    # unmistakably a generated, do-not-edit artefact.
    add(banner(config.STAGE_NAME).rstrip("\n"))
    add("")

    # Preliminary_Disclaimer (8.1) and Analysis_Resolution (8.2) FIRST, so a
    # reader cannot miss that this is a screening output, not a site approval,
    # and at what resolution it was produced.
    add("## Disclaimer")
    add("")
    add(f"> {config.PRELIMINARY_DISCLAIMER}")
    add("")
    add(f"**Analysis resolution:** {config.ANALYSIS_RESOLUTION}.")
    add("")

    # Pipeline_Version + Run_Timestamp — recorded identically to the sidecar
    # (9.4) so the two artefacts agree on which run produced the shortlist.
    add("## Run")
    add("")
    add(f"- **Pipeline version:** `{pipeline_version}`")
    add(f"- **Run timestamp (UTC):** {run_timestamp}")
    add("")

    # Selection sizing (2.5): the effective Top_N and the eligible-vs-included
    # counts, so a reviewer can see the shortlist was clamped rather than padded.
    add("## Selection")
    add("")
    add(f"- **Effective Top_N:** {effective_top_n}")
    add(f"- **Eligible cells (candidates):** {stats.n_eligible:,}")
    add(f"- **Included in shortlist:** {n_shortlisted:,}")
    add(f"- **Scored cells:** {stats.n_scored:,}")
    add(f"- **Total cells (grid):** {stats.n_cells:,}")
    add("")

    # Geometry choice (5.4) recorded for the reviewer of the GeoJSON.
    add("## Output geometry")
    add("")
    add(
        f"- **GeoJSON geometry:** `{geometry}` "
        f"({'centroid Point' if geometry == 'centroid' else 'cell Polygon'}, "
        f"EPSG:4326)."
    )
    add("")

    # Summary_Statistics (Requirement 6). The score distribution is over the
    # ELIGIBLE population only (6.1, 6.6); ranges and confidence over the
    # shortlisted cells (6.2, 6.4); REZ context where available (6.3).
    add("## Summary statistics")
    add("")
    add("### Suitability score (eligible cells only)")
    add("")
    add("| Statistic | Value |")
    add("| --- | --- |")
    add(f"| min | {_fmt(sd['min'])} |")
    add(f"| max | {_fmt(sd['max'])} |")
    add(f"| mean | {_fmt(sd['mean'])} |")
    add(f"| std (sample) | {_fmt(sd['std'])} |")
    add("")
    add("### Geographic spread (shortlisted cells, EPSG:4326)")
    add("")
    add(f"- **Latitude range:** {_fmt_range(stats.lat_range)}")
    add(f"- **Longitude range:** {_fmt_range(stats.lon_range)}")
    add("")
    add("### Confidence distribution (shortlisted cells)")
    add("")
    add("| Confidence | Count |")
    add("| --- | --- |")
    for level in config.CONFIDENCE_LEVELS:
        add(f"| {level} | {conf.get(level, 0):,} |")
    add("")
    add("### Renewable Energy Zones represented")
    add("")
    if stats.rez_represented:
        add(", ".join(str(r) for r in stats.rez_represented))
    else:
        add("_No REZ context available for the shortlisted cells._")
    add("")

    # Optional context-column definitions (4.3): document exactly the optional
    # columns the Shortlist actually carries, with their definition and source.
    add("## Optional context columns")
    add("")
    if optional_context:
        for col in optional_context:
            add(f"- **`{col.name}`** — {col.definition} _Source:_ {col.source}")
    else:
        add("_No optional context columns were available for this run._")
    add("")

    # Name-collision outcome (7.4): whether the finer-grained UTC rule had to be
    # applied rather than silently overwriting an earlier run's output.
    add("## Output naming")
    add("")
    if collision is not None and collision.occurred:
        add(
            f"- **Name collision:** the base name `{collision.base_stem}` "
            f"already existed, so a finer-grained UTC component was appended "
            f"(`{collision.resolved_stem}`, precision `{collision.precision}`) "
            f"rather than overwriting the earlier run."
        )
    elif collision is not None:
        add(
            f"- **Name collision:** none — outputs written under "
            f"`{collision.resolved_stem}` (precision `{collision.precision}`)."
        )
    else:
        add("- **Name collision:** none.")
    add("")

    return "\n".join(lines).rstrip("\n") + "\n"


def write_summary_report(
    path: Path | str,
    *,
    stats: SummaryStats,
    effective_top_n: int,
    n_shortlisted: int,
    geometry: str,
    optional_context: tuple[OptionalContextColumn, ...] = (),
    collision: CollisionOutcome | None = None,
    pipeline_version: str,
    run_timestamp: str,
) -> Path:
    """
    Write the Summary_Report to ``path`` (default
    ``DATA/shortlist/metadata/shortlist_summary.md``) via
    ``common.geo.atomic_write_text``, banner-stamped (Requirements 2.5, 4.3,
    5.4, 6, 7.4, 8.1, 8.2, 9.4, 11.4).

    Parameters
    ----------
    path:
        The Summary_Report path (``run()`` passes
        ``config.SHORTLIST_META_DIR / config.SUMMARY_REPORT_FILENAME``).
    stats:
        The computed :class:`summary.SummaryStats` for the run (Requirement 6).
    effective_top_n:
        The resolved effective Top_N (Requirement 2.5).
    n_shortlisted:
        The number of cells actually included in the shortlist — the included
        count paired with ``stats.n_eligible`` for the eligible-vs-included
        report (Requirement 2.5).
    geometry:
        The GeoJSON geometry choice, one of ``config.GEOMETRY_CHOICES``, noted
        for the reviewer (Requirement 5.4).
    optional_context:
        The optional context columns actually appended to the Shortlist, with
        their definitions and sources (from
        ``assemble.optional_context_columns``), documented in the report
        (Requirement 4.3). Empty when none were available.
    collision:
        The naming :class:`naming.CollisionOutcome`, recorded so a reviewer sees
        whether the finer-grained-UTC rule was applied (Requirement 7.4).
        ``None`` is tolerated and reported as "no collision".
    pipeline_version:
        The Pipeline_Version, recorded identically to the sidecar (Requirement
        9.4).
    run_timestamp:
        The single UTC Run_Timestamp for the run, recorded identically to the
        sidecar (Requirement 9.4).

    Returns
    -------
    Path
        The path written, so ``run()`` can report it in its summary dict.
    """
    text = build_summary_report(
        stats=stats,
        effective_top_n=effective_top_n,
        n_shortlisted=n_shortlisted,
        geometry=geometry,
        optional_context=tuple(optional_context),
        collision=collision,
        pipeline_version=pipeline_version,
        run_timestamp=run_timestamp,
    )
    path = Path(path)
    atomic_write_text(path, text)
    return path


# ---------------------------------------------------------------------------
# Metadata sidecar (Requirements 5.4, 8.1, 8.2, 8.4, 9.1, 9.2, 9.3, 9.4)
# ---------------------------------------------------------------------------


def build_metadata_sidecar(
    *,
    scored_path: Path | str,
    effective_top_n: int,
    n_shortlisted: int,
    geometry: str,
    pipeline_version: str,
    run_timestamp: str,
) -> dict:
    """
    Build the metadata sidecar object (Requirements 5.4, 8.1, 8.2, 8.4, 9.1,
    9.2, 9.3, 9.4).

    Pure: computes the ``scored_table_id`` fingerprint (which reads the
    Scored_Table to hash it) and assembles the record; no output is written
    here. :func:`write_metadata_sidecar` writes it.

    Records, identically to the Summary_Report for a single run (9.4):
      * ``pipeline_version`` and ``run_timestamp`` (UTC) (9.1);
      * ``effective_top_n`` and ``n_shortlisted`` (9.2);
      * ``scored_table_id`` — the Scored_Table path + SHA-256 digest (9.3);
      * ``geometry`` — the GeoJSON geometry choice (5.4);
      * ``preliminary_disclaimer`` and ``analysis_resolution`` (8.1, 8.2, 8.4).
    """
    return {
        "stage": config.STAGE_NAME,
        "product_type": "derived",
        # Pipeline_Version + Run_Timestamp — recorded identically to the
        # Summary_Report (9.1, 9.4).
        "pipeline_version": pipeline_version,
        "run_timestamp": run_timestamp,
        # Selection sizing (9.2).
        "effective_top_n": int(effective_top_n),
        "n_shortlisted": int(n_shortlisted),
        # Score-input fingerprint so the exact scores are traceable (9.3).
        "scored_table_id": scored_table_id(scored_path),
        # GeoJSON geometry choice (5.4).
        "geometry": geometry,
        # Disclaimer + resolution so the CSV's disclaimer travels here (8.1,
        # 8.2, 8.4): no output ever omits BOTH the disclaimer and resolution.
        "preliminary_disclaimer": config.PRELIMINARY_DISCLAIMER,
        "analysis_resolution": config.ANALYSIS_RESOLUTION,
    }


def write_metadata_sidecar(
    path: Path | str,
    *,
    scored_path: Path | str,
    effective_top_n: int,
    n_shortlisted: int,
    geometry: str,
    pipeline_version: str,
    run_timestamp: str,
) -> Path:
    """
    Write the JSON metadata sidecar to ``path`` (default
    ``DATA/shortlist/metadata/shortlist_metadata.json``) via
    ``common.geo.atomic_write_json`` (Requirements 5.4, 8.1, 8.2, 8.4, 9.1,
    9.2, 9.3, 9.4).

    Parameters
    ----------
    path:
        The sidecar path (``run()`` passes
        ``config.SHORTLIST_META_DIR / config.METADATA_SIDECAR_FILENAME``).
    scored_path:
        The Scored_Table input path, fingerprinted (path + SHA-256) into
        ``scored_table_id`` so the exact scores are traceable (Requirement 9.3).
    effective_top_n:
        The resolved effective Top_N (Requirement 9.2).
    n_shortlisted:
        The number of cells included in the shortlist (Requirement 9.2).
    geometry:
        The GeoJSON geometry choice (Requirement 5.4).
    pipeline_version:
        The Pipeline_Version, recorded identically to the Summary_Report
        (Requirement 9.1, 9.4).
    run_timestamp:
        The single UTC Run_Timestamp, recorded identically to the
        Summary_Report (Requirement 9.1, 9.4).

    Returns
    -------
    Path
        The path written, so ``run()`` can report it if needed.
    """
    record = build_metadata_sidecar(
        scored_path=scored_path,
        effective_top_n=effective_top_n,
        n_shortlisted=n_shortlisted,
        geometry=geometry,
        pipeline_version=pipeline_version,
        run_timestamp=run_timestamp,
    )
    path = Path(path)
    atomic_write_json(path, record)
    return path


# ---------------------------------------------------------------------------
# Provenance (Requirement 11.1–11.3) — record_provenance is implemented in
# task 10.2 and appended below this line. It reuses _rel, pipeline_version and
# scored_table_id above.
# ---------------------------------------------------------------------------

PROVENANCE_BEGIN = "<!-- BEGIN shortlist.run derived layer (generated) -->"
PROVENANCE_END = "<!-- END shortlist.run derived layer (generated) -->"


def _input_fingerprint(name: str, path: Path | str, layer: str | None) -> dict:
    """
    Fingerprint one upstream input for the manifest and DATA_PROVENANCE.md row:
    its project-relative path, the layer read, its SHA-256 digest and byte
    count. Mirrors the ``info`` dict ``integration.merge.read_layer`` records,
    so a reviewer can confirm the exact Scored_Table and Analysis_Grid the
    shortlist was drawn from (Requirement 11.1).
    """
    path = Path(path)
    return {
        "name": name,
        "path": _rel(path),
        "layer": layer,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def record_provenance(
    *,
    csv_path: Path | str,
    geojson_path: Path | str,
    scored_path: Path | str,
    grid_path: Path | str,
    effective_top_n: int,
    n_shortlisted: int,
    run_timestamp: str,
    pipeline_version: str,
    manifest_path: Path | str,
    provenance_path: Path | str,
    register_path: Path | str,
    scored_layer: str | None = None,
    grid_layer: str | None = None,
) -> dict:
    """
    Record the shortlist outputs as DERIVED products in all three provenance
    artefacts, mirroring ``integration.merge.record_provenance`` and
    ``scoring.report.record_provenance`` (Requirement 11.1–11.3).

    The stage emits TWO headline outputs — the Shortlist_CSV and the
    Shortlist_GeoJSON — from a single run. They are recorded together as ONE
    derived-product record (they share inputs, Top_N and Run_Timestamp), so
    the manifest, ``DATA_PROVENANCE.md`` and the ``source_register`` never
    disagree about which run produced which pair.

    Writes, all via ``common.geo`` atomic writers:

      * ``shortlist_manifest.json`` — a manifest record keyed by the pair of
        output files (so a rerun REPLACES rather than appends), carrying the
        SHA-256 digest and byte count of each output, the UTC Run_Timestamp,
        the Pipeline_Version, and the generation params: the Scored_Table and
        Analysis_Grid inputs (path + layer + SHA-256 + bytes) and the effective
        Top_N (11.1, 11.3).
      * ``DATA/shortlist/DATA_PROVENANCE.md`` — a generated block spliced
        between BEGIN/END markers (handwritten text above is never touched),
        explicitly labelling the outputs a **derived product**, listing the
        two inputs, the effective Top_N and the UTC Run_Timestamp (11.1, 11.2,
        11.3).
      * ``source_register.csv`` — one row (same column vocabulary as the other
        stages' source registers), replaced on rerun by ``dataset_id`` (11.3).

    Parameters
    ----------
    csv_path, geojson_path:
        The two written shortlist outputs (the timestamped/versioned names
        from ``naming.resolve_output_paths``), fingerprinted into the record.
    scored_path, grid_path:
        The Scored_Table and Analysis_Grid inputs, fingerprinted (path + layer
        + SHA-256 + bytes) as the generation inputs (Requirement 11.1).
    scored_layer, grid_layer:
        The layers read from each input (``config.SCORED_LAYER`` /
        ``config.GRID_LAYER``), recorded alongside the path.
    effective_top_n:
        The resolved effective Top_N recorded as a generation param
        (Requirement 11.1).
    n_shortlisted:
        The number of cells actually included, recorded for context (the
        clamped-vs-requested count).
    run_timestamp:
        The single UTC Run_Timestamp for the run (Requirement 11.1) — the same
        value threaded into the filenames and the metadata sidecar.
    pipeline_version:
        The Pipeline_Version recorded alongside the timestamp.
    manifest_path, provenance_path, register_path:
        Destinations (``run()`` passes
        ``config.SHORTLIST_META_DIR / config.MANIFEST_FILENAME``,
        ``config.SHORTLIST_DIR / config.PROVENANCE_FILENAME`` and
        ``config.SHORTLIST_META_DIR / config.SOURCE_REGISTER_FILENAME``).

    Returns
    -------
    dict
        The manifest record, so ``run()`` can report its provenance paths.
    """
    inputs = [
        _input_fingerprint("scored_table", scored_path, scored_layer),
        _input_fingerprint("analysis_grid", grid_path, grid_layer),
    ]

    record = {
        "csv_file": _rel(csv_path),
        "geojson_file": _rel(geojson_path),
        "stage": config.STAGE_NAME,
        "product_type": "derived",
        "run_timestamp": run_timestamp,
        "pipeline_version": pipeline_version,
        "sha256_csv": sha256_file(Path(csv_path)),
        "sha256_geojson": sha256_file(Path(geojson_path)),
        "bytes_csv": Path(csv_path).stat().st_size,
        "bytes_geojson": Path(geojson_path).stat().st_size,
        # Generation params (Requirement 11.1): the two inputs + the effective
        # Top_N. n_shortlisted records how many were actually included (Top_N
        # is clamped, never padded).
        "effective_top_n": int(effective_top_n),
        "n_shortlisted": int(n_shortlisted),
        "inputs": inputs,
    }

    # --- manifest (read-merge-write, keyed by the output pair so a rerun
    #     replaces rather than appends) ---
    manifest_path = Path(manifest_path)
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {}
    )
    derived = [
        r for r in manifest.get("derived_features", [])
        if r.get("csv_file") != record["csv_file"]
    ]
    derived.append(record)
    manifest["derived_features"] = derived
    atomic_write_json(manifest_path, manifest)

    # --- DATA_PROVENANCE.md generated block (11.1, 11.2, 11.3) ---
    inputs_md = "\n".join(
        f"  - {i['name']}: `{i['path']}`"
        + (f" (layer `{i['layer']}`" if i["layer"] else " (")
        + f", SHA-256 `{i['sha256']}`)"
        for i in inputs
    )
    section = (
        f"{PROVENANCE_BEGIN}\n"
        f"## Derived layer — Preliminary Ranked Shortlist (S1-11)\n\n"
        f"- **DERIVED PRODUCT — not custodial source data.** A preliminary "
        f"screening selection, fully regenerable from the inputs below; it "
        f"contains no data of its own.\n"
        f"- **CSV:** `{record['csv_file']}` (the tabular shortlist)\n"
        f"- **GeoJSON:** `{record['geojson_file']}` (EPSG:4326, one feature per "
        f"shortlisted cell)\n"
        f"- **Derived from:**\n{inputs_md}\n"
        f"- **Method:** the top {record['effective_top_n']} Eligible_Cells by the "
        f"S1-10 `rank` (no re-scoring, no re-ranking); `centroid_lat`/"
        f"`centroid_lon` joined from the Analysis_Grid on `cell_id`; no "
        f"reprojection (EPSG:4326 throughout).\n"
        f"- **Effective Top_N:** {record['effective_top_n']} "
        f"(included {record['n_shortlisted']:,} cells — clamped to the eligible "
        f"population, never padded)\n"
        f"- **SHA-256 (CSV):** `{record['sha256_csv']}`\n"
        f"- **SHA-256 (GeoJSON):** `{record['sha256_geojson']}`\n"
        f"- **Regenerable:** yes — `python -m pipeline --only {config.STAGE_NAME}` "
        f"(after `scoring`).\n"
        f"- **Run timestamp (UTC):** {run_timestamp}\n"
        f"- **Pipeline version:** `{pipeline_version}`\n"
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
            "# Data Provenance — Shortlist (S1-11)\n\n"
            "Everything in `DATA/shortlist/` is a DERIVED product generated by "
            "the `shortlist` stage. Nothing here is custodial source data; the "
            "generated block below is rewritten on every run.\n\n"
        )
        text = (text.rstrip("\n") + "\n\n" + section) if text else (header + section)
    atomic_write_text(provenance_path, text)

    # --- source_register entry (11.3) ---
    _write_source_register(register_path, record, inputs, run_timestamp)
    return record


def _write_source_register(
    register_path: Path | str,
    record: dict,
    inputs: list[dict],
    run_timestamp: str,
) -> None:
    """
    Append/replace this product's row in the shortlist source register (CSV,
    the same column vocabulary as the other stages' registers, e.g.
    ``pipeline/scoring/report._write_source_register`` and
    ``DATA/geographic/metadata/source_register.csv``). Keyed by ``dataset_id``
    so a rerun replaces the row rather than appending a duplicate (11.3).
    """
    scored = next((i for i in inputs if i["name"] == "scored_table"), {})
    row = {
        "dataset_id": "optmining_shortlist",
        "category": "derived-shortlist",
        "custodian": "Opt-Mining (DERIVED — not custodial data)",
        "endpoint": scored.get("path", ""),
        "access_method": f"generated by pipeline stage `{config.STAGE_NAME}`",
        "format": "CSV + GeoJSON (EPSG:4326)",
        "native_crs": config.STORAGE_CRS,
        "licence": "derived from the licensed inputs listed in each source layer's register",
        "vintage": config.REGION_SLUG,
        "size_or_count": (
            f"{record['n_shortlisted']:,} rows (effective Top_N "
            f"{record['effective_top_n']})"
        ),
        "intended_use": (
            "Preliminary ranked shortlist (S1-11) — a screening starting point, "
            "not a site approval; input to S1-12 mapping/reporting"
        ),
        "notes": (
            f"derived product; CSV `{record['csv_file']}`, GeoJSON "
            f"`{record['geojson_file']}`; effective_top_n "
            f"{record['effective_top_n']}; generated {run_timestamp}"
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
