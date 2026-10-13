"""
Known-good / known-bad tests for the S2-02 input-contract checks 8 and 9
(task 4.6).

These exercise the units/ranges and missing-value checks emitted by
``pipeline.validate._run_integrated_input_checks``:

  * Check 8 — ``f"Units/ranges within sanity bound: {column}"`` — ONE
    Check_Record per scored column that carries a ``SANITY_RANGES`` bound
    (8 of the 10 ``SCORED_FEATURE_COLUMNS``; ``dist_connection_km`` and
    ``land_use`` carry no bound and are not range-checked).
  * Check 9 — ``f"Missing-value count: {column}"`` — ONE Check_Record per
    ``SCORED_FEATURE_COLUMNS`` column (all 10).

The tests assert, against the real function output on a temp GeoPackage:

  * a good fixture leaves every check-8 record and every check-9 record
    ``passed=True`` with a populated (non-empty) observed count (no silent
    pass);
  * an out-of-range ``wind_speed`` (999) flips ONLY the ``wind_speed`` check-8
    record to ``passed=False`` with the observed out-of-range count reported,
    while leaving the value UNMODIFIED on disk (the validator never clamps or
    coerces);
  * an injected null in a scored column reports the correct missing-value count
    in that column's check-9 record and flips it to ``passed=False``.

Fixtures come from ``tests/integration/integrated_fixtures.py`` (schema-driven,
so a schema change propagates rather than drifting). Hermetic: the checks read
only the temp GeoPackage handed via ``integrated_path=`` and never write real
metadata.

Requirements: 5.4, 5.5, 6.1, 6.3, 13.1, 13.2.
"""

from __future__ import annotations

import numpy as np
import pytest

from pipeline.validate import _run_integrated_input_checks
from pipeline.integration.config import SCORED_FEATURE_COLUMNS
from pipeline.validate import SANITY_RANGES

from tests.integration.integrated_fixtures import (
    make_integrated_fixture,
    out_of_range_wind_speed,
    write_fixture_gpkg,
)

gpd = pytest.importorskip("geopandas")


# --- Check_Record name builders (mirror the exact strings in validate.py) ---

def _range_name(column: str) -> str:
    return f"Units/ranges within sanity bound: {column}"


def _missing_name(column: str) -> str:
    return f"Missing-value count: {column}"


def _find(checks: list[dict], name: str) -> dict:
    """Locate the single Check_Record with ``name`` in the returned list."""
    matches = [c for c in checks if c["name"] == name]
    assert len(matches) == 1, (
        f"expected exactly one Check_Record named {name!r}, found {len(matches)}"
    )
    return matches[0]


# Scored columns that carry a Sanity_Range (i.e. produce a check-8 record).
_RANGED_COLUMNS = [c for c in SCORED_FEATURE_COLUMNS if c in SANITY_RANGES]


def _run_on(gdf, tmp_path):
    """Write ``gdf`` to a temp GeoPackage and run the input checks over it."""
    path = write_fixture_gpkg(gdf, tmp_path)
    checks = _run_integrated_input_checks(integrated_path=path)
    return path, checks


# ---------------------------------------------------------------------------
# Known-good: all check-8 and check-9 records pass
# ---------------------------------------------------------------------------

class TestKnownGood:
    def test_all_check8_range_records_pass(self, tmp_path):
        gdf = make_integrated_fixture()
        _, checks = _run_on(gdf, tmp_path)

        # One check-8 record per ranged scored column (8 columns).
        for column in _RANGED_COLUMNS:
            record = _find(checks, _range_name(column))
            assert record["passed"] is True, (
                f"check 8 for {column} should pass on the good fixture: {record}"
            )
            assert record["observed"], f"observed must be populated for {column}"
            assert record["expected"], f"expected must be populated for {column}"

    def test_check8_emits_one_record_per_ranged_column(self, tmp_path):
        gdf = make_integrated_fixture()
        _, checks = _run_on(gdf, tmp_path)
        range_records = [c for c in checks if c["name"].startswith(
            "Units/ranges within sanity bound: ")]
        assert len(range_records) == len(_RANGED_COLUMNS) == 8

    def test_all_check9_missing_records_pass(self, tmp_path):
        gdf = make_integrated_fixture()
        _, checks = _run_on(gdf, tmp_path)

        # One check-9 record per scored column (all 10).
        for column in SCORED_FEATURE_COLUMNS:
            record = _find(checks, _missing_name(column))
            assert record["passed"] is True, (
                f"check 9 for {column} should pass on the good fixture: {record}"
            )
            assert "0 missing values" in record["observed"], (
                f"good fixture should report 0 missing for {column}: {record}"
            )

    def test_check9_emits_one_record_per_scored_column(self, tmp_path):
        gdf = make_integrated_fixture()
        _, checks = _run_on(gdf, tmp_path)
        missing_records = [c for c in checks if c["name"].startswith(
            "Missing-value count: ")]
        assert len(missing_records) == len(SCORED_FEATURE_COLUMNS) == 10


# ---------------------------------------------------------------------------
# Known-bad: out-of-range wind_speed flips check 8 and is not modified
# ---------------------------------------------------------------------------

class TestOutOfRangeWindSpeed:
    def test_wind_speed_range_check_fails(self, tmp_path):
        gdf = out_of_range_wind_speed(make_integrated_fixture(), value=999.0)
        _, checks = _run_on(gdf, tmp_path)

        record = _find(checks, _range_name("wind_speed"))
        assert record["passed"] is False, (
            f"out-of-range wind_speed must fail check 8: {record}"
        )
        # The observed out-of-range count is reported (one injected value).
        assert record["observed"] == "1 out-of-range values", (
            f"observed count should report the single out-of-range value: {record}"
        )

    def test_only_wind_speed_range_check_flips(self, tmp_path):
        gdf = out_of_range_wind_speed(make_integrated_fixture(), value=999.0)
        _, checks = _run_on(gdf, tmp_path)

        # Every OTHER ranged column's check 8 still passes — the defect is
        # localised to wind_speed.
        for column in _RANGED_COLUMNS:
            if column == "wind_speed":
                continue
            record = _find(checks, _range_name(column))
            assert record["passed"] is True, (
                f"unrelated check 8 for {column} should still pass: {record}"
            )

    def test_out_of_range_value_left_unmodified_on_disk(self, tmp_path):
        gdf = out_of_range_wind_speed(make_integrated_fixture(), value=999.0)
        path, _ = _run_on(gdf, tmp_path)

        # Re-read the written GeoPackage: the validator must NEVER clamp or
        # coerce out-of-range values — the 999.0 must still be present.
        reloaded = gpd.read_file(path)
        assert (reloaded["wind_speed"] == 999.0).any(), (
            "the out-of-range wind_speed (999.0) must remain unmodified on disk; "
            f"observed values: {sorted(reloaded['wind_speed'].tolist())}"
        )


# ---------------------------------------------------------------------------
# Known-bad: injected null in a scored column reports the check-9 count
# ---------------------------------------------------------------------------

class TestInjectedMissingValue:
    def test_injected_null_reports_missing_count(self, tmp_path):
        # No dedicated mutator for a check-9 null; inject one ourselves into a
        # scored column (slope_deg) and assert THAT column's check 9 reports it.
        column = "slope_deg"
        assert column in SCORED_FEATURE_COLUMNS

        gdf = make_integrated_fixture()
        gdf.loc[gdf.index[0], column] = np.nan
        _, checks = _run_on(gdf, tmp_path)

        record = _find(checks, _missing_name(column))
        assert record["passed"] is False, (
            f"an injected null must fail check 9 for {column}: {record}"
        )
        # The null was injected into the FIRST cell, which the fixture makes
        # eligible, so it is counted (check 9 scopes to the eligible population).
        assert record["observed"].startswith("1 missing values"), (
            f"check 9 should report exactly one missing value for {column}: {record}"
        )
        assert "eligible cells" in record["observed"], (
            f"check 9 observed should name the eligible-population scope: {record}"
        )

    def test_other_scored_columns_report_zero_missing(self, tmp_path):
        column = "slope_deg"
        gdf = make_integrated_fixture()
        gdf.loc[gdf.index[0], column] = np.nan
        _, checks = _run_on(gdf, tmp_path)

        # Every OTHER scored column still reports 0 missing and passes.
        for other in SCORED_FEATURE_COLUMNS:
            if other == column:
                continue
            record = _find(checks, _missing_name(other))
            assert record["passed"] is True, (
                f"unrelated check 9 for {other} should still pass: {record}"
            )
            assert "0 missing values" in record["observed"]


# ---------------------------------------------------------------------------
# Resolve the scored-criteria vs context split from the authoritative source
# (the scoring weights) so these tests track the real model, not a literal.
# ---------------------------------------------------------------------------

from pipeline.validate import _resolve_scored_criteria

_SCORED_CRITERIA, _ = _resolve_scored_criteria()
_CONTEXT_FEATURES = [c for c in SCORED_FEATURE_COLUMNS if c not in _SCORED_CRITERIA]
# A scored criterion that is also a plain numeric feature we can null out.
_A_CRITERION = "slope_deg"


# ---------------------------------------------------------------------------
# Eligible-population scope (Requirement 6.4): a null in an INELIGIBLE cell is
# not counted, because a ranking is only ever emitted from Eligible_Cells.
# ---------------------------------------------------------------------------

class TestMissingValueEligibleScope:
    def test_null_in_ineligible_cell_is_not_counted(self, tmp_path):
        # The fixture makes the LAST cell ineligible. A null there is outside the
        # ranked population, so check 9 must still pass and report 0 missing.
        # Use a scored CRITERION so the pass is due to eligible-scoping, not the
        # context-tier informational rule.
        column = _A_CRITERION
        assert column in _SCORED_CRITERIA

        gdf = make_integrated_fixture()
        ineligible_idx = gdf.index[-1]
        assert bool(gdf.loc[ineligible_idx, "eligible"]) is False, (
            "fixture contract: the last cell is ineligible"
        )
        gdf.loc[ineligible_idx, column] = np.nan
        _, checks = _run_on(gdf, tmp_path)

        record = _find(checks, _missing_name(column))
        assert record["passed"] is True, (
            f"a null in an ineligible cell must NOT fail check 9 for {column}: {record}"
        )
        assert record["observed"].startswith("0 missing values"), (
            f"ineligible-cell null must not be counted for {column}: {record}"
        )

    def test_null_in_eligible_cell_is_counted(self, tmp_path):
        # Same criterion, but the null is in an eligible cell -> counted, fails.
        column = _A_CRITERION
        gdf = make_integrated_fixture()
        eligible_idx = gdf.index[0]
        assert bool(gdf.loc[eligible_idx, "eligible"]) is True
        gdf.loc[eligible_idx, column] = np.nan
        _, checks = _run_on(gdf, tmp_path)

        record = _find(checks, _missing_name(column))
        assert record["passed"] is False, (
            f"a null in an eligible criterion cell must fail check 9 for {column}: {record}"
        )
        assert record["observed"].startswith("1 missing values")


# ---------------------------------------------------------------------------
# Scored-vs-context tier split (Requirement 6.5): a null in a CONTEXT feature
# is informational (does not fail); a null in a scored CRITERION fails. Every
# record names its tier.
# ---------------------------------------------------------------------------

class TestMissingValueTierSplit:
    def test_context_feature_null_is_informational_not_a_failure(self, tmp_path):
        # dist_connection_km is a context feature (tracked, but not a scored
        # criterion). A null among eligible cells is reported but does NOT fail.
        assert _CONTEXT_FEATURES, "expected at least one context feature"
        column = _CONTEXT_FEATURES[0]  # dist_connection_km in the current model

        gdf = make_integrated_fixture()
        gdf.loc[gdf.index[0], column] = np.nan  # eligible cell
        _, checks = _run_on(gdf, tmp_path)

        record = _find(checks, _missing_name(column))
        assert record["passed"] is True, (
            f"a context-feature null must NOT fail the gate: {record}"
        )
        assert record["observed"].startswith("1 missing values"), (
            f"the count must still be reported verbatim (no silent pass): {record}"
        )
        assert "context, informational" in record["observed"], (
            f"the record must name the context tier: {record}"
        )

    def test_criterion_null_fails_and_names_tier(self, tmp_path):
        column = _A_CRITERION
        gdf = make_integrated_fixture()
        gdf.loc[gdf.index[0], column] = np.nan  # eligible cell
        _, checks = _run_on(gdf, tmp_path)

        record = _find(checks, _missing_name(column))
        assert record["passed"] is False
        assert "scored criterion" in record["observed"], (
            f"the record must name the scored-criterion tier: {record}"
        )

    def test_every_scored_column_still_emits_a_record(self, tmp_path):
        # No silent omission: one record per SCORED_FEATURE_COLUMNS regardless
        # of tier.
        gdf = make_integrated_fixture()
        _, checks = _run_on(gdf, tmp_path)
        names = {c["name"] for c in checks}
        for column in SCORED_FEATURE_COLUMNS:
            assert _missing_name(column) in names, column
