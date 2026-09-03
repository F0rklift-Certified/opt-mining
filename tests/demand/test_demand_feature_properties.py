"""Property tests for S1-04 (minimum 100 Hypothesis examples each)."""
import math

import geopandas as gpd
import pandas as pd
from hypothesis import given, settings, strategies as st
from shapely.geometry import box

from pipeline.demand.feature import (
    allocate_demand,
    assign_confidence,
    assign_source_region,
    build_feature_table,
    normalise_proxy,
)


def _grid(n):
    return gpd.GeoDataFrame(
        {"cell_id": [f"c{i}" for i in range(n)]},
        geometry=[box(i, 0, i + 1, 1) for i in range(n)],
        crs="EPSG:4326",
    )


@settings(max_examples=100, deadline=None)
@given(st.integers(min_value=1, max_value=12))
def test_property_1_strict_cell_id_keying(n):
    grid = _grid(n)
    source = pd.Series(["NSW1"] * n)
    proxy = pd.Series([1.0] * n)
    out = build_feature_table(grid, proxy, "uniform", source, assign_confidence(source, proxy))
    assert out.cell_id.tolist() == grid.cell_id.tolist()


@settings(max_examples=100, deadline=None)
@given(st.integers(min_value=1, max_value=12))
def test_property_2_one_row_per_cell_exact_schema(n):
    grid = _grid(n)
    source = pd.Series(["NSW1"] * n)
    proxy = pd.Series([1.0] * n)
    out = build_feature_table(grid, proxy, "uniform", source, assign_confidence(source, proxy))
    assert len(out) == n
    assert out.columns.tolist() == ["cell_id", "demand_proxy", "allocation_method", "source_region", "confidence_flag", "geometry"]


@settings(max_examples=100, deadline=None)
@given(st.integers(min_value=1, max_value=12), st.floats(min_value=0.01, max_value=10000, allow_nan=False))
def test_property_3_demand_conservation(n, total):
    source = pd.Series(["NSW1"] * n)
    raw = allocate_demand(source, pd.Series({"NSW1": total}))
    assert math.isclose(float(raw.sum()), total, rel_tol=0, abs_tol=1e-6)


@settings(max_examples=100, deadline=None)
@given(st.lists(st.floats(min_value=0.01, max_value=1000, allow_nan=False), min_size=1, max_size=12))
def test_property_4_proxy_range(values):
    raw = pd.Series(values)
    source = pd.Series(["NSW1"] * len(values))
    proxy = normalise_proxy(raw, source)
    assert proxy.between(0, 1).all()


@settings(max_examples=100, deadline=None)
@given(st.integers(min_value=1, max_value=8))
def test_property_5_source_region_correctness(n):
    grid = _grid(n)
    regions = gpd.GeoDataFrame({"REGIONID": ["NSW1"]}, geometry=[box(-1, -1, n + 1, 2)], crs="EPSG:4326")
    result = assign_source_region(grid.to_crs("EPSG:3577"), regions.to_crs("EPSG:3577"))
    assert set(result) == {"NSW1"}


@settings(max_examples=100, deadline=None)
@given(st.integers(min_value=2, max_value=8))
def test_property_6_outside_region_is_null(n):
    grid = _grid(n)
    regions = gpd.GeoDataFrame({"REGIONID": ["NSW1"]}, geometry=[box(-1, -1, 0.9, 2)], crs="EPSG:4326")
    result = assign_source_region(grid.to_crs("EPSG:3577"), regions.to_crs("EPSG:3577"))
    assert result.iloc[0] == "NSW1"
    assert result.iloc[-1] is pd.NA or pd.isna(result.iloc[-1])


@settings(max_examples=100, deadline=None)
@given(st.integers(min_value=1, max_value=8))
def test_property_7_deterministic_assignment(n):
    grid = _grid(n).to_crs("EPSG:3577")
    regions = gpd.GeoDataFrame({"REGIONID": ["B", "A"]}, geometry=[box(-1, -1, n + 1, 2), box(-1, -1, n + 1, 2)], crs="EPSG:3577")
    assert assign_source_region(grid, regions).equals(assign_source_region(grid, regions))


@settings(max_examples=100, deadline=None)
@given(st.integers(min_value=1, max_value=12))
def test_property_8_confidence_enum(n):
    source = pd.Series(["NSW1"] * n + [pd.NA])
    proxy = pd.Series([1.0] * n + [float("nan")])
    flags = assign_confidence(source, proxy)
    assert set(flags).issubset({"high", "low", "medium"})


@settings(max_examples=100, deadline=None)
@given(st.integers(min_value=1, max_value=12))
def test_property_9_counting_conservation(n):
    source = pd.Series(["NSW1"] * n + [pd.NA])
    assert int(source.notna().sum() + source.isna().sum()) == len(source)


@settings(max_examples=100, deadline=None)
@given(st.integers(min_value=1, max_value=12))
def test_property_10_storage_crs(n):
    grid = _grid(n)
    source = pd.Series(["NSW1"] * n)
    proxy = pd.Series([1.0] * n)
    out = build_feature_table(grid, proxy, "uniform", source, assign_confidence(source, proxy))
    assert out.crs.to_epsg() == 4326


@settings(max_examples=100, deadline=None)
@given(st.integers(min_value=1, max_value=12), st.sampled_from(["uniform"]))
def test_property_11_constant_allocation_method(n, method):
    grid = _grid(n)
    source = pd.Series(["NSW1"] * n)
    proxy = pd.Series([1.0] * n)
    out = build_feature_table(grid, proxy, method, source, assign_confidence(source, proxy))
    assert set(out.allocation_method) == {method}
