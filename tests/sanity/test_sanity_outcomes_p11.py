"""Property test for the S1-12 sanity-check no-silent-passes contract.

# Feature: s1-12-validation-sanity-check, Property 11: Every automated check reports an explicit pass/fail with an observed value

Property 11: Every automated check reports an explicit pass/fail with an
    observed value.
    Each automated-check outcome carries an ``expected`` outcome, an
    ``observed`` outcome, and an explicit ``passed`` pass/fail; a ``pass`` is
    NEVER recorded without a recorded observed value; and a failing outcome is
    surfaced exactly as recorded, never hidden.

Validates: Requirements 3.4, 11.1, 11.2, 11.3, 11.4, 11.5

The three automated checks that emit a ``CheckOutcome`` are exercised together
over synthetic frames (Check 3 — Feature-Value Spot-Checks — is deliberately a
human-judgement item and emits no automated pass/fail, so it is run but not
asserted against the outcome contract). Grid / scored / integrated / wind
frames are built with the same construction the sibling Property 3 and Property
4 tests use, so containment is unambiguous after the EPSG:4326 -> EPSG:3577
reprojection:

  - ``WindFarmCheckResult.outcome`` (Check 1, the Upper_Quartile count, 11.2);
  - ``ExclusionCheckResult.outcomes`` (Check 2, one per assertion, 11.3);
  - ``DistributionCheckResult.cluster_outcome`` and ``.correlation_outcome``
    (Check 4, the clustering and wind-correlation statistics, 11.4).

For every one of those outcomes the test asserts the three-field contract: an
``expected`` value is present, ``passed`` is an explicit bool, and — the core of
Property 11 — whenever ``passed`` is True the ``observed`` value is non-None and
non-empty (no silent pass, 11.1). A failing outcome is asserted to be present in
the returned results whenever the construction guarantees a failure, confirming
it is surfaced and not hidden (11.5). Finally the ``CheckOutcome`` invariant is
tested directly: constructing a pass with a None or empty-string observed value
raises (11.1).
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Point, box

from pipeline.sanity import config
from pipeline.sanity.checks import (
    CheckOutcome,
    check_distribution,
    check_exclusions,
    check_known_wind_farms,
    check_spot_values,
    select_spot_cells,
)
from pipeline.sanity.geo import CrsTransform

STORAGE_CRS = config.STORAGE_CRS  # "EPSG:4326"
CONTAINMENT_CRS = config.CONTAINMENT_CRS  # "EPSG:3577"

# Grid origin chosen inside the EPSG:3577 (Australian Albers) valid extent so
# reprojection from EPSG:4326 is well-defined; 0.1 deg square cells keep
# interior points unambiguous after reprojection (mirrors the P3/P4 tests).
ORIGIN_LON = 149.0
ORIGIN_LAT = -33.0
CELL_DEG = 0.1

_SCORE = config.REQUIRED_SCORE_COLUMNS[1]  # "suitability_score"
_RANK = config.REQUIRED_SCORE_COLUMNS[2]  # "rank"
_NAME = config.REQUIRED_WIND_GENERATOR_ATTR  # "name"
_INT_CELL_ID = config.REQUIRED_INTEGRATED_COLUMNS[0]  # "cell_id"
_INT_WIND_SPEED = config.REQUIRED_INTEGRATED_COLUMNS[1]  # "wind_speed"
_INT_ELIGIBLE = config.REQUIRED_INTEGRATED_COLUMNS[5]  # "eligible"

# Half-width of each landmark cell (degrees); small enough that landmark cells
# never overlap (landmarks are >0.2 deg apart) yet the reprojected point stays
# comfortably interior (mirrors the P4 test).
_HALF = 0.02


def _cell_id(col: int, row: int) -> str:
    return f"c{col}_{row}"


def _make_grid(n_cols: int, n_rows: int) -> gpd.GeoDataFrame:
    """A rectangular block of adjacent square cells with deterministic ids."""
    cell_ids = []
    geoms = []
    for row in range(n_rows):
        for col in range(n_cols):
            minx = ORIGIN_LON + col * CELL_DEG
            miny = ORIGIN_LAT + row * CELL_DEG
            cell_ids.append(_cell_id(col, row))
            geoms.append(box(minx, miny, minx + CELL_DEG, miny + CELL_DEG))
    return gpd.GeoDataFrame({"cell_id": cell_ids}, geometry=geoms, crs=STORAGE_CRS)


def _interior_point(col: int, row: int) -> Point:
    """A point at the centre of cell ``(col, row)`` — unambiguously interior."""
    minx = ORIGIN_LON + col * CELL_DEG
    miny = ORIGIN_LAT + row * CELL_DEG
    return Point(minx + 0.5 * CELL_DEG, miny + 0.5 * CELL_DEG)


def _cell_box(lon: float, lat: float):
    """A small square landmark cell centred on ``(lon, lat)`` in EPSG:4326."""
    return box(lon - _HALF, lat - _HALF, lon + _HALF, lat + _HALF)


def _assert_outcome_contract(outcome: CheckOutcome) -> None:
    """Assert the three-field no-silent-passes contract for one outcome.

    Every outcome must carry an ``expected`` value and an explicit boolean
    ``passed``; whenever ``passed`` is True the ``observed`` value must be
    non-None and non-empty — no silent pass (Requirements 11.1, 3.4).
    """
    assert isinstance(outcome, CheckOutcome)
    assert isinstance(outcome.passed, bool), "passed must be an explicit bool"
    assert outcome.expected is not None, "every outcome must record an expected value"
    if isinstance(outcome.expected, str):
        assert outcome.expected.strip(), "expected must not be empty"
    if outcome.passed:
        observed = outcome.observed
        assert observed is not None, "a pass must carry a recorded observed value (11.1)"
        if isinstance(observed, str):
            assert observed.strip(), "a pass must not carry an empty observed value (11.1)"


# Scores kept in a bounded, non-degenerate range so eligible/excluded splits and
# percentile ties are exercised without floating-point pathologies.
_score_strategy = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)
_wind_strategy = st.floats(
    min_value=5.0, max_value=12.0, allow_nan=False, allow_infinity=False
)

# The three fates a landmark can take, mirroring the P4 test.
_EXCLUDED = "excluded"
_ELIGIBLE = "eligible"
_ABSENT = "absent"
_fate = st.sampled_from([_EXCLUDED, _ELIGIBLE, _ABSENT])


@settings(max_examples=120, deadline=None)
@given(
    n_cols=st.integers(min_value=2, max_value=5),
    n_rows=st.integers(min_value=2, max_value=5),
    fates=st.lists(
        _fate, min_size=len(config.LANDMARKS), max_size=len(config.LANDMARKS)
    ),
    data=st.data(),
)
def test_property_11_every_check_reports_explicit_pass_fail_with_observed(
    n_cols, n_rows, fates, data
):
    grid = _make_grid(n_cols, n_rows)
    n_cells = n_cols * n_rows
    all_cells = [
        _cell_id(col, row) for row in range(n_rows) for col in range(n_cols)
    ]

    # --- Synthetic Scored_Table over every grid cell (some cells excluded). ---
    eligible_flags = [
        data.draw(st.booleans(), label=f"eligible_{i}") for i in range(n_cells)
    ]
    # Force at least two eligible cells so the eligible population is non-empty
    # and the distribution/correlation statistics are well-defined.
    if sum(eligible_flags) < 2:
        eligible_flags[0] = True
        eligible_flags[1] = True

    scores = []
    ranks = []
    winds = []
    rank_counter = 1
    for i in range(n_cells):
        if eligible_flags[i]:
            scores.append(data.draw(_score_strategy, label=f"score_{i}"))
            ranks.append(rank_counter)
            rank_counter += 1
            winds.append(data.draw(_wind_strategy, label=f"wind_{i}"))
        else:
            scores.append(np.nan)
            ranks.append(np.nan)
            winds.append(np.nan)

    scored = pd.DataFrame({"cell_id": all_cells, _SCORE: scores, _RANK: ranks})

    # --- Synthetic Integrated_Feature_Table over the SAME cells. ---
    # Every grid cell is present so the offshore/ocean assertion (3.3) passes on
    # the wind-farm grid; the eligible flag mirrors the scored eligibility.
    integrated = pd.DataFrame(
        {
            _INT_CELL_ID: all_cells,
            _INT_WIND_SPEED: winds,
            _INT_ELIGIBLE: eligible_flags,
        }
    )

    # --- Synthetic Wind_Generators, each placed at a known interior cell. ---
    n_farms = data.draw(st.integers(min_value=0, max_value=8), label="n_farms")
    farm_geoms = []
    farm_names = []
    for f in range(n_farms):
        col = data.draw(st.integers(min_value=0, max_value=n_cols - 1))
        row = data.draw(st.integers(min_value=0, max_value=n_rows - 1))
        farm_geoms.append(_interior_point(col, row))
        farm_names.append(f"farm_{f}")
    wind_generators = gpd.GeoDataFrame(
        {_NAME: farm_names},
        geometry=farm_geoms if farm_geoms else [],
        crs=STORAGE_CRS,
    )

    # =======================================================================
    # Check 1 — Known Wind Farm Comparison: the Upper_Quartile outcome (11.2).
    # =======================================================================
    wf_log: list[CrsTransform] = []
    wf_result = check_known_wind_farms(
        wind_generators, grid, scored, CONTAINMENT_CRS, wf_log
    )
    wf_outcome = wf_result.outcome
    _assert_outcome_contract(wf_outcome)
    # The Check 1 headline is the Upper_Quartile count against the expectation:
    # its observed value must report the count it was derived from (11.2).
    assert str(wf_result.n_upper_quartile) in str(wf_outcome.observed)

    # =======================================================================
    # Check 2 — Exclusion Validation: one outcome per assertion (11.3).
    # =======================================================================
    # Build a dedicated landmark grid/scored/integrated so the landmark fates
    # (excluded / eligible / absent) are exercised, driving both pass and fail
    # outcomes through the contract.
    lm_grid_ids = []
    lm_grid_geoms = []
    lm_scored_rows = []
    lm_integrated_rows = []
    forced_fail_present = False
    for idx, (landmark, fate) in enumerate(zip(config.LANDMARKS, fates)):
        if fate == _ABSENT:
            continue
        cid = f"landmark_cell_{idx}"
        lm_grid_ids.append(cid)
        lm_grid_geoms.append(_cell_box(landmark.lon, landmark.lat))
        if fate == _ELIGIBLE:
            # An eligible landmark cell MUST fail the exclusion assertion — a
            # failing outcome that must be surfaced, never hidden (11.5).
            lm_scored_rows.append(
                {"cell_id": cid, "suitability_score": 0.5, "rank": idx + 1}
            )
            lm_integrated_rows.append({"cell_id": cid, "eligible": True})
            forced_fail_present = True
        else:  # _EXCLUDED
            lm_scored_rows.append(
                {"cell_id": cid, "suitability_score": None, "rank": None}
            )
            lm_integrated_rows.append({"cell_id": cid, "eligible": False})

    lm_grid = gpd.GeoDataFrame(
        {"cell_id": lm_grid_ids}, geometry=lm_grid_geoms, crs=STORAGE_CRS
    )
    lm_scored = pd.DataFrame(
        lm_scored_rows, columns=["cell_id", "suitability_score", "rank"]
    )
    lm_integrated = pd.DataFrame(
        lm_integrated_rows, columns=["cell_id", "eligible"]
    )

    ex_log: list[CrsTransform] = []
    ex_result = check_exclusions(
        config.LANDMARKS,
        lm_grid,
        lm_scored,
        lm_integrated,
        CONTAINMENT_CRS,
        ex_log,
    )
    ex_outcomes = ex_result.outcomes
    # One outcome per assertion (landmarks + the whole-grid offshore assertion).
    assert len(ex_outcomes) == len(ex_result.assertions)
    for outcome in ex_outcomes:
        _assert_outcome_contract(outcome)
    # Each assertion's pass/fail is mirrored faithfully into its outcome (11.3),
    # so a failing assertion is surfaced as a failing outcome, never hidden.
    assert [o.passed for o in ex_outcomes] == [
        a.passed for a in ex_result.assertions
    ]
    if forced_fail_present:
        assert any(not o.passed for o in ex_outcomes), (
            "an eligible landmark cell must surface a failing outcome (11.5)"
        )

    # =======================================================================
    # Check 4 — Score-Distribution Plausibility: cluster + correlation (11.4).
    # =======================================================================
    # The eligible population, joined with wind_speed so the correlation outcome
    # is defined where possible.
    eligible = scored[scored[_SCORE].notna() & scored[_RANK].notna()].copy()
    eligible = eligible.merge(
        integrated[[_INT_CELL_ID, _INT_WIND_SPEED]],
        left_on="cell_id",
        right_on=_INT_CELL_ID,
        how="left",
    )
    dist_result = check_distribution(eligible)
    cluster_outcome = dist_result.cluster_outcome
    correlation_outcome = dist_result.correlation_outcome
    _assert_outcome_contract(cluster_outcome)
    _assert_outcome_contract(correlation_outcome)
    # The clustering outcome must report the observed fraction it was derived
    # from, and mirror the recorded cluster_passed (11.4).
    assert cluster_outcome.passed == dist_result.cluster_passed
    assert f"{dist_result.cluster_fraction:.4f}" in str(cluster_outcome.observed)
    # The correlation outcome mirrors the recorded corr_passed and is REPORTED,
    # not enforced; when passed it must carry the observed statistic (11.1, 11.4).
    assert correlation_outcome.passed == dist_result.corr_passed

    # =======================================================================
    # Check 3 — Feature-Value Spot-Checks is run (a human-judgement item that
    # emits no automated CheckOutcome), to confirm it does not participate in
    # the pass/fail contract. Only run when enough eligible cells exist to pick
    # the minimum spot-cell count.
    # =======================================================================
    if len(eligible) >= config.SPOT_CHECK_MIN:
        spot = select_spot_cells(eligible, config.SPOT_CHECK_MIN)
        spot_result = check_spot_values(spot, integrated)
        # Spot-check rows carry recorded observed feature values for the human
        # reviewer, but expose no CheckOutcome accessor — the contract is
        # AUTOMATED-checks only.
        assert not hasattr(spot_result, "outcome")
        assert not hasattr(spot_result, "outcomes")


# ===========================================================================
# CheckOutcome invariant — a pass may NEVER carry a None/empty observed (11.1).
# ===========================================================================


def test_checkoutcome_pass_with_none_observed_raises():
    """A pass with a None observed value is a silent pass and must raise (11.1)."""
    with pytest.raises(ValueError):
        CheckOutcome(expected="something", observed=None, passed=True)


def test_checkoutcome_pass_with_empty_string_observed_raises():
    """A pass with an empty/whitespace observed value must raise (11.1)."""
    with pytest.raises(ValueError):
        CheckOutcome(expected="something", observed="", passed=True)
    with pytest.raises(ValueError):
        CheckOutcome(expected="something", observed="   ", passed=True)


def test_checkoutcome_fail_may_carry_none_observed():
    """A FAIL may legitimately carry a None observed — an honest failing outcome
    (11.5); constructing it must NOT raise."""
    outcome = CheckOutcome(expected="something", observed=None, passed=False)
    assert outcome.passed is False
    assert outcome.observed is None


def test_checkoutcome_pass_with_observed_is_accepted():
    """A pass WITH a recorded observed value is valid (11.1)."""
    outcome = CheckOutcome(expected="e", observed="observed value", passed=True)
    assert outcome.passed is True
    assert outcome.observed == "observed value"
