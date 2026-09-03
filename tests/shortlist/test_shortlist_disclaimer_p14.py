"""
Property-based test for the S1-11 shortlist disclaimer/resolution guarantee
(Property 14).

This test corresponds to numbered Property 14 in the feature design document
and runs at least 100 generated examples. It exercises the FULL set of emitted
shortlist artefacts end-to-end against a real temporary directory (``tmp_path``):

  * the Shortlist_GeoJSON (``write.write_geojson``) — carries the
    Preliminary_Disclaimer and the Analysis_Resolution statement as file-level
    foreign members (8.3);
  * the Shortlist_CSV (``write.write_csv``) — has NO in-band metadata, so its
    disclaimer must travel via its co-emitted metadata (the Summary_Report and
    the metadata sidecar, 8.4, 8.5);
  * the Summary_Report (``report.write_summary_report``) — carries both in-band
    (8.1, 8.2);
  * the metadata sidecar (``report.write_metadata_sidecar``) — carries both
    (8.1, 8.2, 8.4).

The invariant under test: for EVERY emitted output, the disclaimer AND the
resolution statement are present either IN-BAND (in the output file itself) OR
in its co-emitted metadata. No output is ever emitted that omits BOTH. The CSV
is the only in-band-metadata-free artefact, so for the CSV we assert the
co-emitted Summary_Report and sidecar carry both — closing the "no output omits
BOTH" gap.

The empty-shortlist case (zero eligible cells, Requirement 3.6) is included in
the generated input space: an empty, headered shortlist must still ship every
disclaimer-carrying artefact.

It lives in a dedicated module (per task 10.3) so the property tests can grow
file-by-file without concurrent-write conflicts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pipeline.shortlist import config
from pipeline.shortlist.report import write_metadata_sidecar, write_summary_report
from pipeline.shortlist.summary import SummaryStats
from pipeline.shortlist.write import write_csv, write_geojson

# The single ``tmp_path`` fixture is reused across generated examples; every
# example writes to distinct, overwritten filenames within it, so reuse is safe
# here — suppress only the function-scoped-fixture health check.
SETTINGS = settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)

# The two strings that MUST accompany every emitted output, in-band or via its
# co-emitted metadata (Requirement 8). Pulled from config so a wording change
# propagates here rather than drifting.
DISCLAIMER = config.PRELIMINARY_DISCLAIMER
RESOLUTION = config.ANALYSIS_RESOLUTION

_confidence = st.sampled_from(config.CONFIDENCE_LEVELS)
# NSW-ish coordinate windows (EPSG:4326) — kept finite and bounded so the
# GeoJSON/CSV serialisation is well-formed; exact values are irrelevant to the
# disclaimer invariant.
_lat = st.floats(min_value=-38.0, max_value=-28.0, allow_nan=False, allow_infinity=False)
_lon = st.floats(min_value=140.0, max_value=154.0, allow_nan=False, allow_infinity=False)
_score = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


@st.composite
def _assembled_shortlists(draw):
    """
    Build a synthetic ASSEMBLED Shortlist frame — the exact shape the writers
    consume — carrying ``config.SHORTLIST_COLUMNS`` in the documented order
    (``rank``, ``cell_id``, ``suitability_score``, ``confidence``,
    ``centroid_lat``, ``centroid_lon``). Rows are already eligible and
    rank-ordered (this test validates output metadata, not selection).

    ``n == 0`` is drawn too, exercising the empty-shortlist case (Requirement
    3.6): the writers must still emit headered, disclaimer-carrying outputs.
    """
    n = draw(st.integers(min_value=0, max_value=12))

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

    frame = pd.DataFrame(rows, columns=list(config.SHORTLIST_COLUMNS))
    if not frame.empty:
        frame["rank"] = frame["rank"].astype("Int64")
        frame["cell_id"] = frame["cell_id"].astype("Int64")
    return frame


def _synthetic_stats(shortlist: pd.DataFrame) -> SummaryStats:
    """A minimal, internally-consistent ``SummaryStats`` for the report writer.

    The disclaimer/resolution invariant does not depend on the statistics'
    values, only on the report being writable, so this builds a plausible frozen
    stats object (honest ``None`` distribution for an empty shortlist)."""
    n = len(shortlist)
    if n:
        scores = shortlist["suitability_score"]
        std = scores.std()
        score_dist = {
            "min": float(scores.min()),
            "max": float(scores.max()),
            "mean": float(scores.mean()),
            "std": None if pd.isna(std) else float(std),
        }
        lat_range = (float(shortlist["centroid_lat"].min()), float(shortlist["centroid_lat"].max()))
        lon_range = (float(shortlist["centroid_lon"].min()), float(shortlist["centroid_lon"].max()))
        conf = shortlist["confidence"].value_counts()
        confidence_dist = {lvl: int(conf.get(lvl, 0)) for lvl in config.CONFIDENCE_LEVELS}
    else:
        score_dist = {"min": None, "max": None, "mean": None, "std": None}
        lat_range = (None, None)
        lon_range = (None, None)
        confidence_dist = {lvl: 0 for lvl in config.CONFIDENCE_LEVELS}

    return SummaryStats(
        score_dist=score_dist,
        lat_range=lat_range,
        lon_range=lon_range,
        rez_represented=[],
        confidence_dist=confidence_dist,
        n_cells=100,
        n_eligible=n,
        n_scored=n,
    )


def _carries_both(text: str) -> bool:
    """True when ``text`` contains BOTH the disclaimer and the resolution
    statement in-band."""
    return DISCLAIMER in text and RESOLUTION in text


# Feature: s1-11-generate-ranked-shortlist, Property 14: Every output carries the disclaimer and resolution statement
@SETTINGS
@given(shortlist=_assembled_shortlists(), geometry=st.sampled_from(config.GEOMETRY_CHOICES))
def test_property_14_every_output_carries_disclaimer_and_resolution(
    shortlist, geometry, tmp_path: Path
):
    # Produce the FULL set of emitted outputs into a real temp directory.
    csv_path = tmp_path / "sprint1_shortlist_20260101.csv"
    geojson_path = tmp_path / "sprint1_shortlist_20260101.geojson"
    report_path = tmp_path / config.SUMMARY_REPORT_FILENAME
    sidecar_path = tmp_path / config.METADATA_SIDECAR_FILENAME

    # write_metadata_sidecar fingerprints (SHA-256s) a real Scored_Table file,
    # so write a tiny stand-in for it in tmp_path.
    scored_path = tmp_path / "optmining_suitability-score_2026_nsw.gpkg"
    scored_path.write_bytes(b"synthetic-scored-table")

    stats = _synthetic_stats(shortlist)
    n_shortlisted = len(shortlist)

    write_csv(shortlist, csv_path)
    write_geojson(shortlist, geojson_path, geometry)
    write_summary_report(
        report_path,
        stats=stats,
        effective_top_n=20,
        n_shortlisted=n_shortlisted,
        geometry=geometry,
        pipeline_version="test-version",
        run_timestamp="2026-01-01T00:00:00+00:00",
    )
    write_metadata_sidecar(
        sidecar_path,
        scored_path=scored_path,
        effective_top_n=20,
        n_shortlisted=n_shortlisted,
        geometry=geometry,
        pipeline_version="test-version",
        run_timestamp="2026-01-01T00:00:00+00:00",
    )

    # All four artefacts must exist on disk (headered even for an empty
    # shortlist, Requirement 3.6).
    assert csv_path.exists()
    assert geojson_path.exists()
    assert report_path.exists()
    assert sidecar_path.exists()

    # --- GeoJSON: carries BOTH in-band, as file-level foreign members (8.3) ---
    geojson_obj = json.loads(geojson_path.read_text(encoding="utf-8"))
    assert geojson_obj.get("preliminary_disclaimer") == DISCLAIMER
    assert geojson_obj.get("analysis_resolution") == RESOLUTION

    # --- Summary_Report: carries BOTH in-band (8.1, 8.2) ---
    report_text = report_path.read_text(encoding="utf-8")
    assert _carries_both(report_text)

    # --- Metadata sidecar: carries BOTH (8.1, 8.2, 8.4) ---
    sidecar_obj = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar_obj.get("preliminary_disclaimer") == DISCLAIMER
    assert sidecar_obj.get("analysis_resolution") == RESOLUTION

    # --- CSV: has NO in-band metadata, so BOTH must travel via its co-emitted
    #     metadata (the Summary_Report and the sidecar) rather than the CSV body
    #     (8.4, 8.5). Confirm the CSV body indeed omits them (the disclaimer is
    #     not smuggled into a data row) AND that the co-emitted metadata carries
    #     them — so the CSV output as a whole never omits BOTH.
    csv_text = csv_path.read_text(encoding="utf-8")
    assert DISCLAIMER not in csv_text
    csv_disclaimer_present_via_metadata = (
        _carries_both(report_text)
        and sidecar_obj.get("preliminary_disclaimer") == DISCLAIMER
        and sidecar_obj.get("analysis_resolution") == RESOLUTION
    )
    assert csv_disclaimer_present_via_metadata

    # --- The property, stated once for EVERY emitted output: disclaimer AND
    #     resolution present either IN-BAND or via CO-EMITTED metadata. No
    #     output omits BOTH. ---
    def carries(in_band: bool, via_metadata: bool) -> bool:
        return in_band or via_metadata

    metadata_carries_both = csv_disclaimer_present_via_metadata

    outputs = {
        # GeoJSON — in-band.
        "geojson": carries(
            geojson_obj.get("preliminary_disclaimer") == DISCLAIMER
            and geojson_obj.get("analysis_resolution") == RESOLUTION,
            metadata_carries_both,
        ),
        # CSV — via co-emitted metadata only.
        "csv": carries(_carries_both(csv_text), metadata_carries_both),
        # Summary_Report — in-band.
        "summary_report": carries(_carries_both(report_text), metadata_carries_both),
        # Sidecar — in-band.
        "sidecar": carries(
            sidecar_obj.get("preliminary_disclaimer") == DISCLAIMER
            and sidecar_obj.get("analysis_resolution") == RESOLUTION,
            metadata_carries_both,
        ),
    }
    assert all(outputs.values()), f"an emitted output omits BOTH: {outputs}"
