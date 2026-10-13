"""
Known-good / known-bad tests for the S2-02 input-contract checks 10–12
(``pipeline.validate._run_integrated_input_checks``) — the eligibility trio.

These tests pin the last three Check_Records the input-contract battery emits,
asserting the *structured* ``{name, expected, observed, passed}`` fields rather
than any log text (Requirement 13.4):

  * Check 10 — "eligible present, boolean, no nulls": a boolean, null-free
    ``eligible`` passes; an ``eligible`` retyped to int, or one carrying nulls,
    flips it to ``passed=False`` (Requirements 7.1, 7.2, 7.2A). The observed
    field always reports the concrete dtype and null count — never a silent
    pass;
  * Check 11 — "eligible/exclusion_reason consistent": a consistent table
    passes; an eligible cell that carries an exclusion reason flips it to
    ``passed=False`` (Requirements 7.3, 7.4). Observed reports the
    inconsistent-row count;
  * Check 12 — "At least one Eligible_Cell": a table with ≥1 eligible cell
    passes; a table with zero eligible cells flips it to ``passed=False``
    (Requirements 7.5, 7.6). Observed reports the Eligible_Cell count.

No-silent-pass discipline (Requirement 8.1 / 13.4): every asserted Check_Record
carries a non-empty ``expected`` and a non-empty ``observed`` alongside an
explicit boolean ``passed``.

Isolation (Requirement 13.2): each single-defect fixture is asserted to flip
*only* its target check. The exception is ``eligible_with_nulls`` — a null
``eligible`` is treated as ineligible by the consistency check (check 11) and a
formerly-eligible row that now reads ineligible but still has an empty
``exclusion_reason`` is by definition inconsistent, so that fixture legitimately
trips both check 10 and check 11. It is therefore used to pin check 10's
null-count reporting, while the strict single-check-isolation guarantee for
check 10 is pinned with ``eligible_as_int`` (int dtype, 0 nulls, still
consistent).

Hermeticity: check 1 (hash) inside the battery verifies against the
Baseline_Manifest whose destination ``freeze_baseline`` resolves from the
module-level ``pipeline.validate.DEFAULT_BASELINE_MANIFEST_PATH`` constant. Each
test ``monkeypatch``-redirects that constant to a path under ``tmp_path`` so the
real ``DATA/integration/metadata`` directory is never written, and every fixture
GeoPackage is a throwaway temp file passed via the ``integrated_path=`` override
— never the real S1-08 table.

Requirements: 7.2, 7.2A, 7.4, 7.6, 13.1, 13.2, 13.4.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import validate

from tests.integration.integrated_fixtures import (
    eligible_as_int,
    eligible_with_nulls,
    inconsistent_eligible_reason,
    make_integrated_fixture,
    write_fixture_gpkg,
    zero_eligible_cells,
)

# Check_Record `name` strings for checks 10–12 (must match validate.py exactly).
CHECK_10_ELIGIBLE_BOOL = "eligible present, boolean, no nulls"
CHECK_11_CONSISTENT = "eligible/exclusion_reason consistent"
CHECK_12_AT_LEAST_ONE = "At least one Eligible_Cell"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _by_name(checks: list[dict], name: str) -> dict:
    """Return the single Check_Record with ``name``, asserting it exists once."""
    matches = [c for c in checks if c["name"] == name]
    assert len(matches) == 1, (
        f"expected exactly one {name!r} Check_Record, found {len(matches)}: "
        f"{[c['name'] for c in checks]}"
    )
    return matches[0]


def _assert_populated(record: dict) -> None:
    """No silent pass: expected and observed are both non-empty, passed is bool."""
    assert isinstance(record["passed"], bool)
    assert record["expected"], f"empty expected for {record['name']!r}"
    assert record["observed"], f"empty observed for {record['name']!r}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def redirected_manifest(monkeypatch, tmp_path) -> Path:
    """
    Redirect ``DEFAULT_BASELINE_MANIFEST_PATH`` to a throwaway location under
    ``tmp_path`` so freezing the baseline never touches the real project
    metadata dir. ``freeze_baseline`` reads the module constant inside its body,
    so patching the attribute on the ``pipeline.validate`` module is sufficient.
    """
    manifest_path = tmp_path / "meta" / validate.BASELINE_MANIFEST_FILENAME
    monkeypatch.setattr(
        validate, "DEFAULT_BASELINE_MANIFEST_PATH", manifest_path, raising=True
    )
    return manifest_path


@pytest.fixture
def good_gpkg(tmp_path) -> Path:
    """A valid integrated-table GeoPackage written to a temp file."""
    return write_fixture_gpkg(make_integrated_fixture(), tmp_path, name="good.gpkg")


def _checks_for(gdf, tmp_path, name: str) -> list[dict]:
    """
    Write ``gdf`` to a temp GeoPackage, freeze the baseline over that same file
    (so the in-battery hash check passes and cannot mask the eligibility
    checks), and return the Check_Record list.
    """
    gpkg = write_fixture_gpkg(gdf, tmp_path, name=name)
    validate.freeze_baseline(gpkg, write=True)
    return validate._run_integrated_input_checks(integrated_path=gpkg)


# ---------------------------------------------------------------------------
# Known-good: checks 10–12 all pass with populated Check_Records
# ---------------------------------------------------------------------------


class TestKnownGoodChecks10to12:
    """A valid table passes checks 10–12 with no silent pass."""

    def test_all_three_pass_with_populated_records(
        self, redirected_manifest, good_gpkg
    ):
        validate.freeze_baseline(good_gpkg, write=True)

        checks = validate._run_integrated_input_checks(integrated_path=good_gpkg)

        bool_check = _by_name(checks, CHECK_10_ELIGIBLE_BOOL)
        consistent_check = _by_name(checks, CHECK_11_CONSISTENT)
        at_least_one_check = _by_name(checks, CHECK_12_AT_LEAST_ONE)

        for record in (bool_check, consistent_check, at_least_one_check):
            _assert_populated(record)
            assert record["passed"] is True, record

        # The passing observations report the concrete state, not just "ok".
        assert "0 nulls" in bool_check["observed"]
        assert "bool" in bool_check["observed"]
        assert "0 inconsistent rows" in consistent_check["observed"]
        # make_integrated_fixture() has n-1 eligible cells (>= 1).
        assert "eligible cells" in at_least_one_check["observed"]
        assert not at_least_one_check["observed"].startswith("0 ")


# ---------------------------------------------------------------------------
# Known-bad: check 10 (eligible dtype / nulls)
# ---------------------------------------------------------------------------


class TestEligibleDtypeFlipsCheck10:
    """A non-boolean or null-bearing ``eligible`` flips the dtype check."""

    def test_eligible_as_int_flips_check_10_only(
        self, redirected_manifest, tmp_path
    ):
        # int64 dtype, 0 nulls, still consistent → ONLY check 10 flips.
        checks = _checks_for(
            eligible_as_int(make_integrated_fixture()),
            tmp_path,
            name="eligible_int.gpkg",
        )

        bool_check = _by_name(checks, CHECK_10_ELIGIBLE_BOOL)
        _assert_populated(bool_check)
        assert bool_check["passed"] is False
        # Observed reports the concrete (non-boolean) dtype and the null count.
        assert "int" in bool_check["observed"]
        assert "0 nulls" in bool_check["observed"]

        # Isolation: consistency and population checks are unaffected.
        assert _by_name(checks, CHECK_11_CONSISTENT)["passed"] is True
        assert _by_name(checks, CHECK_12_AT_LEAST_ONE)["passed"] is True

    def test_eligible_with_nulls_flips_check_10_and_reports_null_count(
        self, redirected_manifest, tmp_path
    ):
        # eligible_with_nulls round-trips through the GeoPackage to a float64
        # column with 1 null, so check 10 fails on BOTH the non-boolean dtype
        # and the null count. A null (formerly-eligible) row that now reads
        # ineligible but keeps an empty exclusion_reason is also inconsistent,
        # so check 11 legitimately flips too — this fixture pins check 10's
        # null-count reporting, not single-check isolation.
        checks = _checks_for(
            eligible_with_nulls(make_integrated_fixture()),
            tmp_path,
            name="eligible_nulls.gpkg",
        )

        bool_check = _by_name(checks, CHECK_10_ELIGIBLE_BOOL)
        _assert_populated(bool_check)
        assert bool_check["passed"] is False
        # No silent pass: the observed field reports the null count explicitly.
        assert "1 nulls" in bool_check["observed"]


# ---------------------------------------------------------------------------
# Known-bad: check 11 (eligible / exclusion_reason consistency)
# ---------------------------------------------------------------------------


class TestInconsistentReasonFlipsCheck11:
    """An eligible cell carrying an exclusion reason flips the consistency check."""

    def test_inconsistent_flips_check_11_only(
        self, redirected_manifest, tmp_path
    ):
        # An eligible row gets an exclusion reason: inconsistent. eligible stays
        # boolean and >=1 cell remains eligible → ONLY check 11 flips.
        checks = _checks_for(
            inconsistent_eligible_reason(make_integrated_fixture()),
            tmp_path,
            name="inconsistent.gpkg",
        )

        consistent_check = _by_name(checks, CHECK_11_CONSISTENT)
        _assert_populated(consistent_check)
        assert consistent_check["passed"] is False
        # Observed reports the inconsistent-row count (non-zero, populated).
        assert "inconsistent rows" in consistent_check["observed"]
        assert not consistent_check["observed"].startswith("0 ")

        # Isolation: dtype and population checks are unaffected.
        assert _by_name(checks, CHECK_10_ELIGIBLE_BOOL)["passed"] is True
        assert _by_name(checks, CHECK_12_AT_LEAST_ONE)["passed"] is True


# ---------------------------------------------------------------------------
# Known-bad: check 12 (at least one Eligible_Cell)
# ---------------------------------------------------------------------------


class TestZeroEligibleFlipsCheck12:
    """A table with zero eligible cells flips the population check."""

    def test_zero_eligible_flips_check_12_only(
        self, redirected_manifest, tmp_path
    ):
        # Every cell ineligible, each with a matching reason (so consistency
        # still holds) and eligible stays boolean → ONLY check 12 flips.
        checks = _checks_for(
            zero_eligible_cells(make_integrated_fixture()),
            tmp_path,
            name="zero_eligible.gpkg",
        )

        at_least_one_check = _by_name(checks, CHECK_12_AT_LEAST_ONE)
        _assert_populated(at_least_one_check)
        assert at_least_one_check["passed"] is False
        # Observed reports the Eligible_Cell count explicitly (zero).
        assert at_least_one_check["observed"].startswith("0 ")
        assert "eligible cells" in at_least_one_check["observed"]

        # Isolation: dtype and consistency checks are unaffected.
        assert _by_name(checks, CHECK_10_ELIGIBLE_BOOL)["passed"] is True
        assert _by_name(checks, CHECK_11_CONSISTENT)["passed"] is True
