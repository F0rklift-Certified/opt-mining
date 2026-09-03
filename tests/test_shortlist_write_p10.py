"""
Property-based test for the S1-11 GeoJSON writer CRS statement (Property 10).

This test corresponds to numbered Property 10 in the feature design document
and runs at least 100 generated examples. It exercises the GeoJSON writer
(`pipeline.shortlist.write.write_geojson`) end to end: an assembled Shortlist
frame is written to a real GeoJSON file under `tmp_path`, read back with the
stdlib `json` module, and inspected to confirm the CRS is stated EXPLICITLY as
EPSG:4326 rather than assumed.

The write stage performs NO reprojection: `centroid_lat`/`centroid_lon` arrive
from the grid in EPSG:4326 and are written unchanged (write.py, Req 5.3). So
the test also asserts that every written geometry coordinate falls inside valid
WGS84 lat/lon bounds — a sanity check that nothing was silently reprojected to
a metric CRS such as EPSG:3577.

Both documented geometry choices ("centroid" Point and "polygon") are covered,
since the CRS statement is a file-level property that must hold regardless of
the per-feature geometry. The style follows tests/test_shortlist_select_p1.py.
"""

from __future__ import annotations

import json

import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pipeline.shortlist import config
from pipeline.shortlist.write import write_geojson

# The function-scoped ``tmp_path`` fixture is not reset between generated
# examples; that is intentional here — each example overwrites the same path
# atomically and reads it straight back, so no state leaks across examples.
SETTINGS = settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)

# WGS84 (EPSG:4326) coordinate bounds. Coordinates written by the stage must
# fall inside these bounds; a value outside them would signal a silent
# reprojection to a metric CRS (e.g. EPSG:3577 metres), which this stage must
# never perform (Req 5.3).
_LON_MIN, _LON_MAX = -180.0, 180.0
_LAT_MIN, _LAT_MAX = -90.0, 90.0

# Generate centroid coordinates within an NSW-plausible WGS84 window, kept a
# half-cell inside the global bounds so the "polygon" ring (built by expanding
# the centroid by HALF_CELL_DEG) also stays within valid lat/lon bounds.
_lat = st.floats(min_value=-38.0, max_value=-28.0, allow_nan=False, allow_infinity=False)
_lon = st.floats(min_value=140.0, max_value=154.0, allow_nan=False, allow_infinity=False)
_score = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_confidence = st.sampled_from(config.CONFIDENCE_LEVELS)

_CORE = list(config.SHORTLIST_COLUMNS)


@st.composite
def _assembled_shortlists(draw):
    """Build an assembled Shortlist frame carrying the documented columns.

    Columns are the documented ``config.SHORTLIST_COLUMNS`` in order (`rank`,
    `cell_id`, `suitability_score`, `confidence`, `centroid_lat`,
    `centroid_lon`) — the exact schema the writer keys against. The frame may
    be empty (zero eligible cells, Req 3.6), in which case the writer still
    emits a well-formed FeatureCollection carrying the CRS statement.
    """
    n = draw(st.integers(min_value=0, max_value=15))
    rows = []
    for i in range(n):
        rows.append(
            {
                "rank": i + 1,
                "cell_id": 1000 + i,
                "suitability_score": draw(_score),
                "confidence": draw(_confidence),
                "centroid_lat": draw(_lat),
                "centroid_lon": draw(_lon),
            }
        )
    frame = pd.DataFrame(rows, columns=_CORE)
    if not frame.empty:
        frame["rank"] = frame["rank"].astype("Int64")
        frame["cell_id"] = frame["cell_id"].astype("Int64")
    return frame


# Feature: s1-11-generate-ranked-shortlist, Property 10: GeoJSON geometry is stored in EPSG:4326
@SETTINGS
@given(
    shortlist=_assembled_shortlists(),
    geometry=st.sampled_from(config.GEOMETRY_CHOICES),
)
def test_property_10_geojson_geometry_is_stored_in_epsg_4326(
    shortlist, geometry, tmp_path
):
    path = tmp_path / "sprint1_shortlist_test.geojson"

    write_geojson(shortlist, path, geometry=geometry)

    # Read the written file back independently via stdlib json — no assumption
    # about the in-memory dict; we inspect what actually landed on disk.
    with open(path, encoding="utf-8") as fh:
        collection = json.load(fh)

    assert collection["type"] == "FeatureCollection"

    # 1. The CRS is stated EXPLICITLY, in two forms, both == EPSG:4326
    #    (config.STORAGE_CRS) rather than left implied (Req 5.3).
    #    a) the plain-text "crs_statement" foreign member; and
    assert collection["crs_statement"] == config.STORAGE_CRS
    assert config.STORAGE_CRS == "EPSG:4326"

    #    b) the legacy "crs" name member, which names EPSG:4326 unambiguously
    #       as a URN for consumers that read it.
    crs = collection["crs"]
    assert crs["type"] == "name"
    crs_name = crs["properties"]["name"]
    assert crs_name == "urn:ogc:def:crs:EPSG::4326"
    # The URN encodes the same authority:code as STORAGE_CRS ("EPSG:4326"),
    # stated rather than assumed.
    assert crs_name == f"urn:ogc:def:crs:{config.STORAGE_CRS.replace(':', '::')}"

    # 2. The recorded geometry type matches the requested choice (Req 5.4).
    assert collection["geometry_type"] == geometry

    # 3. Every written coordinate falls within valid WGS84 lat/lon bounds — a
    #    sanity check that the grid coordinates were carried through unchanged
    #    and NOT silently reprojected to a metric CRS (Req 5.3, no reprojection).
    features = collection["features"]
    assert len(features) == len(shortlist)

    for feature in features:
        geom = feature["geometry"]
        assert geom["type"] == ("Polygon" if geometry == "polygon" else "Point")

        if geom["type"] == "Point":
            coord_pairs = [geom["coordinates"]]
        else:
            # Polygon: coordinates is [ring]; the ring is a list of [lon, lat].
            coord_pairs = geom["coordinates"][0]

        for lon, lat in coord_pairs:
            assert _LON_MIN <= lon <= _LON_MAX, f"lon {lon} outside WGS84 bounds"
            assert _LAT_MIN <= lat <= _LAT_MAX, f"lat {lat} outside WGS84 bounds"
