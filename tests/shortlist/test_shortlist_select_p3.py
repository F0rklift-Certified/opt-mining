"""
Property-based test for S1-11 Property 3 (Requirement 3.4).

This file is dedicated to a SINGLE property so it can be authored without
touching tests/test_shortlist_properties.py (avoiding concurrent-write
conflicts). It exercises the pure selection core
(`pipeline.shortlist.select.select_shortlist`) directly on in-memory synthetic
Scored_Table frames, so no test here touches the filesystem.

Property 3 pins the Top_N-over-count edge case: when the requested Top_N is
STRICTLY GREATER than the number of Eligible_Cells, the Shortlist must contain
every Eligible_Cell exactly once, in rank order, with no Excluded_Cell and no
fabricated/padded row — and its row count must equal the eligible count,
never exceed it.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.shortlist import config
from pipeline.shortlist.select import eligible_cells, select_shortlist

SETTINGS = settings(max_examples=100, deadline=None)

# Column names from the single authoritative source, so a rename in
# shortlist/config.py propagates here rather than silently drifting.
RANK_COL = config.SHORTLIST_COLUMNS[0]  # "rank"
CELL_ID_COL = config.SHORTLIST_COLUMNS[1]  # "cell_id"
SCORE_COL = config.SHORTLIST_COLUMNS[2]  # "suitability_score"


# A single generated cell is either an Eligible_Cell (non-null score AND
# non-null rank) or an Excluded_Cell (null score AND null rank), matching the
# S1-10 Scored_Table semantics. `is_eligible` drives which one is emitted so
# the strategy can produce frames with an arbitrary mix (including all-eligible
# and all-excluded).
_cell = st.fixed_dictionaries(
    {
        "is_eligible": st.booleans(),
        "score": st.floats(
            min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
        ),
        # Rank values are drawn from a bounded range and may collide (ties) or
        # skip values (gaps); Property 3 is about membership and count, not the
        # specific ordering, so ties/gaps are welcome noise here.
        "rank": st.integers(min_value=1, max_value=500),
    }
)


@st.composite
def scored_tables(draw):
    """
    Build a synthetic Scored_Table DataFrame with a unique `cell_id` per row
    and a mix of Eligible_Cells and Excluded_Cells, carrying the documented
    SHORTLIST_COLUMNS. Excluded_Cells have null `suitability_score` AND null
    `rank`; Eligible_Cells have both non-null.
    """
    cells = draw(st.lists(_cell, min_size=0, max_size=40))

    rows = []
    for i, cell in enumerate(cells):
        # cell_id is a stable, unique identifier per row; it is never
        # re-derived by the selection core, only carried through.
        cell_id = f"cell_{i:04d}"
        if cell["is_eligible"]:
            score = cell["score"]
            rank = cell["rank"]
        else:
            # Excluded_Cell: null score AND null rank (S1-10 semantics).
            score = None
            rank = None
        rows.append(
            {
                RANK_COL: rank,
                CELL_ID_COL: cell_id,
                SCORE_COL: score,
                "confidence": "high" if cell["is_eligible"] else None,
                "centroid_lat": -30.0 + i * 0.01,
                "centroid_lon": 150.0 + i * 0.01,
            }
        )

    # Preserve the documented column order even for an empty frame.
    return pd.DataFrame(rows, columns=list(config.SHORTLIST_COLUMNS))


# Feature: s1-11-generate-ranked-shortlist, Property 3: Top_N exceeding the eligible count includes all eligible cells without padding
@SETTINGS
@given(scored=scored_tables(), overshoot=st.integers(min_value=1, max_value=50))
def test_property_3_top_n_over_count_includes_all_eligible_without_padding(
    scored, overshoot
):
    # The set of eligible cell_ids is the ground truth: only these may appear,
    # each exactly once, and never any excluded/fabricated id.
    eligible = eligible_cells(scored)
    n_eligible = len(eligible)
    eligible_ids = set(eligible[CELL_ID_COL])

    # Choose Top_N STRICTLY GREATER than the eligible count so we are squarely
    # in the over-count edge case (including n_eligible == 0 -> top_n >= 1).
    top_n = n_eligible + overshoot
    assert top_n > n_eligible

    shortlist = select_shortlist(scored, top_n)
    result_ids = list(shortlist[CELL_ID_COL])

    # Row count equals the eligible count exactly — never padded up toward the
    # requested Top_N, and never exceeding the eligible count (Requirement 3.4).
    assert len(shortlist) == n_eligible
    assert len(shortlist) <= n_eligible

    # Every eligible cell appears exactly once: no duplicates, and the id set
    # matches the eligible set exactly (no Excluded_Cell, no fabricated row).
    assert len(result_ids) == len(set(result_ids)), "no cell_id may repeat"
    assert set(result_ids) == eligible_ids

    # No selected row is an Excluded_Cell: every included row has a non-null
    # score AND a non-null rank.
    assert shortlist[SCORE_COL].notna().all()
    assert shortlist[RANK_COL].notna().all()
