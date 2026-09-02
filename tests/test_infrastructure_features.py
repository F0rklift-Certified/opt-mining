"""Focused unit tests for the S1-05 infrastructure feature builder."""

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point, Polygon

from pipeline.infrastructure import config
from pipeline.infrastructure.features import (
    _assign_confidence,
    _compute_rez_membership,
    _nearest_distance_km,
    _resolve_connection_points,
    validate_feature_table,
)


def _centroids(points):
    return gpd.GeoDataFrame(
        {"cell_id": [f"c{i}" for i in range(len(points))]},
        geometry=[Point(x, y) for x, y in points],
        crs="EPSG:3577",
    )


def test_nearest_distance_uses_line_interior():
    centroids = _centroids([(5, 100)])
    lines = gpd.GeoDataFrame(
        geometry=[LineString([(0, 0), (10, 0)])], crs="EPSG:3577"
    )
    distance = _nearest_distance_km(centroids, lines).iloc[0]
    assert np.isclose(distance, 0.1)


def test_rez_membership_returns_names_and_null_for_no_overlap():
    grid = gpd.GeoDataFrame(
        {"cell_id": ["inside", "outside"]},
        geometry=[Polygon([(0, 0), (2, 0), (2, 2), (0, 2)]), Polygon([(5, 5), (6, 5), (6, 6), (5, 6)])],
        crs="EPSG:3577",
    )
    rez = gpd.GeoDataFrame(
        {"rez_name": ["Test REZ"]},
        geometry=[Polygon([(1, 1), (3, 1), (3, 3), (1, 3)])],
        crs="EPSG:3577",
    )
    inside, names = _compute_rez_membership(grid, rez)
    assert inside.tolist() == [True, False]
    assert names.iloc[0] == "Test REZ"
    assert pd.isna(names.iloc[1])


def test_unavailable_connection_source_is_counted(tmp_path: Path):
    points, excluded = _resolve_connection_points(tmp_path / "missing.xlsx")
    assert points.empty
    assert excluded == 0


def test_confidence_is_low_when_any_required_feature_is_null():
    frame = gpd.GeoDataFrame(
        {
            "dist_transmission_km": [1.0, 1.0],
            "dist_substation_km": [2.0, 2.0],
            "dist_connection_km": [3.0, np.nan],
            "inside_rez": [False, False],
        }
    )
    assert _assign_confidence(frame).tolist() == ["high", "low"]


def test_generated_feature_table_contract():
    path = config.INFRA_DIR / config.FEATURE_TABLE_NAME
    result = validate_feature_table(path, config.GRID_PATH)
    assert result["rows"] == 47311
    assert result["crs"] == config.STORAGE_CRS
