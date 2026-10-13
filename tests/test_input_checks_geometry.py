"""
Known-good / known-bad tests for the S2-02 input-contract checks 4–7 (task 4.4).

These tests drive the real check battery
``pipeline.validate._run_integrated_input_checks(integrated_path=...)`` against
the schema-driven fixtures in ``tests/integration/integrated_fixtures.py`` and
assert the *structured* Check_Record fields (``{name, expected, observed,
passed}``) — never log text.

Checks under test (the cell_id / coordinate / geometry / CRS group):

  * Check 4 — "cell_id non-null"
  * Check 5 — "cell_id unique"
  * Check 6 — "Coordinates valid and within the NSW analysis bounding box"
  * Check 7 — "Geometry valid and stored in the storage CRS"

For each known-bad fixture we assert that *only* the target check in this group
flips to ``passed=False`` while the other three stay ``passed=True``, and the
known-good fixture leaves all four ``passed=True``. Check 7's observed field is
asserted to always record the observed CRS (the ``crs=`` substring) even when
the CRS assertion passes.

Check 1 (baseline hash) is deliberately NOT asserted here: with no
Baseline_Manifest written, ``freeze_baseline`` in verify mode treats the
observed hash as its own reference, so check 1 passes trivially. This task only
covers checks 4–7. The fixture writer only writes a temp GeoPackage; nothing
here invokes ``freeze_baseline(write=True)``, so no manifest is created and the
tests stay hermetic.
"""

from __future__ import annotations

import pytest

gpd = pytest.importorskip("geopandas")

from pipeline.validate import _run_integrated_input_checks  # noqa: E402

from tests.integration import integrated_fixtures as fx  # noqa: E402


# ---------------------------------------------------------------------------
# The four Check_Record names in this group (must match validate.py exactly)
# ---------------------------------------------------------------------------

CHECK_4_CELL_ID_NON_NULL = "cell_id non-null"
CHECK_5_CELL_ID_UNIQUE = "cell_id unique"
CHECK_6_COORDINATES = "Coordinates valid and within the NSW analysis bounding box"
CHECK_7_GEOMETRY_CRS = "Geometry valid and stored in the storage CRS"

GROUP_CHECKS = (
    CHECK_4_CELL_ID_NON_NULL,
    CHECK_5_CELL_ID_UNIQUE,
    CHECK_6_COORDINATES,
    CHECK_7_GEOMETRY_CRS,
)


# ---------------------------------------------------------------------------
# Helpers — index the structured Check_Records by name
# ---------------------------------------------------------------------------


def _run_checks_on(gdf, tmp_path, name="fixture.gpkg") -> dict[str, dict]:
    """Write ``gdf`` to a temp GeoPackage, run the battery, index by check name.

    Returns a ``{name: Check_Record}`` mapping so tests read structured fields
    (``expected`` / ``observed`` / ``passed``) rather than parsing log text.
    """
    path = fx.write_fixture_gpkg(gdf, tmp_path, name=name)
    checks = _run_integrated_input_checks(integrated_path=path)
    by_name = {c["name"]: c for c in checks}
    # Every group check must be present on a table that exists (no silent skip).
    for check_name in GROUP_CHECKS:
        assert check_name in by_name, f"missing Check_Record: {check_name!r}"
    return by_name


def _assert_only_flipped(by_name: dict[str, dict], target: str) -> None:
    """Assert ``target`` failed and every other group check passed."""
    assert by_name[target]["passed"] is False, (
        f"expected {target!r} to fail; observed={by_name[target]['observed']!r}"
    )
    for check_name in GROUP_CHECKS:
        if check_name == target:
            continue
        assert by_name[check_name]["passed"] is True, (
            f"sibling check {check_name!r} unexpectedly failed; "
            f"observed={by_name[check_name]['observed']!r}"
        )


# ---------------------------------------------------------------------------
# Known-good fixture — all four group checks pass
# ---------------------------------------------------------------------------


class TestKnownGood:
    def test_all_group_checks_pass(self, tmp_path):
        by_name = _run_checks_on(fx.make_integrated_fixture(), tmp_path)
        for check_name in GROUP_CHECKS:
            assert by_name[check_name]["passed"] is True, check_name

    def test_check_records_are_populated(self, tmp_path):
        """No silent passes: expected/observed non-empty on every group check."""
        by_name = _run_checks_on(fx.make_integrated_fixture(), tmp_path)
        for check_name in GROUP_CHECKS:
            rec = by_name[check_name]
            assert rec["expected"], check_name
            assert rec["observed"], check_name

    def test_observed_crs_recorded_when_crs_assertion_passes(self, tmp_path):
        """Check 7 records the observed CRS even when the assertion passes.

        The good fixture is stored in EPSG:4326, so check 7 passes; its observed
        field must still carry the ``crs=`` substring (and the storage CRS
        string) so the CRS is reported regardless of pass/fail.
        """
        by_name = _run_checks_on(fx.make_integrated_fixture(), tmp_path)
        geom_check = by_name[CHECK_7_GEOMETRY_CRS]
        assert geom_check["passed"] is True
        assert "crs=" in geom_check["observed"], geom_check["observed"]
        assert "EPSG:4326" in geom_check["observed"], geom_check["observed"]


# ---------------------------------------------------------------------------
# Known-bad fixtures — each flips exactly its target check
# ---------------------------------------------------------------------------


class TestKnownBad:
    def test_null_cell_id_flips_check_4_only(self, tmp_path):
        bad = fx.null_cell_id(fx.make_integrated_fixture())
        by_name = _run_checks_on(bad, tmp_path, name="null_cell_id.gpkg")
        _assert_only_flipped(by_name, CHECK_4_CELL_ID_NON_NULL)
        # observed reports the null count (structured field, not log text):
        assert "1" in by_name[CHECK_4_CELL_ID_NON_NULL]["observed"]

    def test_duplicate_cell_id_flips_check_5_only(self, tmp_path):
        bad = fx.duplicate_cell_id(fx.make_integrated_fixture())
        by_name = _run_checks_on(bad, tmp_path, name="dup_cell_id.gpkg")
        _assert_only_flipped(by_name, CHECK_5_CELL_ID_UNIQUE)
        assert "1" in by_name[CHECK_5_CELL_ID_UNIQUE]["observed"]

    def test_out_of_range_centroid_lat_flips_check_6_only(self, tmp_path):
        bad = fx.out_of_range_centroid_lat(fx.make_integrated_fixture())
        by_name = _run_checks_on(bad, tmp_path, name="oor_lat.gpkg")
        _assert_only_flipped(by_name, CHECK_6_COORDINATES)
        assert "out-of-range" in by_name[CHECK_6_COORDINATES]["observed"]

    def test_invalid_geometry_flips_check_7_only(self, tmp_path):
        bad = fx.invalid_geometry(fx.make_integrated_fixture())
        by_name = _run_checks_on(bad, tmp_path, name="invalid_geom.gpkg")
        _assert_only_flipped(by_name, CHECK_7_GEOMETRY_CRS)
        # Geometry is invalid but the CRS is still EPSG:4326 and recorded:
        observed = by_name[CHECK_7_GEOMETRY_CRS]["observed"]
        assert "crs=" in observed, observed
        assert "invalid geometr" in observed, observed

    def test_non_epsg4326_crs_flips_check_7(self, tmp_path):
        """A non-EPSG:4326 CRS fails check 7 and records the observed CRS.

        Reprojecting to EPSG:3577 also moves the centroids out of the lat/lon
        envelope, so check 6 legitimately fails too; this test targets the CRS
        assertion of check 7 specifically (the observed CRS is recorded and is
        not EPSG:4326) rather than the only-one-flipped invariant.
        """
        bad = fx.invalid_geometry_crs(fx.make_integrated_fixture())
        by_name = _run_checks_on(bad, tmp_path, name="bad_crs.gpkg")
        geom_check = by_name[CHECK_7_GEOMETRY_CRS]
        assert geom_check["passed"] is False
        observed = geom_check["observed"]
        assert "crs=" in observed, observed
        assert "EPSG:4326" not in observed, observed
        # cell_id checks are unaffected by a reprojection:
        assert by_name[CHECK_4_CELL_ID_NON_NULL]["passed"] is True
        assert by_name[CHECK_5_CELL_ID_UNIQUE]["passed"] is True
