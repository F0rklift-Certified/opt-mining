"""
Tests for the demand coordinate-confidence tier (surface-only metadata).

These pin the three guarantees the prerequisite requires:

  (a) the tier is PRODUCED with the documented definition — a cell within the
      search radius of a low-confidence (Nominatim/OSM) load point is "low", an
      assigned cell whose contributing points are all precise (or which has no
      point in range) is "high", and an outside-region cell is "n/a";
  (b) the tier is WELL-BEHAVED under urban_weighted (and uniform): with no load
      points every cell is the not-applicable "n/a" value;
  (c) the tier is METADATA-ONLY — it is a function of coordinate provenance,
      never of demand_proxy, so it cannot feed back into the proxy/score.

The scoring-stage regression that proves the composite score and ranking are
unchanged by the column's presence lives in
``tests/scoring/test_coord_confidence_metadata_only.py``.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, box

from pipeline.demand import config as demand_config
from pipeline.demand.feature import (
    compute_demand_coord_confidence,
    derive_demand_coord_confidence,
)

# EPSG:3577 (metres) so the LOAD_SEARCH_RADIUS_M distances are literal.
_CRS = demand_config.COMPUTATION_CRS


def _grid(cells: list[tuple[str, float, float]]) -> gpd.GeoDataFrame:
    """Build a tiny EPSG:3577 grid of 1 km cells centred on (x, y) metres."""
    geoms = [box(x - 500, y - 500, x + 500, y + 500) for _, x, y in cells]
    return gpd.GeoDataFrame(
        {"cell_id": [c for c, _, _ in cells]}, geometry=geoms, crs=_CRS
    )


def _load_points(points: list[tuple[float, float, bool, bool]]) -> gpd.GeoDataFrame:
    """Build load points with (x, y, nominatim_low, osm_low) in EPSG:3577."""
    return gpd.GeoDataFrame(
        {
            "max_demand": [10.0] * len(points),
            "nominatim_low_confidence": [n for _, _, n, _ in points],
            "osm_low_confidence": [o for _, _, _, o in points],
        },
        geometry=[Point(x, y) for x, y, _, _ in points],
        crs=_CRS,
    )


def test_cell_near_low_confidence_point_is_low():
    """(a) A cell within the search radius of a low-confidence point is 'low'."""
    radius = demand_config.LOAD_SEARCH_RADIUS_M
    grid = _grid([("near_nominatim", 0.0, 0.0), ("near_osm", 3 * radius, 0.0)])
    # A Nominatim-low point on top of the first cell; an OSM-low point on the second.
    load = _load_points([
        (0.0, 0.0, True, False),
        (3 * radius, 0.0, False, True),
    ])
    source = pd.Series(["NSW1", "NSW1"], index=grid.index)
    tier = compute_demand_coord_confidence(grid, load, source)
    assert tier.loc[0] == demand_config.DEMAND_COORD_CONFIDENCE_LOW
    assert tier.loc[1] == demand_config.DEMAND_COORD_CONFIDENCE_LOW


def test_cell_near_only_precise_points_is_high():
    """(a) An assigned cell whose in-range points are all precise is 'high'."""
    grid = _grid([("precise", 0.0, 0.0)])
    load = _load_points([(0.0, 0.0, False, False)])  # GA/portal/OSM-high
    source = pd.Series(["NSW1"], index=grid.index)
    tier = compute_demand_coord_confidence(grid, load, source)
    assert tier.loc[0] == demand_config.DEMAND_COORD_CONFIDENCE_HIGH


def test_cell_beyond_radius_of_low_point_is_high():
    """(a) A low-confidence point OUTSIDE the search radius does not taint a cell."""
    radius = demand_config.LOAD_SEARCH_RADIUS_M
    grid = _grid([("far", 0.0, 0.0)])
    # Low-confidence point well beyond the radius.
    load = _load_points([(3 * radius, 0.0, True, False)])
    source = pd.Series(["NSW1"], index=grid.index)
    tier = compute_demand_coord_confidence(grid, load, source)
    assert tier.loc[0] == demand_config.DEMAND_COORD_CONFIDENCE_HIGH


def test_outside_region_cell_is_na_even_near_low_point():
    """(a) An unassigned (outside-region) cell is 'n/a', never 'low'."""
    grid = _grid([("outside", 0.0, 0.0)])
    load = _load_points([(0.0, 0.0, True, False)])
    source = pd.Series([pd.NA], index=grid.index, dtype="object")
    tier = compute_demand_coord_confidence(grid, load, source)
    assert tier.loc[0] == demand_config.DEMAND_COORD_CONFIDENCE_NA


def test_urban_weighted_is_all_na():
    """(b) Under urban_weighted (no load points) every cell is the 'n/a' value."""
    grid = _grid([("a", 0.0, 0.0), ("b", 10_000.0, 0.0)])
    source = pd.Series(["NSW1", "NSW1"], index=grid.index)
    tier = derive_demand_coord_confidence(grid, source, "urban_weighted", None)
    assert set(tier.unique()) == {demand_config.DEMAND_COORD_CONFIDENCE_NA}


def test_uniform_is_all_na():
    """(b) Under uniform (no load points) every cell is the 'n/a' value."""
    grid = _grid([("a", 0.0, 0.0)])
    source = pd.Series(["NSW1"], index=grid.index)
    tier = derive_demand_coord_confidence(grid, source, "uniform", None)
    assert set(tier.unique()) == {demand_config.DEMAND_COORD_CONFIDENCE_NA}


def test_tier_values_are_within_vocabulary():
    """The tier only ever emits values from the documented vocabulary."""
    radius = demand_config.LOAD_SEARCH_RADIUS_M
    grid = _grid([("low", 0.0, 0.0), ("high", 10 * radius, 0.0), ("out", 20 * radius, 0.0)])
    load = _load_points([(0.0, 0.0, True, False), (10 * radius, 0.0, False, False)])
    source = pd.Series(["NSW1", "NSW1", pd.NA], index=grid.index, dtype="object")
    tier = derive_demand_coord_confidence(grid, source, "load_weighted", load)
    assert set(tier.unique()) <= set(demand_config.DEMAND_COORD_CONFIDENCE_LEVELS)


def test_tier_is_independent_of_demand_proxy_values():
    """(c) The tier depends only on coordinate provenance, not on any proxy value.

    Two runs with the SAME geometry/flags but different max_demand values yield
    the identical tier — so the tier can never carry demand_proxy information
    back into the output.
    """
    radius = demand_config.LOAD_SEARCH_RADIUS_M
    grid = _grid([("low", 0.0, 0.0), ("high", 10 * radius, 0.0)])
    source = pd.Series(["NSW1", "NSW1"], index=grid.index)
    load_a = _load_points([(0.0, 0.0, True, False)])
    load_b = _load_points([(0.0, 0.0, True, False)])
    load_b["max_demand"] = [9_999.0]  # wildly different magnitude
    tier_a = compute_demand_coord_confidence(grid, load_a, source)
    tier_b = compute_demand_coord_confidence(grid, load_b, source)
    assert tier_a.tolist() == tier_b.tolist()
