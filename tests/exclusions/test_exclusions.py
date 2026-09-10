"""
Tests for the exclusion layer (S1-07).

Covers:
1. Rule-engine condition parsing/evaluation (pipeline.exclusions.rules).
2. Each default exclusion rule independently, plus a fully-eligible cell
   and a multi-reason cell (acceptance criterion: "Unit tests cover each
   exclusion rule independently").
3. The packaged default exclusion_rules.yaml loads and matches the MVP
   criteria from the ticket.
4. The raster zonal-mean helper (pipeline.exclusions.raster_stats), on a
   small synthetic in-memory-sized raster.
5. read_grid_cells halting conditions (missing file, no cell_id, duplicate
   cell_id).
6. An end-to-end synthetic-data run of apply.run() exercising every default
   rule, the non-exclusionary data_flags mechanism, and validate()'s
   no-silent-passes checks.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import yaml
from shapely.geometry import box

from pipeline.exclusions import config as excl_config
from pipeline.exclusions import rules as rules_mod

rasterio = pytest.importorskip("rasterio", reason="rasterio not installed")


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------


class TestEvaluateCondition:
    def test_equals_true(self):
        assert rules_mod.evaluate_condition(True, "== True") is True
        assert rules_mod.evaluate_condition(False, "== True") is False

    def test_equals_false(self):
        assert rules_mod.evaluate_condition(False, "== False") is True

    def test_not_equals(self):
        assert rules_mod.evaluate_condition("Grazing", "!= Forestry") is True
        assert rules_mod.evaluate_condition("Forestry", "!= Forestry") is False

    def test_greater_than(self):
        assert rules_mod.evaluate_condition(20.0, "> 15") is True
        assert rules_mod.evaluate_condition(15.0, "> 15") is False
        assert rules_mod.evaluate_condition(10.0, "> 15") is False

    def test_greater_equal_boundary(self):
        assert rules_mod.evaluate_condition(15.0, ">= 15") is True

    def test_less_than(self):
        assert rules_mod.evaluate_condition(5.0, "< 15") is True
        assert rules_mod.evaluate_condition(15.0, "< 15") is False

    def test_less_equal_boundary(self):
        assert rules_mod.evaluate_condition(15.0, "<= 15") is True

    def test_is_null_matches_none(self):
        assert rules_mod.evaluate_condition(None, "is_null") is True
        assert rules_mod.evaluate_condition(5.0, "is_null") is False

    def test_is_null_matches_nan(self):
        assert rules_mod.evaluate_condition(float("nan"), "is_null") is True

    def test_is_not_null(self):
        assert rules_mod.evaluate_condition(5.0, "is_not_null") is True
        assert rules_mod.evaluate_condition(None, "is_not_null") is False

    def test_missing_value_never_matches_numeric_or_equality(self):
        """A None/NaN field must not accidentally satisfy '> 15' or '== True'."""
        assert rules_mod.evaluate_condition(None, "> 15") is False
        assert rules_mod.evaluate_condition(None, "== True") is False
        assert rules_mod.evaluate_condition(float("nan"), ">= 0") is False

    def test_unparseable_condition_raises(self):
        with pytest.raises(rules_mod.RuleConfigError):
            rules_mod.evaluate_condition(5, "between 1 and 2")


# ---------------------------------------------------------------------------
# Rules-file loading and validation
# ---------------------------------------------------------------------------


class TestLoadRules:
    def _write(self, tmp_path: Path, obj) -> Path:
        path = tmp_path / "rules.yaml"
        path.write_text(yaml.dump(obj))
        return path

    def test_valid_file_loads(self, tmp_path):
        path = self._write(tmp_path, {
            "exclusions": [
                {"name": "r1", "description": "d", "field": "f", "condition": "== True"},
            ]
        })
        rules = rules_mod.load_rules(path)
        assert len(rules) == 1
        assert rules[0]["name"] == "r1"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(rules_mod.RuleConfigError, match="not found"):
            rules_mod.load_rules(tmp_path / "nope.yaml")

    def test_invalid_yaml_raises(self, tmp_path):
        path = tmp_path / "bad.yaml"
        path.write_text("exclusions: [\n  - name: unclosed")
        with pytest.raises(rules_mod.RuleConfigError):
            rules_mod.load_rules(path)

    def test_missing_top_level_key_raises(self, tmp_path):
        path = self._write(tmp_path, {"rules": []})
        with pytest.raises(rules_mod.RuleConfigError, match="exclusions"):
            rules_mod.load_rules(path)

    def test_empty_rules_list_raises(self, tmp_path):
        path = self._write(tmp_path, {"exclusions": []})
        with pytest.raises(rules_mod.RuleConfigError):
            rules_mod.load_rules(path)

    def test_rule_missing_required_key_raises(self, tmp_path):
        path = self._write(tmp_path, {
            "exclusions": [{"name": "r1", "field": "f", "condition": "== True"}]
        })
        with pytest.raises(rules_mod.RuleConfigError, match="missing required"):
            rules_mod.load_rules(path)

    def test_duplicate_rule_name_raises(self, tmp_path):
        path = self._write(tmp_path, {
            "exclusions": [
                {"name": "r1", "description": "d", "field": "f", "condition": "== True"},
                {"name": "r1", "description": "d2", "field": "g", "condition": "is_null"},
            ]
        })
        with pytest.raises(rules_mod.RuleConfigError, match="Duplicate"):
            rules_mod.load_rules(path)

    def test_bad_condition_syntax_raises_at_load_time(self, tmp_path):
        path = self._write(tmp_path, {
            "exclusions": [
                {"name": "r1", "description": "d", "field": "f", "condition": "nonsense"},
            ]
        })
        with pytest.raises(rules_mod.RuleConfigError):
            rules_mod.load_rules(path)


class TestPackagedDefaultRulesFile:
    """The shipped exclusion_rules.yaml is itself valid and matches the ticket's MVP criteria."""

    def test_loads(self):
        rules = rules_mod.load_rules(excl_config.DEFAULT_RULES_PATH)
        names = {r["name"] for r in rules}
        assert names == {"protected_area", "missing_wind_data", "excessive_slope", "urban_area"}

    def test_slope_threshold_matches_project_default(self):
        rules = rules_mod.load_rules(excl_config.DEFAULT_RULES_PATH)
        slope_rule = next(r for r in rules if r["name"] == "excessive_slope")
        assert slope_rule["threshold"] == 15


# ---------------------------------------------------------------------------
# Each default exclusion rule, independently (acceptance criterion)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def default_rules():
    return rules_mod.load_rules(excl_config.DEFAULT_RULES_PATH)


def _clean_fields(**overrides):
    fields = {
        "protected_area": False,
        "protected_area_name": "",
        "slope_deg": 5.0,
        "urban_area": False,
        "wind_speed_100m_ms": 8.0,
    }
    fields.update(overrides)
    return fields


class TestEachRuleIndependently:
    def test_clean_cell_is_eligible(self, default_rules):
        eligible, reason, triggered = rules_mod.evaluate_cell(_clean_fields(), default_rules)
        assert eligible is True
        assert reason is None
        assert triggered == []

    def test_protected_area_rule_alone(self, default_rules):
        fields = _clean_fields(protected_area=True, protected_area_name="Oxley Wild Rivers NP")
        eligible, reason, triggered = rules_mod.evaluate_cell(fields, default_rules)
        assert eligible is False
        assert reason == "Protected area: Oxley Wild Rivers NP"
        assert triggered == ["protected_area"]

    def test_missing_wind_data_rule_alone(self, default_rules):
        fields = _clean_fields(wind_speed_100m_ms=None)
        eligible, reason, triggered = rules_mod.evaluate_cell(fields, default_rules)
        assert eligible is False
        assert reason == "Missing wind data"
        assert triggered == ["missing_wind_data"]

    def test_missing_wind_data_rule_matches_nan_too(self, default_rules):
        fields = _clean_fields(wind_speed_100m_ms=float("nan"))
        eligible, reason, triggered = rules_mod.evaluate_cell(fields, default_rules)
        assert eligible is False
        assert triggered == ["missing_wind_data"]

    def test_excessive_slope_rule_alone(self, default_rules):
        fields = _clean_fields(slope_deg=20.0)
        eligible, reason, triggered = rules_mod.evaluate_cell(fields, default_rules)
        assert eligible is False
        assert reason == "Slope exceeds 15°"
        assert triggered == ["excessive_slope"]

    def test_slope_at_exactly_threshold_does_not_exclude(self, default_rules):
        """Condition is '> 15', so exactly 15.0 must NOT trigger (documented boundary)."""
        fields = _clean_fields(slope_deg=15.0)
        eligible, _reason, triggered = rules_mod.evaluate_cell(fields, default_rules)
        assert eligible is True
        assert triggered == []

    def test_urban_area_rule_alone(self, default_rules):
        fields = _clean_fields(urban_area=True)
        eligible, reason, triggered = rules_mod.evaluate_cell(fields, default_rules)
        assert eligible is False
        assert reason == "Urban area"
        assert triggered == ["urban_area"]

    def test_multiple_reasons_are_joined_and_all_rules_fire_independently(self, default_rules):
        """Rules are evaluated independently — a cell can fail more than one."""
        fields = _clean_fields(
            protected_area=True, protected_area_name="Barrington Tops NP", slope_deg=20.0,
        )
        eligible, reason, triggered = rules_mod.evaluate_cell(fields, default_rules)
        assert eligible is False
        assert set(triggered) == {"protected_area", "excessive_slope"}
        # Deterministic order = rule-config order.
        assert reason == "Protected area: Barrington Tops NP, Slope exceeds 15°"

    def test_unmapped_field_never_crashes(self, default_rules):
        """A cell missing a field the rules reference degrades to 'not triggered', not a crash."""
        eligible, _reason, triggered = rules_mod.evaluate_cell({}, default_rules)
        assert eligible is False  # missing_wind_data triggers: field absent -> None -> is_null
        assert triggered == ["missing_wind_data"]


# ---------------------------------------------------------------------------
# Raster zonal-mean helper
# ---------------------------------------------------------------------------


class TestZonalMean:
    def _write_raster(self, path: Path, data: np.ndarray, bounds, nodata):
        from rasterio.transform import from_bounds as transform_from_bounds

        west, south, east, north = bounds
        transform = transform_from_bounds(west, south, east, north, data.shape[1], data.shape[0])
        with rasterio.open(
            path, "w", driver="GTiff", height=data.shape[0], width=data.shape[1],
            count=1, dtype=data.dtype, crs="EPSG:4326", transform=transform, nodata=nodata,
        ) as dst:
            dst.write(data, 1)

    def test_mean_of_valid_pixels_excludes_nodata(self, tmp_path):
        from pipeline.exclusions.raster_stats import zonal_mean

        data = np.full((20, 20), 10.0, dtype="float32")
        data[0:2, 0:2] = -9999.0  # a nodata patch in a corner far from the test cell
        path = tmp_path / "r.tif"
        self._write_raster(path, data, bounds=(150.0, -30.1, 150.1, -30.0), nodata=-9999.0)

        cell = box(150.04, -30.06, 150.06, -30.04)
        with rasterio.open(path) as src:
            stat = zonal_mean(src, cell, centroid=(150.05, -30.05))

        assert stat.in_coverage is True
        assert stat.value == pytest.approx(10.0)
        assert stat.n_nodata == 0

    def test_out_of_coverage_centroid_returns_null(self, tmp_path):
        from pipeline.exclusions.raster_stats import zonal_mean

        data = np.full((10, 10), 5.0, dtype="float32")
        path = tmp_path / "r.tif"
        self._write_raster(path, data, bounds=(150.0, -30.1, 150.1, -30.0), nodata=None)

        cell = box(151.0, -31.0, 151.1, -30.9)  # nowhere near the raster
        with rasterio.open(path) as src:
            stat = zonal_mean(src, cell, centroid=(151.05, -30.95))

        assert stat.in_coverage is False
        assert stat.value is None

    def test_nan_nodata_is_excluded(self, tmp_path):
        from pipeline.exclusions.raster_stats import zonal_mean

        data = np.full((20, 20), 7.0, dtype="float32")
        data[:, :] = np.nan
        data[8:12, 8:12] = 7.0  # only the centre patch is valid
        path = tmp_path / "r.tif"
        self._write_raster(path, data, bounds=(150.0, -30.1, 150.1, -30.0), nodata=float("nan"))

        cell = box(150.045, -30.055, 150.055, -30.045)
        with rasterio.open(path) as src:
            stat = zonal_mean(src, cell, centroid=(150.05, -30.05))

        assert stat.in_coverage is True
        assert stat.value == pytest.approx(7.0)

    def test_scale_factor_applied(self, tmp_path):
        from pipeline.exclusions.raster_stats import zonal_mean

        data = np.full((10, 10), 1500, dtype="int16")  # e.g. slope * 100 stored as int16
        path = tmp_path / "r.tif"
        west, south, east, north = 150.0, -30.1, 150.1, -30.0
        from rasterio.transform import from_bounds as transform_from_bounds
        transform = transform_from_bounds(west, south, east, north, 10, 10)
        with rasterio.open(
            path, "w", driver="GTiff", height=10, width=10, count=1, dtype="int16",
            crs="EPSG:4326", transform=transform,
        ) as dst:
            dst.write(data, 1)
            dst.scales = (0.01,)

        cell = box(150.04, -30.06, 150.06, -30.04)
        with rasterio.open(path) as src:
            stat = zonal_mean(src, cell, centroid=(150.05, -30.05))

        assert stat.value == pytest.approx(15.0)  # 1500 * 0.01


# ---------------------------------------------------------------------------
# read_grid_cells halting conditions
# ---------------------------------------------------------------------------


class TestReadGridCells:
    def test_missing_file_raises(self, tmp_path):
        from pipeline.exclusions.apply import read_grid_cells

        with pytest.raises(FileNotFoundError):
            read_grid_cells(tmp_path / "nope.gpkg")

    def test_no_cell_id_column_raises(self, tmp_path):
        from pipeline.exclusions.apply import read_grid_cells

        gdf = gpd.GeoDataFrame({"geometry": [box(0, 0, 1, 1)]}, crs="EPSG:4326")
        path = tmp_path / "grid.gpkg"
        gdf.to_file(path, driver="GPKG")
        with pytest.raises(ValueError, match="cell_id"):
            read_grid_cells(path)

    def test_duplicate_cell_id_raises(self, tmp_path):
        from pipeline.exclusions.apply import read_grid_cells

        gdf = gpd.GeoDataFrame(
            {"cell_id": ["A", "A"], "geometry": [box(0, 0, 1, 1), box(1, 1, 2, 2)]},
            crs="EPSG:4326",
        )
        path = tmp_path / "grid.gpkg"
        gdf.to_file(path, driver="GPKG")
        with pytest.raises(ValueError, match="duplicate"):
            read_grid_cells(path)


# ---------------------------------------------------------------------------
# End-to-end synthetic-data run
# ---------------------------------------------------------------------------


def _make_cell(lon, lat, cell_id, half=0.025):
    return {
        "cell_id": cell_id,
        "centroid_lon": lon,
        "centroid_lat": lat,
        "geometry": box(lon - half, lat - half, lon + half, lat + half),
    }


@pytest.fixture
def synthetic_pipeline(tmp_path, monkeypatch):
    """
    Five synthetic cells, one clean and one per default rule, plus the raw
    sources needed to compute their fields — wired up via monkeypatched
    pipeline.exclusions.config paths so apply.run() exercises the real
    code end to end without touching the real DATA/ tree.
    """
    # --- cells ---
    cells = [
        _make_cell(150.95, -30.00, "CELL_CLEAN"),
        _make_cell(151.00, -30.00, "CELL_PROTECTED"),
        _make_cell(151.05, -30.00, "CELL_STEEP"),
        _make_cell(151.10, -30.00, "CELL_URBAN"),
        _make_cell(151.90, -30.00, "CELL_NO_DATA"),  # outside every raster/urban-coverage window
    ]
    grid = gpd.GeoDataFrame(cells, crs="EPSG:4326")
    grid_path = tmp_path / "grid.gpkg"
    grid.to_file(grid_path, driver="GPKG")

    # --- CAPAD protected areas: one polygon over CELL_PROTECTED ---
    capad_fc = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"NAME": "Test Reserve"},
            "geometry": json.loads(gpd.GeoSeries([box(150.98, -30.02, 151.02, -29.98)]).to_json())["features"][0]["geometry"],
        }],
    }
    capad_path = tmp_path / "capad.geojson"
    capad_path.write_text(json.dumps(capad_fc))

    # --- ABS urban centres: one polygon over CELL_URBAN; dataset extent
    # covers CELL_CLEAN..CELL_URBAN but NOT CELL_NO_DATA (tests data_flags) ---
    urban_gdf = gpd.GeoDataFrame(
        {"ucl_name_2021": ["Test Town"]},
        geometry=[box(151.08, -30.02, 151.12, -29.98)],
        crs="EPSG:4326",
    )
    # Pad the dataset's total_bounds out to cover the first four cells only.
    urban_gdf = gpd.GeoDataFrame(
        {"ucl_name_2021": ["Test Town", None]},
        geometry=[box(151.08, -30.02, 151.12, -29.98), box(150.90, -30.05, 150.91, -30.04)],
        crs="EPSG:4326",
    )
    urban_path = tmp_path / "urban.geojson"
    urban_gdf.to_file(urban_path, driver="GeoJSON")

    # --- slope raster: 5 deg everywhere in coverage, 20 deg patch over CELL_STEEP ---
    from rasterio.transform import from_bounds as transform_from_bounds

    raster_bounds = (150.90, -30.05, 151.15, -29.95)
    shape = (40, 100)  # rows, cols
    slope_data = np.full(shape, 5.0, dtype="float32")
    wind_data = np.full(shape, 8.0, dtype="float32")
    transform = transform_from_bounds(*raster_bounds, shape[1], shape[0])

    # Burn a high-slope patch fully covering CELL_STEEP's cell polygon
    # (151.025, -30.025)-(151.075, -29.975), with margin so every pixel in
    # that cell's window is inside the patch, not just a majority.
    from rasterio.features import rasterize
    steep_patch = rasterize(
        [(box(151.00, -30.05, 151.10, -29.95), 1)],
        out_shape=shape, transform=transform, fill=0, dtype="uint8",
    ).astype(bool)
    slope_data[steep_patch] = 20.0

    slope_path = tmp_path / "slope.tif"
    with rasterio.open(
        slope_path, "w", driver="GTiff", height=shape[0], width=shape[1], count=1,
        dtype="float32", crs="EPSG:4326", transform=transform, nodata=-9999.0,
    ) as dst:
        dst.write(slope_data, 1)

    wind_path = tmp_path / "wind.tif"
    with rasterio.open(
        wind_path, "w", driver="GTiff", height=shape[0], width=shape[1], count=1,
        dtype="float32", crs="EPSG:4326", transform=transform, nodata=float("nan"),
    ) as dst:
        dst.write(wind_data, 1)

    # --- wire up config ---
    monkeypatch.setattr(excl_config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(excl_config, "GRID_PATH", grid_path)
    monkeypatch.setattr(excl_config, "CAPAD_PATH", capad_path)
    monkeypatch.setattr(excl_config, "URBAN_PATH", urban_path)
    monkeypatch.setattr(excl_config, "SLOPE_RASTER_PATH", slope_path)
    monkeypatch.setattr(excl_config, "WIND_SPEED_RASTER_PATH", wind_path)
    monkeypatch.setattr(excl_config, "EXCLUSIONS_DIR", tmp_path / "out")
    monkeypatch.setattr(excl_config, "EXCLUSIONS_META_DIR", tmp_path / "out" / "metadata")

    return tmp_path


class TestApplyEndToEnd:
    def test_run_produces_expected_eligibility_per_cell(self, synthetic_pipeline):
        from pipeline.exclusions.apply import run

        result = run(verbose=False)

        assert result["n_cells"] == 5
        assert result["validation"]["passed"] == result["validation"]["total"]

        table = gpd.read_file(result["eligibility_table"]).set_index("cell_id")

        assert table.loc["CELL_CLEAN", "eligible"] == True  # noqa: E712
        # GeoPackage round-trips a missing string as NaN, not None — pandas'
        # own notna()/isna() (used by validate()) treats both identically.
        assert pd.isna(table.loc["CELL_CLEAN", "exclusion_reason"])

        assert table.loc["CELL_PROTECTED", "eligible"] == False  # noqa: E712
        assert "Protected area: Test Reserve" in table.loc["CELL_PROTECTED", "exclusion_reason"]

        assert table.loc["CELL_STEEP", "eligible"] == False  # noqa: E712
        assert "Slope exceeds 15" in table.loc["CELL_STEEP", "exclusion_reason"]

        assert table.loc["CELL_URBAN", "eligible"] == False  # noqa: E712
        assert "Urban area" in table.loc["CELL_URBAN", "exclusion_reason"]

        assert table.loc["CELL_NO_DATA", "eligible"] == False  # noqa: E712
        assert "Missing wind data" in table.loc["CELL_NO_DATA", "exclusion_reason"]
        # Soft flag, not a second exclusion: outside the urban dataset's own coverage.
        assert table.loc["CELL_NO_DATA", "data_flags"] is not None
        assert "Urban-centre data unavailable" in table.loc["CELL_NO_DATA", "data_flags"]

        # Cells inside urban-dataset coverage that simply don't overlap urban
        # must NOT carry the coverage flag.
        assert pd.isna(table.loc["CELL_CLEAN", "data_flags"])

    def test_report_is_written_and_readable(self, synthetic_pipeline):
        from pipeline.exclusions.apply import run

        result = run(verbose=False)
        report_text = Path(result["report"]).read_text()
        assert "Exclusion layer summary" in report_text
        assert "Total cells: **5**" in report_text
        assert "protected_area" in report_text


# ---------------------------------------------------------------------------
# Pipeline registration
# ---------------------------------------------------------------------------


class TestPipelineRegistration:
    def test_stage_registered_after_grid(self):
        from pipeline import config as pipeline_config

        assert "exclusions" in pipeline_config.STAGES
        assert pipeline_config.STAGES.index("exclusions") > pipeline_config.STAGES.index("grid")
        assert pipeline_config.STAGES.index("exclusions") < pipeline_config.STAGES.index("validate")

    def test_domain_registered(self):
        from pipeline import config as pipeline_config

        assert "exclusions" in pipeline_config.DOMAINS

    def test_run_is_importable(self):
        from pipeline.exclusions.apply import run

        assert callable(run)

    def test_only_exclusions_resolves(self):
        import sys

        sys.argv = ["test", "--only", "exclusions"]
        from pipeline.__main__ import parse_args, resolve_stages

        args = parse_args()
        stages = resolve_stages(args)
        assert stages == ["exclusions"]
