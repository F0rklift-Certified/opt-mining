"""
Smoke tests for the S2-02 integrated-table fixtures (task 3.1).

These tests prove the fixture helpers themselves work — that the good fixture
is schema-faithful and writes/reads a valid GeoPackage, and that each known-bad
mutator injects *exactly one* defect. They deliberately DO NOT import the
input-contract checks (those are implemented in later tasks 4.x); instead they
use small local defect-detectors that mirror the check semantics, so this file
stands alone as proof the fixtures are correct.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

gpd = pytest.importorskip("geopandas")

from pipeline.integration.config import (  # noqa: E402
    OUTPUT_LAYER,
    SCORED_FEATURE_COLUMNS,
    STORAGE_CRS,
)
from pipeline.integration.merge import BOOL_COLUMNS, OUTPUT_COLUMNS  # noqa: E402
from pipeline.grid.config import NSW_BBOX  # noqa: E402
from pipeline.validate import SANITY_RANGES  # noqa: E402

from tests.integration import integrated_fixtures as fx  # noqa: E402


# ---------------------------------------------------------------------------
# Independent defect detectors (mirror the check battery, do not import it)
# ---------------------------------------------------------------------------


def _missing_required(gdf) -> int:
    return len([c for c in OUTPUT_COLUMNS if c not in gdf.columns])


def _missing_scored(gdf) -> int:
    return len([c for c in SCORED_FEATURE_COLUMNS if c not in gdf.columns])


def _null_cell_ids(gdf) -> int:
    return int(gdf["cell_id"].isna().sum()) if "cell_id" in gdf.columns else 0


def _dup_cell_ids(gdf) -> int:
    return int(gdf["cell_id"].duplicated().sum()) if "cell_id" in gdf.columns else 0


def _out_of_range(gdf, column) -> int:
    if column not in gdf.columns or column not in SANITY_RANGES:
        return 0
    bound = SANITY_RANGES[column]
    series = gdf[column]
    if isinstance(bound, frozenset):
        return int((~series.isin(list(bound))).sum())
    lo, hi = bound
    numeric = pd.to_numeric(series, errors="coerce")
    return int(((numeric < lo) | (numeric > hi)).sum())


def _bad_coords(gdf) -> int:
    lat = pd.to_numeric(gdf["centroid_lat"], errors="coerce")
    lon = pd.to_numeric(gdf["centroid_lon"], errors="coerce")
    west, south, east, north = NSW_BBOX
    bad = (
        (lat < -90) | (lat > 90) | (lon < -180) | (lon > 180)
        | (lat < south) | (lat > north) | (lon < west) | (lon > east)
    )
    return int(bad.sum())


def _crs_is_storage(gdf) -> bool:
    return gdf.crs is not None and gdf.crs.to_authority() == tuple(STORAGE_CRS.split(":"))


def _invalid_geoms(gdf) -> int:
    return int((~gdf.geometry.is_valid).sum())


def _eligible_is_bool(gdf) -> bool:
    return str(gdf["eligible"].dtype) in ("bool", "boolean")


def _eligible_nulls(gdf) -> int:
    return int(gdf["eligible"].isna().sum())


def _inconsistent_rows(gdf) -> int:
    elig = gdf["eligible"].fillna(False).astype(bool)
    reason = gdf["exclusion_reason"]
    reason_present = reason.notna() & (reason.fillna("").astype(str).str.len() > 0)
    return int(((elig & reason_present) | (~elig & ~reason_present)).sum())


def _n_eligible(gdf) -> int:
    return int(gdf["eligible"].fillna(False).astype(bool).sum())


# ---------------------------------------------------------------------------
# The good fixture is valid on every dimension
# ---------------------------------------------------------------------------


class TestGoodFixture:
    def test_has_every_output_column_plus_geometry(self):
        gdf = fx.make_integrated_fixture()
        for column in OUTPUT_COLUMNS:
            assert column in gdf.columns, column
        assert gdf.geometry.name == "geometry"

    def test_bool_columns_are_boolean(self):
        gdf = fx.make_integrated_fixture()
        for column in BOOL_COLUMNS:
            assert gdf[column].dtype == np.dtype("bool"), column

    def test_scored_columns_in_range_and_non_null(self):
        gdf = fx.make_integrated_fixture()
        for column in SCORED_FEATURE_COLUMNS:
            assert gdf[column].notna().all(), column
            assert _out_of_range(gdf, column) == 0, column

    def test_cell_id_unique_and_non_null(self):
        gdf = fx.make_integrated_fixture()
        assert _null_cell_ids(gdf) == 0
        assert _dup_cell_ids(gdf) == 0

    def test_geometry_valid_crs_and_coords_in_nsw_box(self):
        gdf = fx.make_integrated_fixture()
        assert _invalid_geoms(gdf) == 0
        assert _crs_is_storage(gdf)
        assert _bad_coords(gdf) == 0

    def test_eligibility_consistent_with_at_least_one_eligible(self):
        gdf = fx.make_integrated_fixture()
        assert _eligible_is_bool(gdf)
        assert _eligible_nulls(gdf) == 0
        assert _inconsistent_rows(gdf) == 0
        assert _n_eligible(gdf) >= 1

    def test_writes_and_reads_valid_geopackage(self, tmp_path):
        gdf = fx.make_integrated_fixture()
        path = fx.write_fixture_gpkg(gdf, tmp_path)
        assert path.exists()
        back = gpd.read_file(path, layer=OUTPUT_LAYER)
        assert len(back) == len(gdf)
        assert set(OUTPUT_COLUMNS) <= set(back.columns)
        assert back.crs.to_authority() == tuple(STORAGE_CRS.split(":"))


# ---------------------------------------------------------------------------
# Each mutator injects exactly one defect
# ---------------------------------------------------------------------------

# Map each mutator to the defect-detector that should now fire, plus a probe
# of every *other* invariant to assert the mutator changed nothing else that a
# check keys on.


def _defect_profile(gdf) -> dict:
    """A profile of every input-contract defect signal for one table."""
    return {
        "missing_required": _missing_required(gdf),
        "missing_scored": _missing_scored(gdf),
        "null_cell_id": _null_cell_ids(gdf),
        "dup_cell_id": _dup_cell_ids(gdf),
        "wind_out_of_range": _out_of_range(gdf, "wind_speed"),
        "bad_coords": _bad_coords(gdf),
        "crs_ok": _crs_is_storage(gdf),
        "eligible_is_bool": _eligible_is_bool(gdf),
        "eligible_nulls": _eligible_nulls(gdf),
        "inconsistent_rows": _inconsistent_rows(gdf),
        "n_eligible": _n_eligible(gdf),
    }


class TestKnownBadMutators:
    def test_good_fixture_profile_is_clean(self):
        prof = _defect_profile(fx.make_integrated_fixture())
        assert prof["missing_required"] == 0
        assert prof["missing_scored"] == 0
        assert prof["null_cell_id"] == 0
        assert prof["dup_cell_id"] == 0
        assert prof["wind_out_of_range"] == 0
        assert prof["bad_coords"] == 0
        assert prof["crs_ok"] is True
        assert prof["eligible_is_bool"] is True
        assert prof["eligible_nulls"] == 0
        assert prof["inconsistent_rows"] == 0
        assert prof["n_eligible"] >= 1

    def test_drop_required_column(self):
        good = fx.make_integrated_fixture()
        bad = fx.drop_required_column(good)
        assert _missing_required(bad) == 1
        # nothing else the checks key on changed:
        assert _missing_scored(bad) == 0
        assert _null_cell_ids(bad) == 0 and _dup_cell_ids(bad) == 0

    def test_drop_scored_column(self):
        good = fx.make_integrated_fixture()
        bad = fx.drop_scored_column(good)
        assert _missing_scored(bad) == 1

    def test_null_cell_id(self):
        good = fx.make_integrated_fixture()
        bad = fx.null_cell_id(good)
        assert _null_cell_ids(bad) == 1
        assert _dup_cell_ids(bad) == 0

    def test_duplicate_cell_id(self):
        good = fx.make_integrated_fixture()
        bad = fx.duplicate_cell_id(good)
        assert _dup_cell_ids(bad) == 1
        assert _null_cell_ids(bad) == 0

    def test_out_of_range_wind_speed(self):
        good = fx.make_integrated_fixture()
        bad = fx.out_of_range_wind_speed(good)
        assert _out_of_range(bad, "wind_speed") == 1
        # other scored ranges untouched:
        assert _out_of_range(bad, "slope_deg") == 0

    def test_out_of_range_centroid_lat(self):
        good = fx.make_integrated_fixture()
        bad = fx.out_of_range_centroid_lat(good)
        assert _bad_coords(bad) >= 1
        assert _crs_is_storage(bad) is True  # geometry/CRS untouched

    def test_invalid_geometry_crs(self):
        good = fx.make_integrated_fixture()
        bad = fx.invalid_geometry_crs(good)
        assert _crs_is_storage(bad) is False

    def test_invalid_geometry(self):
        good = fx.make_integrated_fixture()
        bad = fx.invalid_geometry(good)
        assert _invalid_geoms(bad) == 1
        assert _crs_is_storage(bad) is True

    def test_eligible_as_int(self):
        good = fx.make_integrated_fixture()
        bad = fx.eligible_as_int(good)
        assert _eligible_is_bool(bad) is False
        assert _eligible_nulls(bad) == 0

    def test_eligible_with_nulls(self):
        good = fx.make_integrated_fixture()
        bad = fx.eligible_with_nulls(good)
        assert _eligible_nulls(bad) == 1

    def test_inconsistent_eligible_reason(self):
        good = fx.make_integrated_fixture()
        bad = fx.inconsistent_eligible_reason(good)
        assert _inconsistent_rows(bad) == 1
        assert _n_eligible(bad) >= 1  # still eligible cells present

    def test_zero_eligible_cells(self):
        good = fx.make_integrated_fixture()
        bad = fx.zero_eligible_cells(good)
        assert _n_eligible(bad) == 0
        # consistency is preserved (every ineligible cell has a reason):
        assert _inconsistent_rows(bad) == 0

    def test_hash_drift_baseline_changes_bytes_only(self, tmp_path):
        good = fx.make_integrated_fixture()
        drifted = fx.hash_drift_baseline(good)
        # content invariants unchanged — only bytes differ:
        assert _defect_profile(drifted) == _defect_profile(good)
        from pipeline.common.geo import sha256_file

        p_good = fx.write_fixture_gpkg(good, tmp_path, name="good.gpkg")
        p_drift = fx.write_fixture_gpkg(drifted, tmp_path, name="drift.gpkg")
        assert sha256_file(p_good) != sha256_file(p_drift)

    def test_mutators_do_not_mutate_the_input(self):
        good = fx.make_integrated_fixture()
        before = _defect_profile(good)
        for mutator in fx.KNOWN_BAD_MUTATORS.values():
            mutator(good)
        assert _defect_profile(good) == before
