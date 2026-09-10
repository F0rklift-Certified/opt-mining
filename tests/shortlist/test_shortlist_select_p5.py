"""
Property-based test for the S1-11 pure selection core (Property 5).

This test corresponds to numbered Property 5 in the feature design document
and runs at least 100 generated examples. The pure selection function under
test (`pipeline.shortlist.select.select_shortlist`) is exercised directly on
in-memory pandas DataFrames, so this test touches no filesystem: it validates
the ZERO-ELIGIBLE rule — when no cell is eligible, the selection returns an
EMPTY frame that still carries the documented `SHORTLIST_COLUMNS`, so the
downstream writers can emit a headered CSV / GeoJSON with the disclaimer
rather than crashing on a missing column (Requirement 3.6).

It lives in a dedicated module (separate from test_shortlist_properties.py and
the other per-property files) so the property tests over the pure core can
grow file-by-file without concurrent-write conflicts.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.shortlist import config
from pipeline.shortlist.select import eligible_cells, select_shortlist

SETTINGS = settings(max_examples=200, deadline=None)


# The documented columns keyed against by the selection core. We generate
# tables carrying at least these four (the loader-facing SHORTLIST_COLUMNS
# prefix); centroid_lat / centroid_lon are joined downstream, so the selection
# core only relies on rank / cell_id / suitability_score / confidence.
_CORE_COLUMNS = list(config.SHORTLIST_COLUMNS[:4])

_confidence = st.sampled_from(config.CONFIDENCE_LEVELS)


@st.composite
def _excluded_only_tables(draw):
    """Build a Scored_Table DataFrame containing ONLY Excluded_Cells.

    Every row is an Excluded_Cell — null ``suitability_score`` AND null
    ``rank`` (the S1-10 convention) — so the eligible count is always zero.
    The documented columns (`rank`, `cell_id`, `suitability_score`,
    `confidence`) are always present so the downstream writers can emit
    headered output. The table may be empty (zero rows) — also a legal
    zero-eligible input to the selection core.
    """
    n = draw(st.integers(min_value=0, max_value=25))

    rows = []
    for cell_id in range(n):
        rows.append(
            {
                # Excluded_Cell: null score AND null rank (S1-10 convention).
                "rank": None,
                "cell_id": cell_id,
                "suitability_score": None,
                "confidence": draw(_confidence),
            }
        )

    frame = pd.DataFrame(rows, columns=_CORE_COLUMNS)
    if not frame.empty:
        # Keep the nullable integer dtype for rank so null ranks survive as
        # <NA> rather than being coerced to float NaN — honest to the S1-10
        # schema (matches the sibling per-property files).
        frame["rank"] = frame["rank"].astype("Int64")

    return frame


# Feature: s1-11-generate-ranked-shortlist, Property 5: Zero eligible cells yields a well-formed empty shortlist
@SETTINGS
@given(scored=_excluded_only_tables(), top_n=st.integers(min_value=1, max_value=30))
def test_property_5_zero_eligible_yields_well_formed_empty_shortlist(scored, top_n):
    # Precondition of this property: the generated table has zero Eligible_Cells.
    assert len(eligible_cells(scored)) == 0

    shortlist = select_shortlist(scored, top_n)

    # 1. Empty selection: with no eligible cell, nothing is selected and the
    #    shortlist is never padded to reach Top_N (Req 3.6, 3.4).
    assert len(shortlist) == 0

    # 2. Well-formed: the empty frame still carries the documented columns
    #    present on the input, so the downstream writers can emit a headered
    #    CSV / GeoJSON with the disclaimer rather than crash on a missing
    #    column (Req 3.6).
    for column in _CORE_COLUMNS:
        assert column in shortlist.columns

    # The surviving columns preserve the input's documented order (the
    # selection core is a row filter, not a column reshuffle), so downstream
    # header emission is stable.
    assert list(shortlist.columns) == list(scored.columns)
