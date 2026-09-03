"""Property test for the S1-12 sanity-check CRS containment helper.

# Feature: s1-12-validation-sanity-check, Property 1: Point-in-cell location is correct in the metric CRS

Property 1: Point-in-cell location is correct in the metric CRS
    Each interior point is located to exactly its containing cell in EPSG:3577;
    an out-of-extent point gets a null cell; no point is ever dropped.

Validates: Requirements 2.1, 2.2, 2.7

The test builds synthetic grids of adjacent unit cells laid out in a small
EPSG:4326 window and synthetic points. For each grid cell we can name the
containing cell deterministically (integer floor of the offset from the grid
origin), so an interior point's expected Containing_Cell is known by
construction. Points placed outside the grid extent must come back with a null
``cell_id`` rather than being dropped, and the output must carry exactly one row
per input point in input order.
"""

import geopandas as gpd
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Point, box

from pipeline.sanity.geo import CrsTransform, locate_points_to_cells

# Storage CRS for the synthetic grid/points and the single explicit metric
# containment CRS the helper must run the join in.
STORAGE_CRS = "EPSG:4326"
CONTAINMENT_CRS = "EPSG:3577"

# Grid origin chosen inside the EPSG:3577 (Australian Albers) valid extent so
# reprojection from EPSG:4326 is well-defined; cells are 0.1 deg squares, small
# enough that unit-cell interior points stay unambiguous after reprojection.
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


def _interior_point(col: int, row: int, fx: float, fy: float) -> Point:
    """A point strictly inside cell ``(col, row)`` at interior fractions fx, fy."""
    minx = ORIGIN_LON + col * CELL_DEG
    miny = ORIGIN_LAT + row * CELL_DEG
    return Point(minx + fx * CELL_DEG, miny + fy * CELL_DEG)


# Interior fractions kept well away from cell edges (0.15..0.85) so that the
# EPSG:4326 -> EPSG:3577 reprojection cannot nudge a point across a boundary.
_interior_frac = st.floats(min_value=0.15, max_value=0.85, allow_nan=False, allow_infinity=False)


@settings(max_examples=100, deadline=None)
@given(
    n_cols=st.integers(min_value=1, max_value=5),
    n_rows=st.integers(min_value=1, max_value=5),
    data=st.data(),
)
def test_property_1_point_in_cell_location_metric_crs(n_cols, n_rows, data):
    grid = _make_grid(n_cols, n_rows)

    # Draw a batch of interior points, each tied to a known containing cell.
    n_interior = data.draw(st.integers(min_value=1, max_value=8), label="n_interior")
    interior_points = []
    expected_cell_ids = []
    for _ in range(n_interior):
        col = data.draw(st.integers(min_value=0, max_value=n_cols - 1))
        row = data.draw(st.integers(min_value=0, max_value=n_rows - 1))
        fx = data.draw(_interior_frac)
        fy = data.draw(_interior_frac)
        interior_points.append(_interior_point(col, row, fx, fy))
        expected_cell_ids.append(f"c{col}_{row}")

    # Draw a batch of out-of-extent points below/left of the grid origin, well
    # clear of the grid so they fall in NO cell.
    n_outside = data.draw(st.integers(min_value=0, max_value=4), label="n_outside")
    outside_points = []
    for _ in range(n_outside):
        dx = data.draw(st.floats(min_value=1.0, max_value=5.0, allow_nan=False))
        dy = data.draw(st.floats(min_value=1.0, max_value=5.0, allow_nan=False))
        outside_points.append(Point(ORIGIN_LON - dx, ORIGIN_LAT - dy))

    all_geoms = interior_points + outside_points
    points = gpd.GeoDataFrame(
        {"pid": list(range(len(all_geoms)))},
        geometry=all_geoms,
        crs=STORAGE_CRS,
    )

    transform_log: list[CrsTransform] = []
    result = locate_points_to_cells(points, grid, CONTAINMENT_CRS, transform_log)

    # --- No point dropped: exactly one row per input point, in input order. ---
    assert len(result) == len(all_geoms)
    assert result["point_index"].tolist() == list(points.index)

    # --- The containment ran in the explicit metric CRS and was logged. ---
    assert transform_log, "expected the applied transforms to be recorded"
    assert all(t.target == CONTAINMENT_CRS for t in transform_log)

    located = result["cell_id"].tolist()

    # --- Interior points located to exactly their containing cell. ---
    for i in range(n_interior):
        assert located[i] == expected_cell_ids[i]

    # --- Out-of-extent points got a null cell_id (reported, not dropped). ---
    for i in range(n_interior, len(all_geoms)):
        assert pd.isna(located[i])
