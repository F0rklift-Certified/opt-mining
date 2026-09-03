"""
Property-based test for S1-11 Property 2: the Shortlist ordering is consistent
with the S1-10 `rank` ordering.

This test exercises the pure selection core (`pipeline.shortlist.select`)
directly on in-memory synthetic Scored_Table frames — DataFrame in, DataFrame
out, no filesystem access. It lives in its own file (rather than in
`tests/test_shortlist_properties.py`) purely to avoid concurrent-write
conflicts while the property suite is filled in task by task; it follows the
same style — a single Hypothesis test tagged with the feature/property comment
and running at least 100 examples.

Property 2 (Requirements 2.3, 2.4, 12.3): selection is by the existing integer
`rank` using a stable sort, so

  * for any two shortlisted cells the one with the SMALLER `rank` appears
    earlier (ascending `rank`, Requirement 2.3);
  * the upstream S1-10 ordering is preserved exactly THROUGH TIES AND GAPS —
    for cells sharing a `rank`, their original input order survives (a STABLE
    sort, Requirement 2.4);
  * NO rank value is re-assigned — the `rank` values in the output equal the
    input `rank` values for those cells (Requirement 2.4 / 12.3).
"""

from __future__ import annotations

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.shortlist import config
from pipeline.shortlist.select import select_shortlist

SETTINGS = settings(max_examples=200, deadline=None)

RANK_COL = config.SHORTLIST_COLUMNS[0]  # "rank"
CELL_COL = config.SHORTLIST_COLUMNS[1]  # "cell_id"
SCORE_COL = config.SHORTLIST_COLUMNS[2]  # "suitability_score"


@st.composite
def scored_tables(draw):
    """
    Generate a synthetic Scored_Table with `rank` values that deliberately
    include TIES (repeated ranks) and GAPS (missing rank values), plus a mix of
    Excluded_Cells (null `suitability_score` AND null `rank`) that must never be
    selected.

    Ranks are drawn from a small pool so ties are common, and the pool is a
    subset of a larger range so gaps are common. Each row carries a unique
    `cell_id`, which lets the test recover the exact upstream input order and
    check the sort is stable across tied ranks.

    Returns ``(frame, top_n)``.
    """
    n = draw(st.integers(min_value=0, max_value=40))

    # A small rank pool relative to its range => plenty of ties AND gaps.
    rank_pool = draw(
        st.lists(
            st.integers(min_value=1, max_value=60),
            min_size=1,
            max_size=12,
            unique=True,
        )
    )

    rows = []
    for i in range(n):
        # Decide whether this row is an Excluded_Cell (null score AND null rank).
        excluded = draw(st.booleans())
        if excluded:
            rank_val = None
            score_val = None
        else:
            rank_val = draw(st.sampled_from(rank_pool))
            score_val = draw(
                st.floats(
                    min_value=0.0,
                    max_value=1.0,
                    allow_nan=False,
                    allow_infinity=False,
                )
            )
        rows.append(
            {
                # unique, order-revealing cell_id (input order == this sequence)
                CELL_COL: f"cell_{i:04d}",
                RANK_COL: rank_val,
                SCORE_COL: score_val,
                # a stable marker of the ORIGINAL input position, so the test
                # can assert tie ordering without relying on cell_id parsing.
                "orig_pos": i,
            }
        )

    frame = pd.DataFrame(
        rows,
        columns=[CELL_COL, RANK_COL, SCORE_COL, "orig_pos"],
    )

    top_n = draw(st.integers(min_value=1, max_value=50))
    return frame, top_n


# Feature: s1-11-generate-ranked-shortlist, Property 2: Ordering is consistent with the S1-10 rank ordering
@SETTINGS
@given(case=scored_tables())
def test_property_2_ordering_consistent_with_s1_10_rank(case):
    scored, top_n = case

    result = select_shortlist(scored, top_n)

    ranks = result[RANK_COL].tolist()
    orig_positions = result["orig_pos"].tolist()

    # (a) SMALLER RANK EARLIER (Requirement 2.3): the output rank sequence is
    # non-decreasing, so for any two shortlisted cells the one with the smaller
    # rank appears first. Holds trivially for 0/1 rows.
    for earlier, later in zip(ranks, ranks[1:]):
        assert earlier <= later, (
            f"rank ordering violated: {earlier} appears before {later}"
        )

    # (b) STABLE THROUGH TIES (Requirement 2.4): within any block of cells that
    # share a rank, the original input order is preserved. Because the input
    # `orig_pos` is strictly increasing in input order, tied cells must appear
    # with strictly increasing `orig_pos`.
    for i in range(1, len(ranks)):
        if ranks[i] == ranks[i - 1]:
            assert orig_positions[i] > orig_positions[i - 1], (
                "tie ordering not preserved: input order was not kept for "
                f"equal rank {ranks[i]} (orig_pos {orig_positions[i - 1]} "
                f"then {orig_positions[i]})"
            )

    # (c) NO RANK RE-ASSIGNMENT (Requirement 2.4 / 12.3): every output row's
    # rank equals the input rank recorded for that same cell_id. We look the
    # value back up by the unique cell_id rather than trusting the output.
    input_rank_by_cell = dict(zip(scored[CELL_COL], scored[RANK_COL]))
    for cell_id, out_rank in zip(result[CELL_COL], result[RANK_COL]):
        assert out_rank == input_rank_by_cell[cell_id], (
            f"rank was re-assigned for {cell_id}: input "
            f"{input_rank_by_cell[cell_id]!r} -> output {out_rank!r}"
        )

    # (d) The selection is a rank-ordered PREFIX of the eligible cells sorted by
    # the SAME stable rule: the shortlisted (rank, orig_pos) pairs, in output
    # order, are exactly the first min(top_n, n_eligible) of the eligible cells
    # sorted stably by rank. This ties (a)-(c) together into "ordering is the
    # S1-10 ordering, truncated" — the upstream ordering is preserved exactly
    # through ties and gaps.
    eligible = scored[scored[SCORE_COL].notna() & scored[RANK_COL].notna()]
    expected = eligible.sort_values(by=RANK_COL, kind="stable")
    take = min(top_n, len(expected))
    expected_pairs = list(
        zip(
            expected[RANK_COL].tolist()[:take],
            expected["orig_pos"].tolist()[:take],
        )
    )
    actual_pairs = list(zip(ranks, orig_positions))
    assert actual_pairs == expected_pairs, (
        "shortlist ordering does not match the stable S1-10 rank ordering"
    )
