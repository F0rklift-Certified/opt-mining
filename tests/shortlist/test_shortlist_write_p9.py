"""
Property-based test for the S1-11 output writers (Property 9).

This test corresponds to numbered Property 9 in the feature design document
and runs at least 100 generated examples. It exercises the two writers under
test — `pipeline.shortlist.write.write_csv` and
`pipeline.shortlist.write.write_geojson` — against synthetic assembled
Shortlist frames, writing both artefacts to `tmp_path`, reading them back
(the CSV via pandas, the GeoJSON via `json`), and asserting that the ordered
`cell_id` sequence in the CSV equals, element-for-element, the ordered
`cell_id` sequence drawn from the GeoJSON features.

Both writers draw from the SAME in-memory Shortlist frame, so by construction
the CSV and the GeoJSON must carry the same `cell_id` set in the same rank
order (Requirement 5.5, 12.5). The empty-shortlist case is included via the
row-count generator's lower bound of zero.

It lives in a dedicated module (separate from test_shortlist_properties.py) so
the property tests over the writers can grow file-by-file without
concurrent-write conflicts.
"""

from __future__ import annotations

import json

import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pipeline.shortlist import config
from pipeline.shortlist.write import write_csv, write_geojson

# The `tmp_path` fixture is function-scoped, so Hypothesis reuses one directory
# across generated examples. That is safe here: each example writes to the same
# two fixed paths, atomically overwriting the previous example's output before
# reading it back, so no state leaks between examples. Suppress only that check.
SETTINGS = settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


# A synthetic assembled Shortlist row carries the documented SHORTLIST_COLUMNS
# in order plus the centroid coordinates the writers geometrise. cell_id values
# are drawn unique across the frame so the ordered-sequence comparison is
# unambiguous; ranks are a strictly increasing prefix so the frame looks like a
# genuine ascending-rank shortlist (though the writers only echo row order).
_score = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)
_lat = st.floats(
    min_value=-38.0, max_value=-28.0, allow_nan=False, allow_infinity=False
)
_lon = st.floats(
    min_value=140.0, max_value=154.0, allow_nan=False, allow_infinity=False
)
_confidence = st.sampled_from(config.CONFIDENCE_LEVELS)


@st.composite
def _shortlist_frames(draw):
    """Build an assembled Shortlist DataFrame in the documented schema.

    Columns follow `config.SHORTLIST_COLUMNS` in the documented order. Row count
    ranges from 0 (the empty-shortlist case, Requirement 3.6) upward. `cell_id`
    values are a shuffled sample of distinct integers so the ordered sequence is
    well-defined and the row order is not trivially the natural cell_id order.
    """
    n = draw(st.integers(min_value=0, max_value=25))

    # Distinct cell_id values so the ordered sequence is unambiguous; shuffled
    # so the writers' preservation of row order is genuinely exercised.
    cell_ids = draw(
        st.lists(
            st.integers(min_value=0, max_value=100_000),
            min_size=n,
            max_size=n,
            unique=True,
        )
    )

    rows = []
    for i, cell_id in enumerate(cell_ids):
        rows.append(
            {
                "rank": i + 1,
                "cell_id": cell_id,
                "suitability_score": draw(_score),
                "confidence": draw(_confidence),
                "centroid_lat": draw(_lat),
                "centroid_lon": draw(_lon),
            }
        )

    frame = pd.DataFrame(rows, columns=list(config.SHORTLIST_COLUMNS))
    return frame


def _geojson_cell_ids(path):
    """Read the written GeoJSON and return the cell_id sequence in feature order."""
    with open(path, encoding="utf-8") as fh:
        collection = json.load(fh)
    return [feature["properties"]["cell_id"] for feature in collection["features"]]


# Feature: s1-11-generate-ranked-shortlist, Property 9: CSV and GeoJSON carry the same cell_id set in the same order
@SETTINGS
@given(shortlist=_shortlist_frames(), geometry=st.sampled_from(config.GEOMETRY_CHOICES))
def test_property_9_csv_and_geojson_carry_same_cell_id_set_in_same_order(
    tmp_path, shortlist, geometry
):
    csv_path = tmp_path / "sprint1_shortlist_test.csv"
    geojson_path = tmp_path / "sprint1_shortlist_test.geojson"

    # Both writers draw from the SAME in-memory frame (Requirement 5.5).
    write_csv(shortlist, csv_path)
    write_geojson(shortlist, geojson_path, geometry)

    # Read the CSV back via pandas. An empty shortlist still yields a headered
    # file with a cell_id column (Requirement 3.6), so this holds for n == 0.
    csv_frame = pd.read_csv(csv_path)
    csv_cell_ids = list(csv_frame["cell_id"])

    # Read the GeoJSON back via json and pull cell_id from each feature's
    # properties, in feature order.
    geojson_cell_ids = _geojson_cell_ids(geojson_path)

    # Property 9: the ordered cell_id sequence in the CSV equals, element for
    # element, the ordered cell_id sequence in the GeoJSON (Requirement 5.5,
    # 12.5). Compare against the source frame's order too, so a shared bug that
    # reorders BOTH writers the same way cannot slip through.
    source_cell_ids = list(shortlist["cell_id"])

    assert csv_cell_ids == geojson_cell_ids
    assert csv_cell_ids == source_cell_ids

    # Same SET as well as same order (guards against a duplicate/dropped id that
    # a positional compare alone might miss on exotic inputs).
    assert set(csv_cell_ids) == set(geojson_cell_ids)
