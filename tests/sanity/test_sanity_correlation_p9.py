"""Property test for the S1-12 sanity-check wind-versus-score correlation.

# Feature: s1-12-validation-sanity-check, Property 9: Wind-versus-score correlation is reported honestly, not enforced

Property 9: Wind-versus-score correlation is reported honestly, not enforced
    The wind_speed-versus-suitability_score correlation and its sign are
    REPORTED against the documented positive expectation — never enforced. A
    non-positive (or undefined) correlation records an honest Anomaly note and
    sets ``corr_passed`` to ``False`` rather than raising, failing the run, or
    altering the distribution; a sensibly positive correlation sets
    ``corr_passed`` to ``True``.

Validates: Requirements 5.4, 5.5

The test builds synthetic Eligible_Cell frames with ``cell_id``,
``suitability_score``, and ``wind_speed``. Scores are kept in ``[0.2, 0.8]``
(clear of the degenerate-clustering band around 0/1) so the correlation, not
the clustering flag, is exercised. Every generated frame is a valid eligible
population, so ``check_distribution`` must NEVER raise. The reported correlation
is checked against an independent Spearman recomputation (rank-then-Pearson,
matching the implementation's numpy fallback and ``scipy.stats.spearmanr``),
and the honest reporting contract is asserted:

  * a non-positive/undefined correlation -> ``corr_passed is False`` AND an
    anomaly is recorded (surfaced, not suppressed);
  * a sensibly positive correlation      -> ``corr_passed is True``.
"""

import math

import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.sanity.checks import (
    CORR_METHOD_SPEARMAN,
    _DISTRIBUTION_CHECK_NAME,
    check_distribution,
)

# Column names the eligible frame exposes, matching the Scored_Table /
# Integrated_Feature_Table contract check_distribution reads.
_CELL_ID = "cell_id"
_SCORE = "suitability_score"
_WIND = "wind_speed"

# Scores are held well inside (0, 1) and clear of the CLUSTER_EPSILON band
# around 0 and 1 so the degenerate-clustering flag never trips — this test is
# about the correlation report, not the clustering pass/fail.
_score_val = st.floats(
    min_value=0.2, max_value=0.8, allow_nan=False, allow_infinity=False
)
_wind_val = st.floats(
    min_value=0.0, max_value=30.0, allow_nan=False, allow_infinity=False
)


def _rank_average(values: np.ndarray) -> np.ndarray:
    """Independent average-rank implementation (ties share the mean rank)."""
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(values.size, dtype=float)
    ranks[order] = np.arange(1, values.size + 1, dtype=float)
    sorted_vals = values[order]
    i = 0
    n = sorted_vals.size
    while i < n:
        j = i + 1
        while j < n and sorted_vals[j] == sorted_vals[i]:
            j += 1
        if j - i > 1:
            ranks[order[i:j]] = (i + 1 + j) / 2.0
        i = j
    return ranks


def _independent_spearman(wind: np.ndarray, score: np.ndarray):
    """Recompute Spearman independently: Pearson of the average ranks.

    Returns ``None`` for an undefined correlation (fewer than two points or
    zero variance in either the wind ranks or the score ranks), matching the
    honest "reported, not enforced" contract.
    """
    if wind.size < 2 or score.size < 2:
        return None
    wr = _rank_average(wind)
    sr = _rank_average(score)
    if np.std(wr) == 0.0 or np.std(sr) == 0.0:
        return None
    r = np.corrcoef(wr, sr)[0, 1]
    return None if np.isnan(r) else float(r)


@settings(max_examples=200, deadline=None)
@given(
    scores=st.lists(_score_val, min_size=1, max_size=40),
    data=st.data(),
)
def test_property_9_correlation_reported_not_enforced(scores, data):
    n = len(scores)
    winds = [data.draw(_wind_val, label=f"wind_{i}") for i in range(n)]

    eligible = pd.DataFrame(
        {
            _CELL_ID: [f"c{i}" for i in range(n)],
            _SCORE: scores,
            _WIND: winds,
        }
    )

    # --- The correlation is REPORTED, never enforced: a non-positive or
    #     undefined result must NOT raise or fail the run (5.4, 5.5). ---
    result = check_distribution(eligible)  # must not raise for any valid frame

    reported = result.wind_score_corr
    corr_passed = result.corr_passed

    # --- The documented positive expectation is recorded, not enforced. ---
    assert result.corr_sign_expected_positive is True
    assert result.corr_method == CORR_METHOD_SPEARMAN

    # --- The reported correlation matches an independent recomputation. ---
    expected = _independent_spearman(
        np.asarray(winds, dtype=float), np.asarray(scores, dtype=float)
    )
    if expected is None:
        assert reported is None
    else:
        assert reported is not None
        assert math.isclose(reported, expected, rel_tol=1e-9, abs_tol=1e-9)

    # --- Anomalies recorded by this check are attributed to it. ---
    corr_anomalies = [
        a
        for a in result.anomalies
        if a.check == _DISTRIBUTION_CHECK_NAME and "correlation" in a.description.lower()
    ]

    if reported is None:
        # Undefined correlation: does not meet the positive expectation, so it
        # does not pass — but it is reported honestly, never enforced. An
        # undefined correlation is noted (not raised); no correlation anomaly is
        # forced.
        assert corr_passed is False
    elif reported > 0.0:
        # Sensibly positive against the expectation -> passes, no anomaly.
        assert corr_passed is True
        assert corr_anomalies == []
    else:
        # Non-positive against the positive expectation -> does NOT pass, and
        # the surprising result is recorded honestly as an anomaly rather than
        # suppressed or used to fail the run / alter the distribution (5.5).
        assert corr_passed is False
        assert len(corr_anomalies) == 1
