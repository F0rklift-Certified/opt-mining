"""
Tests for the S1-08 integration stage (`pipeline.integration.merge`).

Everything runs against a six-cell synthetic pipeline written to tmp_path —
a grid plus the five upstream feature tables, each with its real layer name,
column names, dtypes and null conventions — wired in by monkeypatching
`pipeline.integration.config`. No network, no rasterio, no real DATA files
except in the opt-in `TestRealDataIntegration` class at the bottom, which
redirects its outputs to tmp_path so the committed products are never
rewritten by a test run.
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

gpd = pytest.importorskip("geopandas")
pytest.importorskip("pyogrio")
from shapely.geometry import box  # noqa: E402

from pipeline.integration import config as icfg  # noqa: E402

STORAGE_CRS = "EPSG:4326"

# ---------------------------------------------------------------------------
# Synthetic upstream layers
# ---------------------------------------------------------------------------

CELL_IDS = [
    "CELL_CLEAN",      # everything present; eligible; inside a REZ
    "CELL_PROTECTED",  # protected area -> excluded
    "CELL_STEEP",      # slope 20 deg -> excluded
    "CELL_NO_GEO",     # outside geographic raster coverage; S1-07 saw no wind
    "CELL_NO_NEM",     # outside every NEM region -> demand_proxy null
    "CELL_PLAIN",      # nothing special; eligible; outside any REZ
]


def _cells():
    """Six 0.05-degree cells in a row along -30.0 latitude."""
    rows = []
    for i, cell_id in enumerate(CELL_IDS):
        lon = 150.95 + 0.05 * i
        lat = -30.0
        rows.append({
            "cell_id": cell_id,
            "centroid_lat": lat,
            "centroid_lon": lon,
            "area_km2": 25.9 + 0.01 * i,
            "geometry": box(lon - 0.025, lat - 0.025, lon + 0.025, lat + 0.025),
        })
    return rows


def _geoms():
    return [c["geometry"] for c in _cells()]


def _write_layer(path: Path, frame: pd.DataFrame, layer: str | None, crs=STORAGE_CRS,
                 geometry=None):
    """Write a GeoPackage layer the way the upstream stages do (with geometry)."""
    gdf = gpd.GeoDataFrame(frame, geometry=geometry if geometry is not None else _geoms(), crs=crs)
    path.parent.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings():
        # Deliberate: the .gpkg.tmp name (mimicking S1-07) and crs=None (a
        # fault-injection case) both make pyogrio warn; that is the point.
        warnings.simplefilter("ignore")
        if layer is None:
            # Mimic pipeline/exclusions/apply.py: tmp file with a .gpkg.tmp
            # suffix, no layer= argument, then os.replace.
            tmp = path.with_suffix(".gpkg.tmp")
            gdf.to_file(tmp, driver="GPKG")
            os.replace(tmp, path)
        else:
            gdf.to_file(path, driver="GPKG", layer=layer)
    return path


def _grid_frame():
    return pd.DataFrame([{k: v for k, v in c.items() if k != "geometry"} for c in _cells()])


def _wind_frame():
    return pd.DataFrame({
        "cell_id": CELL_IDS,
        "wind_speed_100m": pd.Series([7.5, 8.1, 6.9, 7.0, 5.5, 8.4], dtype="float64"),
        "units": ["m/s"] * 6,
        "data_source": ["GWA v4"] * 6,
        "confidence_flag": ["valid"] * 6,
    })


def _geographic_frame():
    return pd.DataFrame({
        "cell_id": CELL_IDS,
        "elevation_m": pd.Series([650.0, 720.0, 900.0, np.nan, 300.0, 410.0], dtype="float64"),
        "slope_deg": pd.Series([3.0, 4.5, 20.0, np.nan, 2.0, 1.5], dtype="float64"),
        "land_use": ["3.2.0 Grazing modified pastures", "1.1.0 Nature conservation",
                     "3.2.0 Grazing modified pastures", None,
                     "3.3.0 Cropping", "3.2.0 Grazing modified pastures"],
        "protected_area": [False, True, False, False, False, False],
        "protected_area_name": ["", "Test Reserve", "", "", "", ""],
        "tri": pd.Series([np.nan, np.nan, 12.0, np.nan, np.nan, np.nan], dtype="float64"),
        "confidence_flag": ["high", "high", "high", "low", "high", "high"],
    })


def _infra_frame():
    return pd.DataFrame({
        "cell_id": CELL_IDS,
        "dist_transmission_km": pd.Series([4.2, 19.7, 5.6, 40.0, 60.5, 12.0], dtype="float64"),
        "dist_substation_km": pd.Series([11.3, 26.4, 8.9, 55.0, 70.2, 15.5], dtype="float64"),
        # AEMO KCI has no coordinates -> entirely null, as in the real product.
        "dist_connection_km": pd.Series([np.nan] * 6, dtype="float64"),
        "inside_rez": [True, False, False, False, False, False],
        "rez_name": ["New England REZ", None, None, None, None, None],
        "confidence_flag": ["low"] * 6,
    })


def _demand_frame():
    return pd.DataFrame({
        "cell_id": CELL_IDS,
        "demand_proxy": pd.Series([1.0, 1.0, 1.0, 1.0, np.nan, 1.0], dtype="float64"),
        "allocation_method": ["uniform"] * 6,
        "source_region": ["NSW1", "NSW1", "NSW1", "NSW1", None, "NSW1"],
        "confidence_flag": ["high", "high", "medium", "high", "low", "high"],
    })


def _exclusions_frame():
    # S1-07 recomputes its own fields from rasters; CELL_NO_GEO deliberately
    # has a null wind sample here although the wind layer has a value, which
    # is exactly the real NE-REZ-clip divergence the cross-layer check reports.
    return pd.DataFrame({
        "cell_id": CELL_IDS,
        "eligible": [True, False, False, False, True, True],
        "exclusion_reason": [None, "Protected area: Test Reserve", "Slope exceeds 15°",
                             "Missing wind data", None, None],
        "triggered_rules": [None, "protected_area", "excessive_slope",
                            "missing_wind_data", None, None],
        "protected_area": [False, True, False, False, False, False],
        "protected_area_name": ["", "Test Reserve", "", "", "", ""],
        "slope_deg": pd.Series([3.0, 4.5, 20.0, np.nan, 2.0, 1.5], dtype="float64"),
        "urban_area": [False] * 6,
        "wind_speed_100m_ms": pd.Series([7.5, 8.1, 6.9, np.nan, 5.5, 8.4], dtype="float64"),
        "data_flags": [None, None, None,
                       "Urban-centre data unavailable outside New England REZ coverage",
                       None, None],
    })


@pytest.fixture
def synthetic_pipeline(tmp_path, monkeypatch):
    """Six cells, six GeoPackages, config redirected to tmp_path."""
    paths = SimpleNamespace(
        grid=tmp_path / "grid" / "nsw_analysis_grid.gpkg",
        wind=tmp_path / "wind" / "wind.gpkg",
        geographic=tmp_path / "geo" / "geo.gpkg",
        infrastructure=tmp_path / "infra" / "infra.gpkg",
        demand=tmp_path / "demand" / "demand.gpkg",
        exclusions=tmp_path / "exclusions" / "optmining_exclusions_2024_nsw.gpkg",
        out_dir=tmp_path / "DATA" / "integration",
        meta_dir=tmp_path / "DATA" / "integration" / "metadata",
    )
    _write_layer(paths.grid, _grid_frame(), icfg.GRID_LAYER)
    _write_layer(paths.wind, _wind_frame(), icfg.WIND_LAYER)
    _write_layer(paths.geographic, _geographic_frame(), icfg.GEOGRAPHIC_LAYER)
    _write_layer(paths.infrastructure, _infra_frame(), icfg.INFRA_LAYER)
    _write_layer(paths.demand, _demand_frame(), icfg.DEMAND_LAYER)
    _write_layer(paths.exclusions, _exclusions_frame(), None)

    monkeypatch.setattr(icfg, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(icfg, "GRID_PATH", paths.grid)
    monkeypatch.setattr(icfg, "WIND_PATH", paths.wind)
    monkeypatch.setattr(icfg, "GEOGRAPHIC_PATH", paths.geographic)
    monkeypatch.setattr(icfg, "INFRA_PATH", paths.infrastructure)
    monkeypatch.setattr(icfg, "DEMAND_PATH", paths.demand)
    monkeypatch.setattr(icfg, "EXCLUSIONS_PATH", paths.exclusions)
    monkeypatch.setattr(icfg, "INTEGRATION_DIR", paths.out_dir)
    monkeypatch.setattr(icfg, "INTEGRATION_META_DIR", paths.meta_dir)
    return paths


# ---------------------------------------------------------------------------
# Layer specs and loaders
# ---------------------------------------------------------------------------


class TestLayerSpecs:
    def test_five_layers_in_join_order_from_config(self, synthetic_pipeline):
        from pipeline.integration.merge import layer_specs

        specs = layer_specs()
        assert [s.name for s in specs] == [
            "wind", "geographic", "infrastructure", "demand", "exclusions",
        ]
        by_name = {s.name: s for s in specs}
        assert by_name["wind"].path == synthetic_pipeline.wind
        assert by_name["wind"].layer == icfg.WIND_LAYER
        assert by_name["wind"].stage == "wind.features"
        assert by_name["wind"].columns == {
            "wind_speed": "wind_speed_100m", "wind_confidence": "confidence_flag",
        }
        assert by_name["exclusions"].path == synthetic_pipeline.exclusions
        assert by_name["exclusions"].layer is None
        assert by_name["exclusions"].stage == "exclusions"
        assert set(by_name["exclusions"].columns) == {
            "eligible", "exclusion_reason", "triggered_rules", "data_flags",
        }
        assert by_name["geographic"].columns["geo_confidence"] == "confidence_flag"
        assert by_name["infrastructure"].columns["infra_confidence"] == "confidence_flag"
        assert by_name["demand"].columns["demand_confidence"] == "confidence_flag"
        assert by_name["wind"].enum_checks == {"wind_confidence": icfg.WIND_CONFIDENCE_LEVELS}


class TestReadGrid:
    def test_returns_geometry_centroids_and_info(self, synthetic_pipeline):
        from pipeline.integration.merge import read_grid

        grid, info = read_grid(synthetic_pipeline.grid, icfg.GRID_LAYER)
        assert isinstance(grid, gpd.GeoDataFrame)
        assert list(grid["cell_id"]) == CELL_IDS
        for col in ("centroid_lat", "centroid_lon", "area_km2", "geometry"):
            assert col in grid.columns
        assert str(grid.crs) == STORAGE_CRS
        assert info["rows"] == 6
        assert info["crs"] == STORAGE_CRS
        assert info["layer"] == icfg.GRID_LAYER
        assert info["path"] == synthetic_pipeline.grid
        assert len(info["sha256"]) == 64
        assert info["bytes"] == synthetic_pipeline.grid.stat().st_size

    def test_missing_grid_names_the_grid_stage(self, synthetic_pipeline):
        from pipeline.integration.merge import read_grid

        with pytest.raises(FileNotFoundError, match=r"--only grid"):
            read_grid(synthetic_pipeline.grid.with_name("nope.gpkg"), icfg.GRID_LAYER)


class TestReadLayer:
    def test_reads_attributes_without_geometry(self, synthetic_pipeline):
        from pipeline.integration.merge import read_layer

        frame, info = read_layer(
            synthetic_pipeline.wind, icfg.WIND_LAYER, stage="wind.features",
            required_columns=("wind_speed_100m", "confidence_flag"),
        )
        assert not isinstance(frame, gpd.GeoDataFrame)
        assert "geometry" not in frame.columns
        assert list(frame["cell_id"]) == CELL_IDS
        assert frame["wind_speed_100m"].dtype == "float64"
        assert info["rows"] == 6 and info["crs"] == STORAGE_CRS
        assert info["layer"] == icfg.WIND_LAYER

    def test_missing_input_names_producing_stage(self, synthetic_pipeline):
        from pipeline.integration.merge import read_layer

        with pytest.raises(FileNotFoundError, match=r"--only demand\.feature"):
            read_layer(synthetic_pipeline.demand.with_name("missing.gpkg"),
                       icfg.DEMAND_LAYER, stage="demand.feature")

    def test_duplicate_cell_id_raises(self, synthetic_pipeline, tmp_path):
        from pipeline.integration.merge import read_layer

        frame = _wind_frame()
        frame.loc[1, "cell_id"] = "CELL_CLEAN"
        path = _write_layer(tmp_path / "dup.gpkg", frame, "wind_features")
        with pytest.raises(ValueError, match="duplicate"):
            read_layer(path, "wind_features", stage="wind.features")

    def test_missing_cell_id_column_raises(self, synthetic_pipeline, tmp_path):
        from pipeline.integration.merge import read_layer

        frame = _wind_frame().rename(columns={"cell_id": "id"})
        path = _write_layer(tmp_path / "noid.gpkg", frame, "wind_features")
        with pytest.raises(ValueError, match="cell_id"):
            read_layer(path, "wind_features", stage="wind.features")

    def test_null_cell_id_raises(self, synthetic_pipeline, tmp_path):
        from pipeline.integration.merge import read_layer

        frame = _wind_frame()
        frame.loc[2, "cell_id"] = None
        path = _write_layer(tmp_path / "nullid.gpkg", frame, "wind_features")
        with pytest.raises(ValueError, match="null"):
            read_layer(path, "wind_features", stage="wind.features")

    def test_crs_mismatch_raises_instead_of_reprojecting(self, synthetic_pipeline, tmp_path):
        from pipeline.integration.merge import read_layer

        projected = gpd.GeoSeries(_geoms(), crs=STORAGE_CRS).to_crs("EPSG:3577")
        path = _write_layer(tmp_path / "proj.gpkg", _wind_frame(), "wind_features",
                            crs="EPSG:3577", geometry=list(projected))
        with pytest.raises(ValueError, match=r"EPSG:3577.*reproject"):
            read_layer(path, "wind_features", stage="wind.features")

    def test_undeclared_crs_raises(self, synthetic_pipeline, tmp_path):
        from pipeline.integration.merge import read_layer

        path = _write_layer(tmp_path / "nocrs.gpkg", _wind_frame(), "wind_features", crs=None)
        with pytest.raises(ValueError, match="no declared CRS"):
            read_layer(path, "wind_features", stage="wind.features")

    def test_missing_source_column_names_layer_and_column(self, synthetic_pipeline):
        from pipeline.integration.merge import read_layer

        with pytest.raises(ValueError, match=r"wind_features.*not_a_column"):
            read_layer(synthetic_pipeline.wind, icfg.WIND_LAYER, stage="wind.features",
                       required_columns=("wind_speed_100m", "not_a_column"))

    def test_exclusions_single_layer_is_autodetected(self, synthetic_pipeline):
        from pipeline.integration.merge import read_layer

        frame, info = read_layer(synthetic_pipeline.exclusions, None, stage="exclusions",
                                 required_columns=("eligible", "exclusion_reason"))
        assert list(frame["cell_id"]) == CELL_IDS
        assert frame["eligible"].tolist() == [True, False, False, False, True, True]
        assert info["layer"]  # whatever GDAL named it; must be reported, not guessed

    def test_multi_layer_file_with_autodetect_raises(self, synthetic_pipeline, tmp_path):
        from pipeline.integration.merge import read_layer

        path = tmp_path / "two.gpkg"
        _write_layer(path, _wind_frame(), "first")
        _write_layer(path, _wind_frame(), "second")
        with pytest.raises(ValueError, match="2 layers"):
            read_layer(path, None, stage="exclusions")


# ---------------------------------------------------------------------------
# Merge core
# ---------------------------------------------------------------------------

EXPECTED_OUTPUT_COLUMNS = [
    "cell_id", "centroid_lat", "centroid_lon", "area_km2",
    "wind_speed", "wind_confidence",
    "demand_proxy", "source_region", "demand_confidence",
    "dist_transmission_km", "dist_substation_km", "dist_connection_km",
    "inside_rez", "rez_name", "infra_confidence",
    "elevation_m", "slope_deg", "tri", "land_use", "protected_area",
    "protected_area_name", "geo_confidence",
    "eligible", "exclusion_reason", "triggered_rules", "data_flags",
    "n_missing_features",
]
EXPECTED_SCORED = (
    "wind_speed", "demand_proxy", "dist_transmission_km", "dist_substation_km",
    "dist_connection_km", "inside_rez", "elevation_m", "slope_deg", "land_use",
    "protected_area",
)
# Nulls among the ten scored columns per synthetic cell (dist_connection_km is
# null everywhere; CELL_NO_GEO also lacks elevation/slope/land_use; CELL_NO_NEM
# lacks demand_proxy).
EXPECTED_N_MISSING = [1, 1, 1, 4, 2, 1]


def _in_memory_inputs():
    """Grid GeoDataFrame + the five attribute frames, no file I/O."""
    grid = gpd.GeoDataFrame(_grid_frame(), geometry=_geoms(), crs=STORAGE_CRS)
    layers = {
        "wind": _wind_frame(),
        "geographic": _geographic_frame(),
        "infrastructure": _infra_frame(),
        "demand": _demand_frame(),
        "exclusions": _exclusions_frame(),
    }
    return grid, layers


def _merge(grid=None, layers=None):
    from pipeline.integration.merge import layer_specs, merge_layers

    if grid is None or layers is None:
        grid, layers = _in_memory_inputs()
    return merge_layers(grid, layers, layer_specs())


class TestSchema:
    def test_output_columns_exact_order(self):
        from pipeline.integration.merge import OUTPUT_COLUMNS, SCORED_FEATURE_COLUMNS

        assert list(OUTPUT_COLUMNS) == EXPECTED_OUTPUT_COLUMNS
        assert "geometry" not in OUTPUT_COLUMNS
        assert tuple(SCORED_FEATURE_COLUMNS) == EXPECTED_SCORED
        assert set(SCORED_FEATURE_COLUMNS) <= set(OUTPUT_COLUMNS)


class TestMergeLayers:
    def test_preserves_count_set_and_order(self):
        merged, _ = _merge()
        assert isinstance(merged, gpd.GeoDataFrame)
        assert str(merged.crs) == STORAGE_CRS
        assert len(merged) == 6
        assert list(merged["cell_id"]) == CELL_IDS
        assert list(merged.columns) == EXPECTED_OUTPUT_COLUMNS + ["geometry"]

    def test_values_land_in_ticket_named_columns(self):
        merged, _ = _merge()
        row = merged.set_index("cell_id")
        assert row.loc["CELL_CLEAN", "wind_speed"] == 7.5
        assert row.loc["CELL_CLEAN", "wind_confidence"] == "valid"
        assert row.loc["CELL_CLEAN", "centroid_lon"] == pytest.approx(150.95)
        assert row.loc["CELL_CLEAN", "inside_rez"] == True  # noqa: E712
        assert row.loc["CELL_CLEAN", "rez_name"] == "New England REZ"
        assert row.loc["CELL_NO_GEO", "geo_confidence"] == "low"
        assert pd.isna(row.loc["CELL_NO_GEO", "elevation_m"])
        assert row.loc["CELL_PROTECTED", "eligible"] == False  # noqa: E712
        assert "Protected area" in row.loc["CELL_PROTECTED", "exclusion_reason"]
        assert row.loc["CELL_PROTECTED", "protected_area"] == True  # noqa: E712
        assert row.loc["CELL_PLAIN", "protected_area_name"] == ""
        assert row.loc["CELL_NO_NEM", "demand_confidence"] == "low"
        assert pd.isna(row.loc["CELL_NO_NEM", "demand_proxy"])

    def test_constant_and_duplicate_upstream_columns_not_carried(self):
        merged, _ = _merge()
        for col in ("units", "data_source", "allocation_method", "confidence_flag",
                    "wind_speed_100m", "urban_area", "wind_speed_100m_ms"):
            assert col not in merged.columns, col

    def test_n_missing_features_arithmetic(self):
        merged, _ = _merge()
        assert merged["n_missing_features"].tolist() == EXPECTED_N_MISSING
        assert merged["n_missing_features"].dtype == "int64"

    def test_join_log_shows_nulls_preserved(self):
        _, log = _merge()
        assert [e["layer"] for e in log] == [
            "wind", "geographic", "infrastructure", "demand", "exclusions",
        ]
        for entry in log:
            assert entry["rows_before"] == entry["rows_after"] == 6
            assert entry["cell_ids_missing_from_upstream"] == 0
            assert entry["cell_ids_extra_in_upstream"] == 0
            assert entry["null_counts_after"] == entry["null_counts_upstream"]
        geo = next(e for e in log if e["layer"] == "geographic")
        assert geo["null_counts_upstream"]["elevation_m"] == 1
        assert geo["null_counts_upstream"]["tri"] == 5

    def test_upstream_missing_cell_yields_null_and_is_logged(self):
        grid, layers = _in_memory_inputs()
        layers["wind"] = layers["wind"][layers["wind"]["cell_id"] != "CELL_PLAIN"]
        merged, log = _merge(grid, layers)
        assert len(merged) == 6
        assert list(merged["cell_id"]) == CELL_IDS
        assert pd.isna(merged.set_index("cell_id").loc["CELL_PLAIN", "wind_speed"])
        wind = next(e for e in log if e["layer"] == "wind")
        assert wind["cell_ids_missing_from_upstream"] == 1
        assert wind["null_counts_upstream"]["wind_speed"] == 0
        assert wind["null_counts_after"]["wind_speed"] == 1  # the inflation validate() flags

    def test_upstream_extra_cell_is_dropped_by_left_join(self):
        grid, layers = _in_memory_inputs()
        extra = layers["demand"].iloc[[0]].assign(cell_id="CELL_X")
        layers["demand"] = pd.concat([layers["demand"], extra], ignore_index=True)
        merged, log = _merge(grid, layers)
        assert len(merged) == 6 and "CELL_X" not in set(merged["cell_id"])
        assert next(e for e in log if e["layer"] == "demand")["cell_ids_extra_in_upstream"] == 1

    def test_duplicate_key_in_upstream_raises_naming_layer(self):
        grid, layers = _in_memory_inputs()
        dup = layers["demand"].iloc[[1]]
        layers["demand"] = pd.concat([layers["demand"], dup], ignore_index=True)
        with pytest.raises(RuntimeError, match="demand"):
            _merge(grid, layers)

    def test_bool_with_nulls_becomes_nullable_boolean(self):
        grid, layers = _in_memory_inputs()
        layers["infrastructure"]["inside_rez"] = pd.array(
            [True, False, None, False, False, False], dtype="boolean",
        )
        merged, _ = _merge(grid, layers)
        assert str(merged["inside_rez"].dtype) == "boolean"
        assert pd.isna(merged.set_index("cell_id").loc["CELL_STEEP", "inside_rez"])
        assert merged["n_missing_features"].tolist() == [1, 1, 2, 4, 2, 1]

    def test_bool_without_nulls_stays_numpy_bool(self):
        merged, _ = _merge()
        for col in ("inside_rez", "protected_area", "eligible"):
            assert merged[col].dtype == bool, col


class TestComputeNMissingFeatures:
    def test_counts_only_scored_columns(self):
        from pipeline.integration.merge import compute_n_missing_features

        frame = pd.DataFrame({
            "wind_speed": [1.0, np.nan],
            "demand_proxy": [np.nan, np.nan],
            "dist_transmission_km": [1.0, 1.0],
            "dist_substation_km": [1.0, 1.0],
            "dist_connection_km": [np.nan, np.nan],
            "inside_rez": [True, False],
            "elevation_m": [1.0, 1.0],
            "slope_deg": [1.0, np.nan],
            "land_use": ["a", None],
            "protected_area": [False, False],
            "tri": [np.nan, np.nan],              # not scored: ignored
            "protected_area_name": ["", ""],      # "" is not missing
            "rez_name": [None, None],             # not scored: ignored
        })
        assert compute_n_missing_features(frame).tolist() == [2, 5]


# ---------------------------------------------------------------------------
# Property-based tests (hypothesis)
# ---------------------------------------------------------------------------

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings, strategies as st  # noqa: E402

_perm6 = st.permutations(list(range(6)))
_mask6 = st.lists(st.booleans(), min_size=6, max_size=6)


class TestMergeProperties:
    # Feature: s1-08-create-integrated-nsw-feature-table, Property 1: the
    # integrated table keeps the grid's row count, cell_id set and order,
    # and every cell's values, whatever order the upstream layers arrive in.
    @settings(max_examples=100, deadline=None)
    @given(perms=st.lists(_perm6, min_size=5, max_size=5))
    def test_property_1_order_independent_of_upstream_row_order(self, perms):
        grid, layers = _in_memory_inputs()
        reference, _ = _merge(grid, layers)
        for (name, frame), perm in zip(list(layers.items()), perms):
            layers[name] = frame.iloc[perm].reset_index(drop=True)
        merged, _ = _merge(grid, layers)
        assert list(merged["cell_id"]) == CELL_IDS
        pd.testing.assert_frame_equal(
            merged.drop(columns="geometry"), reference.drop(columns="geometry"),
        )

    # Feature: s1-08-create-integrated-nsw-feature-table, Property 2: per-column
    # null counts after the join equal the upstream null counts (no inflation,
    # no back-filling) for any pattern of upstream nulls.
    @settings(max_examples=100, deadline=None)
    @given(wind=_mask6, elev=_mask6, dist=_mask6, dem=_mask6)
    def test_property_2_null_counts_preserved(self, wind, elev, dist, dem):
        grid, layers = _in_memory_inputs()
        layers["wind"].loc[wind, "wind_speed_100m"] = np.nan
        layers["geographic"].loc[elev, "elevation_m"] = np.nan
        layers["infrastructure"].loc[dist, "dist_transmission_km"] = np.nan
        layers["demand"].loc[dem, "demand_proxy"] = np.nan
        # Expected = nulls in the (masked) upstream frame, which already
        # contains the fixture's own nulls; the mask may overlap them.
        expected = {
            "wind_speed": int(layers["wind"]["wind_speed_100m"].isna().sum()),
            "elevation_m": int(layers["geographic"]["elevation_m"].isna().sum()),
            "dist_transmission_km": int(layers["infrastructure"]["dist_transmission_km"].isna().sum()),
            "demand_proxy": int(layers["demand"]["demand_proxy"].isna().sum()),
        }
        merged, log = _merge(grid, layers)
        observed = {col: int(merged[col].isna().sum()) for col in expected}
        assert observed == expected
        for entry in log:
            assert entry["null_counts_after"] == entry["null_counts_upstream"]

    # Feature: s1-08-create-integrated-nsw-feature-table, Property 3:
    # n_missing_features equals the row-wise count of nulls over exactly the
    # scored feature columns.
    @settings(max_examples=100, deadline=None)
    @given(wind=_mask6, elev=_mask6, land=_mask6, dem=_mask6)
    def test_property_3_n_missing_equals_recount(self, wind, elev, land, dem):
        from pipeline.integration.merge import SCORED_FEATURE_COLUMNS

        grid, layers = _in_memory_inputs()
        layers["wind"].loc[wind, "wind_speed_100m"] = np.nan
        layers["geographic"].loc[elev, "elevation_m"] = np.nan
        layers["geographic"].loc[land, "land_use"] = None
        layers["demand"].loc[dem, "demand_proxy"] = np.nan
        merged, _ = _merge(grid, layers)
        recount = merged[list(SCORED_FEATURE_COLUMNS)].isna().sum(axis=1)
        assert merged["n_missing_features"].tolist() == recount.tolist()


# ---------------------------------------------------------------------------
# Validation — no silent passes
# ---------------------------------------------------------------------------

CHECK_KEYS = {"name", "expected", "observed", "passed", "severity"}


def _load_all():
    """Read grid + five layers from the synthetic files (with info dicts)."""
    from pipeline.integration.merge import (
        EXCLUSIONS_CROSS_CHECK_COLUMNS, layer_specs, read_grid, read_layer,
    )

    grid, grid_info = read_grid(icfg.GRID_PATH, icfg.GRID_LAYER)
    layers, infos = {}, {"grid": grid_info}
    for spec in layer_specs():
        required = spec.source_columns
        if spec.name == "exclusions":
            required = required + EXCLUSIONS_CROSS_CHECK_COLUMNS
        layers[spec.name], infos[spec.name] = read_layer(
            spec.path, spec.layer, stage=spec.stage, required_columns=required,
        )
    return grid, layers, infos


def _validated(mutate_table=None, mutate_layers=None):
    """Merge the synthetic pipeline, optionally tamper, and validate."""
    from pipeline.integration.merge import layer_specs, merge_layers, validate

    grid, layers, infos = _load_all()
    if mutate_layers:
        mutate_layers(layers)
    specs = layer_specs()
    table, log = merge_layers(grid, layers, specs)
    if mutate_table:
        table = mutate_table(table)
    return validate(table, grid, layers, log, specs, infos)


def _check(result, name):
    matches = [c for c in result["checks"] if c["name"] == name]
    assert len(matches) == 1, f"expected exactly one {name!r} check, got {matches}"
    return matches[0]


def _assert_failed(check):
    assert check["passed"] is False
    assert isinstance(check["expected"], str) and check["expected"] != ""
    assert isinstance(check["observed"], str) and check["observed"] != ""


class TestValidate:
    def test_clean_merge_passes_every_fatal_check(self, synthetic_pipeline):
        result = _validated()
        assert result["failed"] == 0
        assert result["total"] == result["passed"] + result["failed"] + result["warnings"]
        for check in result["checks"]:
            assert set(check) == CHECK_KEYS, check
            assert check["severity"] in {"fatal", "warn"}
            assert isinstance(check["expected"], str) and check["expected"]
            assert isinstance(check["observed"], str) and check["observed"]
        fatal_names = [c["name"] for c in result["checks"] if c["severity"] == "fatal"]
        for expected in (
            "grid: CRS equals storage CRS",
            "wind: CRS equals storage CRS",
            "exclusions: cell_id set matches grid",
            "demand: row count unchanged after left join",
            "geographic: null counts preserved for joined columns",
            "row count equals grid cell count",
            "cell_id unique",
            "cell_id order preserved from grid",
            "geometry identical to grid",
            "output CRS is storage CRS",
            "output columns match OUTPUT_COLUMNS",
            "eligible is boolean with no nulls",
            "eligible/exclusion_reason consistent",
            "n_missing_features equals recount over scored columns",
            "wind_confidence within vocabulary",
            "demand_confidence within vocabulary",
        ):
            assert expected in fatal_names, expected

    def test_cross_layer_checks_are_warn_and_report_the_known_wind_divergence(
        self, synthetic_pipeline,
    ):
        result = _validated()
        warn = [c for c in result["checks"] if c["severity"] == "warn"]
        assert [c["name"] for c in warn] == [
            "cross-layer: exclusions.protected_area == geographic.protected_area",
            "cross-layer: exclusions.slope_deg ~ geographic.slope_deg",
            "cross-layer: exclusions.wind_speed_100m_ms ~ wind.wind_speed",
            "cross-layer: exclusions.protected_area_name == geographic.protected_area_name",
        ]
        wind = _check(result, "cross-layer: exclusions.wind_speed_100m_ms ~ wind.wind_speed")
        _assert_failed(wind)
        # CELL_NO_GEO: S1-07 sampled no wind, the wind layer has 7.0 m/s.
        assert "1 null-pattern mismatch" in wind["observed"]
        assert "0 value mismatches of 5" in wind["observed"]
        assert result["warnings"] == 1  # only that one; never counted as failed
        assert result["failed"] == 0
        for name in (
            "cross-layer: exclusions.protected_area == geographic.protected_area",
            "cross-layer: exclusions.slope_deg ~ geographic.slope_deg",
            "cross-layer: exclusions.protected_area_name == geographic.protected_area_name",
        ):
            assert _check(result, name)["passed"] is True

    def test_cross_layer_value_mismatch_counted(self, synthetic_pipeline):
        def tamper(layers):
            excl = layers["exclusions"]
            excl.loc[excl["cell_id"] == "CELL_PLAIN", "protected_area"] = True
            excl.loc[excl["cell_id"] == "CELL_PLAIN", "protected_area_name"] = "Zed; Alpha"
            excl.loc[excl["cell_id"] == "CELL_CLEAN", "slope_deg"] = 3.0 + 0.2

        result = _validated(mutate_layers=tamper)
        pa = _check(result, "cross-layer: exclusions.protected_area == geographic.protected_area")
        _assert_failed(pa)
        assert pa["observed"] == "1 mismatches of 6 compared"
        names = _check(result, "cross-layer: exclusions.protected_area_name == geographic.protected_area_name")
        assert names["observed"] == "1 mismatches of 6 compared"
        slope = _check(result, "cross-layer: exclusions.slope_deg ~ geographic.slope_deg")
        assert "1 value mismatches of 5" in slope["observed"]
        assert result["failed"] == 0 and result["warnings"] == 4

    def test_missing_upstream_cell_reports_set_and_null_inflation(self, synthetic_pipeline):
        def drop_cell(layers):
            layers["wind"] = layers["wind"][layers["wind"]["cell_id"] != "CELL_PLAIN"]

        result = _validated(mutate_layers=drop_cell)
        ids = _check(result, "wind: cell_id set matches grid")
        _assert_failed(ids)
        assert ids["observed"] == "1 missing, 0 extra"
        nulls = _check(result, "wind: null counts preserved for joined columns")
        _assert_failed(nulls)
        assert "wind_speed 0->1" in nulls["observed"]
        # The dropped cell also has no confidence flag, which is outside the
        # wind vocabulary — a third, independent fatal signal.
        vocab = _check(result, "wind_confidence within vocabulary")
        _assert_failed(vocab)
        assert vocab["observed"].startswith("1 rows outside")
        assert result["failed"] == 3

    def test_eligible_reason_inconsistency_detected(self, synthetic_pipeline):
        def tamper(table):
            table.loc[table["cell_id"] == "CELL_CLEAN", "exclusion_reason"] = "oops"
            return table

        check = _check(_validated(mutate_table=tamper), "eligible/exclusion_reason consistent")
        _assert_failed(check)
        assert check["observed"] == "1 inconsistent rows"

    def test_confidence_vocabulary_violation_detected(self, synthetic_pipeline):
        def tamper(layers):
            layers["demand"].loc[0, "confidence_flag"] = "unknown"

        check = _check(_validated(mutate_layers=tamper), "demand_confidence within vocabulary")
        _assert_failed(check)
        assert check["observed"] == "1 rows outside ('high', 'medium', 'low')"

    def test_order_tampering_detected(self, synthetic_pipeline):
        result = _validated(mutate_table=lambda t: t.iloc[::-1].reset_index(drop=True))
        order = _check(result, "cell_id order preserved from grid")
        _assert_failed(order)
        assert order["observed"] == "first divergence at row 0"

    def test_geometry_tampering_detected(self, synthetic_pipeline):
        def tamper(table):
            geoms = list(table.geometry)
            geoms[0], geoms[1] = geoms[1], geoms[0]
            return table.set_geometry(gpd.GeoSeries(geoms, crs=table.crs))

        check = _check(_validated(mutate_table=tamper), "geometry identical to grid")
        _assert_failed(check)
        assert check["observed"] == "2 differing cells"

    def test_duplicate_row_detected_by_count_and_uniqueness(self, synthetic_pipeline):
        result = _validated(
            mutate_table=lambda t: pd.concat([t, t.iloc[[0]]], ignore_index=True)
        )
        rows = _check(result, "row count equals grid cell count")
        _assert_failed(rows)
        assert rows["observed"] == "7 rows"
        dup = _check(result, "cell_id unique")
        _assert_failed(dup)
        assert dup["observed"] == "1 duplicates"

    def test_n_missing_recount_detected(self, synthetic_pipeline):
        def tamper(table):
            table.loc[2, "n_missing_features"] = 99
            return table

        check = _check(_validated(mutate_table=tamper),
                       "n_missing_features equals recount over scored columns")
        _assert_failed(check)
        assert check["observed"] == "1 rows differ"

    def test_missing_output_column_detected(self, synthetic_pipeline):
        check = _check(_validated(mutate_table=lambda t: t.drop(columns=["tri"])),
                       "output columns match OUTPUT_COLUMNS")
        _assert_failed(check)
        assert "missing ['tri']" in check["observed"]

    def test_null_eligible_detected(self, synthetic_pipeline):
        def tamper(layers):
            layers["exclusions"]["eligible"] = pd.array(
                [True, False, None, False, True, True], dtype="boolean",
            )

        check = _check(_validated(mutate_layers=tamper), "eligible is boolean with no nulls")
        _assert_failed(check)
        assert check["observed"].startswith("1 nulls")


class TestValidateProperties:
    # Feature: s1-08-create-integrated-nsw-feature-table, Property 4: the
    # eligible/exclusion_reason consistency check counts exactly the rows
    # made inconsistent, for any subset of rows.
    @settings(max_examples=100, deadline=None)
    @given(mask=_mask6)
    def test_property_4_consistency_check_counts_injected_rows(self, mask):
        from pipeline.integration.merge import layer_specs, merge_layers, validate

        grid, layers = _in_memory_inputs()
        specs = layer_specs()
        table, log = merge_layers(grid, layers, specs)
        for i, flip in enumerate(mask):
            if not flip:
                continue
            if bool(table.loc[i, "eligible"]):
                table.loc[i, "exclusion_reason"] = "injected"
            else:
                table.loc[i, "exclusion_reason"] = None
        result = validate(table, grid, layers, log, specs, infos=None)
        check = _check(result, "eligible/exclusion_reason consistent")
        assert check["observed"] == f"{sum(mask)} inconsistent rows"
        assert check["passed"] is (sum(mask) == 0)


# ---------------------------------------------------------------------------
# Writers, reports, provenance
# ---------------------------------------------------------------------------


def _merged_from_files():
    from pipeline.integration.merge import layer_specs, merge_layers, validate

    grid, layers, infos = _load_all()
    specs = layer_specs()
    table, log = merge_layers(grid, layers, specs)
    result = validate(table, grid, layers, log, specs, infos)
    return table, grid, layers, log, specs, infos, result


class TestWriters:
    def test_write_gpkg_uses_named_layer_and_leaves_no_tmp(self, synthetic_pipeline, tmp_path):
        import pyogrio
        from pipeline.integration.merge import write_gpkg

        table, *_ = _merged_from_files()
        path = tmp_path / "out" / "integrated.gpkg"
        write_gpkg(table, path)
        assert [str(r[0]) for r in pyogrio.list_layers(path)] == [icfg.OUTPUT_LAYER]
        assert list(path.parent.glob("*_tmp*")) == []
        back = gpd.read_file(path, layer=icfg.OUTPUT_LAYER)
        assert len(back) == 6 and str(back.crs) == STORAGE_CRS
        assert list(back["cell_id"]) == CELL_IDS
        assert back["eligible"].dtype == bool

    def test_write_gpkg_round_trips_nullable_boolean(self, synthetic_pipeline, tmp_path):
        from pipeline.integration.merge import layer_specs, merge_layers, write_gpkg

        grid, layers = _in_memory_inputs()
        layers["infrastructure"]["inside_rez"] = pd.array(
            [True, False, None, False, False, False], dtype="boolean",
        )
        table, _ = merge_layers(grid, layers, layer_specs())
        path = tmp_path / "nullable.gpkg"
        write_gpkg(table, path)
        back = gpd.read_file(path, layer=icfg.OUTPUT_LAYER).set_index("cell_id")
        assert pd.isna(back.loc["CELL_STEEP", "inside_rez"])
        assert bool(back.loc["CELL_CLEAN", "inside_rez"]) is True
        assert bool(back.loc["CELL_PLAIN", "inside_rez"]) is False

    def test_write_csv_drops_geometry_and_round_trips_values(self, synthetic_pipeline, tmp_path):
        from pipeline.integration.merge import OUTPUT_COLUMNS, write_csv

        table, *_ = _merged_from_files()
        path = tmp_path / "out" / "integrated.csv"
        write_csv(table, path)
        assert list(path.parent.glob("*_tmp*")) == []
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")
        assert lines[0] == ",".join(OUTPUT_COLUMNS)
        assert len([ln for ln in lines if ln]) == 7  # header + 6 rows
        assert "geometry" not in lines[0]
        assert "<NA>" not in text and "nan" not in text.lower().split("\n")[1:][0]
        back = pd.read_csv(path)
        assert list(back.columns) == OUTPUT_COLUMNS
        assert back["wind_speed"].tolist() == table["wind_speed"].tolist()
        assert back["centroid_lon"].tolist() == table["centroid_lon"].tolist()
        assert back["dist_connection_km"].isna().all()
        assert back["eligible"].dtype == bool
        assert back["eligible"].tolist() == table["eligible"].tolist()
        # A ", "-joined reason must survive quoting.
        by_id = back.set_index("cell_id")
        assert by_id.loc["CELL_PROTECTED", "exclusion_reason"] == "Protected area: Test Reserve"
        assert by_id.loc["CELL_NO_GEO", "data_flags"].startswith("Urban-centre")

    def test_write_csv_renders_nullable_boolean_null_as_empty(self, synthetic_pipeline, tmp_path):
        from pipeline.integration.merge import layer_specs, merge_layers, write_csv

        grid, layers = _in_memory_inputs()
        layers["infrastructure"]["inside_rez"] = pd.array(
            [True, False, None, False, False, False], dtype="boolean",
        )
        table, _ = merge_layers(grid, layers, layer_specs())
        path = tmp_path / "nullable.csv"
        write_csv(table, path)
        rows = path.read_text(encoding="utf-8").split("\n")
        assert "<NA>" not in "\n".join(rows)
        steep = next(r for r in rows if r.startswith("CELL_STEEP"))
        cols = rows[0].split(",")
        assert steep.split(",")[cols.index("inside_rez")] == ""
        clean = next(r for r in rows if r.startswith("CELL_CLEAN"))
        assert clean.split(",")[cols.index("inside_rez")] == "True"

    def test_verify_written_reports_read_back_counts(self, synthetic_pipeline, tmp_path):
        from pipeline.integration.merge import verify_written, write_csv, write_gpkg

        table, *_ = _merged_from_files()
        gpkg, csv = tmp_path / "t.gpkg", tmp_path / "t.csv"
        write_gpkg(table, gpkg)
        write_csv(table, csv)
        checks = verify_written(gpkg, csv, n_expected=6)
        assert [c["name"] for c in checks] == [
            "GeoPackage read-back row count",
            "CSV read-back row count",
            "CSV columns match OUTPUT_COLUMNS without geometry",
        ]
        assert all(c["passed"] and c["severity"] == "fatal" for c in checks)
        assert checks[0]["observed"] == "6 rows"
        # Truncate the CSV: the read-back check must catch it.
        lines = csv.read_text(encoding="utf-8").split("\n")
        csv.write_text("\n".join(lines[:-2]) + "\n", encoding="utf-8")
        tampered = verify_written(gpkg, csv, n_expected=6)
        assert tampered[1]["passed"] is False and tampered[1]["observed"] == "5 rows"


class TestGitCommit:
    def test_returns_hash_inside_repo_and_unknown_outside(self, tmp_path):
        from pipeline.integration.merge import git_commit

        here = git_commit(Path(__file__).resolve().parent)
        assert here == "unknown" or len(here.split("-")[0]) >= 7
        assert git_commit(tmp_path) == "unknown"

    def test_dirty_suffix_tracks_tracked_changes_not_untracked_outputs(self, tmp_path):
        # A stage run creates untracked output files; that must not mark the
        # code commit as dirty. Only modified tracked files do.
        import subprocess
        from pipeline.integration.merge import git_commit

        def git(*args):
            subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True,
                           env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                                "PATH": os.environ["PATH"], "HOME": str(tmp_path)})

        git("init", "-q")
        (tmp_path / "tracked.txt").write_text("v1\n")
        git("add", "tracked.txt")
        git("commit", "-q", "-m", "init")
        clean = git_commit(tmp_path)
        assert len(clean) == 40 and "-dirty" not in clean
        (tmp_path / "untracked_output.csv").write_text("a,b\n")
        assert git_commit(tmp_path) == clean
        (tmp_path / "tracked.txt").write_text("v2\n")
        assert git_commit(tmp_path) == clean + "-dirty"


class TestReports:
    def test_method_report_contents(self, synthetic_pipeline, tmp_path):
        from pipeline.integration.merge import build_method_report

        table, grid, layers, log, specs, infos, result = _merged_from_files()
        report = build_method_report(
            table=table, infos=infos, specs=specs, join_log=log, result=result,
            runtime_s=1.234, generated_utc="2026-09-03T00:00:00+00:00",
            git_commit="abc1234",
            outputs={"gpkg": tmp_path / "a.gpkg", "csv": tmp_path / "a.csv",
                     "validation_report": tmp_path / "merge_validation.md"},
        )
        assert "pipeline.integration.merge" in report
        assert "Do not edit by hand" in report
        assert "| wind_speed | wind.wind_speed_100m |" in report
        assert "| geo_confidence | geographic.confidence_flag |" in report
        assert infos["wind"]["sha256"] in report
        assert "abc1234" in report
        assert "2026-09-03T00:00:00+00:00" in report
        assert "1.234" in report
        assert "data_confidence" in report and "S1-09" in report
        assert "n_missing_features" in report
        assert "Eligible" in report and "3" in report  # 3 eligible of 6
        assert "| 4 | 1 |" in report  # histogram row: 4 missing -> 1 cell
        assert "merge_validation.md" in report
        assert "CSV" in report and "deterministic" in report

    def test_validation_report_lists_every_check_with_status(self, synthetic_pipeline):
        from pipeline.integration.merge import build_validation_report

        *_, result = _merged_from_files()
        report = build_validation_report(result, generated_utc="2026-09-03T00:00:00+00:00")
        assert "pipeline.integration.merge" in report
        for check in result["checks"]:
            assert check["name"] in report
        assert "| PASS |" in report
        assert "| WARN |" in report  # the known wind divergence
        assert "**FAIL**" not in report
        assert f"{result['passed']}/{result['total']}" in report


class TestProvenance:
    def test_manifest_and_provenance_are_idempotent(self, synthetic_pipeline, tmp_path):
        from pipeline.integration.merge import (
            PROVENANCE_BEGIN, PROVENANCE_END, record_provenance, write_csv, write_gpkg,
        )

        table, grid, layers, log, specs, infos, result = _merged_from_files()
        gpkg, csv = synthetic_pipeline.out_dir / "t.gpkg", synthetic_pipeline.out_dir / "t.csv"
        write_gpkg(table, gpkg)
        write_csv(table, csv)
        manifest = synthetic_pipeline.meta_dir / "integration_manifest.json"
        provenance = synthetic_pipeline.out_dir / "DATA_PROVENANCE.md"
        provenance.parent.mkdir(parents=True, exist_ok=True)
        provenance.write_text("# Handwritten header\n\nKeep me.\n", encoding="utf-8")

        for _ in range(2):
            record = record_provenance(
                gpkg_path=gpkg, csv_path=csv, table=table, infos=infos,
                generated_utc="2026-09-03T00:00:00+00:00", git_commit="abc1234",
                manifest_path=manifest, provenance_path=provenance,
            )

        import json
        data = json.loads(manifest.read_text(encoding="utf-8"))
        assert len(data["derived_features"]) == 1
        entry = data["derived_features"][0]
        assert entry == record
        for key in ("output_file", "csv_file", "stage", "generated_utc", "git_commit",
                    "rows", "columns", "sha256_gpkg", "sha256_csv", "bytes_gpkg",
                    "bytes_csv", "inputs"):
            assert key in entry, key
        assert entry["stage"] == "integration"
        assert entry["rows"] == 6
        assert entry["output_file"] == str(gpkg.relative_to(icfg.PROJECT_ROOT))
        assert {i["name"] for i in entry["inputs"]} == {
            "grid", "wind", "geographic", "infrastructure", "demand", "exclusions",
        }
        assert all(len(i["sha256"]) == 64 for i in entry["inputs"])

        text = provenance.read_text(encoding="utf-8")
        assert text.startswith("# Handwritten header")
        assert "Keep me." in text
        assert text.count(PROVENANCE_BEGIN) == 1 and text.count(PROVENANCE_END) == 1
        assert entry["sha256_csv"] in text
        assert "--only integration" in text


# ---------------------------------------------------------------------------
# run() end to end
# ---------------------------------------------------------------------------

RUN_KEYS = {
    "feature_table", "csv", "report", "validation_report", "manifest", "provenance",
    "n_cells", "n_eligible", "n_excluded", "n_missing_histogram", "runtime_s",
    "validation", "git_commit", "generated_utc",
}


class TestRun:
    def test_run_writes_all_outputs_and_returns_summary(self, synthetic_pipeline):
        from pipeline.integration.merge import PROVENANCE_BEGIN, run

        result = run(verbose=False)
        assert set(result) == RUN_KEYS
        out, meta = synthetic_pipeline.out_dir, synthetic_pipeline.meta_dir
        assert result["feature_table"] == out / icfg.OUTPUT_FILENAME
        assert result["csv"] == out / icfg.CSV_FILENAME
        assert result["report"] == meta / icfg.METHOD_REPORT_FILENAME
        assert result["validation_report"] == meta / icfg.VALIDATION_REPORT_FILENAME
        assert result["manifest"] == meta / icfg.MANIFEST_FILENAME
        assert result["provenance"] == out / "DATA_PROVENANCE.md"
        for key in ("feature_table", "csv", "report", "validation_report", "manifest", "provenance"):
            assert result[key].exists(), key
        assert result["n_cells"] == 6
        assert result["n_eligible"] == 3 and result["n_excluded"] == 3
        assert result["n_missing_histogram"] == {1: 4, 2: 1, 4: 1}
        assert result["validation"]["failed"] == 0
        assert result["validation"]["warnings"] == 1
        assert isinstance(result["git_commit"], str) and result["git_commit"]
        assert result["runtime_s"] > 0
        report = result["report"].read_text(encoding="utf-8")
        assert "Do not edit by hand" in report and result["generated_utc"] in report
        validation = result["validation_report"].read_text(encoding="utf-8")
        assert "GeoPackage read-back row count" in validation
        assert "CSV read-back row count" in validation
        assert PROVENANCE_BEGIN in result["provenance"].read_text(encoding="utf-8")
        # Excluded rows are retained, marked ineligible, with their features intact.
        table = gpd.read_file(result["feature_table"], layer=icfg.OUTPUT_LAYER).set_index("cell_id")
        assert len(table) == 6
        assert bool(table.loc["CELL_STEEP", "eligible"]) is False
        assert table.loc["CELL_STEEP", "slope_deg"] == 20.0

    def test_run_raises_and_still_writes_validation_report_on_fatal(self, synthetic_pipeline):
        from pipeline.integration.merge import run

        frame = _wind_frame()
        _write_layer(synthetic_pipeline.wind, frame[frame["cell_id"] != "CELL_PLAIN"],
                     icfg.WIND_LAYER, geometry=_geoms()[:5])
        with pytest.raises(RuntimeError, match="wind: cell_id set matches grid"):
            run(verbose=False)
        validation = synthetic_pipeline.meta_dir / icfg.VALIDATION_REPORT_FILENAME
        assert validation.exists()
        assert "**FAIL**" in validation.read_text(encoding="utf-8")
        assert not (synthetic_pipeline.out_dir / icfg.OUTPUT_FILENAME).exists()
        assert not (synthetic_pipeline.out_dir / icfg.CSV_FILENAME).exists()

    def test_rerun_is_idempotent(self, synthetic_pipeline):
        import json
        from pipeline.integration.merge import PROVENANCE_BEGIN, run

        first = run(verbose=False)
        csv_bytes = first["csv"].read_bytes()
        second = run(verbose=False)
        assert second["csv"].read_bytes() == csv_bytes
        manifest = json.loads(second["manifest"].read_text(encoding="utf-8"))
        assert len(manifest["derived_features"]) == 1
        assert second["provenance"].read_text(encoding="utf-8").count(PROVENANCE_BEGIN) == 1


# ---------------------------------------------------------------------------
# Pipeline registration
# ---------------------------------------------------------------------------


class TestPipelineRegistration:
    def test_stage_runs_after_every_producer_and_before_validate(self):
        from pipeline import config as top

        assert "integration" in top.STAGES
        idx = top.STAGES.index("integration")
        for producer in ("grid", "wind.features", "geographic.features",
                         "infrastructure.features", "demand.feature", "exclusions"):
            assert top.STAGES.index(producer) < idx, producer
        assert idx < top.STAGES.index("validate")
        assert "integration" in top.DOMAINS

    def test_only_integration_resolves_single_stage(self):
        import sys

        sys.argv = ["test", "--only", "integration"]
        from pipeline.__main__ import parse_args, resolve_stages

        assert resolve_stages(parse_args()) == ["integration"]

    def test_runner_dispatches_to_merge(self):
        from pipeline.__main__ import _get_runner

        assert _get_runner("integration").__module__ == "pipeline.integration.merge"

    # Feature: s1-08-create-integrated-nsw-feature-table, Property 5: whenever
    # `integration` is scheduled together with any of its producers, it runs
    # after all of them and before `validate`, for any --only/--skip combination.
    @settings(max_examples=100, deadline=None)
    @given(
        only=st.sampled_from([None, "integration", "exclusions", "grid", "wind", "validate"]),
        skips=st.lists(st.sampled_from(
            ["wind", "geographic", "demand", "grid", "exclusions", "wind.features",
             "demand.feature", "infrastructure.features"]), max_size=4),
        skip_validate=st.booleans(),
    )
    def test_property_5_integration_after_producers(self, only, skips, skip_validate):
        from pipeline.__main__ import resolve_stages

        stages = resolve_stages(SimpleNamespace(only=only, skip=skips, skip_validate=skip_validate))
        if "integration" not in stages:
            return
        idx = stages.index("integration")
        for producer in ("grid", "wind.features", "geographic.features",
                         "infrastructure.features", "demand.feature", "exclusions"):
            if producer in stages:
                assert stages.index(producer) < idx
        if "validate" in stages:
            assert idx < stages.index("validate")


# ---------------------------------------------------------------------------
# Opt-in real-data integration (outputs redirected; never rewrites DATA/)
# ---------------------------------------------------------------------------


class TestRealDataIntegration:
    def test_run_against_real_layers(self, tmp_path, monkeypatch):
        from pipeline.integration.merge import run

        inputs = [icfg.GRID_PATH, icfg.WIND_PATH, icfg.GEOGRAPHIC_PATH, icfg.INFRA_PATH,
                  icfg.DEMAND_PATH, icfg.EXCLUSIONS_PATH]
        missing = [p for p in inputs if not p.exists()]
        if missing:
            pytest.skip(f"real inputs not present: {[p.name for p in missing]}")
        monkeypatch.setattr(icfg, "INTEGRATION_DIR", tmp_path / "integration")
        monkeypatch.setattr(icfg, "INTEGRATION_META_DIR", tmp_path / "integration" / "metadata")

        result = run(verbose=False)
        assert result["n_cells"] == 47_311
        assert result["validation"]["failed"] == 0
        assert result["n_eligible"] + result["n_excluded"] == 47_311
        assert "Do not edit by hand" in result["report"].read_text(encoding="utf-8")
