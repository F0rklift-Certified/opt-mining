import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from pipeline.demand.feature import (
    allocate_demand,
    assign_source_region,
    normalise_proxy,
    validate_feature_table,
)


def test_uniform_allocation_conserves_region_demand():
    source = pd.Series(["NSW1", "NSW1", "VIC1", pd.NA])
    demand = pd.Series({"NSW1": 100.0, "VIC1": 50.0})
    raw = allocate_demand(source, demand)
    assert raw.iloc[:2].tolist() == [50.0, 50.0]
    assert raw.iloc[2] == 50.0
    assert pd.isna(raw.iloc[3])


def test_normalise_proxy_is_closed_unit_interval():
    raw = pd.Series([2.0, 4.0, float("nan")])
    source = pd.Series(["NSW1", "NSW1", pd.NA])
    result = normalise_proxy(raw, source)
    assert result.iloc[:2].tolist() == [0.5, 1.0]
    assert pd.isna(result.iloc[2])


def test_centroid_assignment_and_outside_are_deterministic():
    grid = gpd.GeoDataFrame({"cell_id": ["a", "b"]}, geometry=[box(0, 0, 1, 1), box(3, 3, 4, 4)], crs="EPSG:3577")
    regions = gpd.GeoDataFrame({"REGIONID": ["NSW1"]}, geometry=[box(-1, -1, 2, 2)], crs="EPSG:3577")
    result = assign_source_region(grid, regions)
    assert result.tolist()[0] == "NSW1"
    assert pd.isna(result.tolist()[1])

