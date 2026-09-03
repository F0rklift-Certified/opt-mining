"""
Pure top-N selection over the S1-10 Scored_Table (S1-11, Requirements 2, 3).

This module is the SELECTION core of the shortlist stage and nothing else:
pure functions of (in-memory frame, Top_N) with NO file I/O and NO dependence
on the grid or the writers. That keeps the selection logic independently
testable — DataFrame in, DataFrame out — and lets the data-loading layer be
swapped without touching the rules that decide which cells are shortlisted.

The stage is a FILTERING step, not a modelling step. Selection is driven by
the existing integer `rank` that S1-10 already assigned (rank 1 = best), NOT
by re-sorting on `suitability_score`. Sorting by the upstream `rank` with a
STABLE sort guarantees the shortlist ordering is identical to S1-10 through
ties and gaps — no rank is ever re-derived or re-assigned (Requirement 2.3,
2.4).

Two rules deserve their names spelled out, because both are places where a
naive implementation would silently lie:

  ELIGIBLE-ONLY. Only Eligible_Cells — rows with a non-null `suitability_score`
  AND a non-null `rank` — are candidates. An Excluded_Cell (null score / null
  rank) is never selected and the shortlist is never padded to reach Top_N
  (Requirement 2.2, 3.4).

  ZERO ELIGIBLE. When no cell is eligible, `select_shortlist` returns an EMPTY
  frame that still carries the documented `SHORTLIST_COLUMNS` present in the
  input, so the downstream writers can emit headered CSV / GeoJSON with the
  disclaimer rather than crashing on a missing column (Requirement 3.6).
"""

from __future__ import annotations

import pandas as pd

from . import config


def eligible_cells(scored: pd.DataFrame) -> pd.DataFrame:
    """
    Return the Eligible_Cells of ``scored``: rows with BOTH a non-null
    ``suitability_score`` AND a non-null ``rank`` (Requirement 2.2).

    PURE: takes an in-memory frame, returns a new in-memory frame; no file
    I/O and no mutation of the input. The row order of the input is preserved
    (this is a boolean mask, not a sort) so any ordering the caller relies on
    survives the filter.

    An Excluded_Cell — null ``suitability_score`` and null ``rank`` in S1-10 —
    is dropped here and can therefore never reach the Shortlist.
    """
    score_col = config.SHORTLIST_COLUMNS[2]  # "suitability_score"
    rank_col = config.SHORTLIST_COLUMNS[0]  # "rank"

    mask = scored[score_col].notna() & scored[rank_col].notna()
    return scored.loc[mask]


def select_shortlist(scored: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """
    Select the Shortlist: the ``min(top_n, n_eligible)`` Eligible_Cells with
    the smallest S1-10 ``rank`` values, ordered ascending by ``rank`` so the
    cell with ``rank`` 1 (when present) appears first (Requirement 2.1, 2.3).

    PURE — DataFrame in, DataFrame out, no file I/O and no mutation of the
    input.

    Selection is by the existing integer ``rank`` using a STABLE sort
    (``kind="stable"``), so the S1-10 ordering is preserved exactly through
    ties and gaps and no rank is ever re-assigned (Requirement 2.4). Only
    Eligible_Cells are considered, so an Excluded_Cell is never included; the
    take is clamped to the eligible count, so the Shortlist is never padded
    with fabricated rows (Requirement 3.4).

    Edge cases:
      * ``top_n > n_eligible`` → every Eligible_Cell is returned, in rank
        order, with no padding (Requirement 3.4). The caller reports that the
        requested Top_N exceeded the eligible count via the eligible-vs-included
        counts (Requirement 2.5).
      * ``n_eligible == 0`` → an EMPTY frame is returned that still carries the
        documented columns present on the input, so downstream writers emit
        headered outputs with the disclaimer (Requirement 3.6).

    The caller obtains the eligible count and the included count for the
    Summary_Report by comparing ``len(eligible_cells(scored))`` with
    ``len(select_shortlist(scored, top_n))`` (Requirement 2.5).
    """
    rank_col = config.SHORTLIST_COLUMNS[0]  # "rank"

    eligible = eligible_cells(scored)

    # Stable sort by the existing S1-10 rank: ties and gaps are preserved in
    # their upstream order, and no rank is re-derived (Requirement 2.3, 2.4).
    ordered = eligible.sort_values(by=rank_col, ascending=True, kind="stable")

    # Clamp the take to the eligible count — never pad (Requirement 3.4). When
    # n_eligible == 0 this yields an empty frame that still carries the
    # documented columns (Requirement 3.6).
    take = min(top_n, len(ordered))
    return ordered.iloc[:take]
