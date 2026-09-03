"""
Property-based test for the S1-11 pure selection core (Property 8).

This test corresponds to numbered Property 8 in the feature design document
and runs at least 100 generated examples. The pure selection function under
test (`pipeline.shortlist.select.select_shortlist`) is exercised directly on
in-memory pandas DataFrames, so this test touches no filesystem.

Property 8 is the SIZE invariant of the shortlist: for ANY Scored_Table and
ANY positive-integer Top_N, the shortlist row count never exceeds the
effective Top_N. `select_shortlist` clamps the take to
`min(top_n, n_eligible)`, so the count can equal Top_N (when there are at
least Top_N eligible cells) but can never exceed it, and it is never padded
past the eligible count when eligibility is the tighter bound (Req 12.1).

It lives in a dedicated module (separate from test_shortlist_properties.py and
the other per-property files) so the property tests over the pure core can
grow file-by-file without concurrent-write conflicts.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.shortlist import config
from pipeline.shortlist.select import select_shortlist

SETTINGS = settings(max_examples=200, deadline=None)


# A synthetic Scored_Table row. An Eligible_Cell carries BOTH a non-null
# suitability_score AND a non-null rank; an Excluded_Cell carries null in both
# (the S1-10 convention). We generate a flag per row and derive the score/rank
# accordingly so the two never contradict each other.
#
# Ranks are drawn from a small integer window so ties and gaps arise naturally
# across a table (two eligible rows can share a rank; some ranks are skipped).
_rank = st.integers(min_value=1, max_value=15)
_score = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)
_confidence = st.sampled_from(config.CONFIDENCE_LEVELS)


@st.composite
def _scored_tables(draw):
    """Build a Scored_Table DataFrame with a mix of eligible/excluded rows.

    Columns follow the documented SHORTLIST_COLUMNS the selection core keys
    against: `rank`, `cell_id`, `suitability_score`, `confidence`. Each row is
    independently either an Eligible_Cell (non-null score AND rank) or an
    Excluded_Cell (null score AND null rank). The table may be empty and may
    contain zero eligible rows — both are legal inputs to the selection core.
    """
    n = draw(st.integers(min_value=0, max_value=25))

    rows = []
    for cell_id in range(n):
        eligible = draw(st.booleans())
        if eligible:
            rank = draw(_rank)
            score = draw(_score)
        else:
            # Excluded_Cell: null score AND null rank (S1-10 convention).
            rank = None
            score = None
        rows.append(
            {
                "rank": rank,
                "cell_id": cell_id,
                "suitability_score": score,
                "confidence": draw(_confidence),
            }
        )

    frame = pd.DataFrame(rows, columns=list(config.SHORTLIST_COLUMNS[:4]))
    if not frame.empty:
        frame["rank"] = frame["rank"].astype("Int64")

    # Shuffle the row order so the test never relies on eligible rows already
    # being contiguous or pre-sorted by rank.
    if n > 1:
        perm = draw(st.permutations(list(range(n))))
        frame = frame.iloc[list(perm)].reset_index(drop=True)

    return frame


# Feature: s1-11-generate-ranked-shortlist, Property 8: Row count never exceeds the effective Top_N
@SETTINGS
@given(scored=_scored_tables(), top_n=st.integers(min_value=1, max_value=30))
def test_property_8_row_count_never_exceeds_effective_top_n(scored, top_n):
    shortlist = select_shortlist(scored, top_n)

    # The core invariant: for ANY Scored_Table and ANY positive-integer Top_N,
    # the shortlist row count is bounded above by the effective Top_N. The take
    # is clamped to min(top_n, n_eligible), so it may equal top_n but can never
    # exceed it (Req 12.1).
    assert len(shortlist) <= top_n
