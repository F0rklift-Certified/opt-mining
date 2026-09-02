"""Focused unit tests for the S1-05 infrastructure feature builder."""

from pathlib import Path
import json
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, Polygon

from pipeline.infrastructure import config
from pipeline.infrastructure.features import (
    _assign_confidence,
    _compute_rez_membership,
    _load_ga_layer,
    _load_rez,
    _nearest_distance_km,
    _resolve_connection_points,
    _validate_computation_crs,
    _write_provenance,
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


def test_nearest_distance_empty_target_preserves_centroid_index():
    centroids = _centroids([(5, 100), (10, 200)])
    empty = gpd.GeoDataFrame(geometry=[], crs="EPSG:3577")
    distances = _nearest_distance_km(centroids, empty)
    assert distances.index.equals(centroids.index)
    assert distances.isna().all()


def test_all_unavailable_rez_sources_return_none(tmp_path: Path):
    # An invalid archive exercises the best-effort path without requiring
    # external EnergyCo data or a shapefile fixture.
    (tmp_path / "new_england.zip").write_bytes(b"not a zip archive")
    assert _load_rez(tmp_path) is None


def test_computation_crs_must_be_projected():
    assert _validate_computation_crs("EPSG:3577") == "EPSG:3577"
    with pytest.raises(ValueError, match="must be projected"):
        _validate_computation_crs("EPSG:4326")


def test_filtered_ga_layer_keeps_empty_geometry_column(tmp_path: Path):
    source = tmp_path / "layer.geojson"
    source.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"state": "VIC"},
            "geometry": {"type": "Point", "coordinates": [144.9, -37.8]},
        }],
    }))
    layer = _load_ga_layer(source, "NSW")
    assert layer.empty
    assert "geometry" in layer.columns
    assert layer.crs.to_string() == config.GA_SOURCE_CRS


def test_rez_archive_paths_are_contained_and_crs_is_normalised(tmp_path: Path, monkeypatch):
    unsafe = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../outside.shp", b"placeholder")
    with pytest.raises(ValueError, match="Unsafe path"):
        _load_rez(tmp_path)

    safe_dir = tmp_path / "safe"
    safe_dir.mkdir()
    for name in ("one.zip", "two.zip"):
        with zipfile.ZipFile(safe_dir / name, "w") as archive:
            archive.writestr(f"{name}.shp", b"placeholder")

    def fake_read_file(path):
        crs = "EPSG:3577" if "one" in str(path) else "EPSG:3857"
        return gpd.GeoDataFrame({"geometry": [Point(1, 1)]}, crs=crs)

    monkeypatch.setattr(gpd, "read_file", fake_read_file)
    result = _load_rez(safe_dir)
    assert result.crs.to_string() == "EPSG:3577"


def test_provenance_uses_actual_computation_crs(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config, "INFRA_DIR", tmp_path)
    monkeypatch.setattr(config, "INFRA_META_DIR", tmp_path / "metadata")
    feature_path = tmp_path / "features.gpkg"
    feature_path.write_bytes(b"snapshot")
    _write_provenance(feature_path, {"computation_crs": "EPSG:3857", "state": "NSW"})
    provenance = (tmp_path / "DATA_PROVENANCE.md").read_text()
    assert "EPSG:3857 centroid distances" in provenance


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


def test_missing_connection_source_is_not_excluded(tmp_path: Path):
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
