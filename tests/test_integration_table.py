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
