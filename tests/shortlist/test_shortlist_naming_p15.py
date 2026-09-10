"""
Property-based test for the S1-11 shortlist Run_Timestamp reuse (Property 15).

This test corresponds to numbered Property 15 in the feature design document
and runs at least 100 generated examples. It validates that the SINGLE UTC
Run_Timestamp derived once per run (via ``naming.run_timestamp`` /
``common.geo.utc_now``) is reused *identically* across the two output
filenames and the metadata sidecar:

  * ``resolve_output_paths(out_dir, ts)`` embeds the UTC ``YYYYMMDD`` date
    parsed from ``ts`` in BOTH the CSV and the GeoJSON filename, and the two
    filenames share one stem (paired outputs, Requirement 7.1, 7.2); and
  * ``build_metadata_sidecar(..., run_timestamp=ts, ...)`` records that same
    ``ts`` verbatim in its ``run_timestamp`` field (Requirement 7.2).

Together this proves the one Run_Timestamp is threaded through the filenames
and the metadata rather than each artefact reading the wall clock separately
(which would let them disagree).

It lives in a dedicated module (per the S1-11 file-by-file property-test
convention) so the property tests can grow without concurrent-write conflicts.
A small real Scored_Table file is written into ``tmp_path`` so the sidecar's
``scored_table_id`` SHA-256 fingerprint (which reads the file) can be computed.

Validates: Requirements 7.2
"""

from __future__ import annotations

import tempfile
from datetime import timezone
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.shortlist import config
from pipeline.shortlist.naming import resolve_output_paths
from pipeline.shortlist.report import build_metadata_sidecar

SETTINGS = settings(max_examples=150, deadline=None)


# Synthetic UTC Run_Timestamps formatted exactly the way common.geo.utc_now
# produces them: an aware UTC datetime rendered with isoformat at seconds
# precision, i.e. "YYYY-MM-DDTHH:MM:SS+00:00". Drawing tz-aware UTC datetimes
# from Hypothesis and formatting them identically keeps the generated space
# faithful to the real timestamps naming.run_timestamp() emits.
_utc_datetimes = st.datetimes(
    timezones=st.just(timezone.utc),
    allow_imaginary=False,
).map(lambda dt: dt.replace(microsecond=0))


@st.composite
def _utc_run_timestamps(draw):
    """An ISO-8601 UTC Run_Timestamp string, seconds precision, +00:00 offset."""
    dt = draw(_utc_datetimes)
    return dt.isoformat(timespec="seconds")


# Feature: s1-11-generate-ranked-shortlist, Property 15: Run_Timestamp is reused across filenames and metadata
@SETTINGS
@given(ts=_utc_run_timestamps())
def test_property_15_run_timestamp_reused_across_filenames_and_metadata(ts):
    # A fresh per-example output directory (a plain tempfile, not a
    # function-scoped fixture) so each generated ts resolves against an empty
    # directory — the base <YYYYMMDD> stem, no leftover-file collision tier.
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)

        # A small real Scored_Table file so the sidecar's scored_table_id
        # SHA-256 (which reads the file) can be computed without a GeoPackage.
        scored_path = out_dir / "scored_table.csv"
        scored_path.write_text(
            "cell_id,suitability_score,rank,confidence\n1,0.9,1,high\n",
            encoding="utf-8",
        )

        # Resolve the paired output paths from the single Run_Timestamp. On a
        # fresh directory no shortlist file exists yet, so the base <YYYYMMDD>
        # stem is chosen and the date component is derived directly from ts.
        resolved = resolve_output_paths(out_dir, ts)

        # Build the metadata sidecar with the SAME ts threaded in.
        sidecar = build_metadata_sidecar(
            scored_path=scored_path,
            effective_top_n=config.DEFAULT_TOP_N,
            n_shortlisted=1,
            geometry="centroid",
            pipeline_version="test-version",
            run_timestamp=ts,
        )

        # The UTC date the filenames must embed: YYYYMMDD parsed from ts. ts is
        # "YYYY-MM-DDTHH:MM:SS+00:00", so the calendar date is the first 10
        # characters with the dashes stripped — computed here INDEPENDENTLY of
        # the naming module so the assertion is a genuine cross-check.
        expected_date = ts[:10].replace("-", "")

        csv_stem = resolved.csv.stem
        geojson_stem = resolved.geojson.stem

        # 1. The UTC date derived from ts appears identically in BOTH filenames
        #    (Requirement 7.1, 7.2).
        assert expected_date in csv_stem
        assert expected_date in geojson_stem

        # 2. The CSV and GeoJSON share one stem and the expected extensions, so
        #    a reviewer sees the pair belongs to the same run (Requirement 7.1).
        assert csv_stem == geojson_stem
        assert resolved.csv.suffix == ".csv"
        assert resolved.geojson.suffix == ".geojson"

        # On a fresh directory the base date stem is used (no collision), so the
        # stem is exactly OUTPUT_PREFIX_<YYYYMMDD> — the Run_Timestamp's date.
        assert csv_stem == f"{config.OUTPUT_PREFIX}_{expected_date}"
        assert resolved.collision.occurred is False

        # 3. The metadata sidecar records the SAME Run_Timestamp verbatim
        #    (Requirement 7.2) — byte-for-byte equal to the ts driving the
        #    filenames.
        assert sidecar["run_timestamp"] == ts
