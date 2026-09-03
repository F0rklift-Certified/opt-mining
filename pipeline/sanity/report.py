"""
Report renderer, writer, and Results_Sidecar for the S1-12 sanity-check stage.

This module turns the structured results of the four plausibility checks into
the human-readable Validation_Report (Markdown) at
``outputs/sprint1_validation_report.md`` and, optionally, the machine-readable
Results_Sidecar (JSON) — both banner-stamped derived products, written
atomically via ``common.geo`` (Requirements 7, 10.2).

The stage is a REALITY CHECK, not a modelling step. The report presents each
automated check's expected-versus-observed pass/fail HONESTLY (no silent
passes — Requirement 11), states the Preliminary_Disclaimer and the
Analysis_Resolution wherever results are presented (7.5, 7.6), renders the
CRS transform log verbatim so no containment CRS is silently assumed (2.2,
3.5), and lists every recorded Anomaly in the "Issues for Sprint 2" section
(Requirement 6). Nothing here mutates any input or re-scores/re-ranks anything:
it reads the already-computed check results and writes two derived outputs.

Report section order (Requirement 7.2):
  header / run-metadata + disclaimers,
  1. Known Wind Farm Comparison,
  2. Exclusion Validation,
  3. Feature Value Spot-Checks,
  4. Score Distribution,
  5. Issues for Sprint 2,
  6. Conclusion (overall trustworthy-for-preliminary-screening assessment, 7.4).

Atomic-write discipline (Requirement 7.7, 7.9): both writers go through
``common.geo.atomic_write_text`` / ``atomic_write_json`` (tmp file +
``os.replace``), so a write failure leaves any pre-existing report/sidecar
unmodified and raises rather than leaving a partial or corrupt output.

Design reference: design.md §9 "Report renderer & writer" and §10 "Provenance".
(``record_provenance`` is authored in task 11.1 and appended below this file's
renderer/writer functions.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..common.geo import atomic_write_json, atomic_write_text, banner
from . import config
from .checks import (
    DistributionCheckResult,
    ExclusionCheckResult,
    SpotCheckResult,
    WindFarmCheckResult,
    MISSING_VALUE,
)
from .geo import CrsTransform
from .issues import ANOMALY_DATA_ISSUE, Anomaly

REPORT_PATH = config.REPORT_PATH
SIDECAR_PATH = config.SIDECAR_PATH


# ---------------------------------------------------------------------------
# Run metadata and the aggregate result the renderer consumes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunMetadata:
    """
    Run-level metadata rendered into the report header (Requirement 7.3).

    Carries the values the report header must record: the ``run_timestamp`` (a
    single UTC Run_Timestamp used across every artefact of the run), the
    ``pipeline_version`` (the identifier of the pipeline version that produced
    the run), the ``n_cells`` total grid cell count, and the ``n_eligible``
    Eligible_Cell count (7.3). ``resolved_shortlist_path`` records the concrete
    timestamped Shortlist file actually used (1.6). These are supplied by
    ``run()`` (task 12.1); the renderer is pure over them.
    """

    run_timestamp: str  # single UTC Run_Timestamp for the run
    pipeline_version: str  # Pipeline_Version identifier (7.3)
    n_cells: int  # total Analysis_Grid cell count (7.3)
    n_eligible: int  # Eligible_Cell count (7.3)
    resolved_shortlist_path: str  # the timestamped Shortlist actually used (1.6)


@dataclass(frozen=True)
class SanityResults:
    """
    The aggregate of the four check results, the collected issues, and the
    transform log the renderer/sidecar consume (Requirement 7).

    Bundles the structured results of Check 1 (``wind_farms``), Check 2
    (``exclusions``), Check 3 (``spot_values``), and Check 4 (``distribution``),
    the ordered list of Anomalies for the "Issues for Sprint 2" section
    (``issues``, from ``issues.collect_issues``), and the shared CRS
    ``transform_log`` the containment operations appended to (rendered verbatim
    so no containment CRS is silently assumed — 2.2, 3.5). ``run()`` assembles
    this and hands it to :func:`render_report` and :func:`write_sidecar`.
    """

    wind_farms: WindFarmCheckResult
    exclusions: ExclusionCheckResult
    spot_values: SpotCheckResult
    distribution: DistributionCheckResult
    issues: list[Anomaly] = field(default_factory=list)
    transform_log: list[CrsTransform] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Small rendering helpers
# ---------------------------------------------------------------------------


def _fmt_num(value, places: int = 4) -> str:
    """Render an optional number; an em dash for ``None`` rather than a fake."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return str(value)
    try:
        return f"{float(value):.{places}f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_cell(value) -> str:
    """Render a cell_id (or any scalar), an em dash for ``None`` (out-of-grid)."""
    return "—" if value is None else str(value)


def _fmt_value(value) -> str:
    """Render a feature value, keeping the MISSING sentinel visible (4.6)."""
    if value == MISSING_VALUE:
        return MISSING_VALUE
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _pass_label(passed: bool) -> str:
    """Explicit PASS / FAIL label so no outcome reads as a silent pass (11.x)."""
    return "PASS" if passed else "FAIL"


def _fmt_range(bounds: tuple, places: int = 4) -> str:
    """Render a ``(min, max)`` range; an em dash when either bound is ``None``."""
    lo, hi = bounds
    if lo is None or hi is None:
        return "—"
    return f"{lo:.{places}f} … {hi:.{places}f}"


def _render_transform_log(transform_log: list[CrsTransform]) -> list[str]:
    """
    Render the CRS transform-log line VERBATIM (Requirements 2.2, 3.5).

    Every containment operation appended its ``source -> target`` transform to
    the shared log; the report enumerates them so a reader can confirm the
    containment ran in one explicit CRS and no conversion was silent. Mirrors
    the "Transform log" line in ``infrastructure/features.py``.
    """
    lines: list[str] = []
    if not transform_log:
        lines.append(
            "- Transform log: (no containment transform recorded for this run)."
        )
        return lines
    parts = [f"{t.source} → {t.target} ({t.purpose})" for t in transform_log]
    lines.append("- Transform log: " + "; ".join(parts) + ".")
    return lines


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------


def _render_header(meta: RunMetadata) -> list[str]:
    """Header, banner, disclaimers, run metadata (Requirements 7.3, 7.5, 7.6)."""
    lines: list[str] = []
    add = lines.append

    add("# Sprint 1 Validation Report — Plausibility Sanity Check (S1-12)")
    add("")
    # Do-not-edit banner, identical wording to common.geo.banner (7.7).
    add(banner(config.STAGE_NAME).rstrip("\n"))
    add("")

    # Preliminary_Disclaimer (7.5) and Analysis_Resolution (7.6) FIRST so a
    # reader cannot miss that this is a plausibility screening output, not a
    # formal accuracy assessment and not a site approval.
    add("## Disclaimer")
    add("")
    add(f"> {config.PRELIMINARY_DISCLAIMER}")
    add("")
    add(f"**Analysis resolution:** {config.ANALYSIS_RESOLUTION}.")
    add(
        "The ~5 km cell is the coarsest unit of this analysis; every result "
        "below is reported at this resolution and cannot resolve within-cell "
        "variation. Results are indicative for preliminary screening only."
    )
    add("")

    # Run metadata (7.3): run date, Pipeline_Version, total cells, eligible cells.
    add("## Run metadata")
    add("")
    add(f"- **Run date (UTC):** {meta.run_timestamp}")
    add(f"- **Pipeline version:** `{meta.pipeline_version}`")
    add(f"- **Total grid cells:** {meta.n_cells:,}")
    add(f"- **Eligible (scored + ranked) cells:** {meta.n_eligible:,}")
    add(f"- **Resolved shortlist:** `{meta.resolved_shortlist_path}`")
    add("")
    return lines


def _render_wind_farms(result: WindFarmCheckResult) -> list[str]:
    """Section 1 — Known Wind Farm Comparison (Requirements 2, 11.2)."""
    lines: list[str] = []
    add = lines.append

    add("## 1. Known Wind Farm Comparison")
    add("")
    add(
        f"_{config.ANALYSIS_RESOLUTION} — each known wind farm is located to its "
        f"containing grid cell; its score/rank/percentile are read from that "
        f"cell._"
    )
    add("")
    add(f"**Expectation:** {result.expectation}")
    add("")

    outcome = result.outcome
    add(
        f"**Outcome ({_pass_label(outcome.passed)}):** "
        f"{outcome.observed} — expected: {outcome.expected}"
    )
    add("")

    add("| Wind Farm | Cell ID | Score | Rank | Percentile | Notes |")
    add("|---|---|---|---|---|---|")
    for row in result.rows:
        add(
            f"| {row.wind_farm} | {_fmt_cell(row.cell_id)} | "
            f"{_fmt_num(row.score)} | {_fmt_cell(row.rank)} | "
            f"{_fmt_num(row.percentile, 1)} | {row.notes} |"
        )
    add("")
    add(
        f"Known wind farms in the Upper_Quartile: "
        f"**{result.n_upper_quartile} of {result.n_known_farms}** "
        f"(proportion {result.proportion_upper_quartile:.3f})."
    )
    add("")
    lines.extend(_render_transform_log(result.transform_log))
    add("")
    return lines


def _render_exclusions(result: ExclusionCheckResult) -> list[str]:
    """Section 2 — Exclusion Validation (Requirements 3, 11.3)."""
    lines: list[str] = []
    add = lines.append

    add("## 2. Exclusion Validation")
    add("")
    add(
        f"_{config.ANALYSIS_RESOLUTION} — named urban centres and national "
        f"parks are located to their cells and asserted excluded; the grid is "
        f"asserted free of offshore/ocean cells._"
    )
    add("")
    add(
        f"**Assertions passed:** {result.n_passed} · "
        f"**failed:** {result.n_failed} · "
        f"**overall:** {_pass_label(result.all_passed)}"
    )
    add("")

    add("| Landmark | Kind | Lat | Lon | Cell ID | Expected | Observed | Result |")
    add("|---|---|---|---|---|---|---|---|")
    for a in result.assertions:
        add(
            f"| {a.landmark} | {a.kind} | {_fmt_num(a.lat, 4)} | "
            f"{_fmt_num(a.lon, 4)} | {_fmt_cell(a.cell_id)} | {a.expected} | "
            f"{a.observed} | {_pass_label(a.passed)} |"
        )
    add("")
    lines.extend(_render_transform_log(result.transform_log))
    add("")
    return lines


def _render_spot_values(result: SpotCheckResult) -> list[str]:
    """Section 3 — Feature Value Spot-Checks (Requirements 4, 4.4, 4.6)."""
    lines: list[str] = []
    add = lines.append

    add("## 3. Feature Value Spot-Checks")
    add("")
    add(
        f"_{config.ANALYSIS_RESOLUTION} — a deterministic sample of "
        f"{result.n_spot_cells} eligible cells spanning the score range. Each "
        f"value is recorded for INDEPENDENT verification by a reviewer against "
        f"the stated source; the `Discrepancy` column is intentionally blank._"
    )
    add("")

    if result.verify_sources:
        add("**Verify each value against:**")
        add("")
        for feature, source in result.verify_sources.items():
            add(f"- `{feature}` — {source}")
        add("")

    add(
        "| Cell ID | Band | Lat | Lon | Score | wind_speed | slope_deg | "
        "dist_transmission_km | protected | Discrepancy | Notes |"
    )
    add("|---|---|---|---|---|---|---|---|---|---|---|")
    for row in result.rows:
        add(
            f"| {_fmt_cell(row.cell_id)} | {row.score_band} | "
            f"{_fmt_num(row.centroid_lat, 4)} | {_fmt_num(row.centroid_lon, 4)} | "
            f"{_fmt_num(row.score)} | {_fmt_value(row.wind_speed)} | "
            f"{_fmt_value(row.slope_deg)} | {_fmt_value(row.dist_transmission_km)} | "
            f"{_fmt_value(row.protected)} | {row.discrepancy} | {row.notes} |"
        )
    add("")
    add(
        "_This check has no automated pass/fail: independent verification is a "
        "human-judgement item. A value recorded as "
        f"`{MISSING_VALUE}` was absent from the Integrated_Feature_Table and is "
        "reported honestly, never fabricated._"
    )
    add("")
    return lines


def _render_distribution(result: DistributionCheckResult) -> list[str]:
    """Section 4 — Score Distribution (Requirements 5, 11.4)."""
    lines: list[str] = []
    add = lines.append

    add("## 4. Score Distribution")
    add("")
    add(
        f"_{config.ANALYSIS_RESOLUTION} — statistics are computed over the "
        f"{result.n_eligible:,} Eligible_Cell population only; excluded cells "
        f"never dilute the distribution._"
    )
    add("")

    s = result.stats
    add("| Statistic | Value |")
    add("|---|---|")
    add(f"| min | {_fmt_num(s.get('min'))} |")
    add(f"| Q1 | {_fmt_num(s.get('q1'))} |")
    add(f"| median | {_fmt_num(s.get('median'))} |")
    add(f"| mean | {_fmt_num(s.get('mean'))} |")
    add(f"| Q3 | {_fmt_num(s.get('q3'))} |")
    add(f"| max | {_fmt_num(s.get('max'))} |")
    add(f"| std | {_fmt_num(s.get('std'))} |")
    add("")

    # Degenerate-clustering headline (5.2, 11.4) with the observed fraction.
    cluster = result.cluster_outcome
    add(
        f"**Degenerate clustering ({_pass_label(cluster.passed)}):** "
        f"{cluster.observed} — expected: {cluster.expected}"
    )
    add("")

    # Geographic diversity of the top-scoring cells (5.3).
    add("**Geographic diversity of top-scoring cells:**")
    add("")
    add(f"- Latitude range: {_fmt_range(result.top_lat_range)}")
    add(f"- Longitude range: {_fmt_range(result.top_lon_range)}")
    if result.rez_represented:
        add(f"- REZs represented: {', '.join(result.rez_represented)}")
    else:
        add("- REZs represented: — (no REZ column available)")
    add("")

    # Wind-versus-score correlation (5.4) — reported, never enforced.
    corr = result.correlation_outcome
    add(
        f"**Wind-versus-score correlation ({_pass_label(corr.passed)}):** "
        f"{corr.observed} — expected: {corr.expected}"
    )
    add(
        "_The correlation is REPORTED against the documented positive "
        "expectation, never enforced and never used to adjust the model._"
    )
    add("")

    for note in result.notes:
        add(f"- Note: {note}")
    if result.notes:
        add("")
    return lines


def _render_issues(issues: list[Anomaly]) -> list[str]:
    """Section 5 — Issues for Sprint 2 (Requirement 6)."""
    lines: list[str] = []
    add = lines.append

    add("## 5. Issues for Sprint 2")
    add("")
    if not issues:
        add(
            "No anomalies were surfaced by the automated checks for this run. "
            "(Absence of a recorded anomaly is not a formal accuracy guarantee — "
            "see the disclaimer.)"
        )
        add("")
        return lines

    add(
        "Every surprising or inconsistent result below is recorded HONESTLY "
        "with an investigation note distinguishing a suspected data issue from a "
        "legitimate model result. Nothing here was suppressed, and the model was "
        "never adjusted to make a check pass."
    )
    add("")
    add("| # | Check | Kind | Description | Investigation note |")
    add("|---|---|---|---|---|")
    for i, issue in enumerate(issues, start=1):
        kind_label = (
            "suspected data issue"
            if issue.kind == ANOMALY_DATA_ISSUE
            else "legitimate model result"
        )
        add(
            f"| {i} | {issue.check} | {kind_label} | {issue.description} | "
            f"{issue.investigation_note} |"
        )
    add("")
    return lines


def _render_conclusion(results: SanityResults, meta: RunMetadata) -> list[str]:
    """
    Section 6 — Conclusion (Requirement 7.4).

    States an overall trustworthy-for-preliminary-screening assessment based on
    the RECORDED check results: the Check 1 Upper_Quartile outcome, the Check 2
    exclusion outcome, and the Check 4 clustering/correlation outcomes, plus the
    count of anomalies logged for Sprint 2. The assessment is derived from the
    already-recorded pass/fail flags — it never re-runs a check and never
    adjusts the model.
    """
    lines: list[str] = []
    add = lines.append

    check1_pass = results.wind_farms.outcome.passed
    check2_pass = results.exclusions.all_passed
    check4_cluster_pass = results.distribution.cluster_outcome.passed
    check4_corr_pass = results.distribution.correlation_outcome.passed
    n_issues = len(results.issues)

    # The core automated checks that gate the headline assessment. Check 3 is a
    # human-judgement item with no automated pass/fail, so it does not gate.
    core_passed = check1_pass and check2_pass and check4_cluster_pass and check4_corr_pass

    add("## 6. Conclusion")
    add("")
    if core_passed and n_issues == 0:
        add(
            "**Overall assessment: the pipeline output is TRUSTWORTHY for "
            "preliminary screening at the stated resolution.** All automated "
            "plausibility checks passed and no anomalies were surfaced."
        )
    elif core_passed:
        add(
            "**Overall assessment: the pipeline output is BROADLY TRUSTWORTHY "
            "for preliminary screening at the stated resolution, with caveats.** "
            f"The automated plausibility checks passed, but {n_issues} "
            f"anomal{'y was' if n_issues == 1 else 'ies were'} surfaced and "
            "logged for Sprint 2 investigation (see section 5)."
        )
    else:
        add(
            "**Overall assessment: the pipeline output requires INVESTIGATION "
            "before it can be relied on for preliminary screening.** One or more "
            "automated plausibility checks did not pass; the failing results are "
            "recorded honestly in the sections above and, where systematic, "
            f"logged as {n_issues} Sprint 2 "
            f"issue{'' if n_issues == 1 else 's'} (see section 5). No result was "
            "suppressed and the model was not adjusted to force a pass."
        )
    add("")

    add("Per-check summary:")
    add("")
    add(
        f"- Check 1 (Known Wind Farm Comparison): {_pass_label(check1_pass)} — "
        f"{results.wind_farms.n_upper_quartile} of "
        f"{results.wind_farms.n_known_farms} known farms in the Upper_Quartile."
    )
    add(
        f"- Check 2 (Exclusion Validation): {_pass_label(check2_pass)} — "
        f"{results.exclusions.n_passed} passed, "
        f"{results.exclusions.n_failed} failed."
    )
    add(
        f"- Check 3 (Feature Value Spot-Checks): recorded "
        f"{results.spot_values.n_spot_cells} cells for independent verification "
        f"(human-judgement item; no automated pass/fail)."
    )
    add(
        f"- Check 4 (Score Distribution): clustering "
        f"{_pass_label(check4_cluster_pass)}, correlation "
        f"{_pass_label(check4_corr_pass)}."
    )
    add("")

    # Re-state the disclaimer at the conclusion so a reader who jumps to the
    # bottom still sees the screening/limitation caveat (7.5, 7.6).
    add(f"> {config.PRELIMINARY_DISCLAIMER}")
    add("")
    add(
        f"**Analysis resolution:** {config.ANALYSIS_RESOLUTION}. This is a "
        "preliminary-screening plausibility sanity check, not a formal accuracy "
        "assessment and not a site approval."
    )
    add("")
    return lines


# ---------------------------------------------------------------------------
# Public: render_report (Requirement 7.1–7.6)
# ---------------------------------------------------------------------------


def render_report(results: SanityResults, meta: RunMetadata) -> str:
    """
    Render the Markdown Validation_Report (Requirements 7.1–7.6).

    PURE: builds the report text from the run's already-computed check results
    and run metadata; performs no file I/O. :func:`write_report` stamps (via the
    banner already included) and atomically writes it.

    The report is banner-stamped via ``common.geo.banner("sanity")`` and its
    sections appear in the order required by 7.2:

      header / run-metadata (run date, Pipeline_Version, total cell count,
        eligible cell count) + disclaimers (7.3, 7.5, 7.6);
      1. Known Wind Farm Comparison (2, 11.2);
      2. Exclusion Validation (3, 11.3);
      3. Feature Value Spot-Checks (4);
      4. Score Distribution (5, 11.4);
      5. Issues for Sprint 2 (6);
      6. Conclusion — the overall trustworthy-for-preliminary-screening
        assessment based on the recorded results (7.4).

    The Preliminary_Disclaimer and the Analysis_Resolution (~5 km / 0.05 degree)
    with its limitations appear wherever results are presented (7.5, 7.6), and
    the CRS transform log is rendered VERBATIM from the check results'
    ``transform_log`` so no containment CRS is silently assumed (2.2, 3.5).

    Args:
        results: the aggregate of the four check results, the collected issues,
            and the shared transform log.
        meta: the run-level metadata for the report header.

    Returns:
        The full Validation_Report as a Markdown string ending in a newline.
    """
    lines: list[str] = []
    lines.extend(_render_header(meta))
    lines.extend(_render_wind_farms(results.wind_farms))
    lines.extend(_render_exclusions(results.exclusions))
    lines.extend(_render_spot_values(results.spot_values))
    lines.extend(_render_distribution(results.distribution))
    lines.extend(_render_issues(results.issues))
    lines.extend(_render_conclusion(results, meta))
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Public: write_report (Requirements 7.7, 7.9)
# ---------------------------------------------------------------------------


def write_report(text: str, path: Path = REPORT_PATH) -> None:
    """
    Atomically write the Validation_Report to ``path`` (Requirements 7.7, 7.9).

    Writes via ``common.geo.atomic_write_text`` (a sibling tmp file +
    ``os.replace``), so a re-run or an interrupt never leaves a partial or
    corrupt report: on any write failure the temporary file is cleaned up and
    any pre-existing report at ``path`` is left unmodified, and the error is
    raised (7.9). The report is already banner-stamped by :func:`render_report`
    (7.7).

    Args:
        text: the rendered report Markdown (from :func:`render_report`).
        path: destination; defaults to ``config.REPORT_PATH``
            (``outputs/sprint1_validation_report.md``).
    """
    atomic_write_text(Path(path), text)


# ---------------------------------------------------------------------------
# Sidecar serialisation (Requirements 7.8, 7.9, 10.2)
# ---------------------------------------------------------------------------


def _sidecar_wind_farms(result: WindFarmCheckResult) -> dict:
    """Serialise Check 1, including the Known_Wind_Farm_Comparison table (7.8)."""
    return {
        "expectation": result.expectation,
        "n_known_farms": result.n_known_farms,
        "n_upper_quartile": result.n_upper_quartile,
        "proportion_upper_quartile": result.proportion_upper_quartile,
        "outcome": _sidecar_outcome(result.outcome),
        "table": [
            {
                "wind_farm": row.wind_farm,
                "cell_id": row.cell_id,
                "score": row.score,
                "rank": row.rank,
                "percentile": row.percentile,
                "in_upper_quartile": row.in_upper_quartile,
                "notes": row.notes,
            }
            for row in result.rows
        ],
    }


def _sidecar_exclusions(result: ExclusionCheckResult) -> dict:
    """Serialise Check 2 assertions with their explicit pass/fail (11.3)."""
    return {
        "n_passed": result.n_passed,
        "n_failed": result.n_failed,
        "all_passed": result.all_passed,
        "assertions": [
            {
                "landmark": a.landmark,
                "kind": a.kind,
                "lat": a.lat,
                "lon": a.lon,
                "cell_id": a.cell_id,
                "expected": a.expected,
                "observed": a.observed,
                "passed": a.passed,
            }
            for a in result.assertions
        ],
    }


def _sidecar_spot_values(result: SpotCheckResult) -> dict:
    """Serialise Check 3 recorded feature values for the reviewer (4.3, 4.4)."""
    return {
        "n_spot_cells": result.n_spot_cells,
        "verify_sources": dict(result.verify_sources),
        "rows": [
            {
                "cell_id": row.cell_id,
                "centroid_lat": row.centroid_lat,
                "centroid_lon": row.centroid_lon,
                "score": row.score,
                "score_band": row.score_band,
                "wind_speed": row.wind_speed,
                "slope_deg": row.slope_deg,
                "dist_transmission_km": row.dist_transmission_km,
                "protected": row.protected,
                "discrepancy": row.discrepancy,
                "notes": row.notes,
            }
            for row in result.rows
        ],
    }


def _sidecar_distribution(result: DistributionCheckResult) -> dict:
    """Serialise Check 4 statistics + explicit pass/fail outcomes (11.4)."""
    return {
        "stats": dict(result.stats),
        "cluster_fraction": result.cluster_fraction,
        "cluster_degenerate": result.cluster_degenerate,
        "cluster_passed": result.cluster_passed,
        "cluster_outcome": _sidecar_outcome(result.cluster_outcome),
        "top_lat_range": list(result.top_lat_range),
        "top_lon_range": list(result.top_lon_range),
        "rez_represented": list(result.rez_represented),
        "wind_score_corr": result.wind_score_corr,
        "corr_method": result.corr_method,
        "corr_sign_expected_positive": result.corr_sign_expected_positive,
        "corr_passed": result.corr_passed,
        "correlation_outcome": _sidecar_outcome(result.correlation_outcome),
        "expectation": result.expectation,
        "n_eligible": result.n_eligible,
        "notes": list(result.notes),
    }


def _sidecar_outcome(outcome) -> dict:
    """Serialise a :class:`checks.CheckOutcome` (expected/observed/passed)."""
    return {
        "label": outcome.label,
        "expected": outcome.expected,
        "observed": outcome.observed,
        "passed": outcome.passed,
    }


def _sidecar_issues(issues: list[Anomaly]) -> list[dict]:
    """Serialise the collected Sprint-2 anomalies (Requirement 6)."""
    return [
        {
            "check": issue.check,
            "description": issue.description,
            "kind": issue.kind,
            "investigation_note": issue.investigation_note,
        }
        for issue in issues
    ]


def _sidecar_transform_log(transform_log: list[CrsTransform]) -> list[dict]:
    """Serialise the CRS transform log verbatim (2.2, 3.5)."""
    return [
        {"source": t.source, "target": t.target, "purpose": t.purpose}
        for t in transform_log
    ]


def build_sidecar(results: SanityResults, meta: RunMetadata | None = None) -> dict:
    """
    Build the machine-readable Results_Sidecar payload (Requirements 7.8, 10.2).

    Assembles the structured results of the automated checks — INCLUDING the
    Known_Wind_Farm_Comparison table (7.8) — into a JSON-serialisable dict,
    labelled a DERIVED PRODUCT so it is never mistaken for custodial source data
    (10.2). The optional ``meta`` records the run date, Pipeline_Version, and
    cell counts alongside the results so the sidecar is self-describing. PURE:
    builds and returns a dict; :func:`write_sidecar` writes it atomically.
    """
    payload: dict = {
        "product_type": "derived",
        "stage": config.STAGE_NAME,
        "description": (
            "Machine-readable results of the S1-12 preliminary-screening "
            "plausibility sanity check. Derived product; not custodial source "
            "data."
        ),
        "analysis_resolution": config.ANALYSIS_RESOLUTION,
        "preliminary_disclaimer": config.PRELIMINARY_DISCLAIMER,
    }
    if meta is not None:
        payload["run_metadata"] = {
            "run_timestamp": meta.run_timestamp,
            "pipeline_version": meta.pipeline_version,
            "n_cells": meta.n_cells,
            "n_eligible": meta.n_eligible,
            "resolved_shortlist_path": meta.resolved_shortlist_path,
        }
    payload["checks"] = {
        "known_wind_farm_comparison": _sidecar_wind_farms(results.wind_farms),
        "exclusion_validation": _sidecar_exclusions(results.exclusions),
        "feature_value_spot_checks": _sidecar_spot_values(results.spot_values),
        "score_distribution": _sidecar_distribution(results.distribution),
    }
    payload["issues_for_sprint_2"] = _sidecar_issues(results.issues)
    payload["transform_log"] = _sidecar_transform_log(results.transform_log)
    return payload


def write_sidecar(
    results: SanityResults,
    path: Path = SIDECAR_PATH,
    meta: RunMetadata | None = None,
) -> None:
    """
    Atomically write the machine-readable Results_Sidecar (7.8, 7.9, 10.2).

    Serialises the structured automated-check results — including the
    Known_Wind_Farm_Comparison table (7.8) — via :func:`build_sidecar` and
    writes them through ``common.geo.atomic_write_json`` (tmp file +
    ``os.replace``). The payload is labelled a DERIVED PRODUCT (``product_type =
    "derived"``) so it is not mistaken for custodial source data (10.2). On any
    write failure the temporary file is cleaned up, any pre-existing sidecar at
    ``path`` is left unmodified, and the error is raised (7.9).

    Args:
        results: the aggregate check results (the sidecar's payload).
        path: destination; defaults to ``config.SIDECAR_PATH``
            (``optmining_validation-results_2026_nsw.json`` under
            ``DATA/sanity/``, per the ``{source}_{dataset}_{year}_{region}``
            naming convention — 10.4).
        meta: optional run metadata recorded alongside the results.
    """
    atomic_write_json(Path(path), build_sidecar(results, meta))


# ---------------------------------------------------------------------------
# Provenance (Requirement 10) — record_provenance is authored in task 11.1 and
# appended below this line. It mirrors infrastructure/features.py: a
# DATA_PROVENANCE.md row, a sanity_manifest.json (SHA-256, bytes, UTC
# Run_Timestamp, generation params listing all five inputs), and a
# source_register entry, labelling the report + sidecar derived products.
# ---------------------------------------------------------------------------
