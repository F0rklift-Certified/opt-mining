"""
Worked-example unit tests for the S1-11 shortlist pure core (Requirement 13).

These are hand-checked, concrete-input → expected-output tests that COMPLEMENT
the Hypothesis property tests (test_shortlist_select_p1.py,
test_shortlist_assemble_p11.py, test_shortlist_summary_p12.py, etc.). Where the
property tests assert universal invariants over generated tables, the cases
here pin down the exact behaviour on small tables a reviewer can verify by eye:
a top-N selection with ties and rank gaps, the documented column order, a
hand-computed summary (score min/max/mean/std, lat/lon ranges, confidence
counts, run counts), and the empty-shortlist headered outputs.

The functions under test are the pure selection/assembly/summary core over
in-memory pandas frames — DataFrame in, DataFrame / stats out — so these tests
touch no filesystem, mirroring the imports of the sibling property tests.

Modules under test:
  * pipeline.shortlist.select   — eligible_cells, select_shortlist
  * pipeline.shortlist.assemble — assemble_shortlist, optional_context_columns
  * pipeline.shortlist.summary  — compute_summary / SummaryStats
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from pipeline.shortlist import config
from pipeline.shortlist.assemble import assemble_shortlist, optional_context_columns
from pipeline.shortlist.coords import GRID_COORDINATE_COLUMNS
from pipeline.shortlist.select import eligible_cells, select_shortlist
from pipeline.shortlist.summary import compute_summary

# The four core score-input columns the selection core keys against, in the
# documented order (rank, cell_id, suitability_score, confidence).
_CORE_SCORE_COLS = list(config.SHORTLIST_COLUMNS[:4])


def _scored_frame(rows: list[dict]) -> pd.DataFrame:
    """Build a small Scored_Table with a nullable Int64 `rank`.

    A nullable integer dtype keeps a null rank as <NA> (matching the S1-10
    schema) rather than coercing the whole column to float — so an
    Excluded_Cell's null rank stays honestly null.
    """
    frame = pd.DataFrame(rows, columns=_CORE_SCORE_COLS)
    frame["rank"] = frame["rank"].astype("Int64")
    return frame


# ---------------------------------------------------------------------------
# select_shortlist — ties, gaps, and Excluded_Cells (13.1, 13.2)
# ---------------------------------------------------------------------------


def _mixed_scored_table() -> pd.DataFrame:
    """A hand-built Scored_Table with ties, a rank gap, and Excluded_Cells.

    Eligible rows (non-null score AND rank), listed in INPUT order:
        cell_id=10  rank=1
        cell_id=11  rank=2   (tie with cell 12, cell 11 first in input)
        cell_id=12  rank=2   (tie)
        cell_id=13  rank=5   (rank 3 and 4 are skipped — a gap)
        cell_id=14  rank=7

    Excluded rows (null score AND null rank) interleaved so they are never
    contiguous with the eligibles:
        cell_id=90, cell_id=91, cell_id=92
    """
    return _scored_frame(
        [
            {"rank": None, "cell_id": 90, "suitability_score": None, "confidence": "low"},
            {"rank": 1, "cell_id": 10, "suitability_score": 0.91, "confidence": "high"},
            {"rank": 2, "cell_id": 11, "suitability_score": 0.72, "confidence": "high"},
            {"rank": None, "cell_id": 91, "suitability_score": None, "confidence": "low"},
            {"rank": 2, "cell_id": 12, "suitability_score": 0.70, "confidence": "low"},
            {"rank": 5, "cell_id": 13, "suitability_score": 0.55, "confidence": "low"},
            {"rank": None, "cell_id": 92, "suitability_score": None, "confidence": "high"},
            {"rank": 7, "cell_id": 14, "suitability_score": 0.40, "confidence": "high"},
        ]
    )


def test_eligible_cells_drops_excluded_and_preserves_input_order():
    scored = _mixed_scored_table()

    eligible = eligible_cells(scored)

    # Excluded_Cells (90, 91, 92) never survive; the five eligibles remain in
    # their INPUT order (this is a mask, not a sort).
    assert list(eligible["cell_id"]) == [10, 11, 12, 13, 14]
    assert eligible["suitability_score"].notna().all()
    assert eligible["rank"].notna().all()


def test_select_shortlist_ties_gaps_and_stable_order():
    scored = _mixed_scored_table()

    shortlist = select_shortlist(scored, top_n=4)

    # Rank 1 leads; the rank-2 tie preserves input order (11 before 12); the
    # rank gap (3,4 skipped) does not disturb ordering — rank 5 follows.
    assert list(shortlist["cell_id"]) == [10, 11, 12, 13]
    # rank 1 is first.
    assert shortlist.iloc[0]["rank"] == 1
    # Ranks are non-decreasing (ascending through the tie).
    assert list(shortlist["rank"]) == [1, 2, 2, 5]
    # No Excluded_Cell ever appears.
    assert not shortlist["cell_id"].isin([90, 91, 92]).any()


def test_select_shortlist_top_n_smaller_returns_prefix():
    scored = _mixed_scored_table()

    shortlist = select_shortlist(scored, top_n=2)

    # A smaller top_n returns the rank-ordered prefix.
    assert list(shortlist["cell_id"]) == [10, 11]
    assert list(shortlist["rank"]) == [1, 2]


def test_select_shortlist_top_n_exceeding_eligible_returns_all_no_padding():
    scored = _mixed_scored_table()  # 5 eligible cells

    shortlist = select_shortlist(scored, top_n=99)

    # Every eligible cell, in rank order, with NO padding to reach top_n.
    assert len(shortlist) == 5
    assert list(shortlist["cell_id"]) == [10, 11, 12, 13, 14]
    assert list(shortlist["rank"]) == [1, 2, 2, 5, 7]


# ---------------------------------------------------------------------------
# assemble_shortlist — documented column order (13.5)
# ---------------------------------------------------------------------------


def test_assemble_shortlist_column_order_with_rez_and_dropped_contrib():
    # A joined frame with columns OUT OF ORDER, an optional `rez` column, and
    # an extra non-schema `contrib_wind` column that must be dropped.
    joined = pd.DataFrame(
        {
            "centroid_lon": [151.0, 151.1],
            "confidence": ["high", "low"],
            "contrib_wind": [0.3, 0.2],  # extra, not in the schema → dropped
            "cell_id": [10, 11],
            "rez": ["New England", "New England"],
            "suitability_score": [0.91, 0.72],
            "centroid_lat": [-29.0, -29.1],
            "rank": [1, 2],
        }
    )

    result = assemble_shortlist(joined)

    # Exactly SHORTLIST_COLUMNS (documented order) then the optional `rez`;
    # the extra contrib_ column is dropped, and nothing is reordered wrongly.
    assert list(result.columns) == list(config.SHORTLIST_COLUMNS) + ["rez"]

    # optional_context_columns reports exactly the appended `rez` column.
    optionals = optional_context_columns(joined)
    assert [c.name for c in optionals] == ["rez"]


def test_assemble_shortlist_column_order_without_optional_context():
    joined = pd.DataFrame(
        {
            "centroid_lat": [-29.0],
            "cell_id": [10],
            "rank": [1],
            "centroid_lon": [151.0],
            "suitability_score": [0.91],
            "confidence": ["high"],
        }
    )

    result = assemble_shortlist(joined)

    # No optional context available → exactly the documented core columns.
    assert list(result.columns) == list(config.SHORTLIST_COLUMNS)
    assert optional_context_columns(joined) == ()


# ---------------------------------------------------------------------------
# compute_summary — hand-computed statistics (13.6)
# ---------------------------------------------------------------------------


def test_compute_summary_hand_computed_values():
    # Scored_Table: 4 eligible cells + 2 excluded cells.
    #
    # The two excluded cells carry a NON-NULL suitability_score but a NULL
    # rank — this proves eligibility is gated on rank (a scored-but-unranked
    # cell counts toward n_scored but NOT n_eligible, and its score must never
    # enter the score distribution).
    scored = _scored_frame(
        [
            {"rank": 1, "cell_id": 10, "suitability_score": 0.80, "confidence": "high"},
            {"rank": 2, "cell_id": 11, "suitability_score": 0.60, "confidence": "high"},
            {"rank": 3, "cell_id": 12, "suitability_score": 0.40, "confidence": "low"},
            {"rank": 4, "cell_id": 13, "suitability_score": 0.20, "confidence": "low"},
            # Scored but unranked (null rank) — counts as scored, not eligible.
            {"rank": None, "cell_id": 90, "suitability_score": 0.99, "confidence": "high"},
            {"rank": None, "cell_id": 91, "suitability_score": 0.05, "confidence": "low"},
        ]
    )

    # Shortlist: top 3 of the 4 eligible cells, coordinate-joined. Confidence
    # among the shortlisted three: high, high, low.
    shortlist = pd.DataFrame(
        {
            "rank": [1, 2, 3],
            "cell_id": [10, 11, 12],
            "suitability_score": [0.80, 0.60, 0.40],
            "confidence": ["high", "high", "low"],
            "centroid_lat": [-29.0, -30.0, -31.0],
            "centroid_lon": [151.0, 152.0, 153.0],
        }
    )

    stats = compute_summary(scored, shortlist)

    # Score distribution over the ELIGIBLE cells only (scores 0.80, 0.60,
    # 0.40, 0.20 — the 0.99 / 0.05 unranked cells are excluded).
    #   min  = 0.20
    #   max  = 0.80
    #   mean = (0.80 + 0.60 + 0.40 + 0.20) / 4 = 0.50
    #   std  = sqrt( (0.30^2 + 0.10^2 + 0.10^2 + 0.30^2) / (4 - 1) )   [ddof=1]
    #        = sqrt( 0.20 / 3 ) = 0.2581988897471611...
    expected_std = math.sqrt(0.20 / 3)
    assert stats.score_dist["min"] == pytest.approx(0.20)
    assert stats.score_dist["max"] == pytest.approx(0.80)
    assert stats.score_dist["mean"] == pytest.approx(0.50)
    assert stats.score_dist["std"] == pytest.approx(expected_std)

    # Geographic spread over the shortlisted cells.
    lat_col, lon_col = GRID_COORDINATE_COLUMNS
    assert lat_col == "centroid_lat" and lon_col == "centroid_lon"
    assert stats.lat_range == pytest.approx((-31.0, -29.0))
    assert stats.lon_range == pytest.approx((151.0, 153.0))

    # Confidence distribution over the shortlisted three: high=2, low=1; and
    # the per-level counts sum to the shortlist row count.
    assert stats.confidence_dist == {"high": 2, "low": 1}
    assert sum(stats.confidence_dist.values()) == len(shortlist)

    # Run counts are three DISTINCT populations:
    #   n_cells    = 6 (all rows)
    #   n_scored   = 6 (all rows carry a non-null score, incl. the 2 unranked)
    #   n_eligible = 4 (non-null score AND rank)
    assert stats.n_cells == 6
    assert stats.n_scored == 6
    assert stats.n_eligible == 4

    # No `rez` column present → no REZs represented.
    assert stats.rez_represented == []


# ---------------------------------------------------------------------------
# Empty shortlist — headered, honest outputs (13.3)
# ---------------------------------------------------------------------------


def test_empty_shortlist_all_excluded_table():
    # An all-excluded Scored_Table: every row has a null score AND null rank.
    scored = _scored_frame(
        [
            {"rank": None, "cell_id": 90, "suitability_score": None, "confidence": "low"},
            {"rank": None, "cell_id": 91, "suitability_score": None, "confidence": "high"},
        ]
    )

    # eligible_cells is empty on an all-excluded table.
    eligible = eligible_cells(scored)
    assert eligible.empty

    # select_shortlist returns an empty frame that STILL carries the documented
    # score-input columns present on the input (headered, not crashing).
    shortlist = select_shortlist(scored, top_n=20)
    assert shortlist.empty
    assert list(shortlist.columns) == _CORE_SCORE_COLS

    # compute_summary on the empty case is honest, not fabricated:
    #   score_dist all None, ranges (None, None), confidence counts all zero.
    stats = compute_summary(scored, shortlist)
    assert stats.score_dist == {"min": None, "max": None, "mean": None, "std": None}
    assert stats.lat_range == (None, None)
    assert stats.lon_range == (None, None)
    assert stats.confidence_dist == {level: 0 for level in config.CONFIDENCE_LEVELS}
    assert stats.rez_represented == []

    # Counts: 2 total cells, 0 scored, 0 eligible.
    assert stats.n_cells == 2
    assert stats.n_scored == 0
    assert stats.n_eligible == 0
