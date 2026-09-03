"""
Tests for the S1-03 wind feature builder (pipeline.wind.features).

Unit tests (Req 11) plus the eight correctness properties from the S1-03
design (hypothesis, >= 100 examples each). All rasters and grids are small
synthetics built in memory or under tmp dirs — no network, no real DATA files.
"""

import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("rasterio")
pytest.importorskip("geopandas")
pytest.importorskip("hypothesis")

import geopandas as gpd
import rasterio
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.extra import numpy as hnp
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from shapely.geometry import box

from pipeline import config as top_config
from pipeline.__main__ import resolve_stages
from pipeline.wind import config as wind_config
from pipeline.wind import features
from pipeline.wind.download import _merge_manifest_samples

RES = 0.0025          # GWA native pixel size (deg)
FACTOR = 20           # native pixels per cell side
CELL = RES * FACTOR   # 0.05 deg
WEST, NORTH = 150.0, -30.0  # lattice-aligned synthetic raster origin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@contextmanager
def _mem_raster(values, west=WEST, north=NORTH, res=RES, nodata=None,
                crs="EPSG:4326"):
    """Yield an open DatasetReader over an in-memory GeoTIFF."""
    values = np.asarray(values, dtype="float32")
    profile = dict(
        driver="GTiff", height=values.shape[0], width=values.shape[1],
        count=1, dtype="float32", crs=crs,
        transform=from_origin(west, north, res, res), nodata=nodata,
    )
    with MemoryFile() as memfile:
        with memfile.open(**profile) as dst:
            dst.write(values, 1)
        with memfile.open() as src:
            yield src


def _cell(col, row, factor=FACTOR, west=WEST, north=NORTH, res=RES):
    """Lattice-aligned rectangular cell polygon (col, row from the NW origin)."""
    size = res * factor
    return box(
        west + col * size, north - (row + 1) * size,
        west + (col + 1) * size, north - row * size,
    )


def _write_grid(path, cells, crs="EPSG:4326"):
    """Write a synthetic analysis grid GeoPackage (layer nsw_grid)."""
    gdf = gpd.GeoDataFrame(
        {"cell_id": [c[0] for c in cells]},
        geometry=[c[1] for c in cells], crs=crs,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path, driver="GPKG", layer=features.GRID_LAYER)
    return gdf


@contextmanager
def _patched_env(tmp, grid_cells, raster_values, grid_crs="EPSG:4326"):
    """
    Point the feature builder's config at a synthetic project under `tmp`.

    Restores every patched attribute on exit (usable inside hypothesis tests
    where function-scoped pytest fixtures are not allowed).
    """
    tmp = Path(tmp)
    wind_dir = tmp / "DATA" / "wind-resource"
    meta_dir = wind_dir / "metadata"
    features_dir = wind_dir / "features"
    grid_path = tmp / "DATA" / "grid" / "nsw_analysis_grid.gpkg"
    raster_name = "gwa_v4_wind-speed_100m_test.tif"
    wind_dir.mkdir(parents=True, exist_ok=True)

    values = np.asarray(raster_values, dtype="float32")
    profile = dict(
        driver="GTiff", height=values.shape[0], width=values.shape[1],
        count=1, dtype="float32", crs="EPSG:4326",
        transform=from_origin(WEST, NORTH, RES, RES), nodata=None,
    )
    with rasterio.open(wind_dir / raster_name, "w", **profile) as dst:
        dst.write(values, 1)

    _write_grid(grid_path, grid_cells, crs=grid_crs)

    saved_cfg = {
        name: getattr(wind_config, name)
        for name in ("PROJECT_ROOT", "WIND_DIR", "WIND_META_DIR",
                     "WIND_FEATURES_DIR", "WIND_FEATURE_SOURCE")
    }
    saved_grid_path = features.GRID_PATH
    try:
        wind_config.PROJECT_ROOT = tmp
        wind_config.WIND_DIR = wind_dir
        wind_config.WIND_META_DIR = meta_dir
        wind_config.WIND_FEATURES_DIR = features_dir
        wind_config.WIND_FEATURE_SOURCE = raster_name
        features.GRID_PATH = grid_path
        yield SimpleNamespace(
            tmp=tmp, wind_dir=wind_dir, meta_dir=meta_dir,
            features_dir=features_dir, grid_path=grid_path,
            raster_path=wind_dir / raster_name,
        )
    finally:
        for name, value in saved_cfg.items():
            setattr(wind_config, name, value)
        features.GRID_PATH = saved_grid_path


# ---------------------------------------------------------------------------
# Zonal block statistic (Req 11.1-11.3, 3.x)
# ---------------------------------------------------------------------------


class TestZonalBlockStat:

    def test_known_mean(self):
        # Req 11.1 — hand-computed mean of a 20x20 block, tolerance 1e-9.
        values = np.arange(400, dtype="float64").reshape(20, 20) / 40.0
        with _mem_raster(values) as src:
            stat = features._zonal_block_stat(src, _cell(0, 0))
        assert stat.value == pytest.approx(values.mean(), abs=1e-9)
        assert stat.n_valid == 400
        assert stat.n_nodata == 0
        assert stat.in_coverage is True

    def test_all_nodata_cell(self):
        # Req 11.2 — all-NoData block yields null value + no_data flag.
        with _mem_raster(np.full((20, 20), np.nan)) as src:
            stat = features._zonal_block_stat(src, _cell(0, 0))
        assert stat.value is None
        assert stat.n_valid == 0
        assert stat.n_nodata == 400
        assert features._confidence_flag(stat) == wind_config.CONF_NODATA

    def test_nodata_excluded_from_statistic(self):
        # Req 11.3 — NaN NoData pixels are excluded from the mean.
        values = np.full((20, 20), 4.0)
        values[:10, :] = np.nan
        with _mem_raster(values) as src:
            stat = features._zonal_block_stat(src, _cell(0, 0))
        assert stat.value == pytest.approx(4.0, abs=1e-9)
        assert stat.n_valid == 200
        assert stat.n_nodata == 200

    def test_declared_numeric_nodata_excluded(self):
        # The GWA clips declare NaN, but a declared numeric nodata must also
        # be honoured via the masked read.
        values = np.full((20, 20), 6.0)
        values[0, :] = -999.0
        with _mem_raster(values, nodata=-999.0) as src:
            stat = features._zonal_block_stat(src, _cell(0, 0))
        assert stat.value == pytest.approx(6.0, abs=1e-9)
        assert stat.n_valid == 380
        assert stat.n_nodata == 20

    def test_cell_overhanging_raster_edge(self):
        # In-cell positions outside the raster extent count as NoData.
        with _mem_raster(np.full((20, 20), 2.5)) as src:
            stat = features._zonal_block_stat(src, _cell(0, -1, factor=20))
        assert stat.n_valid == 0
        assert stat.value is None

    def test_cell_fully_outside_raster(self):
        with _mem_raster(np.full((20, 20), 2.5)) as src:
            stat = features._zonal_block_stat(src, _cell(5, 5))
        assert stat.value is None
        assert stat.n_valid == 0
        assert stat.in_coverage is False

    def test_unsupported_statistic_raises(self):
        with _mem_raster(np.ones((20, 20))) as src:
            with pytest.raises(ValueError, match="mean"):
                features._zonal_block_stat(src, _cell(0, 0), stat="p90")


class TestConfidenceFlag:

    def test_enumerated_values(self):
        valid = features.CellStat(1.0, 1, 399, True)
        empty = features.CellStat(None, 0, 400, True)
        assert features._confidence_flag(valid) == wind_config.CONF_VALID
        assert features._confidence_flag(empty) == wind_config.CONF_NODATA


# ---------------------------------------------------------------------------
# Grid input and CRS boundary (Req 2.3, 2.4, 6.6, 7.4)
# ---------------------------------------------------------------------------


class TestReadGridCells:

    def test_missing_grid_raises(self, tmp_path):
        missing = tmp_path / "nope.gpkg"
        with pytest.raises(FileNotFoundError, match="nope.gpkg"):
            features.read_grid_cells(missing)

    def test_missing_cell_id_column_raises(self, tmp_path):
        path = tmp_path / "grid.gpkg"
        gdf = gpd.GeoDataFrame({"other": ["a"]}, geometry=[_cell(0, 0)],
                               crs="EPSG:4326")
        gdf.to_file(path, driver="GPKG", layer=features.GRID_LAYER)
        with pytest.raises(ValueError, match="cell_id"):
            features.read_grid_cells(path)

    def test_duplicate_cell_id_raises(self, tmp_path):
        path = tmp_path / "grid.gpkg"
        _write_grid(path, [("dup", _cell(0, 0)), ("dup", _cell(1, 0))])
        with pytest.raises(ValueError, match="duplicate"):
            features.read_grid_cells(path)

    def test_cell_ids_preserved_in_order(self, tmp_path):
        path = tmp_path / "grid.gpkg"
        ids = ["S30.025_E150.025", "S30.025_E150.075", "S30.075_E150.025"]
        _write_grid(path, list(zip(ids, [_cell(0, 0), _cell(1, 0), _cell(0, 1)])))
        grid = features.read_grid_cells(path)
        assert grid["cell_id"].tolist() == ids


class TestAssertStorageCrs:

    def test_non_4326_grid_reported(self):
        # Req 7.4 — mismatch reported, never silently reprojected.
        gdf = gpd.GeoDataFrame({"cell_id": ["a"]}, geometry=[_cell(0, 0)],
                               crs="EPSG:3577")
        with _mem_raster(np.ones((20, 20))) as src:
            with pytest.raises(ValueError, match="3577"):
                features._assert_storage_crs(gdf, src)

    def test_grid_without_crs_reported(self):
        gdf = gpd.GeoDataFrame({"cell_id": ["a"]}, geometry=[_cell(0, 0)])
        with _mem_raster(np.ones((20, 20))) as src:
            with pytest.raises(ValueError, match="no declared CRS"):
                features._assert_storage_crs(gdf, src)

    def test_non_4326_raster_reported(self):
        gdf = gpd.GeoDataFrame({"cell_id": ["a"]}, geometry=[_cell(0, 0)],
                               crs="EPSG:4326")
        with _mem_raster(np.ones((20, 20)), crs="EPSG:3577") as src:
            with pytest.raises(ValueError, match="3577"):
                features._assert_storage_crs(gdf, src)


# ---------------------------------------------------------------------------
# End-to-end run() on a synthetic project (Req 4, 6.6, 8, 9)
# ---------------------------------------------------------------------------


def _three_cell_env(tmp):
    """Raster covers cells (0,0) and (1,0); cell (2,0) is out of coverage."""
    values = np.empty((20, 40), dtype="float64")
    values[:, :20] = 5.0
    values[:, 20:] = 7.0
    cells = [
        ("cell_a", _cell(0, 0)),
        ("cell_b", _cell(1, 0)),
        ("cell_c", _cell(2, 0)),
    ]
    return _patched_env(tmp, cells, values)


class TestRunSynthetic:

    def test_run_end_to_end(self, tmp_path):
        with _three_cell_env(tmp_path) as env:
            result = features.run()

            # Summary dict (Req 6.1, 9.1, 9.2)
            assert result["n_cells"] == 3
            assert result["n_valid"] == 2
            assert result["n_nodata"] == 1
            assert result["stats"]["min"] == pytest.approx(5.0)
            assert result["stats"]["max"] == pytest.approx(7.0)

            # Filename convention (Req 4.4)
            table_path = result["feature_table"]
            assert table_path.name == (
                f"gwa_v4_wind-feature_{wind_config.WIND_FEATURE_VINTAGE}_nsw.gpkg"
            )

            table = gpd.read_file(table_path, layer=features.FEATURE_LAYER)
            # One row per cell_id, byte-for-byte, in grid order (Req 11.4, 2.4)
            assert table["cell_id"].tolist() == ["cell_a", "cell_b", "cell_c"]
            # Constants populated (Req 4.2, 4.3)
            assert (table["units"] == wind_config.WIND_VARIABLE_UNITS).all()
            assert (table["data_source"] == wind_config.WIND_DATA_SOURCE).all()
            # Values + flags (Req 2.5, 5.3)
            vals = table[wind_config.WIND_VARIABLE]
            assert vals.iloc[0] == pytest.approx(5.0)
            assert vals.iloc[1] == pytest.approx(7.0)
            assert np.isnan(vals.iloc[2])
            assert table["confidence_flag"].tolist() == [
                wind_config.CONF_VALID, wind_config.CONF_VALID,
                wind_config.CONF_NODATA,
            ]
            # CRS round-trip (Req 4.5)
            assert table.crs.to_epsg() == 4326

            # Method report exists with banner (Req 9.4)
            report = result["report"].read_text()
            assert "pipeline.wind.features" in report
            assert "Do not edit by hand" in report

            # Manifest derived-record merged, not overwritten (Req 8.2)
            manifest = json.loads(result["manifest"].read_text())
            derived = manifest["derived_features"]
            assert len(derived) == 1
            assert derived[0]["sha256"]
            assert derived[0]["local_bytes"] == table_path.stat().st_size

    def test_rerun_is_idempotent(self, tmp_path):
        with _three_cell_env(tmp_path) as env:
            features.run()
            features.run()
            manifest = json.loads(
                (env.meta_dir / "download_manifest.json").read_text()
            )
            assert len(manifest["derived_features"]) == 1
            provenance = (env.wind_dir / "DATA_PROVENANCE.md").read_text()
            assert provenance.count(features._PROVENANCE_BEGIN) == 1

    def test_missing_grid_halts(self, tmp_path):
        # Req 6.6 — missing grid raises, nothing written.
        with _three_cell_env(tmp_path) as env:
            env.grid_path.unlink()
            with pytest.raises(FileNotFoundError, match="--only grid"):
                features.run()
            assert not env.features_dir.exists()

    def test_missing_raster_halts(self, tmp_path):
        with _three_cell_env(tmp_path) as env:
            env.raster_path.unlink()
            with pytest.raises(FileNotFoundError, match="wind.download"):
                features.run()
            assert not env.features_dir.exists()

    def test_non_4326_grid_halts(self, tmp_path):
        values = np.full((20, 20), 5.0)
        cells = [("cell_a", _cell(0, 0))]
        with _patched_env(tmp_path, cells, values, grid_crs="EPSG:3577"):
            with pytest.raises(ValueError, match="3577"):
                features.run()


# ---------------------------------------------------------------------------
# Validation checks (Req 10) — fault injection, no silent passes
# ---------------------------------------------------------------------------


def _write_table(path, rows):
    gdf = gpd.GeoDataFrame(
        {
            "cell_id": [r[0] for r in rows],
            wind_config.WIND_VARIABLE: [r[1] for r in rows],
            "units": wind_config.WIND_VARIABLE_UNITS,
            "data_source": wind_config.WIND_DATA_SOURCE,
            "confidence_flag": [r[2] for r in rows],
        },
        geometry=[_cell(i, 0) for i in range(len(rows))], crs="EPSG:4326",
    )
    gdf.to_file(path, driver="GPKG", layer=features.FEATURE_LAYER)


class TestValidate:

    def _grid(self, tmp_path, n=2):
        path = tmp_path / "grid.gpkg"
        _write_grid(path, [(f"c{i}", _cell(i, 0)) for i in range(n)])
        return path

    def test_all_checks_pass(self, tmp_path):
        grid = self._grid(tmp_path)
        table = tmp_path / "table.gpkg"
        _write_table(table, [("c0", 5.0, "valid"), ("c1", np.nan, "no_data")])
        result = features.validate(table, grid)
        assert result["passed"] == result["total"] == 4
        for c in result["checks"]:
            assert set(c) == {"name", "expected", "observed", "passed"}

    def test_row_count_mismatch_fails(self, tmp_path):
        grid = self._grid(tmp_path, n=3)
        table = tmp_path / "table.gpkg"
        _write_table(table, [("c0", 5.0, "valid"), ("c1", np.nan, "no_data")])
        result = features.validate(table, grid)
        failed = [c for c in result["checks"] if not c["passed"]]
        assert [c["name"] for c in failed] == ["row count equals grid cell count"]
        assert "3" in failed[0]["expected"] and "2" in failed[0]["observed"]

    def test_out_of_range_value_fails(self, tmp_path):
        grid = self._grid(tmp_path)
        table = tmp_path / "table.gpkg"
        _write_table(table, [("c0", 99.0, "valid"), ("c1", 5.0, "valid")])
        result = features.validate(table, grid)
        failed = {c["name"] for c in result["checks"] if not c["passed"]}
        assert "non-null values within plausible range" in failed

    def test_nodata_with_value_fails(self, tmp_path):
        grid = self._grid(tmp_path)
        table = tmp_path / "table.gpkg"
        _write_table(table, [("c0", 5.0, "no_data"), ("c1", 5.0, "valid")])
        result = features.validate(table, grid)
        failed = {c["name"] for c in result["checks"] if not c["passed"]}
        assert "no-data cells have null value" in failed

    def test_flag_outside_enum_fails(self, tmp_path):
        grid = self._grid(tmp_path)
        table = tmp_path / "table.gpkg"
        _write_table(table, [("c0", 5.0, "maybe"), ("c1", 5.0, "valid")])
        result = features.validate(table, grid)
        failed = {c["name"] for c in result["checks"] if not c["passed"]}
        assert "confidence_flag within enumerated set" in failed


# ---------------------------------------------------------------------------
# Manifest merge helper (wind.download integration)
# ---------------------------------------------------------------------------


class TestMergeManifestSamples:

    def test_preserves_replaces_and_appends(self):
        existing = [{"output_file": "a.tif", "v": 1}, {"output_file": "b.tif", "v": 1}]
        new = [{"output_file": "b.tif", "v": 2}, {"output_file": "c.tif", "v": 2}]
        merged = _merge_manifest_samples(existing, new)
        assert merged == [
            {"output_file": "a.tif", "v": 1},   # preserved
            {"output_file": "b.tif", "v": 2},   # replaced in place
            {"output_file": "c.tif", "v": 2},   # appended
        ]

    def test_empty_existing(self):
        new = [{"output_file": "a.tif"}]
        assert _merge_manifest_samples([], new) == new


# ---------------------------------------------------------------------------
# Correctness properties (hypothesis, >= 100 examples each)
# ---------------------------------------------------------------------------

_values_20x20 = hnp.arrays(
    dtype=np.float64, shape=(20, 20),
    elements=st.floats(min_value=0.0, max_value=25.0,
                       allow_nan=False, allow_infinity=False),
)
_mask_20x20 = hnp.arrays(dtype=np.bool_, shape=(20, 20))


class TestProperties:

    # Feature: s1-03-build-wind-feature-layer, Property 1: Zonal statistic
    # equals the mean of valid pixels, NoData excluded
    @settings(max_examples=100, deadline=None)
    @given(values=_values_20x20, mask=_mask_20x20)
    def test_property_1_mean_of_valid_pixels(self, values, mask):
        if mask.all():
            return  # zero-valid behaviour is Property 4
        # Embed the block in a larger all-NaN raster: the extra NoData pixels
        # inside the (larger) cell must not change the derived value.
        raster = np.full((40, 40), np.nan)
        block = values.copy()
        block[mask] = np.nan
        raster[10:30, 10:30] = block
        with _mem_raster(raster) as src:
            stat = features._zonal_block_stat(src, _cell(0, 0, factor=40))
        # The raster stores float32, so the expected mean is computed over the
        # float32-quantised pixels the reader actually sees.
        stored = block.astype(np.float32).astype(np.float64)
        assert stat.value == pytest.approx(
            float(np.nanmean(stored)), rel=1e-9, abs=1e-9
        )
        assert stat.n_valid == int((~mask).sum())

    # Feature: s1-03-build-wind-feature-layer, Property 2: Valid and NoData
    # counts partition the cell's block
    @settings(max_examples=100, deadline=None)
    @given(values=_values_20x20, mask=_mask_20x20)
    def test_property_2_counts_partition_block(self, values, mask):
        block = values.copy()
        block[mask] = np.nan
        with _mem_raster(block) as src:
            stat = features._zonal_block_stat(src, _cell(0, 0))
        assert stat.n_valid >= 0 and stat.n_nodata >= 0
        assert stat.n_valid + stat.n_nodata == 400

    # Feature: s1-03-build-wind-feature-layer, Property 3: Deterministic
    # pixel selection
    @settings(max_examples=100, deadline=None)
    @given(values=_values_20x20, mask=_mask_20x20)
    def test_property_3_deterministic(self, values, mask):
        block = values.copy()
        block[mask] = np.nan
        with _mem_raster(block) as src:
            first = features._zonal_block_stat(src, _cell(0, 0))
            second = features._zonal_block_stat(src, _cell(0, 0))
        assert first == second

    # Feature: s1-03-build-wind-feature-layer, Property 4: Zero valid pixels
    # yield a null value and the no-data flag (no fabrication)
    @settings(max_examples=100, deadline=None)
    @given(outside=st.booleans())
    def test_property_4_zero_valid_is_null_and_flagged(self, outside):
        raster = np.full((20, 20), np.nan)
        cell = _cell(5, 5) if outside else _cell(0, 0)
        with _mem_raster(raster) as src:
            stat = features._zonal_block_stat(src, cell)
        assert stat.value is None
        assert stat.n_valid == 0
        assert features._confidence_flag(stat) == wind_config.CONF_NODATA
        if outside:
            assert stat.in_coverage is False

    # Feature: s1-03-build-wind-feature-layer, Property 5: Confidence flag is
    # the valid/no-data biconditional over the enumerated set
    @settings(max_examples=100, deadline=None)
    @given(values=_values_20x20, mask=_mask_20x20)
    def test_property_5_confidence_biconditional(self, values, mask):
        block = values.copy()
        block[mask] = np.nan
        with _mem_raster(block) as src:
            stat = features._zonal_block_stat(src, _cell(0, 0))
        flag = features._confidence_flag(stat)
        assert flag in {wind_config.CONF_VALID, wind_config.CONF_NODATA}
        assert (flag == wind_config.CONF_VALID) == (stat.n_valid >= 1)

    # Feature: s1-03-build-wind-feature-layer, Property 6: Output cell_id set
    # is a bijection with the grid, values preserved
    @settings(max_examples=100, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    @given(
        ids=st.lists(
            st.text(
                alphabet="abcdefghijklmnopqrstuvwxyz0123456789_.",
                min_size=1, max_size=12,
            ),
            unique=True, min_size=1, max_size=4,
        ),
        data=st.data(),
    )
    def test_property_6_cell_id_bijection(self, ids, data):
        positions = data.draw(
            st.lists(
                st.tuples(st.integers(0, 3), st.integers(0, 3)),
                unique=True, min_size=len(ids), max_size=len(ids),
            )
        )
        cells = [(cid, _cell(col, row)) for cid, (col, row) in zip(ids, positions)]
        values = np.full((40, 40), 5.0)  # covers positions (0..1, 0..1) only
        with tempfile.TemporaryDirectory() as tmp:
            with _patched_env(tmp, cells, values):
                result = features.run()
                table = gpd.read_file(
                    result["feature_table"], layer=features.FEATURE_LAYER
                )
        assert table["cell_id"].tolist() == ids
        assert result["n_cells"] == len(ids)

    # Feature: s1-03-build-wind-feature-layer, Property 7: Non-null wind
    # values fall within the plausible range
    @settings(max_examples=100, deadline=None)
    @given(values=_values_20x20, mask=_mask_20x20)
    def test_property_7_in_range_means_stay_in_range(self, values, mask):
        block = values.copy()
        block[mask] = np.nan
        with _mem_raster(block) as src:
            stat = features._zonal_block_stat(src, _cell(0, 0))
        if stat.value is not None:
            assert wind_config.WIND_PLAUSIBLE_MIN <= stat.value
            assert stat.value <= wind_config.WIND_PLAUSIBLE_MAX

    # Feature: s1-03-build-wind-feature-layer, Property 8: Resolved stage
    # order places the feature builder after the grid
    @settings(max_examples=100, deadline=None)
    @given(
        only=st.sampled_from([None, "wind", "wind.features", "grid"]),
        skips=st.lists(
            st.sampled_from(top_config.STAGES + top_config.DOMAINS),
            max_size=4,
        ),
        skip_validate=st.booleans(),
    )
    def test_property_8_feature_stage_after_grid(self, only, skips, skip_validate):
        args = SimpleNamespace(only=only, skip=skips, skip_validate=skip_validate)
        stages = resolve_stages(args)
        if "grid" in stages and "wind.features" in stages:
            assert stages.index("wind.features") > stages.index("grid")


# ---------------------------------------------------------------------------
# Full-pipeline integration (Req 6.5) — opt-in, skips when inputs absent
# ---------------------------------------------------------------------------


class TestRealDataIntegration:

    def test_run_against_real_grid_and_raster(self):
        grid_path = features.GRID_PATH
        raster_path = wind_config.WIND_DIR / wind_config.WIND_FEATURE_SOURCE
        if not grid_path.exists() or not raster_path.exists():
            pytest.skip("real grid or NSW GWA raster not present")
        result = features.run()
        assert result["n_cells"] == 47_311
        assert result["n_valid"] + result["n_nodata"] == result["n_cells"]
        assert set(result["stats"]) == {"min", "max", "mean"}
        report = result["report"].read_text()
        assert "Do not edit by hand" in report
