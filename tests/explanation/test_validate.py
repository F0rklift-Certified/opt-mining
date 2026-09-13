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
        },
        {
            ecfg.FIELD_CELL_ID: "NSW002",
            ecfg.FIELD_ELIGIBLE: True,
            ecfg.FIELD_HEADLINE: T.headline,
            ecfg.FIELD_POSITIVE_FACTORS: ["Near electrical demand (strong)"],
            ecfg.FIELD_WEAKNESSES: [],
        },
    ]


def test_clean_records_pass_all_checks():
    result = validate(_clean_records(), T, n_eligible_cells=2)
    assert result["failed"] == 0
    assert result["passed"] == result["total"]
    # Every check carries expected/observed/pass-fail.
    for c in result["checks"]:
        assert set(c) == {"name", "expected", "observed", "passed"}


def test_count_mismatch_fails_the_count_check():
    result = validate(_clean_records(), T, n_eligible_cells=3)
    assert "one explanation per eligible cell" in result["failed_names"]


def test_missing_headline_fails():
    recs = _clean_records()
    recs[0][ecfg.FIELD_HEADLINE] = "  "
    result = validate(recs, T, n_eligible_cells=2)
    assert "non-empty headline on every record" in result["failed_names"]


def test_empty_explanation_fails():
    # Neither a positive factor nor a weakness -> the explanation says nothing.
    recs = _clean_records()
    recs[0][ecfg.FIELD_POSITIVE_FACTORS] = []
    recs[0][ecfg.FIELD_WEAKNESSES] = []
    result = validate(recs, T, n_eligible_cells=2)
    assert "every record has at least one factor (positive or weakness)" in result["failed_names"]


def test_no_positive_but_has_weakness_passes():
    # An eligible-but-weak cell (worst on everything) has weaknesses and no
    # standout strength; that is a valid, informative explanation.
    recs = _clean_records()
    recs[0][ecfg.FIELD_POSITIVE_FACTORS] = []
    recs[0][ecfg.FIELD_WEAKNESSES] = ["Weaker wind resource (limited)"]
    result = validate(recs, T, n_eligible_cells=2)
    assert result["failed"] == 0


def test_not_eligible_record_fails():
    recs = _clean_records()
    recs[0][ecfg.FIELD_ELIGIBLE] = False
    result = validate(recs, T, n_eligible_cells=2)
    assert "every record eligible == true" in result["failed_names"]


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
