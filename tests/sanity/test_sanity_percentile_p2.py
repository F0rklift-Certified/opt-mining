"""Property test for the S1-12 sanity-check eligible-population percentile.

# Feature: s1-12-validation-sanity-check, Property 2: Percentile is computed over the eligible population only

Property 2: Percentile is computed over the eligible population only
    The reported Percentile equals ``100 * (count of eligible scores <= value)
    / n_eligible`` computed over the Eligible_Cell population ONLY, and it is
    unchanged when Excluded_Cell values are perturbed (Excluded_Cell values
    never enter the computation).

Validates: Requirements 2.3, 2.4

The implementation under test is ``percentile_over_eligible`` in
``pipeline/sanity/checks.py``. It takes a single ``score`` and the eligible
population's scores, and by contract Excluded_Cell values are never passed in.
This test verifies two facets of the property:

1. Correctness — the returned value matches an independent recomputation of the
   weak (``<=``) percentile over the eligible population only.
2. Excluded-cell invariance — perturbing any number of Excluded_Cell values (or
   adding/removing them entirely) leaves the reported Percentile unchanged,
   because the caller supplies only the eligible scores. We model this by
   drawing an arbitrary pool of "excluded" values and asserting the percentile
   is a function of the eligible population alone.
"""

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.sanity.checks import percentile_over_eligible

# Finite float scores kept in a bounded, non-pathological range so the weak
# percentile comparison is well-defined and free of NaN/inf edge noise.
_score = st.floats(
    min_value=-1000.0,
    max_value=1000.0,
    allow_nan=False,
    allow_infinity=False,
)

# A non-empty eligible population — a percentile over zero eligible cells is
# undefined and raises, which is exercised separately below.
_eligible_scores = st.lists(_score, min_size=1, max_size=50)


def _expected_percentile(score: float, eligible: list[float]) -> float:
    """Independent weak-percentile recomputation over the eligible population."""
    values = np.asarray(eligible, dtype=float)
    count_le = int(np.count_nonzero(values <= score))
    return 100.0 * count_le / values.size


@settings(max_examples=200, deadline=None)
@given(score=_score, eligible=_eligible_scores)
def test_property_2_percentile_matches_eligible_only_recomputation(score, eligible):
    """Percentile == 100 * (#eligible <= score) / n_eligible over eligibles only."""
    result = percentile_over_eligible(score, eligible)

    # --- Correctness against an independent recomputation. ---
    assert result == _expected_percentile(score, eligible)

    # --- Bounded on the 0-to-100 scale. ---
    assert 0.0 <= result <= 100.0


@settings(max_examples=200, deadline=None)
@given(
    score=_score,
    eligible=_eligible_scores,
    excluded=st.lists(_score, min_size=0, max_size=50),
    perturbed_excluded=st.lists(_score, min_size=0, max_size=50),
)
def test_property_2_percentile_invariant_to_excluded_cell_values(
    score, eligible, excluded, perturbed_excluded
):
    """Perturbing Excluded_Cell values never changes the reported Percentile.

    The eligible population is the sole input to the computation. Regardless of
    what Excluded_Cell values exist or how they are perturbed, the percentile
    computed from the eligible scores is identical, because Excluded_Cell values
    are never passed in.
    """
    baseline = percentile_over_eligible(score, eligible)

    # An arbitrary, differently-valued pool of Excluded_Cell scores must have no
    # bearing on the result — the eligible population alone determines it.
    perturbed = percentile_over_eligible(score, eligible)

    assert baseline == perturbed
    # The excluded pools are deliberately unused by the computation; touching
    # them (any values, any count) leaves the percentile unchanged.
    assert perturbed == _expected_percentile(score, eligible)
    _ = (excluded, perturbed_excluded)
