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
6. An end-to-end synthetic-data run of apply.run() over synthetic joined
   feature tables (geographic + wind, keyed on cell_id) exercising every
   default rule and validate()'s no-silent-passes checks.
"""

from __future__ import annotations

import json
import math
import re
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
        assert names == {
            "protected_area",
            "missing_wind_data",
            "excessive_slope",
            "urban_area",
            "offshore_or_marine",
            "missing_slope_data",
            "missing_demand_data",
        }

    def test_slope_threshold_matches_project_default(self):
        rules = rules_mod.load_rules(excl_config.DEFAULT_RULES_PATH)
        slope_rule = next(r for r in rules if r["name"] == "excessive_slope")
        assert slope_rule["threshold"] == 15


class TestReasonCodeVocabularyIsFrozen:
    """
    The exclusion reason-code vocabulary is a Frozen_Decision (F16) recorded in
    the Decision-Engine Specification §6.5. These tests tie the shipped
    exclusion_rules.yaml rule names to that frozen list so the YAML and the
    specification cannot silently diverge.
    """

    # tests/exclusions/ -> repo root is two levels up.
    _SPEC = (
        Path(__file__).resolve().parents[2]
        / "Sprint-2-Tasks"
        / "decision_engine_specification.md"
    )

    def test_spec_documents_every_shipped_code(self):
        spec_text = self._SPEC.read_text(encoding="utf-8")
        assert "§6.5 Exclusion reason-code vocabulary" in spec_text
        rules = rules_mod.load_rules(excl_config.DEFAULT_RULES_PATH)
        for rule in rules:
            # Each shipped rule name (the machine-readable code) is recorded
            # in the frozen vocabulary as an inline-code token.
            assert f"`{rule['name']}`" in spec_text, rule["name"]

    def test_spec_lists_no_stale_codes(self):
        """
        Every code in the spec's F16 vocabulary TABLE is a real shipped rule
        name — the spec must not name a code the YAML no longer defines.
        """
        spec_text = self._SPEC.read_text(encoding="utf-8")
        shipped = {r["name"] for r in rules_mod.load_rules(excl_config.DEFAULT_RULES_PATH)}

        # Extract the vocabulary table rows: lines like "| `code` | ... |".
        start = spec_text.index("§6.5 Exclusion reason-code vocabulary")
        end = spec_text.index("Pairing contract", start)
        table = spec_text[start:end]
        codes_in_table = set(re.findall(r"^\| `([a-z_]+)` \|", table, flags=re.MULTILINE))

        assert codes_in_table, "no reason-code rows parsed from the §6.5 table"
        assert codes_in_table == shipped


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
        "on_land": True,
        "demand_proxy": 100.0,
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

    def test_offshore_or_marine_rule_alone(self, default_rules):
        """on_land == False excludes a cell whose centre is offshore/marine."""
        fields = _clean_fields(on_land=False)
        eligible, reason, triggered = rules_mod.evaluate_cell(fields, default_rules)
        assert eligible is False
        assert reason == "Offshore or marine (not on land)"
        assert triggered == ["offshore_or_marine"]

    def test_missing_slope_data_rule_alone(self, default_rules):
        """A null slope excludes via missing_slope_data (never silently passes)."""
        fields = _clean_fields(slope_deg=None)
        eligible, reason, triggered = rules_mod.evaluate_cell(fields, default_rules)
        assert eligible is False
        assert reason == "Missing slope data"
        assert triggered == ["missing_slope_data"]

    def test_missing_slope_data_matches_nan_too(self, default_rules):
        fields = _clean_fields(slope_deg=float("nan"))
        eligible, _reason, triggered = rules_mod.evaluate_cell(fields, default_rules)
        assert eligible is False
        assert triggered == ["missing_slope_data"]

    def test_missing_demand_data_rule_alone(self, default_rules):
        """A null demand_proxy excludes via missing_demand_data (demand_proxy is a
        scored criterion, so a null must exclude rather than silently pass)."""
        fields = _clean_fields(demand_proxy=None)
        eligible, reason, triggered = rules_mod.evaluate_cell(fields, default_rules)
        assert eligible is False
        assert reason == "Missing demand data"
        assert triggered == ["missing_demand_data"]

    def test_missing_demand_data_matches_nan_too(self, default_rules):
        fields = _clean_fields(demand_proxy=float("nan"))
        eligible, _reason, triggered = rules_mod.evaluate_cell(fields, default_rules)
        assert eligible is False
        assert triggered == ["missing_demand_data"]

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
        assert eligible is False
        # Absent fields read as None -> only the is_null rules fire (never a
        # numeric/equality rule): wind, slope and demand are all absent here.
        assert triggered == ["missing_wind_data", "missing_slope_data", "missing_demand_data"]


class TestEvaluateCellDetailed:
    """The structured {code, text} pairing — the single source of machine+human reasons."""

    def test_clean_cell_has_no_reasons(self, default_rules):
        eligible, reasons = rules_mod.evaluate_cell_detailed(_clean_fields(), default_rules)
        assert eligible is True
        assert reasons == []

    def test_protected_area_pair(self, default_rules):
        fields = _clean_fields(protected_area=True, protected_area_name="Oxley Wild Rivers NP")
        eligible, reasons = rules_mod.evaluate_cell_detailed(fields, default_rules)
        assert eligible is False
        assert reasons == [{"code": "protected_area", "text": "Protected area: Oxley Wild Rivers NP"}]

    def test_missing_wind_data_pair(self, default_rules):
        eligible, reasons = rules_mod.evaluate_cell_detailed(
            _clean_fields(wind_speed_100m_ms=None), default_rules
        )
        assert eligible is False
        assert reasons == [{"code": "missing_wind_data", "text": "Missing wind data"}]

    def test_excessive_slope_pair(self, default_rules):
        eligible, reasons = rules_mod.evaluate_cell_detailed(
            _clean_fields(slope_deg=20.0), default_rules
        )
        assert eligible is False
        assert reasons == [{"code": "excessive_slope", "text": "Slope exceeds 15\xb0"}]

    def test_urban_area_pair(self, default_rules):
        eligible, reasons = rules_mod.evaluate_cell_detailed(
            _clean_fields(urban_area=True), default_rules
        )
        assert eligible is False
        assert reasons == [{"code": "urban_area", "text": "Urban area"}]

    def test_multiple_reasons_ordered_pairs(self, default_rules):
        """A cell can carry multiple pairs, in deterministic rule-config order."""
        fields = _clean_fields(
            protected_area=True, protected_area_name="Barrington Tops NP", slope_deg=20.0,
        )
        eligible, reasons = rules_mod.evaluate_cell_detailed(fields, default_rules)
        assert eligible is False
        assert reasons == [
            {"code": "protected_area", "text": "Protected area: Barrington Tops NP"},
            {"code": "excessive_slope", "text": "Slope exceeds 15\xb0"},
        ]

    def test_wrapper_and_detailed_agree(self, default_rules):
        """evaluate_cell must be derivable from evaluate_cell_detailed — no drift."""
        fields = _clean_fields(
            protected_area=True, protected_area_name="Barrington Tops NP", slope_deg=20.0,
        )
        eligible, reason, triggered = rules_mod.evaluate_cell(fields, default_rules)
        eligible_d, reasons = rules_mod.evaluate_cell_detailed(fields, default_rules)

        assert eligible == eligible_d
        assert triggered == [r["code"] for r in reasons]
        assert reason == rules_mod.REASON_DELIMITER.join(r["text"] for r in reasons)


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
        "geometry": box(lon - half, lat - half, lon + half, lat + half),
    }


@pytest.fixture
def synthetic_pipeline(tmp_path, monkeypatch):
    """
    Seven synthetic cells, one clean and one per default rule, wired up as the
    JOINED per-cell feature tables the migrated stage now reads — a synthetic
    geographic feature table, a synthetic wind feature table and a synthetic
    demand-proxy feature table, all keyed on cell_id — via monkeypatched
    pipeline.exclusions.config paths so apply.run() exercises the real
    read_feature_tables + join path end to end without touching the real
    DATA/ tree.

    Post-migration there is no raw-source sampling and no urban coverage
    window: every field is read straight from the three feature tables, so
    each cell's field values are set directly here.
    """
    # --- cells (one clean, one per rule) ---
    specs = [
        # cell_id,         lon,     lat,  slope, land_use, protected, name, urban, on_land, wind, demand
        ("CELL_CLEAN",     150.95, -30.0, 5.0,  "Grazing", False, "",             False, True,  8.0,  100.0),
        ("CELL_PROTECTED", 151.00, -30.0, 5.0,  "Grazing", True,  "Test Reserve", False, True,  8.0,  100.0),
        ("CELL_STEEP",     151.05, -30.0, 20.0, "Grazing", False, "",             False, True,  8.0,  100.0),
        ("CELL_URBAN",     151.10, -30.0, 5.0,  "Urban",   False, "",             True,  True,  8.0,  100.0),
        ("CELL_OFFSHORE",  153.40, -30.0, 5.0,  "Grazing", False, "",             False, False, 8.0,  100.0),
        ("CELL_NO_WIND",   151.90, -30.0, 5.0,  "Grazing", False, "",             False, True,  None, 100.0),
        ("CELL_NO_DEMAND", 149.00, -35.4, 5.0,  "Grazing", False, "",             False, True,  8.0,  None),
    ]

    grid = gpd.GeoDataFrame(
        [_make_cell(lon, lat, cid) for cid, lon, lat, *_ in specs],
        crs="EPSG:4326",
    )
    grid_path = tmp_path / "grid.gpkg"
    grid.to_file(grid_path, driver="GPKG")

    # --- synthetic geographic feature table (geographic_features layer) ---
    geo_rows = [
        {
            "cell_id": cid,
            "slope_deg": slope,
            "land_use": land_use,
            "protected_area": protected,
            "protected_area_name": name,
            "urban_area": urban,
            "on_land": on_land,
        }
        for cid, lon, lat, slope, land_use, protected, name, urban, on_land, wind, demand in specs
    ]
    geo_gdf = gpd.GeoDataFrame(
        geo_rows,
        geometry=[grid.geometry.iloc[i] for i in range(len(geo_rows))],
        crs="EPSG:4326",
    )
    geo_path = tmp_path / "geographic_features.gpkg"
    geo_gdf.to_file(geo_path, driver="GPKG", layer="geographic_features")

    # --- synthetic wind feature table (wind_features layer) ---
    wind_rows = [
        {"cell_id": cid, "wind_speed_100m": wind}
        for cid, lon, lat, slope, land_use, protected, name, urban, on_land, wind, demand in specs
    ]
    wind_gdf = gpd.GeoDataFrame(
        wind_rows,
        geometry=[grid.geometry.iloc[i] for i in range(len(wind_rows))],
        crs="EPSG:4326",
    )
    wind_path = tmp_path / "wind_features.gpkg"
    wind_gdf.to_file(wind_path, driver="GPKG", layer="wind_features")

    # --- synthetic demand-proxy feature table (demand_proxy layer) ---
    demand_rows = [
        {"cell_id": cid, "demand_proxy": demand}
        for cid, lon, lat, slope, land_use, protected, name, urban, on_land, wind, demand in specs
    ]
    demand_gdf = gpd.GeoDataFrame(
        demand_rows,
        geometry=[grid.geometry.iloc[i] for i in range(len(demand_rows))],
        crs="EPSG:4326",
    )
    demand_path = tmp_path / "demand_proxy.gpkg"
    demand_gdf.to_file(demand_path, driver="GPKG", layer="demand_proxy")

    # --- wire up config ---
    monkeypatch.setattr(excl_config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(excl_config, "GRID_PATH", grid_path)
    monkeypatch.setattr(excl_config, "GEOGRAPHIC_FEATURE_PATH", geo_path)
    monkeypatch.setattr(excl_config, "GEOGRAPHIC_FEATURE_LAYER", "geographic_features")
    monkeypatch.setattr(excl_config, "WIND_FEATURE_PATH", wind_path)
    monkeypatch.setattr(excl_config, "WIND_FEATURE_LAYER", "wind_features")
    monkeypatch.setattr(excl_config, "DEMAND_FEATURE_PATH", demand_path)
    monkeypatch.setattr(excl_config, "DEMAND_FEATURE_LAYER", "demand_proxy")
    monkeypatch.setattr(excl_config, "EXCLUSIONS_DIR", tmp_path / "out")
    monkeypatch.setattr(excl_config, "EXCLUSIONS_META_DIR", tmp_path / "out" / "metadata")

    return tmp_path


class TestApplyEndToEnd:
    def test_run_produces_expected_eligibility_per_cell(self, synthetic_pipeline):
        from pipeline.exclusions.apply import run

        result = run(verbose=False)

        assert result["n_cells"] == 7
        assert result["validation"]["passed"] == result["validation"]["total"]

        table = gpd.read_file(result["eligibility_table"]).set_index("cell_id")

        assert table.loc["CELL_CLEAN", "eligible"] == True  # noqa: E712
        # GeoPackage round-trips a missing string as NaN, not None — pandas'
        # own notna()/isna() (used by validate()) treats both identically.
        assert pd.isna(table.loc["CELL_CLEAN", "exclusion_reason"])
        # An eligible cell carries no structured reasons either.
        assert pd.isna(table.loc["CELL_CLEAN", "exclusion_reasons"])

        assert table.loc["CELL_PROTECTED", "eligible"] == False  # noqa: E712
        assert "Protected area: Test Reserve" in table.loc["CELL_PROTECTED", "exclusion_reason"]
        # Structured machine+human paired reason schema round-trips through the GeoPackage.
        protected_pairs = json.loads(table.loc["CELL_PROTECTED", "exclusion_reasons"])
        assert protected_pairs == [
            {"code": "protected_area", "text": "Protected area: Test Reserve"}
        ]

        assert table.loc["CELL_STEEP", "eligible"] == False  # noqa: E712
        assert "Slope exceeds 15" in table.loc["CELL_STEEP", "exclusion_reason"]

        assert table.loc["CELL_URBAN", "eligible"] == False  # noqa: E712
        assert "Urban area" in table.loc["CELL_URBAN", "exclusion_reason"]

        # on_land == False -> offshore_or_marine (a real geographic rule-out).
        assert table.loc["CELL_OFFSHORE", "eligible"] == False  # noqa: E712
        assert "Offshore or marine" in table.loc["CELL_OFFSHORE", "exclusion_reason"]
        assert "offshore_or_marine" in table.loc["CELL_OFFSHORE", "triggered_rules"]

        assert table.loc["CELL_NO_WIND", "eligible"] == False  # noqa: E712
        assert "Missing wind data" in table.loc["CELL_NO_WIND", "exclusion_reason"]

        # Null demand_proxy -> missing_demand_data (demand_proxy is a scored
        # criterion, so a null must exclude the cell, not let it be scored).
        assert table.loc["CELL_NO_DEMAND", "eligible"] == False  # noqa: E712
        assert "Missing demand data" in table.loc["CELL_NO_DEMAND", "exclusion_reason"]
        assert "missing_demand_data" in table.loc["CELL_NO_DEMAND", "triggered_rules"]

        # data_flags no longer carries the New-England urban coverage-window
        # note (removed in the feature-table migration): urban_area is now
        # statewide-definite from the joined geographic feature table. The
        # column stays in OUTPUT_COLUMNS but is null for every cell unless the
        # geographic builder later carries a soft note.
        assert table["data_flags"].isna().all()

    def test_report_is_written_and_readable(self, synthetic_pipeline):
        from pipeline.exclusions.apply import run

        result = run(verbose=False)
        report_text = Path(result["report"]).read_text()
        assert "Exclusion layer summary" in report_text
        assert "Total cells: **7**" in report_text
        assert "protected_area" in report_text
        # The report documents the machine+human paired reason schema.
        assert "Exclusion reason schema" in report_text
        assert "exclusion_reasons" in report_text

    def test_validate_passes_the_structured_reason_check(self, synthetic_pipeline):
        """The real run's Eligibility_Table passes the exclusion_reasons consistency check."""
        from pipeline.exclusions.apply import run

        result = run(verbose=False)
        names = [c["name"] for c in result["validation"]["checks"]]
        assert any("exclusion_reasons pairs consistent" in n for n in names)
        failing = [c for c in result["validation"]["checks"] if not c["passed"]]
        assert failing == []


# ---------------------------------------------------------------------------
# validate() no-silent-passes check for the structured reason column
# ---------------------------------------------------------------------------


class TestValidateStructuredReasons:
    """The exclusion_reasons consistency check must FAIL on a drifted column."""

    def _write_pair(self, tmp_path, rows):
        grid = gpd.GeoDataFrame(
            [{"cell_id": r["cell_id"], "geometry": box(0, 0, 1, 1)} for r in rows],
            crs="EPSG:4326",
        )
        # give each row a distinct geometry so the GeoPackage is well-formed
        geoms = [box(i, 0, i + 1, 1) for i in range(len(rows))]
        grid = gpd.GeoDataFrame(
            [{"cell_id": r["cell_id"]} for r in rows], geometry=geoms, crs="EPSG:4326"
        )
        grid_path = tmp_path / "grid.gpkg"
        grid.to_file(grid_path, driver="GPKG")

        table = gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326")
        table_path = tmp_path / "table.gpkg"
        table.to_file(table_path, driver="GPKG")
        return table_path, grid_path

    def test_consistent_table_passes(self, tmp_path):
        from pipeline.exclusions.apply import validate

        rows = [
            {
                "cell_id": "A", "eligible": True, "exclusion_reason": None,
                "triggered_rules": None, "exclusion_reasons": None,
            },
            {
                "cell_id": "B", "eligible": False,
                "exclusion_reason": "Urban area",
                "triggered_rules": "urban_area",
                "exclusion_reasons": json.dumps([{"code": "urban_area", "text": "Urban area"}]),
            },
        ]
        table_path, grid_path = self._write_pair(tmp_path, rows)
        result = validate(table_path, grid_path)
        struct = next(c for c in result["checks"] if "exclusion_reasons pairs consistent" in c["name"])
        assert struct["passed"] is True

    def test_code_mismatch_fails(self, tmp_path):
        from pipeline.exclusions.apply import validate

        rows = [
            {
                "cell_id": "B", "eligible": False,
                "exclusion_reason": "Urban area",
                "triggered_rules": "urban_area",
                # code disagrees with triggered_rules -> must be caught
                "exclusion_reasons": json.dumps([{"code": "protected_area", "text": "Urban area"}]),
            },
        ]
        table_path, grid_path = self._write_pair(tmp_path, rows)
        result = validate(table_path, grid_path)
        struct = next(c for c in result["checks"] if "exclusion_reasons pairs consistent" in c["name"])
        assert struct["passed"] is False

    def test_missing_pairs_on_excluded_cell_fails(self, tmp_path):
        from pipeline.exclusions.apply import validate

        rows = [
            {
                "cell_id": "B", "eligible": False,
                "exclusion_reason": "Urban area",
                "triggered_rules": "urban_area",
                "exclusion_reasons": None,  # excluded but no structured reasons
            },
        ]
        table_path, grid_path = self._write_pair(tmp_path, rows)
        result = validate(table_path, grid_path)
        struct = next(c for c in result["checks"] if "exclusion_reasons pairs consistent" in c["name"])
        assert struct["passed"] is False

    def test_reasons_on_eligible_cell_fails(self, tmp_path):
        from pipeline.exclusions.apply import validate

        rows = [
            {
                "cell_id": "A", "eligible": True, "exclusion_reason": None,
                "triggered_rules": None,
                # eligible cell should carry NO structured reasons
                "exclusion_reasons": json.dumps([{"code": "urban_area", "text": "Urban area"}]),
            },
        ]
        table_path, grid_path = self._write_pair(tmp_path, rows)
        result = validate(table_path, grid_path)
        struct = next(c for c in result["checks"] if "exclusion_reasons pairs consistent" in c["name"])
        assert struct["passed"] is False

    def test_new_rule_codes_validate_clean(self, tmp_path):
        """
        The new codes (missing_slope_data, offshore_or_marine,
        missing_demand_data) flow through the same evaluate_cell_detailed
        path, so a cell excluded by any must pass validate()'s
        exclusion_reasons↔triggered_rules consistency check unchanged
        (confirms validate() needs no edit for the extended vocabulary).
        """
        from pipeline.exclusions.apply import validate

        rows = [
            {
                "cell_id": "A", "eligible": False,
                "exclusion_reason": "Missing slope data",
                "triggered_rules": "missing_slope_data",
                "exclusion_reasons": json.dumps(
                    [{"code": "missing_slope_data", "text": "Missing slope data"}]
                ),
            },
            {
                "cell_id": "B", "eligible": False,
                "exclusion_reason": "Offshore or marine (not on land)",
                "triggered_rules": "offshore_or_marine",
                "exclusion_reasons": json.dumps(
                    [{"code": "offshore_or_marine", "text": "Offshore or marine (not on land)"}]
                ),
            },
            {
                "cell_id": "C", "eligible": False,
                "exclusion_reason": "Missing demand data",
                "triggered_rules": "missing_demand_data",
                "exclusion_reasons": json.dumps(
                    [{"code": "missing_demand_data", "text": "Missing demand data"}]
                ),
            },
        ]
        table_path, grid_path = self._write_pair(tmp_path, rows)
        result = validate(table_path, grid_path)
        struct = next(c for c in result["checks"] if "exclusion_reasons pairs consistent" in c["name"])
        assert struct["passed"] is True
        assert [c for c in result["checks"] if not c["passed"]] == []


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
