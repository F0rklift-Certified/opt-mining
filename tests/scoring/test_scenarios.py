"""
Tests for the S2-07 scenario / weight-comparison engine.

Feature: s2-07-scenario-weight-comparison-engine.

This module covers scenario loading and validation (Task 2). The scenario
abstraction is a named weight set validated by the SAME validator as the
default weights, so a malformed preset must fail loudly — and name the
offending scenario — before any scoring is attempted.
"""

from __future__ import annotations

import copy

import pytest
import yaml

import pandas as pd

from pipeline.scoring import config as scfg
from pipeline.scoring.score import score_and_rank
from pipeline.scoring.scenarios import (
    Scenario,
    load_scenarios,
    parse_scenarios,
    run_scenario,
)
from pipeline.scoring.weights import ScoringConfigError

# A minimal but valid two-criteria scenario body used across the fault-path
# tests. Two criteria (not the full six) keeps the fixtures readable; the
# packaged scenarios.yaml carries the full frozen criteria set.
_VALID_CRITERIA = [
    {"feature": "wind_speed", "weight": 0.6, "direction": "higher_is_better",
     "rationale": "resource quality"},
    {"feature": "dist_transmission_km", "weight": 0.4, "direction": "lower_is_better",
     "rationale": "grid cost"},
]


def _scenarios_body(**overrides) -> dict:
    """
    A valid two-scenario mapping, with per-test overrides merged in.

    Deep-copied so a test that mutates a nested criterion cannot leak the
    change into another test through the shared module-level fixtures.
    """
    body = {
        "scenarios": {
            "wind_led": {
                "label": "Wind-led",
                "description": "Emphasises wind resource",
                "criteria": copy.deepcopy(_VALID_CRITERIA),
            },
            "grid_led": {
                "label": "Grid-led",
                "description": "Emphasises grid accessibility",
                "criteria": [
                    {"feature": "wind_speed", "weight": 0.3,
                     "direction": "higher_is_better", "rationale": "resource"},
                    {"feature": "dist_transmission_km", "weight": 0.7,
                     "direction": "lower_is_better", "rationale": "grid cost"},
                ],
            },
        }
    }
    body.update(overrides)
    return body


class TestLoadPackagedScenarios:
    """The shipped scenarios.yaml is valid and exposes the two documented presets."""

    def test_packaged_file_loads_both_presets_with_labels(self):
        scenarios = load_scenarios()  # defaults to config.DEFAULT_SCENARIOS_PATH

        assert set(scenarios) == {"wind_led", "grid_led"}
        assert scenarios["wind_led"].label == "Wind-led"
        assert scenarios["grid_led"].label == "Grid-led"
        for scenario in scenarios.values():
            assert isinstance(scenario, Scenario)
            assert scenario.description  # non-empty

    def test_packaged_presets_share_the_same_criteria_set(self):
        """Only weights differ between presets — the criteria set is identical."""
        scenarios = load_scenarios()
        assert scenarios["wind_led"].features == scenarios["grid_led"].features

    def test_packaged_presets_carry_distinct_weights(self):
        """The whole point of a scenario: the weight sets genuinely differ."""
        scenarios = load_scenarios()
        wind_w = {c.feature: c.weight for c in scenarios["wind_led"].weights.criteria}
        grid_w = {c.feature: c.weight for c in scenarios["grid_led"].weights.criteria}
        assert wind_w != grid_w
        # Wind-led weights wind above grid; Grid-led weights transmission above wind.
        assert wind_w["wind_speed"] > wind_w["dist_transmission_km"]
        assert grid_w["dist_transmission_km"] > grid_w["wind_speed"]


class TestParseScenariosValid:
    def test_valid_body_parses_two_scenarios(self):
        scenarios = parse_scenarios(_scenarios_body(), config_id="test")
        assert set(scenarios) == {"wind_led", "grid_led"}
        assert scenarios["wind_led"].weights.weight_sum == pytest.approx(1.0)


class TestParseScenariosFaults:
    """Every fault names the offending scenario and raises before any scoring."""

    def test_empty_file_fails(self):
        with pytest.raises(ScoringConfigError, match="empty"):
            parse_scenarios(None)

    def test_no_scenarios_key_fails(self):
        with pytest.raises(ScoringConfigError, match="non-empty mapping"):
            parse_scenarios({"scenarios": {}})

    def test_missing_label_fails_naming_the_scenario(self):
        body = _scenarios_body()
        del body["scenarios"]["wind_led"]["label"]
        with pytest.raises(ScoringConfigError, match="wind_led.*label"):
            parse_scenarios(body)

    def test_missing_description_fails_naming_the_scenario(self):
        body = _scenarios_body()
        del body["scenarios"]["grid_led"]["description"]
        with pytest.raises(ScoringConfigError, match="grid_led.*description"):
            parse_scenarios(body)

    def test_missing_criteria_fails_naming_the_scenario(self):
        body = _scenarios_body()
        del body["scenarios"]["wind_led"]["criteria"]
        with pytest.raises(ScoringConfigError, match="wind_led.*criteria"):
            parse_scenarios(body)

    def test_negative_weight_fails_naming_the_scenario(self):
        body = _scenarios_body()
        body["scenarios"]["wind_led"]["criteria"][0]["weight"] = -0.1
        with pytest.raises(ScoringConfigError, match="wind_led"):
            parse_scenarios(body)

    def test_zero_weight_sum_fails_naming_the_scenario(self):
        body = _scenarios_body()
        for c in body["scenarios"]["grid_led"]["criteria"]:
            c["weight"] = 0.0
        with pytest.raises(ScoringConfigError, match="grid_led"):
            parse_scenarios(body)

    def test_invalid_direction_fails_naming_the_scenario(self):
        body = _scenarios_body()
        body["scenarios"]["wind_led"]["criteria"][0]["direction"] = "sideways"
        with pytest.raises(ScoringConfigError, match="wind_led"):
            parse_scenarios(body)


class TestLoadScenariosFromDisk:
    def test_missing_file_fails(self, tmp_path):
        missing = tmp_path / "nope.yaml"
        with pytest.raises(ScoringConfigError, match="not found"):
            load_scenarios(missing)

    def test_unparsable_yaml_fails(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("scenarios: [unterminated\n", encoding="utf-8")
        with pytest.raises(ScoringConfigError, match="not valid YAML"):
            load_scenarios(bad)

    def test_roundtrip_from_written_file(self, tmp_path):
        path = tmp_path / "scenarios.yaml"
        path.write_text(yaml.safe_dump(_scenarios_body()), encoding="utf-8")
        scenarios = load_scenarios(path)
        assert set(scenarios) == {"wind_led", "grid_led"}


def _tiny_features() -> pd.DataFrame:
    """A two-criterion, four-cell eligible table for the pass-through tests."""
    return pd.DataFrame(
        {
            "cell_id": ["a", "b", "c", "d"],
            "wind_speed": [8.0, 6.0, 4.0, 2.0],
            "dist_transmission_km": [10.0, 6.0, 4.0, 2.0],
            "eligible": [True, True, True, True],
            "data_confidence": ["high", "high", "high", "high"],
        }
    )


class TestRunScenarioIsPureReuse:
    """
    run_scenario is a pass-through: its output must equal score_and_rank
    called directly with the scenario's weights and the same bounds. If they
    ever diverge, a scenario-specific scorer has crept in.
    """

    def test_output_equals_score_and_rank_no_bounds(self):
        features = _tiny_features()
        scenario = parse_scenarios(_scenarios_body(), config_id="x")["wind_led"]

        via_scenario = run_scenario(features, scenario)
        direct = score_and_rank(features.copy(), scenario.weights)
        pd.testing.assert_frame_equal(via_scenario, direct, check_exact=True)

    def test_output_equals_score_and_rank_with_shared_bounds(self):
        from pipeline.scoring.normalise import compute_bounds

        features = _tiny_features()
        scenario = parse_scenarios(_scenarios_body(), config_id="x")["grid_led"]
        bounds = compute_bounds(features, scenario.weights.criteria)

        via_scenario = run_scenario(features, scenario, bounds=bounds)
        direct = score_and_rank(features.copy(), scenario.weights, bounds=bounds)
        pd.testing.assert_frame_equal(via_scenario, direct, check_exact=True)
