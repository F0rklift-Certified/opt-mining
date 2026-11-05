"""Explicit centroid policy and fail-closed source guards for the NSW mask."""
import geopandas as gpd
import pytest
from shapely.geometry import box
from pipeline.exclusions import config
from pipeline.exclusions.apply import nsw_land_field


def cells():
    return gpd.GeoDataFrame({"cell_id": ["inside", "outside", "edge"],
                            "centroid_lon": [151.0, 153.0, 150.0],
                            "centroid_lat": [-30.0, -30.0, -31.0]},
                           geometry=[box(150.9, -30.1, 151.1, -29.9)] * 3,
                           crs="EPSG:4326")


def test_centroid_not_polygon_overlap_and_boundary_is_included(tmp_path, monkeypatch):
    path = tmp_path / "states.geojson"
    gpd.GeoDataFrame({"state_code_2021": ["1"]}, geometry=[box(150, -31, 152, -29)],
                     crs="EPSG:4326").to_file(path, driver="GeoJSON")
    monkeypatch.setattr(config, "NSW_BOUNDARY_PATH", path)
    assert nsw_land_field(cells()) == {"inside": True, "outside": False, "edge": True}


def test_missing_boundary_halts(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "NSW_BOUNDARY_PATH", tmp_path / "missing.geojson")
    with pytest.raises(RuntimeError, match="source not found"):
        nsw_land_field(cells())


@pytest.mark.parametrize("codes", [["2"], ["1", "1"]])
def test_missing_or_ambiguous_nsw_halts(tmp_path, monkeypatch, codes):
    path = tmp_path / "states.geojson"
    gpd.GeoDataFrame({"state_code_2021": codes}, geometry=[box(150, -31, 152, -29)] * len(codes),
                     crs="EPSG:4326").to_file(path, driver="GeoJSON")
    monkeypatch.setattr(config, "NSW_BOUNDARY_PATH", path)
    with pytest.raises(ValueError, match="exactly one"):
        nsw_land_field(cells())
