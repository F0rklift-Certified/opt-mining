"""
Property-based test for the S2-02 input-contract gate — Property 1 (P1):
No silent passes.

This test corresponds to numbered Property 1 in the feature design document and
runs at least 100 generated examples. It exercises the input-contract battery
``pipeline.validate._run_integrated_input_checks(integrated_path=...)`` over a
family of *present, valid-shape* integrated tables whose VALUES vary (wind_speed,
demand_proxy, slope_deg within/around their sanity bounds; eligible booleans;
cell_id strings; the number of cells, always >= 2). Regardless of the values
drawn, the gate must:

  (a) emit a Check_Record for every check with a NON-EMPTY ``expected``, a
      NON-EMPTY ``observed``, and an explicit boolean ``passed`` (Req 8.1);
  (b) emit a number of Check_Records that is INVARIANT to the values in the
      table — the count depends on the schema (number of scored/output
      columns), never on the data (Req 8.2, 8.4); and
  (c) never OMIT a check for a present table — the set of Check_Record names is
      exactly the schema-derived expected set (Req 8.2).

The expected count and the expected set of names are DERIVED FROM THE SCHEMA
CONSTANTS (``OUTPUT_COLUMNS`` / ``SCORED_FEATURE_COLUMNS`` / ``SANITY_RANGES``),
never hard-coded — so a schema change propagates into the assertion rather than
letting the test drift (KAN-38 cross-cutting note). For the standard Sprint 1
schema this is 28 records: 3 schema/hash + 4 cell/coord/geom + 8 range + 10
missing + 3 eligibility.

It lives in a dedicated module (its own per-property file, following the sibling
specs' convention, e.g. ``tests/shortlist/test_shortlist_select_p1.py``) so the
S2-02 property tests can grow file-by-file without concurrent-write conflicts.
This test does NOT modify ``pipeline/validate.py``.

Hermeticity: each generated table is written to a throwaway GeoPackage under a
per-example ``tempfile.TemporaryDirectory`` (never the function-scoped
``tmp_path`` fixture, which Hypothesis would reuse across examples). The
Baseline_Manifest destination — resolved by ``freeze_baseline`` from the module
constant ``pipeline.validate.DEFAULT_BASELINE_MANIFEST_PATH`` — is redirected to
that same temp directory for the duration of the test and restored afterwards,
so the real ``DATA/integration/metadata`` directory is never written. The gate
runs in verify mode (``freeze_baseline`` with no recorded manifest), which
writes nothing.

Validates: Requirements 8.1, 8.2, 8.4.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pipeline import validate
from pipeline.integration.config import SCORED_FEATURE_COLUMNS
from pipeline.integration.merge import OUTPUT_COLUMNS

from tests.integration.integrated_fixtures import (
    make_integrated_fixture,
    write_fixture_gpkg,
)

SETTINGS = settings(
    max_examples=100,
    deadline=None,
    # A fresh temp dir + GeoPackage write per example is deliberately not fast;
    # suppress the too-slow health check rather than weaken the property.
    suppress_health_check=[HealthCheck.too_slow],
)


# ---------------------------------------------------------------------------
# Schema-derived expectations (never hard-coded counts)
# ---------------------------------------------------------------------------
#
# The battery emits a FIXED set of Check_Records for a present table, driven by
# the schema — not by the data. We reconstruct that expected set of names from
# the same Schema_Authority constants the validator reads, so this stays correct
# if the schema changes.

_RANGED_COLUMNS = [c for c in SCORED_FEATURE_COLUMNS if c in validate.SANITY_RANGES]


def _expected_check_names() -> list[str]:
    """The exact Check_Record names a present, valid-shape table must emit.

    Mirrors the order the battery builds them, but the test only relies on the
    SET and COUNT of names, not their order.
    """
    names = [
        "Baseline hash matches the frozen reference",
        "Required columns present",
        "Scored feature columns present",
        "cell_id non-null",
        "cell_id unique",
        "Coordinates valid and within the NSW analysis bounding box",
        "Geometry valid and stored in the storage CRS",
    ]
    # Check 8 — one units/ranges record per scored column that HAS a bound.
    names += [f"Units/ranges within sanity bound: {c}" for c in _RANGED_COLUMNS]
    # Check 9 — one missing-value record per scored column (all of them).
    names += [f"Missing-value count: {c}" for c in SCORED_FEATURE_COLUMNS]
    # Checks 10–12 — eligibility.
    names += [
        "eligible present, boolean, no nulls",
        "eligible/exclusion_reason consistent",
        "At least one Eligible_Cell",
    ]
    return names


EXPECTED_NAMES = _expected_check_names()
EXPECTED_COUNT = len(EXPECTED_NAMES)


# ---------------------------------------------------------------------------
# Strategy — vary the VALUES of a valid-shape integrated table
# ---------------------------------------------------------------------------
#
# We start from the schema-faithful good fixture and mutate only cell VALUES,
# keeping the table well-formed (present, all columns, valid EPSG:4326 geometry,
# consistent eligible/exclusion_reason). The property must hold regardless of
# whether individual checks pass or fail, so the drawn values may push a column
# out of range, flip eligibility, or reuse a cell_id — the count and populated
# fields are what is invariant, not the pass/fail verdict.

# Draw wind_speed around its sanity bound [0, 25] — spanning below, inside, and
# above so some examples fail check 8 for wind_speed and some pass.
_wind_speed = st.floats(min_value=-5.0, max_value=40.0, allow_nan=False,
                        allow_infinity=False)
# demand_proxy around [0, 1].
_demand_proxy = st.floats(min_value=-0.5, max_value=1.5, allow_nan=False,
                          allow_infinity=False)
# slope_deg around [0, 90].
_slope_deg = st.floats(min_value=-10.0, max_value=120.0, allow_nan=False,
                       allow_infinity=False)


@st.composite
def _valued_tables(draw):
    """A present, valid-shape integrated table with varied cell VALUES.

    Returns a GeoDataFrame built from ``make_integrated_fixture`` (so every
    column, the geometry and the CRS are schema-faithful) with per-cell
    wind_speed / demand_proxy / slope_deg, per-cell ``eligible`` booleans, and
    per-cell ``cell_id`` strings redrawn. ``exclusion_reason`` is kept
    CONSISTENT with the drawn ``eligible`` flag (a reason iff ineligible) so the
    table shape stays valid; the property is about the gate's reporting
    discipline, not about forcing every check to pass.
    """
    n_cells = draw(st.integers(min_value=2, max_value=6))
    gdf = make_integrated_fixture(n_cells=n_cells).copy(deep=True)

    idx = list(gdf.index)

    # Vary the numeric scored values per row (only for columns present in this
    # schema; guard so a schema change that drops one does not KeyError).
    for col, strat in (
        ("wind_speed", _wind_speed),
        ("demand_proxy", _demand_proxy),
        ("slope_deg", _slope_deg),
    ):
        if col in gdf.columns:
            for i in idx:
                gdf.loc[i, col] = draw(strat)

    # Vary the cell_id strings (may collide → duplicates; may be distinct).
    for i in idx:
        gdf.loc[i, "cell_id"] = draw(
            st.text(alphabet="ABCDEF0123456789_", min_size=1, max_size=8)
        )

    # Vary eligibility per row, keeping exclusion_reason consistent so the
    # table stays well-formed. A row is eligible → no reason; ineligible → a
    # reason.
    eligible_flags = [draw(st.booleans()) for _ in idx]
    gdf["eligible"] = eligible_flags
    gdf["eligible"] = gdf["eligible"].astype(bool)
    for i, flag in zip(idx, eligible_flags):
        gdf.loc[i, "exclusion_reason"] = None if flag else "Slope exceeds 15\u00b0"

    return gdf


# ---------------------------------------------------------------------------
# The property
# ---------------------------------------------------------------------------


# Feature: s2-02-freeze-validate-integrated-dataset, Property 1: No silent passes
@SETTINGS
@given(gdf=_valued_tables())
def test_property_1_no_silent_passes(gdf):
    """For any present, valid-shape table with varying values: every check emits
    a populated Check_Record, the record count is invariant to the values, and
    no check name is omitted.
    """
    # Per-example temp dir (NOT the function-scoped tmp_path fixture, which
    # Hypothesis reuses across examples). The Baseline_Manifest destination is
    # redirected here too, so verify-mode freezing stays hermetic. Verify mode
    # with no recorded manifest writes nothing, but redirecting the constant
    # guarantees the real metadata dir is never touched even if that changes.
    #
    # We set/restore the module constant manually (rather than via the
    # function-scoped ``monkeypatch`` fixture, which Hypothesis does not reset
    # between examples) so each generated example is isolated.
    original_manifest_path = validate.DEFAULT_BASELINE_MANIFEST_PATH
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        manifest_path = tmp / "meta" / validate.BASELINE_MANIFEST_FILENAME
        validate.DEFAULT_BASELINE_MANIFEST_PATH = manifest_path
        try:
            gpkg = write_fixture_gpkg(gdf, tmp, name="valued.gpkg")
            checks = validate._run_integrated_input_checks(integrated_path=gpkg)
            _assert_property(checks)
        finally:
            validate.DEFAULT_BASELINE_MANIFEST_PATH = original_manifest_path


def _assert_property(checks: list[dict]) -> None:
    """The P1 assertions, factored out of the try/finally for clarity."""
    # (a) No silent pass: every Check_Record carries a non-empty expected,
    #     a non-empty observed, and an explicit boolean passed (Req 8.1).
    for record in checks:
        assert set(record) >= {"name", "expected", "observed", "passed"}, record
        assert isinstance(record["passed"], bool), record
        assert record["expected"] != "" and record["expected"] is not None, record
        assert record["observed"] != "" and record["observed"] is not None, record

    names = [c["name"] for c in checks]

    # (c) No check is omitted for a present table, and none is invented: the set
    #     of names equals the schema-derived expected set, and each appears
    #     exactly once (Req 8.2).
    assert sorted(names) == sorted(EXPECTED_NAMES), (
        f"check-name set differs from the schema-derived expectation: "
        f"missing={sorted(set(EXPECTED_NAMES) - set(names))}, "
        f"unexpected={sorted(set(names) - set(EXPECTED_NAMES))}"
    )
    assert len(names) == len(set(names)), f"duplicate check names: {names}"

    # (b) The record count is invariant to the VALUES in the table — it depends
    #     only on the schema (Req 8.2, 8.4).
    assert len(checks) == EXPECTED_COUNT, (
        f"expected {EXPECTED_COUNT} Check_Records (schema-derived), "
        f"got {len(checks)}"
    )
