"""
Compensation-guard cross-module test (S2-03 acceptance criterion).

Proves, end to end across the exclusion -> scoring boundary, that:

  A high wind score can NEVER compensate for a hard exclusion.

The exclusion layer (S1-07 / S2-03) sets `eligible = False` on an excluded
cell; the scoring core (S1-10) consumes that flag as its gate. This test
builds a synthetic integrated feature table over the six real scored criteria
(Decision_Engine_Spec §2 / §4) with one excluded cell whose `wind_speed` is
pushed far ABOVE every eligible cell's wind — the exact "a great resource
buys its way past the gate" scenario the acceptance criterion forbids — and
asserts the scoring core:

  1. leaves the excluded cell with a NULL suitability_score, NULL rank and
     NULL contributions (it is never scored, so wind cannot lift it); and
  2. does not let that cell's extreme wind stretch the normalisation bounds
     the eligible candidates are measured on (§5.2 eligible-only bounds).

This is deliberately a scoring-stage test rather than an exclusions-stage
test: the guarantee that matters is that the CONSUMER of the eligibility
flag honours it, which is where a regression would silently re-admit
excluded land to the ranking.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from pipeline.scoring import config as scfg
from pipeline.scoring.normalise import compute_bounds
from pipeline.scoring.score import score_and_rank
from pipeline.scoring.weights import Criterion, WeightsConfig

TOL = 1e-12

# The six scored criteria of the frozen decision-engine contract (§4.1),
# with their real directions. Weights here are only relative; wind carries
# the largest weight, which is precisely what makes the guard meaningful —
# even the most heavily weighted criterion cannot rescue an excluded cell.
_CRITERIA = (
    Criterion("wind_speed", 0.35, scfg.HIGHER_IS_BETTER, "resource"),
    Criterion("dist_transmission_km", 0.20, scfg.LOWER_IS_BETTER, "connection cost"),
    Criterion("demand_proxy", 0.15, scfg.HIGHER_IS_BETTER, "offtake"),
    Criterion("dist_substation_km", 0.10, scfg.LOWER_IS_BETTER, "interconnection"),
    Criterion("slope_deg", 0.10, scfg.LOWER_IS_BETTER, "civil works"),
    Criterion("inside_rez", 0.10, scfg.HIGHER_IS_BETTER, "policy"),
)


def _weights() -> WeightsConfig:
    return WeightsConfig(
        criteria=_CRITERIA,
        confidence_discount=False,
        confidence_factors={"high": 1.0, "medium": 0.9, "low": 0.5},
        config_id="test-compensation-guard",
    )


def _features() -> pd.DataFrame:
    """
    Four cells over the six scored criteria. Cells A/B/C are eligible with
    ordinary values; cell EXCLUDED_MAXWIND is `eligible = False` and carries
    the maximum wind, minimum distances, and best of every other criterion —
    a cell that would rank first if the exclusion were (wrongly) ignored.
    """
    return pd.DataFrame(
        {
            "cell_id": ["A", "B", "C", "EXCLUDED_MAXWIND"],
            # eligible winds 6-10; excluded cell is far above them all
            "wind_speed": [10.0, 8.0, 6.0, 999.0],
            "dist_transmission_km": [5.0, 10.0, 20.0, 0.0],
            "demand_proxy": [0.5, 0.4, 0.3, 1.0],
            "dist_substation_km": [3.0, 6.0, 9.0, 0.0],
            "slope_deg": [5.0, 8.0, 12.0, 0.0],
            "inside_rez": [True, False, True, True],
            "eligible": [True, True, True, False],
            "data_confidence": ["high", "high", "high", "high"],
        }
    )


class TestHighWindCannotOverrideExclusion:
    def test_excluded_maxwind_cell_is_never_scored_or_ranked(self):
        weights = _weights()
        scored = score_and_rank(_features(), weights).set_index("cell_id")

        # The excluded cell — despite the best wind and best everything — is
        # null throughout. Wind bought it nothing.
        assert pd.isna(scored.loc["EXCLUDED_MAXWIND", scfg.SCORE_COLUMN])
        assert pd.isna(scored.loc["EXCLUDED_MAXWIND", scfg.RANK_COLUMN])
        for column in weights.contribution_columns:
            assert pd.isna(scored.loc["EXCLUDED_MAXWIND", column])

        # The eligible cells are scored and ranked normally; the top rank goes
        # to an ELIGIBLE cell, never the excluded one.
        eligible_ranks = scored.loc[["A", "B", "C"], scfg.RANK_COLUMN]
        assert set(eligible_ranks) == {1, 2, 3}
        assert scored.loc["A", scfg.RANK_COLUMN] == 1  # best eligible wind

    def test_excluded_extreme_wind_does_not_stretch_bounds(self):
        """
        §5.2 — bounds come from the eligible population only. The excluded
        cell's wind of 999 must not become the upper bound; if it did, it
        would compress every eligible cell's normalised wind and silently let
        the exclusion influence the ranking it is supposed to be removed from.
        """
        features = _features()
        eligible = features[features["eligible"]]
        bounds = compute_bounds(eligible, _CRITERIA)

        # wind bound is the eligible max (10), never the excluded 999
        assert bounds["wind_speed"].hi == pytest.approx(10.0, abs=TOL)
        assert bounds["wind_speed"].lo == pytest.approx(6.0, abs=TOL)
        # distances: the excluded cell's 0.0 must not become the lower bound
        assert bounds["dist_transmission_km"].lo == pytest.approx(5.0, abs=TOL)
        assert bounds["dist_substation_km"].lo == pytest.approx(3.0, abs=TOL)
        assert bounds["slope_deg"].lo == pytest.approx(5.0, abs=TOL)

    def test_null_eligibility_is_also_gated_out(self):
        """
        An unknown eligibility is not an eligibility — a null `eligible` with
        maximal wind is treated exactly like an explicit exclusion and is
        never scored (score.eligible_mask contract).
        """
        features = _features()
        features["eligible"] = features["eligible"].astype("object")
        features.loc[features["cell_id"] == "EXCLUDED_MAXWIND", "eligible"] = np.nan
        scored = score_and_rank(features, _weights()).set_index("cell_id")
        assert pd.isna(scored.loc["EXCLUDED_MAXWIND", scfg.SCORE_COLUMN])
        assert pd.isna(scored.loc["EXCLUDED_MAXWIND", scfg.RANK_COLUMN])
