"""
No-silent-passes validation tests for S2-06a.

A clean set of records passes every check; each seeded fault fails exactly the
check that owns it. Every check reports expected/observed/pass-fail.

Feature: s2-06a-explanation-engine-eligible-cells
"""

from __future__ import annotations

import copy

from pipeline.explanation import config as ecfg
from pipeline.explanation.templates import load_templates
from pipeline.explanation.validate import validate

T = load_templates()


DEMAND_PROXY_CAVEAT = T.phrases["demand_proxy"].proxy_caveat
DQ_HIGH = T.data_quality.level_template.format(level="high")
DQ_MEDIUM = T.data_quality.notes_template.format(
    level_note=T.data_quality.level_template.format(level="medium"),
    notes="one feature interpolated",
)


def _clean_records() -> list[dict]:
    return [
        {
            ecfg.FIELD_CELL_ID: "NSW001",
            ecfg.FIELD_ELIGIBLE: True,
            ecfg.FIELD_HEADLINE: T.headline,
            ecfg.FIELD_POSITIVE_FACTORS: [
                "Strong wind resource (top decile)",
                "Inside a Renewable Energy Zone (present)",
            ],
            ecfg.FIELD_WEAKNESSES: ["Distant from transmission (limited)"],
            ecfg.FIELD_PROXY_CAVEATS: [DEMAND_PROXY_CAVEAT],
            ecfg.FIELD_DATA_QUALITY_NOTES: [DQ_HIGH],
        },
        {
            ecfg.FIELD_CELL_ID: "NSW002",
            ecfg.FIELD_ELIGIBLE: True,
            ecfg.FIELD_HEADLINE: T.headline,
            ecfg.FIELD_POSITIVE_FACTORS: ["Near electrical demand (strong)"],
            ecfg.FIELD_WEAKNESSES: [],
            ecfg.FIELD_PROXY_CAVEATS: [DEMAND_PROXY_CAVEAT],
            ecfg.FIELD_DATA_QUALITY_NOTES: [DQ_HIGH],
        },
    ]


def _excluded_record() -> dict:
    return {
        ecfg.FIELD_CELL_ID: "NSW003",
        ecfg.FIELD_ELIGIBLE: False,
        ecfg.FIELD_EXCLUSION_REASONS: [
            {"code": "protected_area", "text": "Protected area: Test NP"}
        ],
        ecfg.FIELD_PROXY_CAVEATS: [DEMAND_PROXY_CAVEAT],
        ecfg.FIELD_DATA_QUALITY_NOTES: [DQ_MEDIUM],
    }


def test_clean_records_pass_all_checks():
    recs = _clean_records() + [_excluded_record()]
    result = validate(recs, T, n_eligible_cells=2, n_excluded_cells=1)
    assert result["failed"] == 0
    assert result["passed"] == result["total"]
    # Every check carries expected/observed/pass-fail.
    for c in result["checks"]:
        assert set(c) == {"name", "expected", "observed", "passed"}


def test_count_mismatch_fails_the_count_check():
    result = validate(_clean_records(), T, n_eligible_cells=3)
    assert "one explanation per cell (eligible + excluded)" in result["failed_names"]


def test_missing_headline_fails():
    recs = _clean_records()
    recs[0][ecfg.FIELD_HEADLINE] = "  "
    result = validate(recs, T, n_eligible_cells=2)
    assert "non-empty headline on every eligible record" in result["failed_names"]


def test_empty_explanation_fails():
    # Neither a positive factor nor a weakness -> the explanation says nothing.
    recs = _clean_records()
    recs[0][ecfg.FIELD_POSITIVE_FACTORS] = []
    recs[0][ecfg.FIELD_WEAKNESSES] = []
    result = validate(recs, T, n_eligible_cells=2)
    assert (
        "every eligible record has at least one factor (positive or weakness)"
        in result["failed_names"]
    )


def test_no_positive_but_has_weakness_passes():
    # An eligible-but-weak cell (worst on everything) has weaknesses and no
    # standout strength; that is a valid, informative explanation.
    recs = _clean_records()
    recs[0][ecfg.FIELD_POSITIVE_FACTORS] = []
    recs[0][ecfg.FIELD_WEAKNESSES] = ["Weaker wind resource (limited)"]
    result = validate(recs, T, n_eligible_cells=2)
    assert result["failed"] == 0


def test_eligible_flagged_excluded_fails_partition():
    recs = _clean_records()
    recs[0][ecfg.FIELD_ELIGIBLE] = False
    result = validate(recs, T, n_eligible_cells=2)
    assert "eligible/excluded records match the cell counts" in result["failed_names"]


def test_unknown_criterion_phrase_fails():
    recs = _clean_records()
    recs[0][ecfg.FIELD_POSITIVE_FACTORS] = ["Invented factor nobody configured (top decile)"]
    result = validate(recs, T, n_eligible_cells=2)
    assert "every factor references a configured criterion" in result["failed_names"]


def test_banned_superlative_fails():
    recs = _clean_records()
    recs[0][ecfg.FIELD_HEADLINE] = "The best site under the assumptions"
    result = validate(recs, T, n_eligible_cells=2)
    assert "no non-screening superlative in any explanation" in result["failed_names"]


# --- S2-06b checks ----------------------------------------------------------


def test_excluded_missing_reasons_fails():
    rec = _excluded_record()
    rec[ecfg.FIELD_EXCLUSION_REASONS] = []
    result = validate(
        _clean_records() + [rec], T, n_eligible_cells=2, n_excluded_cells=1
    )
    assert (
        "every excluded record has a non-empty {code, text} reason list"
        in result["failed_names"]
    )


def test_excluded_reason_with_empty_text_fails():
    rec = _excluded_record()
    rec[ecfg.FIELD_EXCLUSION_REASONS] = [{"code": "protected_area", "text": "  "}]
    result = validate(
        _clean_records() + [rec], T, n_eligible_cells=2, n_excluded_cells=1
    )
    assert (
        "every excluded record has a non-empty {code, text} reason list"
        in result["failed_names"]
    )


def test_eligible_carrying_reasons_fails():
    recs = _clean_records()
    recs[0][ecfg.FIELD_EXCLUSION_REASONS] = [{"code": "x", "text": "y"}]
    result = validate(recs, T, n_eligible_cells=2)
    assert "no eligible record carries exclusion reasons" in result["failed_names"]


def test_missing_data_quality_note_fails():
    recs = _clean_records()
    recs[0][ecfg.FIELD_DATA_QUALITY_NOTES] = []
    result = validate(recs, T, n_eligible_cells=2)
    assert (
        "exactly one data-quality note with a known level on every record"
        in result["failed_names"]
    )


def test_unknown_confidence_level_fails():
    recs = _clean_records()
    recs[0][ecfg.FIELD_DATA_QUALITY_NOTES] = ["Confidence: bogus"]
    result = validate(recs, T, n_eligible_cells=2)
    assert (
        "exactly one data-quality note with a known level on every record"
        in result["failed_names"]
    )


def test_unrecognised_proxy_caveat_fails():
    recs = _clean_records()
    recs[0][ecfg.FIELD_PROXY_CAVEATS] = ["Some caveat nobody configured"]
    result = validate(recs, T, n_eligible_cells=2)
    assert "every proxy caveat is a configured proxy-variable caveat" in result["failed_names"]


def test_banned_superlative_in_caveat_fails():
    recs = _clean_records()
    recs[0][ecfg.FIELD_DATA_QUALITY_NOTES] = ["Confidence: high for the best site"]
    result = validate(recs, T, n_eligible_cells=2)
    assert "no non-screening superlative in any explanation" in result["failed_names"]
