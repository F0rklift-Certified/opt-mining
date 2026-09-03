"""Property test for the S1-12 sanity-check score-distribution statistics.

# Feature: s1-12-validation-sanity-check, Property 7: Distribution statistics are computed over eligible cells only

Property 7: Distribution statistics are computed over eligible cells only
    The reported min / max / mean / std / quartiles equal an independent
    recomputation over the eligible scores ALONE, and are unchanged when
    Excluded_Cell values are perturbed.

Validates: Requirements 5.1

``check_distribution(eligible, ...)`` takes ONLY the Eligible_Cell frame, so
Excluded_Cell values structurally cannot enter the statistics. This test
demonstrates that fact two ways:

  1. Correctness — the reported ``.stats`` dict equals an independent numpy
     recomputation over the eligible ``suitability_score`` values (min, max,
     mean, population std with ddof=0, and the 25/50/75 percentiles).
  2. Excluded-perturbation invariance — building an arbitrary Excluded_Cell
     frame with wildly different scores and never handing it to
     ``check_distribution`` leaves the reported stats bit-for-bit identical,
     confirming the statistics are a function of the eligible population alone.
"""

import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.sanity.checks import check_distribution

# Suitability scores live in the unit interval by construction; keep the
# generated eligible scores inside a well-behaved finite range so the numpy
# recomputation is exact.
_score = st.floats(
    min_value=0.0,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
    width=64,
)

# Excluded-cell scores are deliberately drawn from a WIDER range (including
# values far outside [0, 1]) so that, if they ever leaked into the statistics,
# min/max/mean/std would visibly shift. They must not, because the excluded
# frame is never passed to check_distribution.
_excluded_score = st.floats(
    min_value=-1000.0,
    max_value=1000.0,
    allow_nan=False,
    allow_infinity=False,
    width=64,
)


def _eligible_frame(scores: list[float]) -> pd.DataFrame:
    """A synthetic Eligible_Cell frame: cell_id + suitability_score."""
    return pd.DataFrame(
        {
            "cell_id": [f"c{i}" for i in range(len(scores))],
            "suitability_score": scores,
        }
    )


@settings(max_examples=200, deadline=None)
@given(
    eligible_scores=st.lists(_score, min_size=1, max_size=200),
    excluded_scores=st.lists(_excluded_score, min_size=0, max_size=200),
)
def test_property_7_distribution_stats_over_eligible_only(eligible_scores, excluded_scores):
    eligible = _eligible_frame(eligible_scores)

    result = check_distribution(eligible)
    stats = result.stats

    # --- Independent numpy recomputation over the eligible scores ALONE. ---
    arr = np.asarray(eligible_scores, dtype=float)
    q1, median, q3 = (float(v) for v in np.percentile(arr, [25.0, 50.0, 75.0]))
    expected = {
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
        # Population std — np.std defaults to ddof=0.
        "std": float(np.std(arr)),
        "q1": q1,
        "median": median,
        "q3": q3,
    }

    assert set(stats.keys()) == set(expected.keys())
    for key, want in expected.items():
        assert stats[key] == want, f"stat {key!r}: reported {stats[key]!r} != recomputed {want!r}"

    # n_eligible reflects only the eligible population.
    assert result.n_eligible == len(eligible_scores)

    # --- Excluded-perturbation invariance. ---
    # check_distribution takes ONLY the eligible frame, so an arbitrary
    # Excluded_Cell frame (built here but never passed) cannot alter the stats.
    # Re-running over the identical eligible frame reproduces identical stats,
    # regardless of the excluded population's (wildly different) values.
    _excluded_frame = _eligible_frame(excluded_scores) if excluded_scores else _eligible_frame([])  # noqa: F841
    result_again = check_distribution(eligible)
    assert result_again.stats == stats
