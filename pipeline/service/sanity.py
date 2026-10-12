"""
`get_sanity_check` — the sanity-surfacing Service_Operation (S3-08,
CONTRACT.md §4.8).

Surfaces the S1-12 sanity-check / validation result for the baseline engine
output so the Web_Application can render a sanity panel reachable from the app
shell (FR4/AC6). The operation reads the machine-readable Results_Sidecar the
S1-12 sanity stage (`pipeline/sanity/`) materialised and PROJECTS it verbatim
into the typed ``SanityCheck`` the contract defines — the per-check
expected/observed/pass-fail outcomes, the known-wind-farm comparison table, the
full contradictions list, the always-on model-not-trained caveat, and the
lineage `run_metadata` — all carried through UNCHANGED.

THE SERVICE PERFORMS NO SANITY CHECK. It re-runs no plausibility check,
re-derives no verdict and re-scores nothing; every pass/fail and every figure is
the sanity stage's own (CONTRACT.md §1, Requirement 2). This mirrors
`get_data_quality` end to end so the frontend can only call the service and
therefore performs no decision arithmetic (NFR1).

NO SILENT PASSES. Every check is surfaced — passing and failing alike — and an
ABSENT check block is projected as a VISIBLE honest failure (``passed=False``,
``observed="not available"``), never omitted: an omitted check would read as a
silent pass (AC6). The exclusion summary is a single synthesized check item read
from the sidecar's existing ``{n_passed, n_failed, all_passed}`` fields — pure
projection of the engine's own verdict, no new pass/fail arithmetic.

FAIL HONESTLY. When the Results_Sidecar is missing or unreadable, the loader
raises ``EngineOutputError`` naming the missing input rather than fabricating a
passing verdict (Requirement 7.3). A missing ``run_metadata`` degrades honestly
to empty lineage (the panel renders "lineage metadata unavailable"); it never
raises.
"""

from __future__ import annotations

from typing import Any

from .models import (
    SanityCheck,
    SanityCheckItem,
    SanityContradiction,
    SanityRunMetadata,
    SanityWindFarmRow,
)
from .runs import load_sanity_result


def _coerce_optional_number(value: Any) -> float | None:
    """Coerce a sidecar numeric field to ``float`` or ``None`` (never raise)."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_optional_int(value: Any) -> int | None:
    """Coerce a sidecar numeric field to ``int`` or ``None`` (never raise)."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _check_item(name: str, block: Any) -> SanityCheckItem:
    """
    Project one ``{label, expected, observed, passed}`` outcome block into a
    ``SanityCheckItem``.

    ``name`` is the fallback label used when the block carries none. An ABSENT
    block (``None`` / not a mapping) is projected as a visible honest failure —
    ``passed=False``, ``observed="not available"`` — never omitted (AC6).
    """
    if not isinstance(block, dict):
        return SanityCheckItem(
            name=name, expected="", observed="not available", passed=False
        )
    return SanityCheckItem(
        name=str(block.get("label", name)),
        expected=str(block.get("expected", "")),
        observed=str(block.get("observed", "")),
        passed=bool(block.get("passed", False)),
    )


def get_sanity_check() -> SanityCheck:
    """
    Return the S1-12 sanity-check / validation result for the baseline engine
    output (CONTRACT.md §4.8, FR2/FR4/FR5, AC3/AC6/AC7).

    Reads the materialised S1-12 Results_Sidecar and projects it VERBATIM into a
    ``SanityCheck``: the top-level ``caveat`` and ``preliminary_disclaimer``, the
    lineage ``run_metadata``, the six normalised check outcomes (the
    Upper_Quartile and top-band known-wind-farm outcomes, the synthesized
    exclusion summary, and the clustering/correlation/REZ distribution outcomes),
    the full ``issues_for_sprint_2`` contradictions list, the known-wind-farm
    comparison table, the top-ranked band N, and the per-landmark exclusion
    assertions. Every check is surfaced — passing and failing alike — so there
    are no silent passes (CONTRACT.md §5).

    NO RECOMPUTE. This function performs no sanity check, re-runs nothing and
    re-derives no verdict; the pass/fail flags and figures are the S1-12 sanity
    stage's own, carried through unchanged (CONTRACT.md §1, Requirement 2).

    Returns
    -------
    SanityCheck
        The projected sanity result.

    Raises
    ------
    EngineOutputError
        The Results_Sidecar is missing or unreadable — the error names the
        missing input rather than fabricating a passing verdict (Requirement
        7.3).
    """
    result = load_sanity_result()

    # Top-level first-class strings (AC3): the always-on caveat and the
    # preliminary-screening disclaimer, carried verbatim.
    caveat = str(result.get("caveat", ""))
    preliminary_disclaimer = str(result.get("preliminary_disclaimer", ""))

    # Lineage (FR5/AC7): project run_metadata into SanityRunMetadata. An absent
    # block or a missing field degrades to empty / None — never raises.
    meta_raw = result.get("run_metadata")
    meta = meta_raw if isinstance(meta_raw, dict) else {}
    run_metadata = SanityRunMetadata(
        run_timestamp=str(meta.get("run_timestamp", "")),
        pipeline_version=str(meta.get("pipeline_version", "")),
        resolved_shortlist_path=str(meta.get("resolved_shortlist_path", "")),
        n_cells=_coerce_optional_int(meta.get("n_cells")),
        n_eligible=_coerce_optional_int(meta.get("n_eligible")),
    )

    checks_block = result.get("checks")
    checks_block = checks_block if isinstance(checks_block, dict) else {}
    kwf = checks_block.get("known_wind_farm_comparison")
    kwf = kwf if isinstance(kwf, dict) else {}
    dist = checks_block.get("score_distribution")
    dist = dist if isinstance(dist, dict) else {}

    # The six normalised check items, IN ORDER (design §5). An absent block ->
    # passed=False/"not available" via _check_item (AC6).
    checks: list[SanityCheckItem] = [
        _check_item("Upper_Quartile count", kwf.get("outcome")),
        _check_item(
            "Known-wind-farm top-ranked band", kwf.get("top_band_outcome")
        ),
        _exclusion_summary_item(checks_block.get("exclusion_validation")),
        _check_item("Degenerate-clustering", dist.get("cluster_outcome")),
        _check_item("Wind-versus-score correlation", dist.get("correlation_outcome")),
        _check_item("REZ representation among top cells", dist.get("rez_outcome")),
    ]

    # Contradictions — the FULL issues_for_sprint_2 list (all four checks'
    # anomalies, a deliberate superset of AC10's Check-1 contradictions).
    contradictions = [
        SanityContradiction(
            check=str(issue.get("check", "")),
            description=str(issue.get("description", "")),
            kind=str(issue.get("kind", "")),
            investigation_note=str(issue.get("investigation_note", "")),
        )
        for issue in result.get("issues_for_sprint_2", [])
        if isinstance(issue, dict)
    ]

    # Known-wind-farm table rows, carried verbatim. The farm label is read from
    # `wind_farm` (the engine's resolved feature_name), NOT a `name` attribute.
    wind_farms = [
        SanityWindFarmRow(
            wind_farm=str(row.get("wind_farm", "")),
            cell_id=str(row.get("cell_id", "")),
            score=_coerce_optional_number(row.get("score")),
            rank=_coerce_optional_int(row.get("rank")),
            percentile=_coerce_optional_number(row.get("percentile")),
            in_upper_quartile=bool(row.get("in_upper_quartile", False)),
            notes=str(row.get("notes", "")),
        )
        for row in kwf.get("table", [])
        if isinstance(row, dict)
    ]

    top_band_n = _coerce_optional_int(kwf.get("top_band_n")) or 0

    # The per-landmark exclusion assertions, carried verbatim for the optional
    # sub-table.
    ev = checks_block.get("exclusion_validation")
    ev = ev if isinstance(ev, dict) else {}
    exclusion_assertions = [
        dict(a) for a in ev.get("assertions", []) if isinstance(a, dict)
    ]

    return SanityCheck(
        caveat=caveat,
        preliminary_disclaimer=preliminary_disclaimer,
        run_metadata=run_metadata,
        checks=checks,
        contradictions=contradictions,
        wind_farms=wind_farms,
        top_band_n=top_band_n,
        exclusion_assertions=exclusion_assertions,
    )


def _exclusion_summary_item(block: Any) -> SanityCheckItem:
    """
    Synthesize the single exclusion-validation summary ``SanityCheckItem``.

    `_sidecar_exclusions` emits ``{n_passed, n_failed, all_passed,
    assertions:[...]}`` with NO single ``outcome`` block, so the service reads
    those existing fields and composes one summary item (design §5). This is pure
    projection — ``all_passed`` is the engine's own verdict, the service invents
    no pass/fail arithmetic (NFR1). An absent block degrades to the honest
    "not available" failure (AC6).
    """
    if not isinstance(block, dict):
        return SanityCheckItem(
            name="Exclusion validation",
            expected="all documented landmarks excluded or absent from grid",
            observed="not available",
            passed=False,
        )
    n_passed = _coerce_optional_int(block.get("n_passed")) or 0
    n_failed = _coerce_optional_int(block.get("n_failed")) or 0
    return SanityCheckItem(
        name="Exclusion validation",
        expected="all documented landmarks excluded or absent from grid",
        observed=f"{n_passed} passed / {n_failed} failed",
        passed=bool(block.get("all_passed", False)),
    )
