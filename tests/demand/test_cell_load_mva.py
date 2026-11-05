"""
Tests for the DISPLAY-ONLY per-cell 'network load within the decay radius' (MVA).

These pin the documented definition of ``compute_cell_load_mva`` /
``derive_cell_load_mva`` (``pipeline.demand.feature``):

  (a) the figure is the RAW SUM of zone-substation ``max_demand`` (MVA) over the
      substations WITHIN ``LOAD_SEARCH_RADIUS_M`` of the cell centroid — no decay
      kernel, no per-region rescale, no normalisation;
  (b) a cell with no substation in range is 0 MVA;
  (c) the same ``max_demand (MVA) > 0`` filter the weight path uses applies, so a
      zero/negative-MVA row never contributes;
  (d) the figure is deterministic (a set-membership sum, order-independent);
  (e) it is method-aware: ``None`` under uniform/urban_weighted (no load points).

The scoring-stage regression proving the column is METADATA-ONLY (the composite
score and ranking are unchanged by its presence) lives in
``tests/scoring/test_load_mva_metadata_only.py``.
"""

from __future__ import annotations

import geopandas as gpd
from shapely.geometry import Point, box

from pipeline.demand import config as demand_config
from pipeline.demand.feature import compute_cell_load_mva, derive_cell_load_mva

# EPSG:3577 (metres) so the LOAD_SEARCH_RADIUS_M distances are literal.
_CRS = demand_config.COMPUTATION_CRS
_RADIUS = demand_config.LOAD_SEARCH_RADIUS_M


def _grid(cells: list[tuple[str, float, float]]) -> gpd.GeoDataFrame:
    """Build a tiny EPSG:3577 grid of 1 km cells centred on (x, y) metres."""
    geoms = [box(x - 500, y - 500, x + 500, y + 500) for _, x, y in cells]
    return gpd.GeoDataFrame(
        {"cell_id": [c for c, _, _ in cells]}, geometry=geoms, crs=_CRS
    )


def _load_points(points: list[tuple[float, float, float]]) -> gpd.GeoDataFrame:
    """Build load points with (x, y, max_demand_mva) in EPSG:3577."""
    return gpd.GeoDataFrame(
        {demand_config.LOAD_MVA_COLUMN: [mva for _, _, mva in points]},
        geometry=[Point(x, y) for x, y, _ in points],
        crs=_CRS,
    )


def test_sum_is_raw_mva_within_radius():
    """(a) The figure sums raw max_demand over substations within the radius."""
    grid = _grid([("cell", 0.0, 0.0)])
    # Two substations well within the radius, one far outside it.
    load = _load_points([
        (0.0, 0.0, 30.0),
        (0.3 * _RADIUS, 0.0, 20.0),
        (3.0 * _RADIUS, 0.0, 999.0),
    ])
    mva = compute_cell_load_mva(grid.to_crs(_CRS), load)
    # 30 + 20 = 50 MVA; the far substation contributes nothing. No decay applied
    # (a decay kernel would make the result < 50).
    assert mva.loc[grid.index[0]] == 50.0


def test_cell_with_no_substation_in_range_is_zero():
    """(b) A cell with no substation within the radius is 0 MVA."""
    grid = _grid([("isolated", 0.0, 0.0)])
    load = _load_points([(5.0 * _RADIUS, 0.0, 100.0)])
    mva = compute_cell_load_mva(grid.to_crs(_CRS), load)
    assert mva.loc[grid.index[0]] == 0.0


def test_zero_and_negative_mva_points_never_contribute():
    """(c) The MVA > 0 filter drops zero/negative-demand substations."""
    grid = _grid([("cell", 0.0, 0.0)])
    load = _load_points([
        (0.0, 0.0, 0.0),            # documented Pindari = 0 style row
        (0.1 * _RADIUS, 0.0, -5.0),  # defensive: negative load
        (0.2 * _RADIUS, 0.0, 12.5),  # the only contributor
    ])
    mva = compute_cell_load_mva(grid.to_crs(_CRS), load)
    assert mva.loc[grid.index[0]] == 12.5


def test_deterministic_regardless_of_point_order():
    """(d) The sum is a set-membership total, independent of row order."""
    grid = _grid([("cell", 0.0, 0.0)])
    pts = [
        (0.0, 0.0, 7.0),
        (0.2 * _RADIUS, 0.0, 11.0),
        (0.4 * _RADIUS, 0.0, 3.0),
    ]
    forward = compute_cell_load_mva(grid.to_crs(_CRS), _load_points(pts))
    reverse = compute_cell_load_mva(grid.to_crs(_CRS), _load_points(list(reversed(pts))))
    assert forward.loc[grid.index[0]] == reverse.loc[grid.index[0]] == 21.0


def test_no_load_points_gives_all_zero():
    """An empty load layer yields 0 MVA for every cell (no crash)."""
    grid = _grid([("a", 0.0, 0.0), ("b", 2.0 * _RADIUS, 0.0)])
    empty = _load_points([])
    mva = compute_cell_load_mva(grid.to_crs(_CRS), empty)
    assert list(mva) == [0.0, 0.0]


def test_derive_is_method_aware():
    """(e) Only load_weighted yields a figure; other methods return None."""
    grid = _grid([("cell", 0.0, 0.0)]).to_crs(_CRS)
    load = _load_points([(0.0, 0.0, 42.0)])

    load_weighted = derive_cell_load_mva(grid, "load_weighted", load)
    assert load_weighted is not None
    assert load_weighted.loc[grid.index[0]] == 42.0

    assert derive_cell_load_mva(grid, "uniform", None) is None
    assert derive_cell_load_mva(grid, "urban_weighted", None) is None
    # load_weighted with no load points also degrades to None (no figure).
    assert derive_cell_load_mva(grid, "load_weighted", None) is None
