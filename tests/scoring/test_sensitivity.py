"""
Unit tests for the S4-08 sensitivity runner (`scripts/sensitivity_analysis.py`).

A small synthetic frame keeps the real scoring engine in the loop while the
expected rank movements stay hand-checkable. No DATA/ file is read or written.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.scoring import config as scoring_config
from pipeline.scoring.scenarios import Scenario
from pipeline.scoring.weights import Criterion, WeightsConfig
from scripts import sensitivity_analysis as sa


def _weights(wind: float, grid: float, config_id: str = "test") -> WeightsConfig:
    return WeightsConfig(
        criteria=(
            Criterion("wind_speed", wind, scoring_config.HIGHER_IS_BETTER, "resource"),
            Criterion("dist_transmission_km", grid, scoring_config.LOWER_IS_BETTER, "grid"),
        ),
        confidence_discount=False,
        confidence_factors={"high": 1.0, "medium": 0.9, "low": 0.8},
        config_id=config_id,
    )


def _features(n: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    return pd.DataFrame(
        {
            "cell_id": [f"C{i:03d}" for i in range(n)] + ["X"],
            "wind_speed": list(rng.uniform(5, 10, n)) + [99.0],
            "dist_transmission_km": list(rng.uniform(0, 50, n)) + [-99.0],
            "eligible": [True] * n + [False],
            "data_confidence": ["high"] * (n + 1),
        }
    )


def test_perturb_scales_only_the_named_criterion():
    weights = _weights(0.6, 0.4)
    changed = sa.perturb(weights, "wind_speed", -0.2)
    assert [c.weight for c in changed.criteria] == pytest.approx([0.48, 0.4])
    assert [c.weight for c in weights.criteria] == [0.6, 0.4]  # original untouched
    assert changed.config_id == "test:wind_speed-20%"


def test_kendall_tau_matches_known_values():
    assert sa.kendall_tau(np.array([1, 2, 3, 4.0]), np.array([1, 2, 3, 4.0])) == 1.0
    assert sa.kendall_tau(np.array([1, 2, 3, 4.0]), np.array([4, 3, 2, 1.0])) == -1.0
    assert sa.kendall_tau(np.array([1.0]), np.array([1.0])) is None


def test_identical_rankings_are_perfectly_stable():
    ranks = pd.Series([1, 2, 3, 4], index=["a", "b", "c", "d"])
    metrics = sa.compare_rankings(ranks, ranks)
    assert metrics["spearman_all_eligible"] == pytest.approx(1.0)
    assert metrics["rank1_unchanged"] is True
    assert metrics["max_rank_shift_base_top20"] == 0


def test_run_analysis_covers_every_perturbation_and_scenario():
    features = _features()
    weights = _weights(0.6, 0.4)
    scenarios = {
        "grid_led": Scenario("grid_led", "Grid-led", "grid first", _weights(0.1, 0.9, "grid")),
    }
    result = sa.run_analysis(features, weights, scenarios)

    assert result["n_eligible"] == 60
    perturbations = [r for r in result["runs"] if r["kind"] == "perturbation"]
    assert len(perturbations) == len(weights.criteria) * len(sa.PERTURBATIONS)
    # Small perturbations keep the ranking highly correlated with the baseline.
    assert all(r["spearman_all_eligible"] > 0.9 for r in perturbations)
    # Reversing the emphasis moves the ranking far more than any +/-20 % change.
    scenario = next(r for r in result["runs"] if r["kind"] == "scenario")
    assert scenario["spearman_all_eligible"] < min(r["spearman_all_eligible"] for r in perturbations)
    # The excluded cell never enters a ranking.
    assert "X" not in result["baseline_top20"]


def test_markdown_lists_one_row_per_run():
    features = _features()
    result = sa.run_analysis(features, _weights(0.6, 0.4), {})
    result.update(integrated_sha256="abc", code_version="def")
    text = sa.render_markdown(result)
    assert text.count("\n| wind_speed ") == len(sa.PERTURBATIONS)
    assert "Integrated table SHA-256: `abc`" in text
