"""Example-based known-value unit tests for the S1-12 sanity-check core (Req. 13).

Task 15.3 — these tests pin the automated check computations against SMALL,
hand-constructed inputs with HAND-COMPUTED expected outputs. They complement the
Hypothesis property tests (which assert universal properties) by nailing down a
handful of concrete, human-verifiable cases so a regression in the arithmetic is
caught immediately.

Each test covers one Requirement-13 sub-item:

  13.1 Point-in-cell location on a small synthetic grid (EPSG:3577 containment).
  13.2 Percentile over a small Eligible_Cell population (Excluded_Cell omitted).
  13.3 Exclusion assertions (excluded PASS, an eligible urban/park cell FAILs
       with a recorded observed value).
  13.4 Distribution statistics (min/max/mean/std/quartiles, clustering flag,
       wind-vs-score correlation) against hand-computed values.
  13.5 Spot_Check_Cells selection count in [5, 10] spanning top/middle/bottom.
  13.6 Determinism — the automated outputs reproduce on a second run.

Conventions for building the synthetic grid / scored / integrated frames follow
the existing property tests in this directory (test_sanity_geo_p1.py,
test_sanity_exclusion_p4.py, test_sanity_spotcells_p5.py).

All tolerances are documented inline; floating-point comparisons use
``pytest.approx`` with an explicit ``abs`` tolerance.
"""

import math

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, box

from pipeline.sanity import config
from pipeline.sanity.checks import (
    SPOT_BAND_BOTTOM,
    SPOT_BAND_MIDDLE,
    SPOT_BAND_TOP,
    check_distribution,
    check_exclusions,
    check_spot_values,
    percentile_over_eligible,
    select_spot_cells,
)
from pipeline.sanity.geo import CrsTransform, locate_points_to_cells

STORAGE_CRS = config.STORAGE_CRS  # "EPSG:4326"
CONTAINMENT_CRS = config.CONTAINMENT_CRS  # "EPSG:3577"

# A documented absolute tolerance for all float comparisons. Reprojection
# (EPSG:4326 -> EPSG:3577) and numpy percentile/statistic arithmetic are exact
# to well within 1e-9 for these tiny hand-built inputs; 1e-9 is a comfortable,
# deliberately tight bound that still absorbs last-bit floating-point noise.
ABS_TOL = 1e-9

# Grid geometry constants shared by the containment tests. The origin sits
# comfortably inside the EPSG:3577 (Australian Albers) valid extent so the
# EPSG:4326 -> EPSG:3577 reprojection is well-defined; 0.1-degree cells are
# small enough that an interior point stays unambiguous after reprojection.
ORIGIN_LON = 149.0
ORIGIN_LAT = -33.0
CELL_DEG = 0.1


def _make_grid(n_cols: int, n_rows: int) -> gpd.GeoDataFrame:
    """A rectangular block of adjacent square cells with deterministic ids.

    Cell ``(col, row)`` covers
    ``[ORIGIN_LON + col*CELL_DEG, ORIGIN_LON + (col+1)*CELL_DEG] x
       [ORIGIN_LAT + row*CELL_DEG, ORIGIN_LAT + (row+1)*CELL_DEG]``
    and carries ``cell_id == f"c{col}_{row}"``.
    """
    cell_ids = []
    geoms = []
    for row in range(n_rows):
        for col in range(n_cols):
            minx = ORIGIN_LON + col * CELL_DEG
            miny = ORIGIN_LAT + row * CELL_DEG
            cell_ids.append(f"c{col}_{row}")
            geoms.append(box(minx, miny, minx + CELL_DEG, miny + CELL_DEG))
    return gpd.GeoDataFrame({"cell_id": cell_ids}, geometry=geoms, crs=STORAGE_CRS)


def _cell_centre(col: int, row: int) -> Point:
    """The exact centre of cell ``(col, row)`` — unambiguously interior."""
    minx = ORIGIN_LON + col * CELL_DEG
    miny = ORIGIN_LAT + row * CELL_DEG
    return Point(minx + 0.5 * CELL_DEG, miny + 0.5 * CELL_DEG)


# ===========================================================================
# 13.1 — Point-in-cell location on a small synthetic grid (EPSG:3577)
# ===========================================================================


def test_13_1_point_in_cell_location_known_cells():
    """Each synthetic wind-farm point lands in its known Containing_Cell (3577).

    A 3x2 grid of named cells is built. Four points are placed at the exact
    centre of four chosen cells (so the Containing_Cell is known by
    construction) plus one point well below/left of the grid origin that falls
    in NO cell. The located ``cell_id`` for each interior point must equal the
    known cell, the out-of-extent point must come back null (reported, not
    dropped), and the containment must have run in EPSG:3577 (logged).
    """
    grid = _make_grid(n_cols=3, n_rows=2)

    # Points at the centres of known cells, in a fixed order, plus one outside.
    specs = [(0, 0), (2, 0), (1, 1), (2, 1)]
    expected_cells = [f"c{col}_{row}" for col, row in specs]
    geoms = [_cell_centre(col, row) for col, row in specs]
    # Out-of-extent point: 2 degrees below/left of the grid origin.
    geoms.append(Point(ORIGIN_LON - 2.0, ORIGIN_LAT - 2.0))

    points = gpd.GeoDataFrame(
        {"name": [f"farm_{i}" for i in range(len(geoms))]},
        geometry=geoms,
        crs=STORAGE_CRS,
    )

    transform_log: list[CrsTransform] = []
    result = locate_points_to_cells(points, grid, CONTAINMENT_CRS, transform_log)

    # One row per input point, in input order (no point dropped).
    assert len(result) == len(geoms)
    assert result["point_index"].tolist() == list(points.index)

    located = result["cell_id"].tolist()
    # Interior points located to exactly their known Containing_Cell.
    for i, expected in enumerate(expected_cells):
        assert located[i] == expected
    # The out-of-extent point is null, not dropped.
    assert pd.isna(located[-1])

    # The containment ran in the single explicit metric CRS, and was logged.
    assert transform_log, "expected the applied transforms to be logged"
    assert all(t.target == CONTAINMENT_CRS for t in transform_log)


# ===========================================================================
# 13.2 — Percentile over an Eligible_Cell population (Excluded_Cell omitted)
# ===========================================================================


def test_13_2_percentile_over_eligible_known_values():
    """Percentile == 100 * count(<= score) / n_eligible, hand-computed.

    Eligible population: [0.1, 0.2, 0.3, 0.4] (n_eligible = 4). By the weak
    (<=) definition:
        percentile(0.1) = 100 * 1/4 = 25.0
        percentile(0.2) = 100 * 2/4 = 50.0
        percentile(0.3) = 100 * 3/4 = 75.0
        percentile(0.4) = 100 * 4/4 = 100.0
    A score above every eligible value is the 100th percentile.
    """
    eligible = [0.1, 0.2, 0.3, 0.4]

    assert percentile_over_eligible(0.1, eligible) == pytest.approx(25.0, abs=ABS_TOL)
    assert percentile_over_eligible(0.2, eligible) == pytest.approx(50.0, abs=ABS_TOL)
    assert percentile_over_eligible(0.3, eligible) == pytest.approx(75.0, abs=ABS_TOL)
    assert percentile_over_eligible(0.4, eligible) == pytest.approx(100.0, abs=ABS_TOL)
    assert percentile_over_eligible(0.9, eligible) == pytest.approx(100.0, abs=ABS_TOL)


def test_13_2_percentile_ignores_excluded_values():
    """Excluded_Cell values are omitted: only the eligible population counts.

    The percentile helper takes the ELIGIBLE scores directly (the caller never
    passes Excluded_Cell values in), so a percentile computed over the eligible
    subset is unchanged whether or not excluded scores exist. Here the eligible
    subset is [0.1, 0.2, 0.3, 0.4]; adding excluded values (which are NOT
    passed) cannot alter percentile(0.3) = 75.0.
    """
    eligible_only = [0.1, 0.2, 0.3, 0.4]
    # Excluded values that must NOT participate — they are simply never passed.
    _excluded_ignored = [10.0, 20.0, 30.0]

    assert percentile_over_eligible(0.3, eligible_only) == pytest.approx(
        75.0, abs=ABS_TOL
    )
    # NaNs among the eligible array are dropped before the count, so a stray NaN
    # cannot inflate n_eligible.
    assert percentile_over_eligible(0.3, [0.1, 0.2, 0.3, 0.4, float("nan")]) == (
        pytest.approx(75.0, abs=ABS_TOL)
    )


# ===========================================================================
# 13.3 — Exclusion assertions (excluded PASS; eligible urban/park FAIL)
# ===========================================================================

# Half-width of each landmark cell (degrees): small enough that adjacent
# landmark cells never overlap (documented landmarks are >0.2 deg apart), large
# enough that the reprojected point stays comfortably interior.
_HALF = 0.02


def _cell_box(lon: float, lat: float):
    """A small square cell centred on ``(lon, lat)`` in EPSG:4326."""
    return box(lon - _HALF, lat - _HALF, lon + _HALF, lat + _HALF)


def test_13_3_exclusion_excluded_pass_eligible_fail_with_observed():
    """A synthetic urban/protected cell is detected excluded; an eligible one FAILs.

    Two documented landmarks are exercised by construction:
      - Sydney CBD (urban): its cell is EXCLUDED (null score/rank, eligible ==
        False) → the assertion must PASS.
      - Blue Mountains NP (park): its cell is deliberately made ELIGIBLE
        (non-null score/rank, eligible == True) → the assertion must FAIL, and
        the failure must carry a non-empty observed value (never a silent pass).
    The remaining landmarks are absent from the grid (their points fall in no
    cell) so they PASS trivially. No offshore cell is seeded, so the whole-grid
    offshore/ocean assertion PASSES.
    """
    sydney = next(lm for lm in config.LANDMARKS if lm.name == "Sydney CBD")
    blue_mtns = next(lm for lm in config.LANDMARKS if lm.name == "Blue Mountains NP")

    # Grid: one excluded cell (Sydney) and one eligible cell (Blue Mountains).
    grid = gpd.GeoDataFrame(
        {"cell_id": ["syd_excluded", "bm_eligible"]},
        geometry=[_cell_box(sydney.lon, sydney.lat), _cell_box(blue_mtns.lon, blue_mtns.lat)],
        crs=STORAGE_CRS,
    )
    scored = pd.DataFrame(
        [
            {"cell_id": "syd_excluded", "suitability_score": None, "rank": None},
            {"cell_id": "bm_eligible", "suitability_score": 0.7, "rank": 1},
        ],
        columns=["cell_id", "suitability_score", "rank"],
    )
    integrated = pd.DataFrame(
        [
            {"cell_id": "syd_excluded", "eligible": False},
            {"cell_id": "bm_eligible", "eligible": True},
        ],
        columns=["cell_id", "eligible"],
    )

    transform_log: list[CrsTransform] = []
    result = check_exclusions(
        config.LANDMARKS, grid, scored, integrated, CONTAINMENT_CRS, transform_log
    )

    by_landmark = {a.landmark: a for a in result.assertions}

    # --- Excluded urban cell: PASS, with an observed value recorded. ---
    syd = by_landmark["Sydney CBD"]
    assert syd.cell_id == "syd_excluded"
    assert syd.passed is True
    assert syd.observed.strip(), "a pass must still record an observed value (3.4)"

    # --- Eligible park cell: FAIL, with a non-empty observed value. ---
    bm = by_landmark["Blue Mountains NP"]
    assert bm.cell_id == "bm_eligible"
    assert bm.passed is False, "an eligible national-park cell must FAIL the exclusion assertion"
    assert bm.observed.strip(), "a failing assertion must report the observed value (3.4)"

    # The failing assertion is surfaced as an anomaly (never suppressed).
    assert any(
        "Blue Mountains NP" in a.description for a in result.anomalies
    ), "the eligible-park failure must be recorded honestly as an anomaly"

    # Landmarks with no grid cell pass trivially; offshore assertion passes
    # (no ocean cell seeded).
    offshore = [a for a in result.assertions if a.kind == "offshore"]
    assert len(offshore) == 1
    assert offshore[0].passed is True

    # Counts: exactly one failing assertion (Blue Mountains).
    assert result.n_failed == 1
    assert result.all_passed is False


# ===========================================================================
# 13.4 — Distribution statistics against hand-computed values
# ===========================================================================


def test_13_4_distribution_statistics_known_values():
    """min/max/mean/std/quartiles, clustering flag, and correlation, hand-computed.

    Eligible scores: [0.00, 0.25, 0.50, 0.75, 1.00] (n = 5, evenly spaced).
    Hand-computed:
        min = 0.0, max = 1.0, mean = 0.5
        population std (ddof=0):
            deviations^2 = 0.25, 0.0625, 0, 0.0625, 0.25 -> sum 0.625
            variance = 0.625 / 5 = 0.125 -> std = sqrt(0.125) = 0.353553390...
        numpy linear-interp percentiles over 5 sorted values (index (n-1)*p):
            q1  (25%) -> index 1.0 -> 0.25
            median   -> index 2.0 -> 0.50
            q3  (75%) -> index 3.0 -> 0.75

    Degenerate-clustering flag (CLUSTER_EPSILON = 0.02, threshold 0.5):
        within 0.02 of 0 or 1 -> {0.0, 1.0} -> 2 of 5 = 0.4.
        0.4 is NOT > 0.5 -> NOT degenerate -> cluster_passed True.

    Wind-vs-score correlation: wind_speed is constructed strictly increasing
    with the score, so the Spearman (rank) correlation is exactly +1.0.
    """
    scores = [0.00, 0.25, 0.50, 0.75, 1.00]
    # wind_speed strictly increasing with score => perfect positive rank corr.
    wind = [5.0, 6.0, 7.0, 8.0, 9.0]
    eligible = pd.DataFrame(
        {
            "cell_id": [f"cell_{i}" for i in range(len(scores))],
            "suitability_score": scores,
            "rank": [5, 4, 3, 2, 1],
            "wind_speed": wind,
            "centroid_lat": [-33.0, -33.1, -33.2, -33.3, -33.4],
            "centroid_lon": [150.0, 150.1, 150.2, 150.3, 150.4],
        }
    )

    result = check_distribution(eligible)

    assert result.stats["min"] == pytest.approx(0.0, abs=ABS_TOL)
    assert result.stats["max"] == pytest.approx(1.0, abs=ABS_TOL)
    assert result.stats["mean"] == pytest.approx(0.5, abs=ABS_TOL)
    assert result.stats["std"] == pytest.approx(math.sqrt(0.125), abs=ABS_TOL)
    assert result.stats["q1"] == pytest.approx(0.25, abs=ABS_TOL)
    assert result.stats["median"] == pytest.approx(0.50, abs=ABS_TOL)
    assert result.stats["q3"] == pytest.approx(0.75, abs=ABS_TOL)

    # Clustering: 2 of 5 within epsilon of {0, 1} = 0.4, not degenerate.
    assert result.cluster_fraction == pytest.approx(0.4, abs=ABS_TOL)
    assert result.cluster_degenerate is False
    assert result.cluster_passed is True

    # Correlation: strictly increasing wind vs score => Spearman == +1.0.
    assert result.wind_score_corr == pytest.approx(1.0, abs=ABS_TOL)
    assert result.corr_passed is True
    assert result.n_eligible == 5


def test_13_4_distribution_degenerate_clustering_flag_known():
    """A distribution clustered at the extremes is flagged degenerate.

    Eligible scores: [0.0, 0.0, 0.0, 1.0, 0.5] (n = 5). Within CLUSTER_EPSILON
    (0.02) of 0 or 1: the three 0.0 values and the single 1.0 => 4 of 5 = 0.8.
    0.8 > 0.5 threshold -> degenerate -> cluster_passed False, and an anomaly is
    recorded honestly.
    """
    scores = [0.0, 0.0, 0.0, 1.0, 0.5]
    eligible = pd.DataFrame(
        {
            "cell_id": [f"cell_{i}" for i in range(len(scores))],
            "suitability_score": scores,
            "rank": [1, 2, 3, 4, 5],
        }
    )

    result = check_distribution(eligible)

    assert result.cluster_fraction == pytest.approx(0.8, abs=ABS_TOL)
    assert result.cluster_degenerate is True
    assert result.cluster_passed is False
    assert any(
        a.check == "Score-Distribution Plausibility" for a in result.anomalies
    ), "a degenerate distribution must surface an anomaly, recorded honestly"


def test_13_4_distribution_negative_correlation_reported_not_enforced():
    """A non-positive wind-vs-score correlation is reported honestly, not fixed.

    wind_speed is constructed strictly DECREASING with the score, so the
    Spearman rank correlation is exactly -1.0. The check must report the
    negative correlation (corr_passed False) and surface an anomaly, WITHOUT
    raising or altering the distribution (5.4, 5.5).
    """
    scores = [0.00, 0.25, 0.50, 0.75, 1.00]
    wind = [9.0, 8.0, 7.0, 6.0, 5.0]  # strictly decreasing => corr -1.0
    eligible = pd.DataFrame(
        {
            "cell_id": [f"cell_{i}" for i in range(len(scores))],
            "suitability_score": scores,
            "rank": [5, 4, 3, 2, 1],
            "wind_speed": wind,
        }
    )

    result = check_distribution(eligible)

    assert result.wind_score_corr == pytest.approx(-1.0, abs=ABS_TOL)
    assert result.corr_passed is False
    assert any(
        "correlation" in a.description.lower() for a in result.anomalies
    ), "a non-positive correlation must be recorded honestly as an anomaly"


# ===========================================================================
# 13.5 — Spot_Check_Cells selection count in [5, 10], spanning the range
# ===========================================================================


def _make_eligible_scores(scores):
    """A synthetic Eligible_Cell frame with one distinct cell per score."""
    return pd.DataFrame(
        {
            "cell_id": [f"cell_{i:04d}" for i in range(len(scores))],
            "suitability_score": scores,
            "rank": list(range(len(scores), 0, -1)),
        }
    )


def test_13_5_spot_cell_selection_count_and_span():
    """The selection has n in [5, 10] and spans top / middle / bottom.

    Eligible population: 20 distinct cells with strictly increasing scores
    0.00, 0.05, ..., 0.95. Requesting n = SPOT_CHECK_DEFAULT (8) must return
    exactly 8 distinct cells whose min/max scores equal the population min/max
    (so the span includes the bottom and top cell), with at least one interior
    (middle) selection between them.
    """
    scores = [round(0.05 * i, 2) for i in range(20)]  # 0.00 .. 0.95
    eligible = _make_eligible_scores(scores)

    n = config.SPOT_CHECK_DEFAULT
    assert config.SPOT_CHECK_MIN <= n <= config.SPOT_CHECK_MAX

    selected = select_spot_cells(eligible, n)

    # Exactly n distinct cells.
    assert len(selected) == n
    assert selected["cell_id"].nunique() == n

    # The span includes the population's bottom and top score.
    assert selected["suitability_score"].min() == pytest.approx(
        eligible["suitability_score"].min(), abs=ABS_TOL
    )
    assert selected["suitability_score"].max() == pytest.approx(
        eligible["suitability_score"].max(), abs=ABS_TOL
    )

    # The bands span top / middle / bottom.
    bands = set(selected["score_band"].tolist())
    assert SPOT_BAND_BOTTOM in bands
    assert SPOT_BAND_TOP in bands
    assert SPOT_BAND_MIDDLE in bands


def test_13_5_spot_cell_count_rejected_outside_range():
    """A requested count outside [5, 10] raises, naming the range (4.5)."""
    eligible = _make_eligible_scores([round(0.05 * i, 2) for i in range(20)])

    with pytest.raises(ValueError):
        select_spot_cells(eligible, config.SPOT_CHECK_MIN - 1)
    with pytest.raises(ValueError):
        select_spot_cells(eligible, config.SPOT_CHECK_MAX + 1)


def test_13_5_spot_values_recorded_for_selected_cells():
    """check_spot_values records the feature values for each selected cell.

    A 6-cell eligible population is joined to a matching Integrated_Feature_Table
    carrying wind_speed / slope_deg / dist_transmission_km / protected. Selecting
    n = 5 must record 5 rows, each carrying the exact feature values of its cell.
    """
    scores = [0.10, 0.20, 0.40, 0.60, 0.80, 0.95]
    eligible = pd.DataFrame(
        {
            "cell_id": [f"cell_{i}" for i in range(len(scores))],
            "suitability_score": scores,
            "rank": list(range(len(scores), 0, -1)),
            "centroid_lat": [-33.0 - 0.1 * i for i in range(len(scores))],
            "centroid_lon": [150.0 + 0.1 * i for i in range(len(scores))],
        }
    )
    integrated = pd.DataFrame(
        {
            "cell_id": [f"cell_{i}" for i in range(len(scores))],
            "wind_speed": [6.0 + i for i in range(len(scores))],
            "slope_deg": [2.0 + i for i in range(len(scores))],
            "dist_transmission_km": [10.0 + i for i in range(len(scores))],
            "protected_area": [False] * len(scores),
        }
    )

    selected = select_spot_cells(eligible, 5)
    result = check_spot_values(selected, integrated)

    assert result.n_spot_cells == 5
    assert len(result.rows) == 5

    # Each recorded row carries the exact feature values of its cell.
    by_cell = {row.cell_id: row for row in result.rows}
    for cell_id, row in by_cell.items():
        idx = int(cell_id.split("_")[1])
        assert row.wind_speed == pytest.approx(6.0 + idx, abs=ABS_TOL)
        assert row.slope_deg == pytest.approx(2.0 + idx, abs=ABS_TOL)
        assert row.dist_transmission_km == pytest.approx(10.0 + idx, abs=ABS_TOL)
        assert row.protected is False
        assert row.discrepancy == "", "the human-verification field is left blank"


# ===========================================================================
# 13.6 — Determinism: the automated outputs reproduce on a second run
# ===========================================================================


def test_13_6_determinism_over_identical_inputs():
    """A second run over identical inputs reproduces the automated outputs.

    Covers determinism across the three deterministic automated computations:
    percentile, distribution statistics, and spot-cell selection. Each is run
    twice over identical inputs and the outputs must be bit-for-bit identical.
    """
    # Percentile determinism.
    eligible_scores = [0.1, 0.2, 0.3, 0.4]
    assert percentile_over_eligible(0.3, eligible_scores) == percentile_over_eligible(
        0.3, eligible_scores
    )

    # Distribution determinism.
    scores = [0.00, 0.25, 0.50, 0.75, 1.00]
    eligible = pd.DataFrame(
        {
            "cell_id": [f"cell_{i}" for i in range(len(scores))],
            "suitability_score": scores,
            "rank": [5, 4, 3, 2, 1],
            "wind_speed": [5.0, 6.0, 7.0, 8.0, 9.0],
        }
    )
    first = check_distribution(eligible)
    second = check_distribution(eligible)
    assert first.stats == second.stats
    assert first.cluster_fraction == second.cluster_fraction
    assert first.cluster_degenerate == second.cluster_degenerate
    assert first.wind_score_corr == second.wind_score_corr

    # Spot-cell selection determinism (cells, scores, and bands identical).
    big_scores = [round(0.05 * i, 2) for i in range(20)]
    pop = _make_eligible_scores(big_scores)
    sel_a = select_spot_cells(pop, config.SPOT_CHECK_DEFAULT)
    sel_b = select_spot_cells(pop, config.SPOT_CHECK_DEFAULT)
    assert sel_a["cell_id"].tolist() == sel_b["cell_id"].tolist()
    assert sel_a["suitability_score"].tolist() == sel_b["suitability_score"].tolist()
    assert sel_a["score_band"].tolist() == sel_b["score_band"].tolist()
