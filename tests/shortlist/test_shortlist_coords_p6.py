"""
Property-based test for the S1-11 coordinate join (Property 6).

This test corresponds to numbered Property 6 in the feature design document and
runs at least 100 generated examples. The pure coordinate-join function under
test (`pipeline.shortlist.coords.join_coordinates`) is exercised directly on
in-memory pandas DataFrames, so this test touches no filesystem: it validates
the JOIN RULES that attach each shortlisted cell's map coordinates
(`centroid_lat` / `centroid_lon`) from the Analysis_Grid on `cell_id` in
EPSG:4326, and the fail-fast rule that an unmatched shortlisted `cell_id` halts
the join before any write rather than emitting a fabricated or null coordinate.

It lives in a dedicated module (separate from test_shortlist_properties.py and
the other per-property files) so the property tests over the pure core can grow
file-by-file without concurrent-write conflicts.
"""

from __future__ import annotations

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.shortlist import config
from pipeline.shortlist.coords import GRID_COORDINATE_COLUMNS, join_coordinates

SETTINGS = settings(max_examples=200, deadline=None)


# A synthetic shortlist row carries the columns the selection core hands to the
# coordinate join: a `cell_id`, its S1-10 `rank`, `suitability_score`, and
# `confidence`. Coordinates are NOT present on the shortlist yet — the join adds
# them from the grid. cell_ids are drawn from a modest integer window so grid
# hits and misses both arise naturally across a generated pair of frames.
_cell_id = st.integers(min_value=0, max_value=40)
_rank = st.integers(min_value=1, max_value=100)
_score = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)
_confidence = st.sampled_from(config.CONFIDENCE_LEVELS)
# Coordinates in a plausible EPSG:4326 window for NSW; exact values don't matter
# to the join, only that they are carried through unchanged and byte-comparable.
_lat = st.floats(min_value=-38.0, max_value=-28.0, allow_nan=False, allow_infinity=False)
_lon = st.floats(min_value=140.0, max_value=154.0, allow_nan=False, allow_infinity=False)


@st.composite
def _shortlist_and_grid(draw):
    """Build a (shortlist, grid, all_matched) triple.

    The shortlist is a set of distinct `cell_id`s (a Shortlist has one row per
    cell) with their carried-through rank/score/confidence. The grid is a set of
    distinct `cell_id`s each with a `centroid_lat` / `centroid_lon`. We choose
    per example whether EVERY shortlisted cell_id is present in the grid (the
    happy path) or whether at least one is deliberately absent (the halt path),
    and return that flag so the test can pick the right branch.
    """
    # Distinct shortlisted cell_ids (a shortlist never repeats a cell_id).
    shortlist_ids = draw(
        st.lists(_cell_id, min_size=1, max_size=12, unique=True)
    )

    all_matched = draw(st.booleans())

    if all_matched:
        # Every shortlisted cell_id must appear in the grid. The grid may also
        # carry extra cells that no shortlist row references (a left-join must
        # ignore those).
        extra_ids = draw(
            st.lists(_cell_id, min_size=0, max_size=8, unique=True)
        )
        grid_ids = list(dict.fromkeys([*shortlist_ids, *extra_ids]))
    else:
        # Drop at least one shortlisted cell_id from the grid so the join has an
        # unmatched key. Keep a random subset of the rest, plus optional extras.
        drop_count = draw(st.integers(min_value=1, max_value=len(shortlist_ids)))
        drop = set(draw(st.permutations(shortlist_ids))[:drop_count])
        kept = [c for c in shortlist_ids if c not in drop]
        extra_ids = draw(st.lists(_cell_id, min_size=0, max_size=8, unique=True))
        grid_ids = [c for c in dict.fromkeys([*kept, *extra_ids]) if c not in drop]

    shortlist = pd.DataFrame(
        {
            "rank": [draw(_rank) for _ in shortlist_ids],
            "cell_id": shortlist_ids,
            "suitability_score": [draw(_score) for _ in shortlist_ids],
            "confidence": [draw(_confidence) for _ in shortlist_ids],
        }
    )

    grid = pd.DataFrame(
        {
            "cell_id": grid_ids,
            "centroid_lat": [draw(_lat) for _ in grid_ids],
            "centroid_lon": [draw(_lon) for _ in grid_ids],
            # A decoy column that shares no name with the shortlist; the join
            # must NOT pull it through (only the two coordinate columns).
            "some_grid_only_column": [draw(_score) for _ in grid_ids],
        }
    )

    return shortlist, grid, all_matched


# Feature: s1-11-generate-ranked-shortlist, Property 6: Coordinate-join correctness and halt on unmatched cell_id
@SETTINGS
@given(case=_shortlist_and_grid())
def test_property_6_coordinate_join_correctness_and_halt_on_unmatched_cell_id(case):
    shortlist, grid, all_matched = case
    coord_cols = list(GRID_COORDINATE_COLUMNS)

    # An independent lookup of the grid's coordinates per cell_id, used as the
    # reference the join must reproduce exactly (Req 4.2).
    grid_lookup = grid.set_index("cell_id")[coord_cols].to_dict("index")

    if all_matched:
        # BRANCH 1 — every shortlisted cell_id exists in the grid.
        joined = join_coordinates(shortlist, grid)

        # The join is a left-join on cell_id: one output row per shortlisted
        # cell, in the shortlist's (rank) order, unchanged (Req 4.2).
        assert list(joined["cell_id"]) == list(shortlist["cell_id"])
        assert len(joined) == len(shortlist)

        # No coordinate is null — every shortlisted cell resolved to a grid row
        # (Req 4.5 / 12.4: never a fabricated or null coordinate).
        assert joined[coord_cols].notna().all().all()

        # The joined centroid_lat / centroid_lon equal the grid's values for the
        # matching cell_id, in EPSG:4326 (carried through, not recomputed)
        # (Req 4.2, 12.4).
        for _, row in joined.iterrows():
            expected = grid_lookup[row["cell_id"]]
            assert row["centroid_lat"] == expected["centroid_lat"]
            assert row["centroid_lon"] == expected["centroid_lon"]

        # The join draws ONLY the two coordinate columns from the grid; the
        # grid-only decoy column is never pulled into the shortlist output.
        assert "some_grid_only_column" not in joined.columns

        # The carried-through score/confidence/rank are untouched by the join.
        assert list(joined["suitability_score"]) == list(shortlist["suitability_score"])
        assert list(joined["confidence"]) == list(shortlist["confidence"])
        assert list(joined["rank"]) == list(shortlist["rank"])
    else:
        # BRANCH 2 — at least one shortlisted cell_id is absent from the grid.
        # The join must HALT (raise ValueError) before producing any output,
        # naming the unmatched cell_id(s), and emit no fabricated/null-coordinate
        # frame at all (Req 4.5, 12.4).
        grid_ids = set(grid["cell_id"])
        unmatched = [c for c in shortlist["cell_id"] if c not in grid_ids]
        assert unmatched  # the generator guarantees at least one miss

        with pytest.raises(ValueError) as excinfo:
            join_coordinates(shortlist, grid)

        # The error names the unmatched cell_id(s) so an operator can see which
        # cells broke the grid/Scored_Table cell_id contract (Req 4.5). The
        # implementation reports up to the first five ids; assert at least one
        # of the unmatched ids is named.
        message = str(excinfo.value)
        assert any(str(c) in message for c in unmatched)
