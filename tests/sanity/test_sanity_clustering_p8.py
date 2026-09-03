"""Property test for the S1-12 sanity-check degenerate-clustering flag.

# Feature: s1-12-validation-sanity-check, Property 8: Degenerate-clustering flag is correct

Property 8: Degenerate-clustering flag is correct
    The distribution is flagged degenerate iff the fraction of eligible scores
    within ``config.CLUSTER_EPSILON`` of 0 or 1 EXCEEDS
    ``config.CLUSTER_FRACTION_THRESHOLD``; the fraction is reported as the
    observed value alongside the pass/fail (``cluster_passed == not degenerate``).

Validates: Requirements 5.2

The test draws an arbitrary population of eligible ``suitability_score`` values
(mixing scores deliberately near 0/1 and scores comfortably in the interior so
Hypothesis explores both sides of the threshold), feeds them to
``check_distribution`` as the eligible frame, and independently recomputes the
near-extreme fraction over the same eligible scores. It then asserts the
reported ``cluster_fraction`` matches the recomputation, that
``cluster_degenerate`` equals ``fraction > threshold``, and that
``cluster_passed`` is exactly its negation.
"""

import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.sanity import config
from pipeline.sanity.checks import check_distribution

# Scores deliberately drawn near the extremes so many examples cross the
# CLUSTER_FRACTION_THRESHOLD boundary, plus interior scores that are never
# within CLUSTER_EPSILON of 0 or 1. Mixing the two lets the flag flip both ways.
_near_extreme_score = st.one_of(
    st.floats(min_value=0.0, max_value=config.CLUSTER_EPSILON, allow_nan=False, allow_infinity=False),
    st.floats(
        min_value=1.0 - config.CLUSTER_EPSILON,
        max_value=1.0,
        allow_nan=False,
        allow_infinity=False,
    ),
)
# Interior scores kept clear of both extremes (a margin past CLUSTER_EPSILON).
_interior_score = st.floats(
    min_value=config.CLUSTER_EPSILON + 0.05,
    max_value=1.0 - config.CLUSTER_EPSILON - 0.05,
    allow_nan=False,
    allow_infinity=False,
)
_score = st.one_of(_near_extreme_score, _interior_score)


@settings(max_examples=200, deadline=None)
@given(scores=st.lists(_score, min_size=1, max_size=60))
def test_property_8_degenerate_clustering_flag_correct(scores):
    eligible = pd.DataFrame(
        {
            "cell_id": [f"c{i}" for i in range(len(scores))],
            "suitability_score": scores,
        }
    )

    result = check_distribution(eligible)

    # --- Independently recompute the near-extreme fraction over eligible scores. ---
    arr = np.asarray(scores, dtype=float)
    near_zero = np.abs(arr - 0.0) <= config.CLUSTER_EPSILON
    near_one = np.abs(arr - 1.0) <= config.CLUSTER_EPSILON
    expected_fraction = float(np.count_nonzero(near_zero | near_one) / arr.size)
    expected_degenerate = expected_fraction > config.CLUSTER_FRACTION_THRESHOLD

    # --- The reported fraction is the observed value. ---
    assert result.cluster_fraction == expected_fraction

    # --- Flagged degenerate iff the fraction EXCEEDS the threshold. ---
    assert result.cluster_degenerate == expected_degenerate

    # --- Pass/fail is exactly the negation of the degenerate flag. ---
    assert result.cluster_passed == (not expected_degenerate)
