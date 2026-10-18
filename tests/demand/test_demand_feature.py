import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from pipeline.demand import config as demand_config
from pipeline.demand.feature import (
    allocate_demand,
    assign_confidence,
    assign_source_region,
    compute_cell_weights,
    load_urban_weights,
    normalise_proxy,
    validate_feature_table as validate_in_memory_feature_table,
)
from pipeline.demand.validate import validate_feature_table as validate_persisted_feature_table


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


def test_demand_conservation_rejects_missing_nonzero_region():
    source = pd.Series(["NSW1", "NSW1"])
    raw = allocate_demand(source, pd.Series({"NSW1": 100.0}))
    grid = gpd.GeoDataFrame({"cell_id": ["a", "b"]}, geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)], crs="EPSG:3577")
    table = gpd.GeoDataFrame(
        {"cell_id": ["a", "b"], "demand_proxy": [1.0, 1.0], "allocation_method": ["uniform", "uniform"], "source_region": ["NSW1", "NSW1"], "confidence_flag": ["high", "high"]},
        geometry=grid.geometry,
        crs=grid.crs,
    )
    aggregate = pd.DataFrame({"REGIONID": ["NSW1", "QLD1"], "MEAN_DEMAND_MW": [100.0, 200.0]})
    with pytest.raises(ValueError, match="missing observed regions"):
        validate_in_memory_feature_table(table, grid, source, raw, aggregate)


def test_persisted_feature_validation_uses_named_layer_and_checks_crs(tmp_path):
    grid = gpd.GeoDataFrame(
        {"cell_id": ["a", "b"]},
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs=demand_config.STORAGE_CRS,
    )
    grid_path = tmp_path / "grid.gpkg"
    grid.to_file(grid_path, layer="grid", driver="GPKG", index=False)

    feature = grid.assign(
        demand_proxy=[0.5, 1.0],
        allocation_method=["uniform", "uniform"],
        source_region=["NSW1", "NSW1"],
        confidence_flag=["high", "high"],
    )[
        ["cell_id", "demand_proxy", "allocation_method", "source_region", "confidence_flag", "geometry"]
    ]
    feature_path = tmp_path / "features.gpkg"
    # Put a decoy layer first: validation must select the named demand layer.
    feature.head(0).to_file(feature_path, layer="decoy", driver="GPKG", index=False)
    feature.to_file(feature_path, layer=demand_config.FEATURE_TABLE_LAYER, driver="GPKG", index=False)
    aggregate_path = tmp_path / "aggregate.csv"
    pd.DataFrame({"REGIONID": ["NSW1"], "MEAN_DEMAND_MW": [100.0]}).to_csv(aggregate_path, index=False)

    result = validate_persisted_feature_table(feature_path, grid_path, aggregate_path)
    assert result.passed
    assert dict((name, passed) for name, passed, _ in result.details)["Feature CRS"]

    wrong_crs_path = tmp_path / "features_wrong_crs.gpkg"
    feature.to_crs("EPSG:3857").to_file(
        wrong_crs_path, layer=demand_config.FEATURE_TABLE_LAYER, driver="GPKG", index=False
    )
    wrong_result = validate_persisted_feature_table(wrong_crs_path, grid_path, aggregate_path)
    assert not wrong_result.passed
    assert not dict((name, passed) for name, passed, _ in wrong_result.details)["Feature CRS"]


# ---------------------------------------------------------------------------
# Urban-weighted allocation (Option A) tests
# ---------------------------------------------------------------------------


def _urban_grid():
    """Two NSW1 cells: cell 'a' overlaps an urban polygon, cell 'b' does not."""
    grid = gpd.GeoDataFrame(
        {"cell_id": ["a", "b"]},
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs=demand_config.COMPUTATION_CRS,
    )
    source = pd.Series(["NSW1", "NSW1"], index=grid.index)
    return grid, source


def _urban_layer():
    # Urban polygon covers only cell 'a' (x in [0,1]); SOS 10 (Major Urban).
    return gpd.GeoDataFrame(
        {"sos_code_2021": ["10"], "sosr_name_2021": ["1 million or more"]},
        geometry=[box(0.0, 0.0, 1.0, 1.0)],
        crs=demand_config.COMPUTATION_CRS,
    )


def test_urban_weighted_allocation_conserves_region_demand_and_varies():
    source = pd.Series(["NSW1", "NSW1", "VIC1", pd.NA])
    demand = pd.Series({"NSW1": 100.0, "VIC1": 50.0})
    weights = pd.Series([3.0, 1.0, 2.0, float("nan")])
    raw = allocate_demand(source, demand, "urban_weighted", weights)
    # Conservation: each region's raw sums to its total.
    assert pytest.approx(float(raw.iloc[:2].sum()), abs=1e-6) == 100.0
    assert pytest.approx(float(raw.iloc[2]), abs=1e-6) == 50.0
    assert pd.isna(raw.iloc[3])
    # Unequal weights give unequal raw values within NSW1.
    assert raw.iloc[0] != raw.iloc[1]
    assert raw.iloc[0] == pytest.approx(75.0, abs=1e-6)
    assert raw.iloc[1] == pytest.approx(25.0, abs=1e-6)


def test_urban_weighted_proxy_not_constant_within_region():
    grid, source = _urban_grid()
    weights = compute_cell_weights(grid, _urban_layer(), source)
    demand = pd.Series({"NSW1": 100.0})
    raw = allocate_demand(source, demand, "urban_weighted", weights)
    proxy = normalise_proxy(raw, source)
    # The urban cell should carry more weight than the floored rural cell.
    assert weights.loc[grid.index[0]] > weights.loc[grid.index[1]]
    assert proxy.nunique() > 1
    assert proxy.max() == pytest.approx(1.0, abs=1e-9)


def test_floored_cells_medium_null_cells_low():
    grid, source = _urban_grid()
    # Add an outside-region cell (null source).
    source = pd.Series(["NSW1", "NSW1", pd.NA])
    grid = gpd.GeoDataFrame(
        {"cell_id": ["a", "b", "c"]},
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1), box(10, 10, 11, 11)],
        crs=demand_config.COMPUTATION_CRS,
    )
    weights = compute_cell_weights(grid, _urban_layer(), source)
    demand = pd.Series({"NSW1": 100.0})
    raw = allocate_demand(source, demand, "urban_weighted", weights)
    proxy = normalise_proxy(raw, source)
    # Floored = assigned cells carrying only the floor weight (cell 'b').
    floored = list(weights.index[weights.notna() & (weights <= demand_config.DEMAND_WEIGHT_FLOOR)])
    conf = assign_confidence(source, proxy, boundary_indices=None, floored_indices=floored)
    assert conf.iloc[0] == "high"    # real urban overlap
    assert conf.iloc[1] == "medium"  # floored (non-urban)
    assert conf.iloc[2] == "low"     # outside region / null proxy


def test_region_with_no_urban_overlap_degrades_to_uniform():
    grid, source = _urban_grid()
    # Urban layer that overlaps neither cell.
    empty_urban = gpd.GeoDataFrame(
        {"sos_code_2021": ["10"], "sosr_name_2021": ["1 million or more"]},
        geometry=[box(50, 50, 51, 51)],
        crs=demand_config.COMPUTATION_CRS,
    )
    weights = compute_cell_weights(grid, empty_urban, source)
    # Both assigned cells carry only the floor -> equal weights.
    assert weights.loc[grid.index[0]] == pytest.approx(demand_config.DEMAND_WEIGHT_FLOOR)
    assert weights.loc[grid.index[1]] == pytest.approx(demand_config.DEMAND_WEIGHT_FLOOR)
    raw = allocate_demand(source, pd.Series({"NSW1": 100.0}), "urban_weighted", weights)
    assert raw.iloc[0] == pytest.approx(50.0, abs=1e-6)
    assert raw.iloc[1] == pytest.approx(50.0, abs=1e-6)


def test_missing_urban_source_raises(tmp_path):
    missing = tmp_path / "does_not_exist.geojson"
    with pytest.raises(RuntimeError, match="missing"):
        load_urban_weights(missing)


def test_compute_cell_weights_is_deterministic():
    grid, source = _urban_grid()
    urban = _urban_layer()
    first = compute_cell_weights(grid, urban, source)
    second = compute_cell_weights(grid, urban, source)
    assert first.equals(second)
