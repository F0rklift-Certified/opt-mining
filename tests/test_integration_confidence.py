"""
Tests for the S1-09 data-quality and confidence layer
(`pipeline.integration.confidence`).

The module is pure pandas/numpy/yaml: everything here runs on in-memory
frames and small YAML files under tmp_path. The six synthetic cells mirror
`tests/test_integration_table.py` so the worked numbers in the plan can be
asserted exactly.
"""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

yaml = pytest.importorskip("yaml")

from pipeline.integration import config as icfg  # noqa: E402

SCORED = (
    "wind_speed", "demand_proxy", "dist_transmission_km", "dist_substation_km",
    "dist_connection_km", "inside_rez", "elevation_m", "slope_deg", "land_use",
    "protected_area",
)


def _default_raw() -> dict:
    """Deep copy of the packaged YAML as a dict, for mutation in fault tests."""
    return copy.deepcopy(yaml.safe_load(icfg.DEFAULT_CONFIDENCE_WEIGHTS_PATH.read_text(encoding="utf-8")))


def _write(tmp_path: Path, obj, name="weights.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(obj) if not isinstance(obj, str) else obj, encoding="utf-8")
    return path


def _parse(raw: dict):
    from pipeline.integration.confidence import parse_weights

    return parse_weights(raw)


# ---------------------------------------------------------------------------
# Packaged defaults
# ---------------------------------------------------------------------------


class TestPackagedDefaults:
    def test_config_constants(self):
        assert tuple(icfg.SCORED_FEATURE_COLUMNS) == SCORED
        assert icfg.CONFIDENCE_COLUMNS == ("data_confidence", "confidence_score", "confidence_notes")
        assert icfg.DATA_CONFIDENCE_LEVELS == ("high", "medium", "low")
        assert set(icfg.CONFIDENCE_FLAG_COLUMNS) == {"wind", "geographic", "infrastructure", "demand"}
        assert icfg.CONFIDENCE_FLAG_COLUMNS["wind"] == ("wind_confidence", icfg.WIND_CONFIDENCE_LEVELS)
        assert icfg.CONFIDENCE_FLAG_COLUMNS["geographic"] == ("geo_confidence", icfg.GEO_CONFIDENCE_LEVELS)
        assert icfg.CONFIDENCE_NOTE_DELIMITER == "; " and icfg.CONFIDENCE_NO_NOTES == "—"
        assert icfg.CONFIDENCE_SCORE_DECIMALS == 3
        assert icfg.DEFAULT_CONFIDENCE_WEIGHTS_PATH.name == "confidence_weights.yaml"
        assert icfg.CONFIDENCE_METHOD_FILENAME == "confidence_method.md"
        assert icfg.CONFIDENCE_SUMMARY_FILENAME == "confidence_summary.md"
        assert icfg.CELL_DEG == 0.05 and icfg.GRID_ORIGIN_LON == 109.21125

    def test_packaged_yaml_loads_with_s1_10_weights(self):
        from pipeline.integration.confidence import load_weights

        w = load_weights(icfg.DEFAULT_CONFIDENCE_WEIGHTS_PATH)
        assert w.version == "1.0"
        assert w.path == icfg.DEFAULT_CONFIDENCE_WEIGHTS_PATH and len(w.sha256) == 64
        assert [f.name for f in w.features] == list(SCORED)
        weights = {f.name: f.weight for f in w.features}
        assert weights == {
            "wind_speed": 0.35, "dist_transmission_km": 0.20, "demand_proxy": 0.15,
            "dist_substation_km": 0.10, "slope_deg": 0.10, "inside_rez": 0.10,
            "elevation_m": 0.05, "land_use": 0.05, "protected_area": 0.05,
            "dist_connection_km": 0.05,
        }
        assert w.weight_sum == pytest.approx(1.20)
        assert w.thresholds.high == 0.8 and w.thresholds.medium == 0.5
        assert all(f.resolution_basis and f.limitation_basis for f in w.features)
        assert w.feature("demand_proxy").resolution == 0.5
        assert w.feature("demand_proxy").limitation == 0.75
        assert w.max_attainable == pytest.approx(1.04375 / 1.20, abs=1e-6)

    def test_packaged_flag_rules(self):
        from pipeline.integration.confidence import load_weights

        w = load_weights(icfg.DEFAULT_CONFIDENCE_WEIGHTS_PATH)
        rules = {r.layer: r for r in w.flags}
        assert [r.layer for r in w.flags] == ["wind", "geographic", "infrastructure", "demand"]
        assert rules["wind"].column == "wind_confidence"
        assert rules["wind"].factors == {"valid": 1.0, "no_data": 0.0}
        assert rules["geographic"].features == ("elevation_m", "slope_deg", "land_use")
        assert "protected_area" not in rules["geographic"].features
        assert rules["geographic"].factors == {"high": 1.0, "low": 0.5}
        assert rules["infrastructure"].factors == {"high": 1.0, "low": 1.0}
        assert rules["demand"].factors == {"high": 1.0, "medium": 0.75, "low": 0.5}
        assert rules["demand"].notes["medium"] == "Demand region assigned by boundary overlap"
        assert w.layer_of("elevation_m") == "geographic"
        assert w.layer_of("protected_area") is None
        assert len(w.soft_flags) == 1
        assert w.soft_flags[0].match == "Urban-centre data unavailable"
        assert w.soft_flags[0].factor == 1.0


# ---------------------------------------------------------------------------
# Loader validation ladder
# ---------------------------------------------------------------------------


class TestLoadWeights:
    def _err(self):
        from pipeline.integration.confidence import ConfidenceConfigError

        return ConfidenceConfigError

    def test_missing_file(self, tmp_path):
        from pipeline.integration.confidence import load_weights

        with pytest.raises(self._err(), match="not found"):
            load_weights(tmp_path / "nope.yaml")

    def test_invalid_yaml(self, tmp_path):
        from pipeline.integration.confidence import load_weights

        path = _write(tmp_path, "features: [unclosed\n")
        with pytest.raises(self._err(), match="not valid YAML"):
            load_weights(path)

    def test_top_level_must_be_mapping(self, tmp_path):
        from pipeline.integration.confidence import load_weights

        path = _write(tmp_path, "- just\n- a list\n")
        with pytest.raises(self._err(), match="mapping"):
            load_weights(path)

    def test_missing_and_unknown_top_level_keys(self):
        raw = _default_raw()
        del raw["thresholds"]
        with pytest.raises(self._err(), match="missing top-level key.*thresholds"):
            _parse(raw)
        raw = _default_raw()
        raw["extra"] = 1
        with pytest.raises(self._err(), match="unknown top-level key.*extra"):
            _parse(raw)

    def test_version_required(self):
        raw = _default_raw()
        raw["version"] = ""
        with pytest.raises(self._err(), match="version"):
            _parse(raw)

    def test_features_must_match_scored_columns(self):
        raw = _default_raw()
        del raw["features"]["slope_deg"]
        raw["features"]["slopes"] = raw["features"]["elevation_m"]
        with pytest.raises(self._err(), match=r"missing \['slope_deg'\].*unknown \['slopes'\]"):
            _parse(raw)

    @pytest.mark.parametrize("value", [0, -0.1, "0.3", True])
    def test_weight_must_be_positive_number(self, value):
        raw = _default_raw()
        raw["features"]["wind_speed"]["weight"] = value
        with pytest.raises(self._err(), match=r"features\.wind_speed\.weight"):
            _parse(raw)

    @pytest.mark.parametrize("key,value", [("resolution", 0), ("resolution", 1.5),
                                           ("limitation", 0), ("limitation", 2), ("limitation", False)])
    def test_resolution_and_limitation_in_unit_interval(self, key, value):
        raw = _default_raw()
        raw["features"]["land_use"][key] = value
        with pytest.raises(self._err(), match=rf"features\.land_use\.{key}.*\(0, 1\]"):
            _parse(raw)

    def test_feature_note_required(self):
        raw = _default_raw()
        raw["features"]["tri" if False else "elevation_m"]["note"] = ""
        with pytest.raises(self._err(), match=r"features\.elevation_m\.note"):
            _parse(raw)

    def test_feature_unknown_key(self):
        raw = _default_raw()
        raw["features"]["elevation_m"]["weigth"] = 0.1
        with pytest.raises(self._err(), match=r"features\.elevation_m has unknown key.*weigth"):
            _parse(raw)

    def test_flag_layer_must_be_known(self):
        raw = _default_raw()
        raw["flag_factors"]["exclusions"] = {"features": ["wind_speed"], "factors": {"x": 1.0}}
        with pytest.raises(self._err(), match="unknown layer.*exclusions"):
            _parse(raw)

    def test_flag_factors_must_cover_vocabulary_exactly(self):
        raw = _default_raw()
        del raw["flag_factors"]["demand"]["factors"]["medium"]
        with pytest.raises(self._err(), match=r"flag_factors\.demand\.factors.*missing \['medium'\]"):
            _parse(raw)
        raw = _default_raw()
        raw["flag_factors"]["demand"]["factors"]["unknown"] = 0.5
        with pytest.raises(self._err(), match=r"flag_factors\.demand\.factors.*unknown \['unknown'\]"):
            _parse(raw)

    @pytest.mark.parametrize("value", [1.5, -0.1, "1"])
    def test_flag_factor_in_closed_unit_interval(self, value):
        raw = _default_raw()
        raw["flag_factors"]["geographic"]["factors"]["low"] = value
        with pytest.raises(self._err(), match=r"flag_factors\.geographic\.factors\.low.*\[0, 1\]"):
            _parse(raw)

    def test_feature_scoped_under_two_layers(self):
        raw = _default_raw()
        raw["flag_factors"]["wind"]["features"].append("elevation_m")
        with pytest.raises(self._err(), match="elevation_m.*more than one layer"):
            _parse(raw)

    def test_scoped_feature_must_be_scored(self):
        raw = _default_raw()
        raw["flag_factors"]["wind"]["features"] = ["tri"]
        with pytest.raises(self._err(), match=r"flag_factors\.wind\.features.*tri"):
            _parse(raw)

    def test_note_required_when_factor_below_one(self):
        raw = _default_raw()
        del raw["flag_factors"]["geographic"]["notes"]["low"]
        with pytest.raises(self._err(), match=r"flag_factors\.geographic\.notes\.low is required"):
            _parse(raw)

    def test_note_for_unknown_flag_value(self):
        raw = _default_raw()
        raw["flag_factors"]["geographic"]["notes"]["mid"] = "x"
        with pytest.raises(self._err(), match=r"flag_factors\.geographic\.notes.*unknown.*mid"):
            _parse(raw)

    def test_soft_flags_validation(self):
        raw = _default_raw()
        raw["soft_flags"].append({"match": "", "factor": 1.0, "note": "n"})
        with pytest.raises(self._err(), match=r"soft_flags\[1\]\.match"):
            _parse(raw)
        raw = _default_raw()
        raw["soft_flags"].append(dict(raw["soft_flags"][0]))
        with pytest.raises(self._err(), match="duplicate soft_flags match"):
            _parse(raw)
        raw = _default_raw()
        raw["soft_flags"][0]["factor"] = 0
        with pytest.raises(self._err(), match=r"soft_flags\[0\]\.factor.*\(0, 1\]"):
            _parse(raw)
        raw = _default_raw()
        raw["soft_flags"][0]["note"] = ""
        with pytest.raises(self._err(), match=r"soft_flags\[0\]\.note"):
            _parse(raw)

    def test_soft_flags_optional(self):
        raw = _default_raw()
        del raw["soft_flags"]
        assert _parse(raw).soft_flags == ()

    @pytest.mark.parametrize("high,medium", [(1.1, 0.5), (0.8, -0.1), (0.5, 0.5), (0.4, 0.6), ("0.8", 0.5)])
    def test_thresholds_ordering(self, high, medium):
        raw = _default_raw()
        raw["thresholds"] = {"high": high, "medium": medium}
        with pytest.raises(self._err(), match="thresholds"):
            _parse(raw)

    def test_load_records_path_and_sha(self, tmp_path):
        from pipeline.common.geo import sha256_file
        from pipeline.integration.confidence import load_weights

        path = _write(tmp_path, _default_raw())
        w = load_weights(path)
        assert w.path == path and w.sha256 == sha256_file(path)
