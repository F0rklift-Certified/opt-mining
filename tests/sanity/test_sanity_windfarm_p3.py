"""Property test for the S1-12 sanity-check Known Wind Farm Comparison (Check 1).

# Feature: s1-12-validation-sanity-check, Property 3: Upper-quartile count is correct

Property 3: Upper-quartile count is correct
    The reported Upper_Quartile count equals the number of Known_Wind_Farms
    whose cell Percentile is at or above the documented UPPER_QUARTILE_PERCENTILE
    (75), and the reported proportion equals that count divided by the number of
    Known_Wind_Farms.

Validates: Requirements 2.5

The test builds a synthetic Analysis_Grid of adjacent square cells in a small
EPSG:4326 window, a synthetic Scored_Table assigning each cell a
suitability_score (some cells excluded via null score/rank), and synthetic
Wind_Generators points each placed at the interior of a known grid cell so its
Containing_Cell — and therefore its Percentile over the eligible population — is
known by construction. We recompute, independently of the counting logic under
test, each farm's expected percentile via ``percentile_over_eligible`` and count
how many land in the Upper_Quartile. The check's reported ``n_upper_quartile``
must equal that independent count, its ``in_upper_quartile`` row flags must
agree with it row-for-row, and ``proportion_upper_quartile`` must equal
``n_upper_quartile / n_known_farms`` (or 0 when there are no farms).
"""

import geopandas as gpd
import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Point, box

from pipeline.sanity import config
from pipeline.sanity.checks import (
    check_known_wind_farms,
    percentile_over_eligible,
)
from pipeline.sanity.geo import CrsTransform

# Storage CRS for the synthetic grid/points and the single explicit metric
# containment CRS the check must run the join in.
STORAGE_CRS = "EPSG:4326"
CONTAINMENT_CRS = "EPSG:3577"

# Grid origin chosen inside the EPSG:3577 (Australian Albers) valid extent so
# reprojection from EPSG:4326 is well-defined; cells are 0.1 deg squares, small
# enough that unit-cell interior points stay unambiguous after reprojection.
ORIGIN_LON = 149.0
ORIGIN_LAT = -33.0
CELL_DEG = 0.1

_SCORE = config.REQUIRED_SCORE_COLUMNS[1]  # "suitability_score"
_RANK = config.REQUIRED_SCORE_COLUMNS[2]  # "rank"
_NAME = config.REQUIRED_WIND_GENERATOR_ATTR  # "feature_name"


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


# Scores kept in a bounded, non-degenerate range so eligible/excluded splits and
# percentile ties are exercised without floating-point pathologies.
_score_strategy = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)


@settings(max_examples=150, deadline=None)
@given(
    n_cols=st.integers(min_value=1, max_value=5),
    n_rows=st.integers(min_value=1, max_value=5),
    data=st.data(),
)
def test_property_3_upper_quartile_count_is_correct(n_cols, n_rows, data):
    grid = _make_grid(n_cols, n_rows)
    n_cells = n_cols * n_rows

    # --- Build a synthetic Scored_Table over every grid cell. ---
    # Each cell is either eligible (a real score + rank) or excluded (null score
    # AND null rank), so both the eligible population and the excluded path are
    # exercised. At least one cell is forced eligible so the eligible population
    # is non-empty (percentile over an empty population is undefined).
    all_cells = [
        _cell_id(col, row) for row in range(n_rows) for col in range(n_cols)
    ]
    eligible_flags = [
        data.draw(st.booleans(), label=f"eligible_{i}") for i in range(n_cells)
    ]
    if not any(eligible_flags):
        eligible_flags[0] = True

    scores = []
    ranks = []
    for i in range(n_cells):
        if eligible_flags[i]:
            scores.append(data.draw(_score_strategy, label=f"score_{i}"))
            ranks.append(i + 1)
        else:
            scores.append(np.nan)
            ranks.append(np.nan)
    scored = pd.DataFrame(
        {"cell_id": all_cells, _SCORE: scores, _RANK: ranks}
    )

    # Eligible population used for the independent percentile recomputation.
    eligible_scores = np.asarray(
        [s for s, e in zip(scores, eligible_flags) if e], dtype=float
    )

    # --- Build synthetic Wind_Generators, each in a known interior cell. ---
    n_farms = data.draw(st.integers(min_value=0, max_value=10), label="n_farms")
    farm_cols_rows = []
    farm_geoms = []
    farm_names = []
    for f in range(n_farms):
        col = data.draw(st.integers(min_value=0, max_value=n_cols - 1))
        row = data.draw(st.integers(min_value=0, max_value=n_rows - 1))
        farm_cols_rows.append((col, row))
        farm_geoms.append(_interior_point(col, row))
        farm_names.append(f"farm_{f}")

    wind_generators = gpd.GeoDataFrame(
        {_NAME: farm_names},
        geometry=farm_geoms if farm_geoms else [],
        crs=STORAGE_CRS,
    )

    # --- Independently compute the expected Upper_Quartile membership. ---
    # A farm contributes to the Upper_Quartile count only when its cell is an
    # Eligible_Cell (non-null score AND rank) whose Percentile over the eligible
    # population is >= UPPER_QUARTILE_PERCENTILE. Farms on Excluded_Cells never
    # count (score/percentile are null there).
    score_by_cell = dict(zip(all_cells, scores))
    eligible_by_cell = dict(zip(all_cells, eligible_flags))

    expected_uq_flags = []
    for (col, row) in farm_cols_rows:
        cid = _cell_id(col, row)
        if eligible_by_cell[cid]:
            pct = percentile_over_eligible(score_by_cell[cid], eligible_scores)
            expected_uq_flags.append(pct >= config.UPPER_QUARTILE_PERCENTILE)
        else:
            expected_uq_flags.append(False)
    expected_uq_count = sum(expected_uq_flags)

    # --- Run the check under test. ---
    transform_log: list[CrsTransform] = []
    result = check_known_wind_farms(
        wind_generators, grid, scored, CONTAINMENT_CRS, transform_log
    )

    # --- One row per farm, never dropped, in wind-generator order. ---
    assert result.n_known_farms == n_farms
    assert len(result.rows) == n_farms

    # --- Reported Upper_Quartile count == independent count of farms >= 75th. ---
    assert result.n_upper_quartile == expected_uq_count

    # --- Row-level in_upper_quartile flags agree with the independent flags. ---
    reported_row_flags = [row.in_upper_quartile for row in result.rows]
    assert reported_row_flags == expected_uq_flags
    assert sum(reported_row_flags) == result.n_upper_quartile

    # --- Reported proportion == count / n_known_farms (0 when no farms). ---
    if n_farms == 0:
        assert result.proportion_upper_quartile == 0.0
    else:
        expected_proportion = expected_uq_count / n_farms
        assert result.proportion_upper_quartile == expected_proportion


def test_in_top_band_tracks_rank_and_diverges_from_upper_quartile():
    """S3-08 (review Finding): the per-row ``in_top_band`` flag reflects the
    engine's rank <= ``top_band_n`` membership, NOT the Upper_Quartile flag.

    This pins the exact confusion the review found: a farm can be in the
    Upper_Quartile yet OUTSIDE the top-ranked band, so the two column values
    must be able to diverge. We construct a 1x3 grid where every cell is
    eligible, with ranks 1, 2, 3 assigned so that only the two best-ranked cells
    fall inside a ``top_band_n = 2`` band while all three sit in the
    Upper_Quartile. The row whose rank is > N must report ``in_top_band=False``
    even though its ``in_upper_quartile`` is True.
    """
    top_band_n = 2
    n_cells = 10
    grid = _make_grid(n_cols=n_cells, n_rows=1)
    all_cells = [_cell_id(c, 0) for c in range(n_cells)]

    # Ten eligible cells. The engine `rank` is assigned INDEPENDENTLY of the
    # score so that band membership (rank <= N) and Upper_Quartile membership
    # (percentile >= 75) genuinely diverge:
    #   - cell 0 has the LOWEST score (percentile 10, NOT Upper_Quartile) but
    #     rank 1 → in the top-ranked band;
    #   - cell 9 has the HIGHEST score (percentile 100, Upper_Quartile) but
    #     rank 10 → OUTSIDE the top-ranked band.
    scores = [0.10 + 0.05 * c for c in range(n_cells)]  # 0.10 .. 0.55, ascending
    ranks = [c + 1 for c in range(n_cells)]  # cell 0 -> rank 1, cell 9 -> rank 10
    scored = pd.DataFrame({"cell_id": all_cells, _SCORE: scores, _RANK: ranks})

    # One farm per cell, placed at each cell's interior so its containing cell —
    # and therefore its rank — is known by construction.
    wind_generators = gpd.GeoDataFrame(
        {_NAME: [f"farm_{c}" for c in range(n_cells)]},
        geometry=[_interior_point(c, 0) for c in range(n_cells)],
        crs=STORAGE_CRS,
    )

    transform_log: list[CrsTransform] = []
    result = check_known_wind_farms(
        wind_generators,
        grid,
        scored,
        CONTAINMENT_CRS,
        transform_log,
        top_band_n=top_band_n,
    )

    rows_by_rank = {int(row.rank): row for row in result.rows}

    # Band membership tracks rank <= N exactly, regardless of percentile.
    assert rows_by_rank[1].in_top_band is True
    assert rows_by_rank[2].in_top_band is True
    assert rows_by_rank[3].in_top_band is False
    assert rows_by_rank[10].in_top_band is False

    # ...and the aggregate count agrees with the per-row flags.
    assert result.n_in_top_band == 2
    assert sum(1 for row in result.rows if row.in_top_band) == result.n_in_top_band

    # The two columns genuinely DIVERGE in BOTH directions, so they can no longer
    # silently coincide — the exact confusion a panel reading in_upper_quartile
    # under a "rank <= N" header would create:
    #   rank-1 farm: in band but NOT Upper_Quartile (lowest score);
    low_rank_cell = rows_by_rank[1]
    assert low_rank_cell.in_top_band is True
    assert low_rank_cell.in_upper_quartile is False
    #   rank-10 farm: Upper_Quartile (highest score) but NOT in band.
    high_score_cell = rows_by_rank[10]
    assert high_score_cell.in_upper_quartile is True
    assert high_score_cell.in_top_band is False

    # A null-rank / out-of-grid farm is never in band: an offshore point lands in
    # no cell, so its row carries in_top_band=False.
    offshore = gpd.GeoDataFrame(
        {_NAME: ["offshore"]},
        geometry=[Point(ORIGIN_LON - 10.0, ORIGIN_LAT - 10.0)],
        crs=STORAGE_CRS,
    )
    offshore_result = check_known_wind_farms(
        offshore, grid, scored, CONTAINMENT_CRS, [], top_band_n=top_band_n
    )
    assert offshore_result.rows[0].rank is None
    assert offshore_result.rows[0].in_top_band is False
    assert offshore_result.n_in_top_band == 0
