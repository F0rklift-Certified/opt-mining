"""
Property-based test for the S1-11 coordinate join (Property 7).

This test corresponds to numbered Property 7 in the feature design document
and runs at least 100 generated examples. It exercises the pure selection core
(`pipeline.shortlist.select.select_shortlist`) followed by the pure coordinate
join (`pipeline.shortlist.coords.join_coordinates`) directly on in-memory
pandas DataFrames, so it touches no filesystem.

The property under test is that the shortlist stage is a FILTERING and
FORMATTING step, not a modelling step: each shortlisted cell's
`suitability_score`, `confidence`, and `rank` must equal the Scored_Table
values for that same `cell_id`, with no recomputation and no re-ranking. The
coordinate join attaches `centroid_lat`/`centroid_lon` but must carry the
score/confidence/rank straight through unchanged (Requirements 1.3, 4.6).

It lives in a dedicated module (separate from the other shortlist property
tests) so the property tests over the pure core can grow file-by-file without
concurrent-write conflicts.
"""

from __future__ import annotations

import math

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.shortlist import config
from pipeline.shortlist.coords import join_coordinates
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

# Grid coordinates for a matching cell. EPSG:4326 lat/lon bounds loosely
# covering NSW; exact ranges are unimportant — the property is that whatever
# the grid holds is joined without disturbing the score/confidence/rank.
_lat = st.floats(
    min_value=-37.5, max_value=-28.0, allow_nan=False, allow_infinity=False
)
_lon = st.floats(
    min_value=141.0, max_value=154.0, allow_nan=False, allow_infinity=False
)


@st.composite
def _scored_and_grid(draw):
    """Build a synthetic Scored_Table plus a matching grid frame.

    The Scored_Table columns follow the documented order the selection core
    keys against: `rank`, `cell_id`, `suitability_score`, `confidence`. Each
    row is independently an Eligible_Cell (non-null score AND rank) or an
    Excluded_Cell (null score AND null rank). The grid frame carries
    `cell_id`, `centroid_lat`, `centroid_lon` and covers EVERY cell_id in the
    Scored_Table, so `join_coordinates` never halts on an unmatched cell (that
    fail-fast path is Property 6's concern, not Property 7's).
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
    # <NA> rather than being coerced to float NaN.
    scored = pd.DataFrame(rows, columns=list(config.SHORTLIST_COLUMNS[:4]))
    if not scored.empty:
        scored["rank"] = scored["rank"].astype("Int64")

    # Shuffle the row order so the test never relies on eligible rows being
    # contiguous or pre-sorted by rank.
    if n > 1:
        perm = draw(st.permutations(list(range(n))))
        scored = scored.iloc[list(perm)].reset_index(drop=True)

    # A matching grid frame covering every cell_id, with independent
    # coordinates per cell so a wrong join (e.g. off-by-one) would be caught.
    grid_rows = [
        {
            "cell_id": cell_id,
            "centroid_lat": draw(_lat),
            "centroid_lon": draw(_lon),
        }
        for cell_id in range(n)
    ]
    grid = pd.DataFrame(
        grid_rows, columns=["cell_id", "centroid_lat", "centroid_lon"]
    )

    return scored, grid


def _equal(observed, expected) -> bool:
    """Value equality that also treats NaN==NaN and <NA>==<NA> as equal."""
    obs_null = pd.isna(observed)
    exp_null = pd.isna(expected)
    if obs_null or exp_null:
        return bool(obs_null and exp_null)
    if isinstance(expected, float):
        return math.isclose(observed, expected, rel_tol=0.0, abs_tol=0.0)
    return observed == expected


# Feature: s1-11-generate-ranked-shortlist, Property 7: Scores, confidence, and rank are carried through unchanged
@SETTINGS
@given(data=_scored_and_grid(), top_n=st.integers(min_value=1, max_value=30))
def test_property_7_scores_confidence_rank_carried_through_unchanged(data, top_n):
    scored, grid = data

    shortlist = select_shortlist(scored, top_n)
    joined = join_coordinates(shortlist, grid)

    # Reference: the original Scored_Table values keyed by cell_id. Selection
    # and the join must NEVER recompute or re-rank these — they are carried
    # straight through (Requirements 1.3, 4.6).
    original = scored.set_index("cell_id")

    # Every shortlisted cell_id must still exist in the Scored_Table (the join
    # neither invents nor drops rows) and appear exactly once in the output.
    assert list(joined["cell_id"]) == list(shortlist["cell_id"])
    assert joined["cell_id"].is_unique or joined.empty

    for _, row in joined.iterrows():
        cell_id = row["cell_id"]
        assert cell_id in original.index

        for col in ("suitability_score", "confidence", "rank"):
            observed = row[col]
            expected = original.at[cell_id, col]
            assert _equal(observed, expected), (
                f"cell_id {cell_id}: {col} changed through the join — "
                f"observed {observed!r}, Scored_Table had {expected!r}. "
                f"The shortlist must carry score/confidence/rank unchanged "
                f"(Requirements 1.3, 4.6)."
            )

    # And the join must not have mutated the score/confidence/rank columns of
    # the input shortlist frame in place (purity) — the shortlist's own values
    # still match the Scored_Table for its cell_ids.
    for _, row in shortlist.iterrows():
        cell_id = row["cell_id"]
        for col in ("suitability_score", "confidence", "rank"):
            assert _equal(row[col], original.at[cell_id, col])
