"""
Controlled hand-computed ranking case for the S2-05 scoring engine.

Feature: s2-05-suitability-scoring-ranking (Requirement 7.3, design.md
"Controlled_Test_Case"; guidance Step 11 — the KEY SAFEGUARD against a subtly
wrong formula).

This module holds ONE tiny synthetic integrated table (five cells, one of
them excluded) whose expected suitability_score, per-criterion contributions
and rank are HAND-COMPUTED below — every number is derived on paper from the
frozen S2-01 formula, not copied from a previous run of the code. If the
weighted-sum formula, the directional min-max normalisation, the W-cell
denominator (weight re-normalisation), the eligible-only rule, or the
ascending-cell_id tie-break ever drift, this end-to-end assertion breaks.

It exercises `score_and_rank` — the complete pure core (score + rank) — so
the whole computation is checked in one call, not a single stage in
isolation.

FROZEN FORMULA (S2-01 decision-engine spec §5, mirrored in
pipeline/scoring/README.md):

    norm_k(i)  = (v - lo_k) / (hi_k - lo_k)             for higher_is_better
    norm_k(i)  = 1 - (v - lo_k) / (hi_k - lo_k)         for lower_is_better
    contrib_k  = w_k * norm_k(i) / W_i                  W_i = Σ applied w_k
    S_i        = Σ_k contrib_k                          in [0, 1]

Bounds lo_k / hi_k are the min/max over the ELIGIBLE population only. Ties in
S_i are broken by ASCENDING cell_id; rank 1 is the best cell; excluded cells
get null score / rank / contributions and take no part in the bounds.

============================================================================
HAND-COMPUTATION (verify this arithmetic on paper)
============================================================================

Criteria and weights (deliberately NOT summing to 1, so the W_i denominator
genuinely RE-NORMALISES the weights — this is the weight re-normalisation the
task asks the controlled case to cover):

    wind_speed            weight 2.0   higher_is_better
    dist_transmission_km  weight 1.0   lower_is_better
    slope_deg             weight 1.0   lower_is_better

    W_i = 2.0 + 1.0 + 1.0 = 4.0   (every eligible cell has all three values)

Cells (c5 is EXCLUDED; its values are extreme on purpose, to prove excluded
cells never stretch the normalisation bounds):

    cell_id  wind_speed  dist_transmission_km  slope_deg  eligible
    c2        8.0          2.0                    5.0       True
    c1        8.0          2.0                    5.0       True     (== c2 -> tie)
    c3        4.0          6.0                   15.0       True
    c4        0.0         10.0                   25.0       True
    c5      999.0       -999.0                  999.0       False    (excluded)

Bounds from the ELIGIBLE cells (c1..c4) ONLY — c5 is ignored:

    wind_speed:            lo = 0.0,  hi = 8.0     (NOT 999.0)
    dist_transmission_km:  lo = 2.0,  hi = 10.0    (NOT -999.0)
    slope_deg:             lo = 5.0,  hi = 25.0    (NOT 999.0)

Normalise (higher: (v-lo)/(hi-lo);  lower: 1 - (v-lo)/(hi-lo)):

  c1 and c2 (identical inputs):
    wind : (8 - 0)/(8 - 0)      = 1.0
    dist : 1 - (2 - 2)/(10 - 2) = 1 - 0.0 = 1.0
    slope: 1 - (5 - 5)/(25 - 5) = 1 - 0.0 = 1.0
    contrib_wind  = 2.0 * 1.0 / 4.0 = 0.50
    contrib_dist  = 1.0 * 1.0 / 4.0 = 0.25
    contrib_slope = 1.0 * 1.0 / 4.0 = 0.25
    S             = 0.50 + 0.25 + 0.25 = 1.00

  c3:
    wind : (4 - 0)/8            = 0.5
    dist : 1 - (6 - 2)/8        = 1 - 0.5 = 0.5
    slope: 1 - (15 - 5)/20      = 1 - 0.5 = 0.5
    contrib_wind  = 2.0 * 0.5 / 4.0 = 0.25
    contrib_dist  = 1.0 * 0.5 / 4.0 = 0.125
    contrib_slope = 1.0 * 0.5 / 4.0 = 0.125
    S             = 0.25 + 0.125 + 0.125 = 0.50

  c4:
    wind : (0 - 0)/8            = 0.0
    dist : 1 - (10 - 2)/8       = 1 - 1.0 = 0.0
    slope: 1 - (25 - 5)/20      = 1 - 1.0 = 0.0
    contrib_wind  = 0.0 ; contrib_dist = 0.0 ; contrib_slope = 0.0
    S             = 0.00

  c5: EXCLUDED -> score null, rank null, contributions null.

Expected scores:  c1 = 1.00,  c2 = 1.00,  c3 = 0.50,  c4 = 0.00,  c5 = null

Rank = descending score, ties by ASCENDING cell_id. c1 and c2 tie at 1.00, so
c1 (smaller id) outranks c2:

    rank 1 -> c1   (score 1.00)
    rank 2 -> c2   (score 1.00, loses the tie to c1 on cell_id)
    rank 3 -> c3   (score 0.50)
    rank 4 -> c4   (score 0.00)
    c5     -> null (excluded)
============================================================================
"""

from __future__ import annotations

import pandas as pd
import pytest

from pipeline.scoring import config as scfg
from pipeline.scoring.score import score_and_rank
from pipeline.scoring.weights import Criterion, WeightsConfig

# Documented numeric tolerance for the hand-computed expectations. Every
# expected value here is an exact terminating fraction of small integers, so
# the only error is float round-off over three summed terms; 1e-12 is far
# above that and far below any decision-relevant difference.
TOL = 1e-12


def _controlled_weights() -> WeightsConfig:
    """
    The three criteria and weights of the hand-computation above.

    Weights 2/1/1 sum to 4.0, NOT 1.0, so the W_i denominator must
    re-normalise them; a formula that forgot to divide by W_i would push c1
    and c2 to a score of 4.0 and fail the `<= 1` bound immediately.
    """
    return WeightsConfig(
        criteria=(
            Criterion("wind_speed", 2.0, scfg.HIGHER_IS_BETTER, "resource quality"),
            Criterion("dist_transmission_km", 1.0, scfg.LOWER_IS_BETTER, "grid cost"),
            Criterion("slope_deg", 1.0, scfg.LOWER_IS_BETTER, "buildability"),
        ),
        confidence_discount=False,
        confidence_factors={"high": 1.0, "medium": 0.9, "low": 0.5},
        config_id="controlled-ranking",
    )


def _controlled_features() -> pd.DataFrame:
    """
    The five-cell synthetic integrated table of the hand-computation above.

    c1 and c2 are identical (a genuine score tie). c5 is excluded and carries
    extreme values so the test can prove those values never touch the
    normalisation bounds.
    """
    return pd.DataFrame(
        {
            "cell_id": ["c2", "c1", "c3", "c4", "c5"],
            "wind_speed": [8.0, 8.0, 4.0, 0.0, 999.0],
            "dist_transmission_km": [2.0, 2.0, 6.0, 10.0, -999.0],
            "slope_deg": [5.0, 5.0, 15.0, 25.0, 999.0],
            "eligible": [True, True, True, True, False],
            "data_confidence": ["high", "high", "high", "high", "high"],
        }
    )


class TestControlledRanking:
    """
    Requirement 7.3 — one Controlled_Test_Case with a hand-computed expected
    ranking that verifies the scoring code end-to-end.
    """

    def test_end_to_end_scores_match_the_hand_computation(self):
        scored = score_and_rank(_controlled_features(), _controlled_weights())
        got = scored.set_index("cell_id")[scfg.SCORE_COLUMN]

        assert got["c1"] == pytest.approx(1.00, abs=TOL)
        assert got["c2"] == pytest.approx(1.00, abs=TOL)
        assert got["c3"] == pytest.approx(0.50, abs=TOL)
        assert got["c4"] == pytest.approx(0.00, abs=TOL)
        assert pd.isna(got["c5"])  # excluded -> null score

    def test_end_to_end_contributions_match_the_hand_computation(self):
        scored = score_and_rank(
            _controlled_features(), _controlled_weights()
        ).set_index("cell_id")

        # c1/c2: wind 0.50, dist 0.25, slope 0.25 (sum 1.00).
        for cell in ("c1", "c2"):
            assert scored.loc[cell, "contrib_wind_speed"] == pytest.approx(0.50, abs=TOL)
            assert scored.loc[cell, "contrib_dist_transmission_km"] == pytest.approx(
                0.25, abs=TOL
            )
            assert scored.loc[cell, "contrib_slope_deg"] == pytest.approx(0.25, abs=TOL)

        # c3: wind 0.25, dist 0.125, slope 0.125 (sum 0.50).
        assert scored.loc["c3", "contrib_wind_speed"] == pytest.approx(0.25, abs=TOL)
        assert scored.loc["c3", "contrib_dist_transmission_km"] == pytest.approx(
            0.125, abs=TOL
        )
        assert scored.loc["c3", "contrib_slope_deg"] == pytest.approx(0.125, abs=TOL)

        # c4: every contribution is 0.0.
        for column in ("contrib_wind_speed", "contrib_dist_transmission_km",
                       "contrib_slope_deg"):
            assert scored.loc["c4", column] == pytest.approx(0.0, abs=TOL)

        # The explainability contract: contributions reconstruct the score.
        contributions = list(_controlled_weights().contribution_columns)
        for cell in ("c1", "c2", "c3", "c4"):
            total = scored.loc[cell, contributions].sum()
            assert total == pytest.approx(scored.loc[cell, scfg.SCORE_COLUMN], abs=TOL)

    def test_end_to_end_rank_matches_the_hand_computation(self):
        scored = score_and_rank(
            _controlled_features(), _controlled_weights()
        ).set_index("cell_id")
        rank = scored[scfg.RANK_COLUMN]

        # Tie at 1.00 between c1 and c2 is broken by ascending cell_id: c1 wins.
        assert rank["c1"] == 1
        assert rank["c2"] == 2
        assert rank["c3"] == 3
        assert rank["c4"] == 4
        assert pd.isna(rank["c5"])  # excluded -> null rank

    def test_excluded_cell_never_stretches_the_bounds(self):
        """
        Requirement 4.3 / 7.3 — c5's extreme values (999, -999, 999) are
        excluded, so the eligible cells still normalise against [0, 8],
        [2, 10] and [5, 25]. If c5 leaked into the bounds, c1/c2 would no
        longer normalise to 1.0 and their score would fall below 1.00.
        """
        scored = score_and_rank(
            _controlled_features(), _controlled_weights()
        ).set_index("cell_id")
        # A leak of the wind bound to 999 would drop c1's wind norm from
        # 1.0 to 8/999, so its score to well under 1.0. It stays exactly 1.00.
        assert scored.loc["c1", scfg.SCORE_COLUMN] == pytest.approx(1.00, abs=TOL)

    def test_determinism_over_repeated_runs_scores_ranks_and_contributions(self):
        """
        Requirement 7.4 — identical inputs and Weights_Config yield identical
        scores, ranks AND contributions. Asserted on the controlled fixture as
        full-frame equality across two runs (the second fed an independent
        copy of the input so it cannot observe any mutation from the first).
        """
        features, weights = _controlled_features(), _controlled_weights()
        first = score_and_rank(features, weights)
        second = score_and_rank(features.copy(), weights)
        pd.testing.assert_frame_equal(first, second, check_exact=True)
