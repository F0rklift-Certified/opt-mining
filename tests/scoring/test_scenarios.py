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
    ScenarioComparison,
    compare_scenarios,
    load_scenarios,
    parse_scenarios,
    run_scenario,
)
from pipeline.scoring.weights import ScoringConfigError, parse_weights

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


def _two_criterion_scenario(name, label, w_wind, w_dist) -> Scenario:
    """Build a two-criterion Scenario over wind_speed + dist_transmission_km."""
    body = {
        "criteria": [
            {"feature": "wind_speed", "weight": w_wind,
             "direction": "higher_is_better", "rationale": "resource"},
            {"feature": "dist_transmission_km", "weight": w_dist,
             "direction": "lower_is_better", "rationale": "grid cost"},
        ]
    }
    return Scenario(name=name, label=label, description="desc",
                    weights=parse_weights(body, config_id="x"))


class TestCompareScenarios:
    def test_mismatched_criteria_sets_raise(self):
        wind = _two_criterion_scenario("wind_led", "Wind-led", 0.6, 0.4)
        # A scenario over a different criteria set (adds slope_deg).
        other = Scenario(
            name="other", label="Other", description="desc",
            weights=parse_weights(
                {"criteria": [
                    {"feature": "wind_speed", "weight": 0.5,
                     "direction": "higher_is_better", "rationale": "r"},
                    {"feature": "slope_deg", "weight": 0.5,
                     "direction": "lower_is_better", "rationale": "r"},
                ]}, config_id="x"),
        )
        with pytest.raises(ScoringConfigError, match="different criteria sets"):
            compare_scenarios(_tiny_features(), wind, other)

    def test_rows_cover_the_scored_intersection(self):
        features = _tiny_features()  # 4 eligible cells, all scored under any weights
        a = _two_criterion_scenario("wind_led", "Wind-led", 0.7, 0.3)
        b = _two_criterion_scenario("grid_led", "Grid-led", 0.3, 0.7)

        comparison = compare_scenarios(features, a, b)
        assert isinstance(comparison, ScenarioComparison)
        assert {row.cell_id for row in comparison.rows} == set(features["cell_id"])

    def test_shared_bounds_only_weights_differ(self):
        """
        compare_scenarios must score both scenarios against ONE bounds set from
        the eligible population. We verify by reproducing each scenario with
        that shared bounds via run_scenario and asserting identical scores —
        proving the comparison did not recompute bounds per scenario.
        """
        from pipeline.scoring.normalise import compute_bounds

        features = _tiny_features()
        a = _two_criterion_scenario("wind_led", "Wind-led", 0.7, 0.3)
        b = _two_criterion_scenario("grid_led", "Grid-led", 0.3, 0.7)

        shared = compute_bounds(features, a.weights.criteria)
        expect_a = run_scenario(features, a, bounds=shared).set_index("cell_id")
        expect_b = run_scenario(features, b, bounds=shared).set_index("cell_id")

        comparison = compare_scenarios(features, a, b)
        for row in comparison.rows:
            assert row.score_a == pytest.approx(
                expect_a.loc[row.cell_id, scfg.SCORE_COLUMN])
            assert row.score_b == pytest.approx(
                expect_b.loc[row.cell_id, scfg.SCORE_COLUMN])

    def test_rank_and_score_deltas_are_consistent(self):
        features = _tiny_features()
        a = _two_criterion_scenario("wind_led", "Wind-led", 0.7, 0.3)
        b = _two_criterion_scenario("grid_led", "Grid-led", 0.3, 0.7)
        comparison = compare_scenarios(features, a, b)
        for row in comparison.rows:
            assert row.rank_delta == row.rank_a - row.rank_b
            assert row.score_delta == pytest.approx(row.score_a - row.score_b)

    def test_to_dict_matches_s2_08_shape(self):
        features = _tiny_features()
        a = _two_criterion_scenario("wind_led", "Wind-led", 0.7, 0.3)
        b = _two_criterion_scenario("grid_led", "Grid-led", 0.3, 0.7)
        payload = compare_scenarios(features, a, b).to_dict()

        # S2-08 ScenarioComparison = { rows: [...], labels: {a, b} }
        assert set(payload) >= {"rows", "labels"}
        assert payload["labels"] == {"a": "Wind-led", "b": "Grid-led"}
        for row in payload["rows"]:
            # Required S2-08 fields plus the additive score fields.
            assert set(row) >= {"cell_id", "rank_a", "rank_b", "rank_delta"}
            assert set(row) >= {"score_a", "score_b", "score_delta"}


# ===========================================================================
# CONTROLLED HAND-COMPUTED RE-RANKING CASE (S2-07 AC: different weights produce
# different, correctly re-ranked outputs). Every number below is derived on
# paper from the frozen formula, not copied from a code run.
# ===========================================================================
#
# Two criteria, bounds from the eligible population (all three cells eligible):
#     wind_speed            higher_is_better   bounds [0, 10]
#     dist_transmission_km  lower_is_better    bounds [0, 10]
#
# Cells:
#     cell_id  wind_speed  dist_transmission_km   profile
#     w        10.0         10.0                  wind-strong / grid-far
#     g         0.0          0.0                  wind-weak   / grid-near
#     m         5.0          5.0                  middle
#
# Normalise (higher: (v-lo)/(hi-lo); lower: 1-(v-lo)/(hi-lo)):
#     w: norm_wind = 10/10 = 1.0 ; norm_dist = 1 - 10/10 = 0.0
#     g: norm_wind =  0/10 = 0.0 ; norm_dist = 1 -  0/10 = 1.0
#     m: norm_wind =  5/10 = 0.5 ; norm_dist = 1 -  5/10 = 0.5
#
# Wind-led weights: wind 0.8, dist 0.2   (W = 1.0)
#     S(w) = 0.8*1.0 + 0.2*0.0 = 0.80  -> rank 1
#     S(m) = 0.8*0.5 + 0.2*0.5 = 0.50  -> rank 2
#     S(g) = 0.8*0.0 + 0.2*1.0 = 0.20  -> rank 3
#
# Grid-led weights: wind 0.2, dist 0.8   (W = 1.0)
#     S(g) = 0.2*0.0 + 0.8*1.0 = 0.80  -> rank 1
#     S(m) = 0.2*0.5 + 0.8*0.5 = 0.50  -> rank 2
#     S(w) = 0.2*1.0 + 0.8*0.0 = 0.20  -> rank 3
#
# THE SWAP: w goes rank 1 (Wind-led) -> rank 3 (Grid-led); g goes rank 3 -> 1;
# m stays rank 2. Bounds are shared, so ONLY the weights caused the re-ranking.
# rank_delta = rank_a - rank_b, so w = 1 - 3 = -2 and g = 3 - 1 = +2 (a
# negative delta means scenario B ranks the cell higher).
# ===========================================================================

_CTRL_TOL = 1e-12


def _ctrl_features() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cell_id": ["w", "g", "m"],
            "wind_speed": [10.0, 0.0, 5.0],
            "dist_transmission_km": [10.0, 0.0, 5.0],
            "eligible": [True, True, True],
            "data_confidence": ["high", "high", "high"],
        }
    )


class TestControlledReRanking:
    """Different weights produce a specific, hand-verified rank swap."""

    def test_wind_led_and_grid_led_produce_the_hand_computed_ranks(self):
        features = _ctrl_features()
        wind = _two_criterion_scenario("wind_led", "Wind-led", 0.8, 0.2)
        grid = _two_criterion_scenario("grid_led", "Grid-led", 0.2, 0.8)

        a = run_scenario(features, wind).set_index("cell_id")
        b = run_scenario(features, grid).set_index("cell_id")

        # Wind-led scores and ranks.
        assert a.loc["w", scfg.SCORE_COLUMN] == pytest.approx(0.80, abs=_CTRL_TOL)
        assert a.loc["m", scfg.SCORE_COLUMN] == pytest.approx(0.50, abs=_CTRL_TOL)
        assert a.loc["g", scfg.SCORE_COLUMN] == pytest.approx(0.20, abs=_CTRL_TOL)
        assert a.loc["w", scfg.RANK_COLUMN] == 1
        assert a.loc["m", scfg.RANK_COLUMN] == 2
        assert a.loc["g", scfg.RANK_COLUMN] == 3

        # Grid-led scores and ranks — the top and bottom cells swap.
        assert b.loc["g", scfg.SCORE_COLUMN] == pytest.approx(0.80, abs=_CTRL_TOL)
        assert b.loc["m", scfg.SCORE_COLUMN] == pytest.approx(0.50, abs=_CTRL_TOL)
        assert b.loc["w", scfg.SCORE_COLUMN] == pytest.approx(0.20, abs=_CTRL_TOL)
        assert b.loc["g", scfg.RANK_COLUMN] == 1
        assert b.loc["m", scfg.RANK_COLUMN] == 2
        assert b.loc["w", scfg.RANK_COLUMN] == 3

    def test_comparison_reports_the_hand_computed_rank_deltas(self):
        features = _ctrl_features()
        wind = _two_criterion_scenario("wind_led", "Wind-led", 0.8, 0.2)
        grid = _two_criterion_scenario("grid_led", "Grid-led", 0.2, 0.8)

        rows = {r.cell_id: r for r in compare_scenarios(features, wind, grid).rows}

        # w: rank 1 under Wind-led, rank 3 under Grid-led -> delta 1-3 = -2.
        assert rows["w"].rank_a == 1 and rows["w"].rank_b == 3
        assert rows["w"].rank_delta == -2
        # g: rank 3 -> rank 1 -> delta 3-1 = +2.
        assert rows["g"].rank_a == 3 and rows["g"].rank_b == 1
        assert rows["g"].rank_delta == 2
        # m: unchanged at rank 2.
        assert rows["m"].rank_a == 2 and rows["m"].rank_b == 2
        assert rows["m"].rank_delta == 0

    def test_only_weights_differ_shared_bounds_hold_scores_symmetric(self):
        """
        The re-ranking is caused ONLY by the weights: w and g have mirror-image
        normalised profiles, so swapping the weights swaps their scores exactly
        (w scores 0.80/0.20, g scores 0.20/0.80). This is only true if both
        scenarios normalised against the same [0, 10] bounds.
        """
        features = _ctrl_features()
        wind = _two_criterion_scenario("wind_led", "Wind-led", 0.8, 0.2)
        grid = _two_criterion_scenario("grid_led", "Grid-led", 0.2, 0.8)
        rows = {r.cell_id: r for r in compare_scenarios(features, wind, grid).rows}

        assert rows["w"].score_a == pytest.approx(rows["g"].score_b, abs=_CTRL_TOL)
        assert rows["w"].score_b == pytest.approx(rows["g"].score_a, abs=_CTRL_TOL)
