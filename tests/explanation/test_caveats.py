"""
Tests for the pure S2-06b caveat builders (proxy + data-quality).

The builders are pure functions of (per-cell facts, templates): a proxy caveat
is emitted only for a participating proxy criterion; a data-quality note is
always emitted for the cell's confidence level, with reasons appended when
present.

Feature: s2-06b-excluded-explanations-proxy-quality-caveats
"""

from __future__ import annotations

from pipeline.explanation import config as ecfg
from pipeline.explanation.caveats import (
    CriterionParticipation,
    data_quality_notes,
    proxy_caveats,
)
from pipeline.explanation.templates import load_templates

T = load_templates()
DEMAND_PROXY_CAVEAT = T.phrases["demand_proxy"].proxy_caveat


# --- proxy caveats ----------------------------------------------------------


def test_proxy_caveat_emitted_for_participating_proxy():
    participation = (
        CriterionParticipation("wind_speed", True),
        CriterionParticipation("demand_proxy", True),
    )
    assert proxy_caveats(participation, T) == [DEMAND_PROXY_CAVEAT]


def test_proxy_caveat_absent_when_proxy_did_not_participate():
    participation = (
        CriterionParticipation("wind_speed", True),
        CriterionParticipation("demand_proxy", False),
    )
    assert proxy_caveats(participation, T) == []


def test_non_proxy_criteria_never_emit_a_caveat():
    participation = (
        CriterionParticipation("wind_speed", True),
        CriterionParticipation("slope_deg", True),
        CriterionParticipation("inside_rez", True),
    )
    assert proxy_caveats(participation, T) == []


def test_proxy_caveats_are_deterministic_and_ordered():
    participation = (
        CriterionParticipation("demand_proxy", True),
        CriterionParticipation("wind_speed", True),
    )
    assert proxy_caveats(participation, T) == proxy_caveats(participation, T)
    assert proxy_caveats(participation, T) == [DEMAND_PROXY_CAVEAT]


# --- data-quality notes -----------------------------------------------------


def test_high_confidence_still_surfaces_a_level_note():
    # 3C: transparency on every record, including high.
    assert data_quality_notes("high", "—", T) == ["Confidence: high"]


def test_low_confidence_appends_reasons():
    assert data_quality_notes("low", "two features interpolated", T) == [
        "Confidence: low — two features interpolated"
    ]


def test_no_notes_sentinel_yields_level_only():
    assert data_quality_notes("medium", ecfg.CONFIDENCE_NO_NOTES, T) == ["Confidence: medium"]


def test_empty_or_null_notes_yields_level_only():
    assert data_quality_notes("high", None, T) == ["Confidence: high"]
    assert data_quality_notes("high", "", T) == ["Confidence: high"]


def test_missing_level_renders_unknown_not_dropped():
    # A note is always emitted so the transparency guarantee holds; validation
    # then flags the unknown level rather than a silently missing note.
    assert data_quality_notes(None, None, T) == ["Confidence: unknown"]
