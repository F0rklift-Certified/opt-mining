"""
Property-based test for the S1-11 shortlist assembly schema (Property 11).

This test corresponds to numbered Property 11 in the feature design document
and runs at least 100 generated examples. The pure assembly function under
test (`pipeline.shortlist.assemble.assemble_shortlist`) is exercised directly
on in-memory pandas DataFrames, so this test touches no filesystem: it
validates the OUTPUT SCHEMA contract — the documented `SHORTLIST_COLUMNS`
appear first, in the documented order, with any available optional context
column (`rez`, `nearby_wind_farm`) appended after them, and any extra
non-documented column dropped (Requirement 4.1, 4.3).

Because the Shortlist_CSV columns and the Shortlist_GeoJSON feature properties
are both drawn from this assembled frame's column order (design §6), asserting
the assembled schema here validates the documented column order carried into
both output formats.

It lives in a dedicated module (separate from the other property tests) so the
property tests over the pure core can grow file-by-file without
concurrent-write conflicts.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.shortlist import config
from pipeline.shortlist.assemble import assemble_shortlist

SETTINGS = settings(max_examples=200, deadline=None)

# The documented core schema (Requirement 4.1) and the optional context
# columns catalogue (Requirement 4.3), read from config so a rename there
# propagates into this test rather than drifting.
CORE = list(config.SHORTLIST_COLUMNS)
OPTIONAL = list(config.OPTIONAL_CONTEXT_COLUMNS)

# Extra, non-documented columns an upstream layer might carry on the joined
# frame (e.g. per-criterion contribution columns). These MUST be dropped by
# assembly — they are neither core nor catalogued optional context.
_EXTRA_COLUMN_POOL = ["contrib_wind", "contrib_demand", "contrib_slope", "geometry", "notes"]

_score = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_confidence = st.sampled_from(config.CONFIDENCE_LEVELS)
_lat = st.floats(min_value=-45.0, max_value=-10.0, allow_nan=False, allow_infinity=False)
_lon = st.floats(min_value=110.0, max_value=155.0, allow_nan=False, allow_infinity=False)


@st.composite
def _joined_frames(draw):
    """Build a synthetic coordinate-joined frame for assembly.

    The frame always carries the six documented core columns
    (`config.SHORTLIST_COLUMNS`) but presents them in an ARBITRARY column
    order, so the test never relies on assembly receiving pre-ordered columns.
    It MAY additionally carry a random subset of the optional context columns
    (`rez`, `nearby_wind_farm`) and/or a random subset of extra non-documented
    columns — each interleaved into the column order at random — so assembly's
    select-and-reorder must both promote the core columns to the documented
    order AND drop the extras regardless of where they sit.
    """
    n = draw(st.integers(min_value=0, max_value=20))

    # Decide which optional context / extra columns this frame carries.
    present_optional = draw(st.lists(st.sampled_from(OPTIONAL), unique=True, max_size=len(OPTIONAL)))
    present_extra = draw(
        st.lists(st.sampled_from(_EXTRA_COLUMN_POOL), unique=True, max_size=len(_EXTRA_COLUMN_POOL))
    )

    # Build each column's values (row order is irrelevant to this schema
    # property, so simple per-row draws suffice).
    data: dict[str, list] = {
        "rank": [draw(st.integers(min_value=1, max_value=1000)) for _ in range(n)],
        "cell_id": list(range(n)),
        "suitability_score": [draw(_score) for _ in range(n)],
        "confidence": [draw(_confidence) for _ in range(n)],
        "centroid_lat": [draw(_lat) for _ in range(n)],
        "centroid_lon": [draw(_lon) for _ in range(n)],
    }
    for col in present_optional:
        data[col] = [draw(st.text(max_size=8)) for _ in range(n)]
    for col in present_extra:
        data[col] = [draw(st.integers()) for _ in range(n)]

    # Shuffle the column order so core columns arrive interleaved with the
    # optional/extra columns in an arbitrary arrangement.
    all_columns = list(data.keys())
    shuffled = draw(st.permutations(all_columns))
    frame = pd.DataFrame(data, columns=list(shuffled))

    return frame, list(present_optional), list(present_extra)


# Feature: s1-11-generate-ranked-shortlist, Property 11: Output schema and documented column order
@SETTINGS
@given(built=_joined_frames())
def test_property_11_output_schema_and_documented_column_order(built):
    joined, present_optional, present_extra = built

    assembled = assemble_shortlist(joined)
    columns = list(assembled.columns)

    # 1. The first six columns are EXACTLY the documented SHORTLIST_COLUMNS in
    #    the documented order (rank, cell_id, suitability_score, confidence,
    #    centroid_lat, centroid_lon) — regardless of the arbitrary input order
    #    (Requirement 4.1).
    assert columns[: len(CORE)] == CORE

    # 2. Any available optional context column appears AFTER the core columns,
    #    in the documented OPTIONAL_CONTEXT_COLUMNS order (Requirement 4.3).
    expected_optional = [c for c in OPTIONAL if c in present_optional]
    assert columns[len(CORE):] == expected_optional

    # 3. Extra, non-documented columns are dropped — they are neither core nor
    #    catalogued optional context.
    for extra in present_extra:
        assert extra not in columns

    # 4. The full column set is exactly the core columns followed by the
    #    available optional context columns — nothing more, nothing less.
    assert columns == CORE + expected_optional

    # 5. Row count is preserved: assembly only selects and reorders columns, it
    #    never adds or drops a row.
    assert len(assembled) == len(joined)
