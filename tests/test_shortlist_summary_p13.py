"""
Property-based test for the S1-11 pure summary core (Property 13).

This test corresponds to numbered Property 13 in the feature design document
and runs at least 100 generated examples. The pure summary function under test
(`pipeline.shortlist.summary.compute_summary`) is exercised directly on
in-memory pandas DataFrames, so this test touches no filesystem: it validates
that the reported `confidence_dist` is a faithful tally of the SHORTLISTED
cells at each documented `confidence` level, independent of the loader and the
writers.

Property 13 asserts two things about the confidence distribution
(Requirement 6.4):

  1. PER-LEVEL COUNTS MATCH THE SHORTLIST. For every level in the documented
     vocabulary (`config.CONFIDENCE_LEVELS` == "high"/"low"), the reported
     count equals the number of shortlisted cells actually carrying that
     `confidence` value — computed independently here.

  2. THE COUNTS SUM TO THE SHORTLIST ROW COUNT. Because every generated
     shortlisted cell carries a `confidence` value drawn from the vocabulary,
     the per-level counts partition the shortlist and therefore sum to the
     shortlist row count.

It lives in a dedicated module (separate from the other shortlist property
tests) so the property tests over the pure core can grow file-by-file without
concurrent-write conflicts.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.shortlist import config
from pipeline.shortlist.summary import compute_summary

SETTINGS = settings(max_examples=200, deadline=None)


# A confidence value drawn from the documented vocabulary ("high"/"low"). Every
# generated shortlisted cell carries one of these, so the two per-level counts
# partition the shortlist and sum to its row count (the second half of the
# property).
_confidence = st.sampled_from(config.CONFIDENCE_LEVELS)
_score = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)
_rank = st.integers(min_value=1, max_value=50)


@st.composite
def _shortlists(draw):
    """Build a synthetic Shortlist frame with a `confidence` column.

    Columns follow the documented SHORTLIST_COLUMNS the summary core keys
    against (`rank`, `cell_id`, `suitability_score`, `confidence`, and the two
    coordinate columns). Every row is a shortlisted Eligible_Cell carrying a
    `confidence` value drawn from `config.CONFIDENCE_LEVELS`. The shortlist may
    be empty — a zero-eligible run is a legal input to the summary core and
    must report {"high": 0, "low": 0}.
    """
    n = draw(st.integers(min_value=0, max_value=25))

    rows = []
    for cell_id in range(n):
        rows.append(
            {
                "rank": cell_id + 1,
                "cell_id": cell_id,
                "suitability_score": draw(_score),
                "confidence": draw(_confidence),
                "centroid_lat": draw(
                    st.floats(min_value=-38.0, max_value=-28.0, allow_nan=False)
                ),
                "centroid_lon": draw(
                    st.floats(min_value=140.0, max_value=154.0, allow_nan=False)
                ),
            }
        )

    shortlist = pd.DataFrame(rows, columns=list(config.SHORTLIST_COLUMNS))
    return shortlist


@st.composite
def _scored_tables(draw, shortlist):
    """Build a Scored_Table that contains the shortlisted cells plus extra rows.

    ``compute_summary`` takes the full Scored_Table alongside the shortlist,
    but the confidence distribution is computed over the SHORTLIST only, so the
    scored frame's contents must not perturb the result. We include the
    shortlisted rows verbatim plus a handful of additional Eligible_Cells and
    Excluded_Cells so the test proves the confidence tally is driven by the
    shortlist and not by the wider table.
    """
    extra = draw(st.integers(min_value=0, max_value=10))
    base_id = 10_000  # disjoint from the shortlist cell_ids

    rows = shortlist.to_dict("records")
    for i in range(extra):
        eligible = draw(st.booleans())
        if eligible:
            rank = draw(_rank)
            score = draw(_score)
        else:
            rank = None
            score = None
        rows.append(
            {
                "rank": rank,
                "cell_id": base_id + i,
                "suitability_score": score,
                "confidence": draw(_confidence),
                "centroid_lat": None,
                "centroid_lon": None,
            }
        )

    scored = pd.DataFrame(rows, columns=list(config.SHORTLIST_COLUMNS))
    if not scored.empty:
        scored["rank"] = scored["rank"].astype("Int64")
    return scored


# Feature: s1-11-generate-ranked-shortlist, Property 13: Confidence distribution matches the shortlisted cells
@SETTINGS
@given(data=st.data())
def test_property_13_confidence_distribution_matches_the_shortlisted_cells(data):
    shortlist = data.draw(_shortlists())
    scored = data.draw(_scored_tables(shortlist))

    stats = compute_summary(scored, shortlist)
    confidence_dist = stats.confidence_dist

    # Independently recompute the count of shortlisted cells at each confidence
    # value. Because every generated shortlisted cell carries a vocabulary
    # value, `value_counts` over the shortlist gives the reference tally.
    if shortlist.empty:
        observed = {}
    else:
        observed = shortlist["confidence"].value_counts().to_dict()

    # 1. Per-level counts == shortlisted counts, for EVERY documented level.
    #    A level with no shortlisted cell must still be present with an explicit
    #    zero (Requirement 6.4) — the level never silently disappears.
    assert set(confidence_dist.keys()) == set(config.CONFIDENCE_LEVELS)
    for level in config.CONFIDENCE_LEVELS:
        assert confidence_dist[level] == int(observed.get(level, 0))

    # 2. The per-level counts sum to the shortlist row count. Every generated
    #    shortlisted cell carries a value within the vocabulary, so the two
    #    counts partition the shortlist exactly (Requirement 6.4).
    assert sum(confidence_dist.values()) == len(shortlist)
