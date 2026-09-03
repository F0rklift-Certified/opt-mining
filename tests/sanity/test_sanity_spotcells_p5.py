"""Property test for the S1-12 sanity-check deterministic spot-cell selection.

# Feature: s1-12-validation-sanity-check, Property 5: Spot-cell selection is deterministic and spans the score range

Property 5: Spot-cell selection is deterministic and spans the score range
    ``select_spot_cells(eligible, n)`` returns exactly ``n`` distinct eligible
    cells (when the eligible population has at least ``n`` distinct cells),
    always including the top-score and bottom-score cell plus ``n - 2`` interior
    selections spanning the range; the selection is identical on a repeat call
    over identical inputs (determinism) and is order-independent (shuffling the
    input rows produces the same selection).

Validates: Requirements 4.1, 4.2

The test builds synthetic Eligible_Cell frames (``cell_id``,
``suitability_score``) with a controlled number of distinct cells (>= n) and a
requested count ``n`` drawn from the documented spot-check range [5, 10]. Because
``select_spot_cells`` is a fixed function of ``(sorted eligible scores, n)`` with
a ``cell_id`` tie-break, the selection can be checked directly: exactly ``n``
distinct cells come back, the lowest-score and highest-score cells (by the
(score, cell_id) total order) are always present, a repeat call yields an
identical selection, and shuffling the input rows leaves the selection unchanged.
"""

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.sanity import config
from pipeline.sanity.checks import (
    SPOT_BAND_BOTTOM,
    SPOT_BAND_TOP,
    select_spot_cells,
)

# The Scored_Table column names the selection orders / selects on.
_CELL_ID = config.REQUIRED_SCORE_COLUMNS[0]  # "cell_id"
_SCORE = config.REQUIRED_SCORE_COLUMNS[1]  # "suitability_score"


def _make_eligible(scores: list[float]) -> pd.DataFrame:
    """A synthetic Eligible_Cell frame with one distinct cell per score.

    ``cell_id`` values are distinct, deterministic strings so the (score,
    cell_id) tie-break is total and well-defined even when scores repeat.
    """
    return pd.DataFrame(
        {
            _CELL_ID: [f"cell_{i:04d}" for i in range(len(scores))],
            _SCORE: scores,
        }
    )


def _key_set(frame: pd.DataFrame) -> set:
    """The set of (cell_id, score) pairs selected — identity of the selection."""
    return set(zip(frame[_CELL_ID].tolist(), frame[_SCORE].tolist()))


# Finite, well-separated scores so the total (score, cell_id) order is
# unambiguous; ties are still allowed (min_value..max_value can repeat) so the
# cell_id tie-break is exercised.
_score = st.floats(
    min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False
)


@settings(max_examples=200, deadline=None)
@given(data=st.data())
def test_property_5_spot_cell_selection_deterministic_and_spanning(data):
    n = data.draw(
        st.integers(min_value=config.SPOT_CHECK_MIN, max_value=config.SPOT_CHECK_MAX),
        label="n",
    )
    # A population with AT LEAST n distinct cells (each row is a distinct cell).
    m = data.draw(st.integers(min_value=n, max_value=n + 20), label="m")
    scores = data.draw(
        st.lists(_score, min_size=m, max_size=m),
        label="scores",
    )

    eligible = _make_eligible(scores)

    selected = select_spot_cells(eligible, n)

    # --- Exactly n distinct cells returned (population has >= n distinct). ---
    assert len(selected) == n
    assert selected[_CELL_ID].nunique() == n

    # Every selected cell is drawn from the eligible population, unchanged.
    eligible_keys = _key_set(eligible)
    assert _key_set(selected).issubset(eligible_keys)

    # --- The top and bottom cells (by the (score, cell_id) total order) are
    #     always included, and are labelled bottom / top. ---
    ordered = eligible.sort_values(
        by=[_SCORE, _CELL_ID], ascending=[True, True], kind="mergesort"
    ).reset_index(drop=True)
    bottom_key = (ordered[_CELL_ID].iloc[0], ordered[_SCORE].iloc[0])
    top_key = (ordered[_CELL_ID].iloc[-1], ordered[_SCORE].iloc[-1])
    selected_keys = _key_set(selected)
    assert bottom_key in selected_keys
    assert top_key in selected_keys

    # The score_band column marks the span endpoints.
    bands = selected.set_index(_CELL_ID)["score_band"].to_dict()
    assert bands[bottom_key[0]] == SPOT_BAND_BOTTOM
    assert bands[top_key[0]] == SPOT_BAND_TOP

    # --- The selection spans the range: min/max selected score equal the
    #     eligible min/max score. ---
    assert selected[_SCORE].min() == eligible[_SCORE].min()
    assert selected[_SCORE].max() == eligible[_SCORE].max()

    # --- Determinism: a repeat call over identical inputs is identical. ---
    repeat = select_spot_cells(eligible, n)
    assert repeat[_CELL_ID].tolist() == selected[_CELL_ID].tolist()
    assert repeat[_SCORE].tolist() == selected[_SCORE].tolist()
    assert repeat["score_band"].tolist() == selected["score_band"].tolist()

    # --- Order-independence: shuffling the input rows gives the same selection. ---
    perm = data.draw(st.permutations(list(range(m))), label="perm")
    shuffled = eligible.iloc[perm].reset_index(drop=True)
    shuffled_sel = select_spot_cells(shuffled, n)
    assert shuffled_sel[_CELL_ID].tolist() == selected[_CELL_ID].tolist()
    assert shuffled_sel[_SCORE].tolist() == selected[_SCORE].tolist()
    assert shuffled_sel["score_band"].tolist() == selected["score_band"].tolist()
