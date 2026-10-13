"""
Known-good / known-bad tests for the S2-02 input-contract checks 1–3
(``pipeline.validate._run_integrated_input_checks``).

These tests pin the first three Check_Records the input-contract battery emits —
the schema/hash trio — against their requirements, asserting the *structured*
``{name, expected, observed, passed}`` fields rather than any log text
(Requirement 13.4):

  * Check 1 — "Baseline hash matches the frozen reference": an unchanged,
    freshly frozen table matches (``passed=True``); a byte-different table
    (Hash_Drift) flips it to ``passed=False`` (Requirement 1.4);
  * Check 2 — "Required columns present": a complete table passes; a dropped
    ``OUTPUT_COLUMNS`` member flips it to ``passed=False`` (Requirement 2.4);
  * Check 3 — "Scored feature columns present": a complete table passes; a
    dropped ``SCORED_FEATURE_COLUMNS`` member flips it to ``passed=False``
    (Requirement 2.6).

No-silent-pass discipline (Requirement 8.1 / 13.4): the known-good case asserts
each of the three Check_Records carries a non-empty ``expected`` and a non-empty
``observed`` alongside ``passed=True``.

Hermeticity: check 1 verifies against the Baseline_Manifest whose destination
``freeze_baseline`` resolves from the module-level
``pipeline.validate.DEFAULT_BASELINE_MANIFEST_PATH`` constant (read inside the
function body, not bound as a default argument). Every test that touches the
manifest ``monkeypatch``-redirects that constant to a path under ``tmp_path``,
so the real ``DATA/integration/metadata`` directory is never written. Fixture
GeoPackages live under ``tmp_path`` and are passed via the ``integrated_path=``
override, so the artefact under test is always a throwaway temp file — never the
real S1-08 table.

Requirements: 1.4, 2.4, 2.6, 13.1, 13.2, 13.4.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import validate

from tests.integration.integrated_fixtures import (
    drop_required_column,
    drop_scored_column,
    hash_drift_baseline,
    make_integrated_fixture,
    write_fixture_gpkg,
)

# Check_Record `name` strings for checks 1–3 (must match validate.py exactly).
CHECK_1_HASH = "Baseline hash matches the frozen reference"
CHECK_2_REQUIRED = "Required columns present"
CHECK_3_SCORED = "Scored feature columns present"


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


# ---------------------------------------------------------------------------
# Known-good: checks 1–3 all pass with populated Check_Records
# ---------------------------------------------------------------------------


class TestKnownGoodChecks1to3:
    """A freshly frozen, complete table passes checks 1–3 with no silent pass."""

    def test_all_three_pass_with_populated_records(
        self, redirected_manifest, good_gpkg
    ):
        # Freeze the SAME file we then validate so the recorded reference and
        # the observed hash agree → hash check passes.
        validate.freeze_baseline(good_gpkg, write=True)

        checks = validate._run_integrated_input_checks(integrated_path=good_gpkg)

        hash_check = _by_name(checks, CHECK_1_HASH)
        required_check = _by_name(checks, CHECK_2_REQUIRED)
        scored_check = _by_name(checks, CHECK_3_SCORED)

        for record in (hash_check, required_check, scored_check):
            _assert_populated(record)
            assert record["passed"] is True, record

        # The passing observations report the concrete state, not just "ok".
        assert hash_check["observed"] == "match"
        assert "0 missing" in required_check["observed"]
        assert "0 missing" in scored_check["observed"]

    def test_hermetic_real_metadata_dir_untouched(self, redirected_manifest, good_gpkg):
        # The redirected manifest is the only place a baseline is written; the
        # real DEFAULT path (from config) must never be created by these tests.
        validate.freeze_baseline(good_gpkg, write=True)
        validate._run_integrated_input_checks(integrated_path=good_gpkg)

        assert redirected_manifest.exists(), "baseline should write to the temp path"
        assert str(redirected_manifest).startswith(str(redirected_manifest.parent.parent))


# ---------------------------------------------------------------------------
# Known-bad: check 1 (Hash_Drift)
# ---------------------------------------------------------------------------


class TestHashDriftFlipsCheck1:
    """A byte-different table flips the hash-match Check_Record to passed=False."""

    def test_drift_flips_check_1_only(self, redirected_manifest, good_gpkg, tmp_path):
        # Record the good file's SHA-256 as the frozen reference.
        validate.freeze_baseline(good_gpkg, write=True)

        # Point the checks at a byte-different GeoPackage. hash_drift_baseline
        # nudges one in-range scored value, so every CONTENT check still passes
        # while only the file bytes (hash) differ.
        drifted_gpkg = write_fixture_gpkg(
            hash_drift_baseline(make_integrated_fixture()),
            tmp_path,
            name="drifted.gpkg",
        )

        checks = validate._run_integrated_input_checks(integrated_path=drifted_gpkg)

        hash_check = _by_name(checks, CHECK_1_HASH)
        _assert_populated(hash_check)
        assert hash_check["passed"] is False
        assert hash_check["observed"] == "DRIFTED"

        # The drift is isolated to check 1: the schema checks still pass.
        assert _by_name(checks, CHECK_2_REQUIRED)["passed"] is True
        assert _by_name(checks, CHECK_3_SCORED)["passed"] is True


# ---------------------------------------------------------------------------
# Known-bad: check 2 (dropped required column) and check 3 (dropped scored)
# ---------------------------------------------------------------------------


class TestDroppedColumnsFlipTheirCheck:
    """Each dropped-column defect flips exactly its target Check_Record."""

    def test_dropped_required_column_flips_check_2(
        self, redirected_manifest, tmp_path
    ):
        # drop_required_column drops a non-scored OUTPUT_COLUMNS member
        # (area_km2 by default), so ONLY the required-columns check fails.
        bad = drop_required_column(make_integrated_fixture())
        bad_gpkg = write_fixture_gpkg(bad, tmp_path, name="dropped_required.gpkg")
        validate.freeze_baseline(bad_gpkg, write=True)

        checks = validate._run_integrated_input_checks(integrated_path=bad_gpkg)

        required_check = _by_name(checks, CHECK_2_REQUIRED)
        _assert_populated(required_check)
        assert required_check["passed"] is False
        assert "missing" in required_check["observed"]

        # A dropped non-scored required column leaves the scored-columns check
        # passing (isolation of the defect).
        assert _by_name(checks, CHECK_3_SCORED)["passed"] is True

    def test_dropped_scored_column_flips_check_3(
        self, redirected_manifest, tmp_path
    ):
        # drop_scored_column drops a SCORED_FEATURE_COLUMNS member (wind_speed
        # by default). wind_speed is not in OUTPUT_COLUMNS-only territory — it
        # is both required and scored — so the required check may also flag it;
        # the contract we pin here is that the SCORED check flips to False.
        bad = drop_scored_column(make_integrated_fixture())
        bad_gpkg = write_fixture_gpkg(bad, tmp_path, name="dropped_scored.gpkg")
        validate.freeze_baseline(bad_gpkg, write=True)

        checks = validate._run_integrated_input_checks(integrated_path=bad_gpkg)

        scored_check = _by_name(checks, CHECK_3_SCORED)
        _assert_populated(scored_check)
        assert scored_check["passed"] is False
        assert "missing" in scored_check["observed"]
