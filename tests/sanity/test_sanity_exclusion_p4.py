"""Property test for the S1-12 sanity-check Exclusion Validation (Check 2).

# Feature: s1-12-validation-sanity-check, Property 4: Exclusion checks report expected-versus-observed with honest out-of-grid/ineligible handling

Property 4: Exclusion checks report expected-versus-observed with honest
    out-of-grid/ineligible handling.
    A landmark assertion passes iff the located cell is observed ineligible
    (excluded / null suitability_score) or absent from the grid; a fail is
    recorded honestly, never a pass without an observed value.

Validates: Requirements 3.1, 3.2, 3.3, 3.4

The test drives ``pipeline.sanity.checks.check_exclusions`` with synthetic
grid / scored / integrated frames. Each documented ``config.LANDMARKS`` entry is
assigned one of three fates by construction:

  - ``excluded``  — the landmark's cell exists in the grid but is ineligible
                    (null ``suitability_score``/``rank`` in the Scored_Table AND
                    ``eligible == False`` in the Integrated_Feature_Table) →
                    the assertion MUST pass;
  - ``eligible``  — the landmark's cell exists and is eligible (non-null
                    score/rank, ``eligible == True``) → the assertion MUST fail
                    (recorded honestly as an anomaly, never suppressed);
  - ``absent``    — the landmark's cell is omitted from the grid so the point
                    falls in NO cell → the assertion MUST pass.

Because each landmark cell is a small square built around the landmark's own
documented EPSG:4326 coordinate, the point-in-cell location is unambiguous after
the EPSG:4326 → EPSG:3577 reprojection. An extra "offshore" cell is optionally
seeded into the grid but not into the Integrated_Feature_Table so the whole-grid
offshore/ocean assertion (3.3) exercises both its pass and fail branches.
"""

import geopandas as gpd
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import box

from pipeline.sanity import config
from pipeline.sanity.checks import ExclusionAssertion, check_exclusions
from pipeline.sanity.geo import CrsTransform

STORAGE_CRS = config.STORAGE_CRS  # "EPSG:4326"
CONTAINMENT_CRS = config.CONTAINMENT_CRS  # "EPSG:3577"

# Half-width of each landmark cell (degrees). Small enough that adjacent
# landmark cells never overlap (landmarks are >0.2 deg apart) yet large enough
# that the reprojected point stays comfortably interior.
_HALF = 0.02

# The three fates a landmark can be assigned by construction.
_EXCLUDED = "excluded"
_ELIGIBLE = "eligible"
_ABSENT = "absent"

# A synthetic offshore cell placed well clear of every landmark. It is seeded
# into the grid but NOT into the Integrated_Feature_Table when present, so the
# offshore/ocean assertion (3.3) sees a cell with no land membership.
_OFFSHORE_CELL_ID = "offshore_cell"
_OFFSHORE_LON = 155.5  # east of the NSW coast, still within EPSG:3577 validity
_OFFSHORE_LAT = -33.0


def _landmark_cell_id(index: int) -> str:
    return f"landmark_cell_{index}"


def _cell_box(lon: float, lat: float):
    """A small square cell centred on ``(lon, lat)`` in EPSG:4326."""
    return box(lon - _HALF, lat - _HALF, lon + _HALF, lat + _HALF)


def _build_frames(fates, include_offshore):
    """Build synthetic grid / scored / integrated frames for the given fates.

    ``fates`` is one label per ``config.LANDMARKS`` entry. Returns
    ``(grid, scored, integrated)`` as in-memory frames. A landmark's cell is
    present in the grid unless its fate is ``_ABSENT``; when present it is
    eligible or excluded per its fate. The optional offshore cell is added to
    the grid only.
    """
    grid_cell_ids = []
    grid_geoms = []
    scored_rows = []
    integrated_rows = []

    for idx, (landmark, fate) in enumerate(zip(config.LANDMARKS, fates)):
        if fate == _ABSENT:
            # Cell omitted from the grid entirely — the point falls in no cell.
            continue

        cell_id = _landmark_cell_id(idx)
        grid_cell_ids.append(cell_id)
        grid_geoms.append(_cell_box(landmark.lon, landmark.lat))

        if fate == _ELIGIBLE:
            scored_rows.append(
                {"cell_id": cell_id, "suitability_score": 0.5, "rank": idx + 1}
            )
            integrated_rows.append({"cell_id": cell_id, "eligible": True})
        else:  # _EXCLUDED
            scored_rows.append(
                {"cell_id": cell_id, "suitability_score": None, "rank": None}
            )
            integrated_rows.append({"cell_id": cell_id, "eligible": False})

    if include_offshore:
        # Seed an offshore cell into the grid but NOT into the integrated table,
        # so it has no land/eligible-population membership (an ocean anomaly).
        grid_cell_ids.append(_OFFSHORE_CELL_ID)
        grid_geoms.append(_cell_box(_OFFSHORE_LON, _OFFSHORE_LAT))

    grid = gpd.GeoDataFrame(
        {"cell_id": grid_cell_ids},
        geometry=grid_geoms,
        crs=STORAGE_CRS,
    )
    scored = pd.DataFrame(
        scored_rows, columns=["cell_id", "suitability_score", "rank"]
    )
    integrated = pd.DataFrame(
        integrated_rows, columns=["cell_id", "eligible"]
    )
    return grid, scored, integrated


# One fate per documented landmark; drawn independently so every combination of
# excluded / eligible / absent landmarks is exercised across examples.
_fate = st.sampled_from([_EXCLUDED, _ELIGIBLE, _ABSENT])


@settings(max_examples=150, deadline=None)
@given(
    fates=st.lists(_fate, min_size=len(config.LANDMARKS), max_size=len(config.LANDMARKS)),
    include_offshore=st.booleans(),
)
def test_property_4_exclusion_expected_versus_observed_honest(fates, include_offshore):
    grid, scored, integrated = _build_frames(fates, include_offshore)

    transform_log: list[CrsTransform] = []
    result = check_exclusions(
        config.LANDMARKS,
        grid,
        scored,
        integrated,
        CONTAINMENT_CRS,
        transform_log,
    )

    assertions = result.assertions

    # One assertion per landmark plus exactly one whole-grid offshore assertion.
    assert len(assertions) == len(config.LANDMARKS) + 1
    offshore = [a for a in assertions if a.kind == "offshore"]
    assert len(offshore) == 1, "expected exactly one offshore/ocean assertion (3.3)"
    landmark_assertions = [a for a in assertions if a.kind != "offshore"]
    assert len(landmark_assertions) == len(config.LANDMARKS)

    # --- Every assertion records an observed value; a pass is never recorded
    #     without one (Requirement 3.4). ---
    for a in assertions:
        assert isinstance(a, ExclusionAssertion)
        assert a.expected, "every assertion must record an expected outcome"
        assert isinstance(a.observed, str) and a.observed.strip(), (
            "no assertion may record a pass/fail without an observed value (3.4)"
        )
        assert isinstance(a.passed, bool)

    # --- Landmark assertions: pass iff observed ineligible/absent (3.1, 3.2). ---
    # The assertions come back in LANDMARKS order, so zip against the fates.
    for landmark, fate, a in zip(config.LANDMARKS, fates, landmark_assertions):
        assert a.landmark == landmark.name
        assert a.kind == landmark.kind
        if fate == _ELIGIBLE:
            # An eligible landmark cell is NOT excluded → the assertion fails,
            # recorded honestly and never suppressed into a pass.
            assert a.passed is False, (
                f"{landmark.name}: an eligible cell must fail the exclusion "
                f"assertion, not silently pass"
            )
            assert a.cell_id is not None
        elif fate == _EXCLUDED:
            assert a.passed is True, (
                f"{landmark.name}: an ineligible/excluded cell must pass"
            )
            assert a.cell_id is not None
        else:  # _ABSENT
            assert a.passed is True, (
                f"{landmark.name}: a point in no grid cell must pass (3.2)"
            )
            assert a.cell_id is None

    # --- Offshore/ocean assertion: pass iff no grid cell lacks land membership
    #     i.e. iff no offshore cell was seeded (Requirement 3.3). ---
    offshore_assertion = offshore[0]
    assert offshore_assertion.passed is (not include_offshore)

    # --- Counts are consistent with the recorded pass/fail outcomes. ---
    expected_failed = sum(1 for a in assertions if not a.passed)
    expected_passed = len(assertions) - expected_failed
    assert result.n_failed == expected_failed
    assert result.n_passed == expected_passed
    assert result.all_passed is (expected_failed == 0)

    # --- Every failing assertion is recorded honestly as an anomaly, never
    #     suppressed (Requirements 3.4, 3.6 — a fail is never hidden). ---
    n_failing = sum(1 for a in assertions if not a.passed)
    assert len(result.anomalies) >= n_failing, (
        "every failing assertion must surface an anomaly; none may be suppressed"
    )
