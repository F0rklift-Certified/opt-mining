"""
Property-based test for the S1-11 pure selection core (Property 1).

This test corresponds to numbered Property 1 in the feature design document
and runs at least 100 generated examples. The pure selection functions under
test (`pipeline.shortlist.select.eligible_cells` and
`pipeline.shortlist.select.select_shortlist`) are exercised directly on
in-memory pandas DataFrames, so this test touches no filesystem: it validates
the selection RULES (eligible-only, rank-ordered, clamped, never padded) that
decide which cells reach the Shortlist, independent of the loader and writers.

It lives in a dedicated module (separate from test_shortlist_properties.py) so
the property tests over the pure core can grow file-by-file without
concurrent-write conflicts.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.shortlist import config
from pipeline.shortlist.select import eligible_cells, select_shortlist

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

    # Build with a nullable integer dtype for rank so null ranks survive as
    # <NA> (rather than being coerced to float NaN, which would still be
    # notna()==False but is worth keeping honest to the S1-10 schema).
    frame = pd.DataFrame(rows, columns=list(config.SHORTLIST_COLUMNS[:4]))
    if not frame.empty:
        frame["rank"] = frame["rank"].astype("Int64")

    # Shuffle the row order so the test never relies on eligible rows already
    # being contiguous or pre-sorted by rank.
    if n > 1:
        perm = draw(st.permutations(list(range(n))))
        frame = frame.iloc[list(perm)].reset_index(drop=True)

    return frame


# Feature: s1-11-generate-ranked-shortlist, Property 1: Top-N selection is eligible-only and rank-ordered
@SETTINGS
@given(scored=_scored_tables(), top_n=st.integers(min_value=1, max_value=30))
def test_property_1_top_n_selection_is_eligible_only_and_rank_ordered(scored, top_n):
    eligible = eligible_cells(scored)
    n_eligible = len(eligible)

    shortlist = select_shortlist(scored, top_n)

    # 1. Size: the Shortlist holds exactly min(top_n, n_eligible) rows — every
    #    eligible cell when top_n meets or exceeds the count, otherwise a
    #    top_n-length prefix. Never padded past the eligible count (Req 2.1).
    assert len(shortlist) == min(top_n, n_eligible)

    # 2. Eligible-only: no Excluded_Cell reaches the Shortlist. Every selected
    #    row has a non-null suitability_score AND a non-null rank (Req 2.2).
    assert shortlist["suitability_score"].notna().all()
    assert shortlist["rank"].notna().all()

    # 3. Rank-ordered: the Shortlist is the eligible cells with the SMALLEST
    #    rank values, ordered ascending, so rank 1 (when present) is first
    #    (Req 2.1, 2.3). Compare against an independent reference computed by
    #    stable-sorting all eligible cells by rank and taking the same count.
    ref_ids = list(
        eligible.sort_values(by="rank", kind="stable")["cell_id"].iloc[
            : min(top_n, n_eligible)
        ]
    )
    assert list(shortlist["cell_id"]) == ref_ids

    # The selected ranks are non-decreasing (ascending order holds through
    # ties), and no eligible cell outside the Shortlist has a smaller rank than
    # the last selected cell — i.e. the Shortlist truly holds the smallest
    # ranks (Req 12.2 — the shortlist is the top of the ranking).
    selected_ranks = list(shortlist["rank"])
    assert selected_ranks == sorted(selected_ranks)

    if 0 < len(shortlist) < n_eligible:
        cutoff_rank = selected_ranks[-1]
        excluded_from_shortlist = eligible[~eligible["cell_id"].isin(shortlist["cell_id"])]
        # Any eligible cell left out has a rank >= the worst selected rank
        # (equal only through a tie that the size cap split).
        assert (excluded_from_shortlist["rank"] >= cutoff_rank).all()

    # 4. Rank 1 first: when any eligible cell has rank 1, the Shortlist leads
    #    with a rank-1 cell (Req 2.3).
    if (eligible["rank"] == 1).any():
        assert shortlist.iloc[0]["rank"] == 1
