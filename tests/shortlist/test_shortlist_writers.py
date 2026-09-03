"""
Unit tests for the S1-11 shortlist writers, timestamped naming, and atomicity
(task 9.4).

These are example-based unit tests (the universal invariants are covered by the
property tests P9/P10/P15). They exercise, over ``tmp_path``:

  * timestamped filenames — ``resolve_output_paths`` yields
    ``sprint1_shortlist_<UTCdate>.csv`` / ``.geojson`` carrying the region slug
    ``nsw`` via ``OUTPUT_PREFIX``, and the SAME Run_Timestamp / stem in both
    (Requirements 7.1, 7.2, 7.3);
  * the name-collision rule — an existing base-stem output forces a finer-grained
    UTC component and ``CollisionOutcome.occurred`` is True with the resolved
    stem recorded (Requirement 7.4);
  * the empty-shortlist case — a zero-row shortlist still emits a headered CSV
    and a GeoJSON with an empty ``features`` array plus the CRS / disclaimer /
    resolution members (Requirement 3.6);
  * atomicity — a forced ``os.replace`` failure leaves a pre-existing output
    unmodified (Requirement 5.7);
  * the documented geometry choice — ``write_geojson`` rejects an unknown choice
    and states the chosen ``geometry_type`` on the FeatureCollection for the
    Summary_Report (Requirement 5.4).

Conventions follow ``tests/test_common_geo.py`` (tmp_path, atomic-write
assertions) and the shortlist config/naming/write contracts.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from pipeline.common import geo as common_geo
from pipeline.shortlist import config
from pipeline.shortlist.naming import (
    CollisionOutcome,
    ResolvedPaths,
    resolve_output_paths,
    run_timestamp,
)
from pipeline.shortlist.write import write_csv, write_geojson

# A fixed UTC Run_Timestamp (seconds precision, +00:00 offset) matching the
# shape ``common.geo.utc_now`` emits, so the tests are deterministic regardless
# of wall-clock time.
FIXED_TS = "2026-03-14T09:30:15+00:00"
EXPECTED_STEM = "sprint1_shortlist_20260314"


def _shortlist_frame(n: int = 3) -> pd.DataFrame:
    """A minimal assembled shortlist with the documented columns in order."""
    return pd.DataFrame(
        {
            "rank": list(range(1, n + 1)),
            "cell_id": [f"C{i:04d}" for i in range(1, n + 1)],
            "suitability_score": [0.9 - 0.1 * i for i in range(n)],
            "confidence": (["high", "low"] * n)[:n],
            "centroid_lat": [-30.0 - 0.05 * i for i in range(n)],
            "centroid_lon": [151.0 + 0.05 * i for i in range(n)],
        },
        columns=list(config.SHORTLIST_COLUMNS),
    )


def _empty_frame() -> pd.DataFrame:
    """A zero-row shortlist carrying the documented columns (Requirement 3.6)."""
    return pd.DataFrame({c: [] for c in config.SHORTLIST_COLUMNS})


# ---------------------------------------------------------------------------
# Timestamped filenames (Requirements 7.1, 7.2, 7.3)
# ---------------------------------------------------------------------------


class TestResolveOutputPaths:
    def test_filenames_match_convention_with_region_slug(self, tmp_path):
        """
        Both outputs are ``sprint1_shortlist_<UTCdate>.{csv,geojson}``; the
        ``nsw`` region slug is carried by OUTPUT_PREFIX (7.1, 7.3).
        """
        resolved = resolve_output_paths(tmp_path, FIXED_TS)

        assert isinstance(resolved, ResolvedPaths)
        assert resolved.csv.name == f"{EXPECTED_STEM}.csv"
        assert resolved.geojson.name == f"{EXPECTED_STEM}.geojson"
        # The region slug lives in the shared prefix (7.3).
        assert config.REGION_SLUG == "nsw"
        assert resolved.csv.name.startswith(config.OUTPUT_PREFIX)
        assert resolved.geojson.name.startswith(config.OUTPUT_PREFIX)

    def test_same_timestamp_and_stem_in_both_filenames(self, tmp_path):
        """
        The single Run_Timestamp produces the SAME stem in both filenames (7.2).
        """
        resolved = resolve_output_paths(tmp_path, FIXED_TS)

        assert resolved.csv.stem == resolved.geojson.stem == EXPECTED_STEM
        # The UTC date component of the one timestamp appears in both names.
        assert "20260314" in resolved.csv.name
        assert "20260314" in resolved.geojson.name

    def test_no_collision_reports_date_precision(self, tmp_path):
        """With no pre-existing output the base date stem is used, no collision."""
        resolved = resolve_output_paths(tmp_path, FIXED_TS)

        assert resolved.collision.occurred is False
        assert resolved.collision.precision == "date"
        assert resolved.collision.base_stem == EXPECTED_STEM
        assert resolved.collision.resolved_stem == EXPECTED_STEM

    def test_run_timestamp_is_utc_seconds_precision(self):
        """run_timestamp() returns a single UTC ISO-8601 string (7.2)."""
        ts = run_timestamp()
        assert ts.endswith("+00:00")
        # Parsable and round-trips through resolve_output_paths without error.
        resolved = resolve_output_paths(Path("."), ts)
        assert resolved.csv.name.startswith(config.OUTPUT_PREFIX)


# ---------------------------------------------------------------------------
# Name-collision rule (Requirement 7.4)
# ---------------------------------------------------------------------------


class TestCollisionRule:
    def test_existing_base_stem_appends_finer_utc_component(self, tmp_path):
        """
        A pre-existing base-stem output forces a finer-grained UTC component and
        records the collision outcome (7.4).
        """
        # Seed a prior run's CSV under the base stem so the base collides.
        (tmp_path / f"{EXPECTED_STEM}.csv").write_text("prior run\n")

        resolved = resolve_output_paths(tmp_path, FIXED_TS)

        assert isinstance(resolved.collision, CollisionOutcome)
        assert resolved.collision.occurred is True
        assert resolved.collision.base_stem == EXPECTED_STEM
        # The resolved stem is finer-grained than the base and drives the names.
        assert resolved.collision.resolved_stem != EXPECTED_STEM
        assert resolved.collision.resolved_stem.startswith(EXPECTED_STEM + "T")
        assert resolved.collision.precision == "second"
        assert resolved.csv.stem == resolved.collision.resolved_stem
        assert resolved.geojson.stem == resolved.collision.resolved_stem
        # The prior file is untouched by name resolution.
        assert (tmp_path / f"{EXPECTED_STEM}.csv").read_text() == "prior run\n"

    def test_geojson_collision_also_bumps_stem(self, tmp_path):
        """A stem collides if EITHER extension exists, keeping CSV+GeoJSON paired."""
        (tmp_path / f"{EXPECTED_STEM}.geojson").write_text("{}\n")

        resolved = resolve_output_paths(tmp_path, FIXED_TS)

        assert resolved.collision.occurred is True
        assert resolved.csv.stem == resolved.geojson.stem
        assert resolved.csv.stem != EXPECTED_STEM

    def test_second_precise_collision_falls_back_to_microsecond(self, tmp_path):
        """When the second-precise stem also exists, microseconds are appended."""
        second_stem = f"{EXPECTED_STEM}T093015"
        (tmp_path / f"{EXPECTED_STEM}.csv").write_text("base\n")
        (tmp_path / f"{second_stem}.csv").write_text("second\n")

        resolved = resolve_output_paths(tmp_path, FIXED_TS)

        assert resolved.collision.occurred is True
        assert resolved.collision.precision == "microsecond"
        assert resolved.collision.resolved_stem.startswith(second_stem + "f")


# ---------------------------------------------------------------------------
# Empty shortlist still emits headered CSV + GeoJSON (Requirement 3.6)
# ---------------------------------------------------------------------------


class TestEmptyShortlistOutputs:
    def test_empty_csv_has_header_and_zero_data_rows(self, tmp_path):
        path = tmp_path / "empty.csv"
        write_csv(_empty_frame(), path)

        lines = path.read_text().splitlines()
        # Header row present, zero data rows (3.6).
        assert len(lines) == 1
        assert lines[0].split(",") == list(config.SHORTLIST_COLUMNS)

    def test_empty_geojson_is_wellformed_with_disclaimer_members(self, tmp_path):
        path = tmp_path / "empty.geojson"
        write_geojson(_empty_frame(), path)

        collection = json.loads(path.read_text())
        assert collection["type"] == "FeatureCollection"
        assert collection["features"] == []
        # CRS stated explicitly plus disclaimer + resolution members (3.6, 8.3).
        assert collection["crs_statement"] == config.STORAGE_CRS
        assert collection["preliminary_disclaimer"] == config.PRELIMINARY_DISCLAIMER
        assert collection["analysis_resolution"] == config.ANALYSIS_RESOLUTION


# ---------------------------------------------------------------------------
# Atomic write leaves prior output intact on forced failure (Requirement 5.7)
# ---------------------------------------------------------------------------


class TestAtomicityOnFailure:
    def test_csv_failure_leaves_prior_output_unmodified(self, tmp_path, monkeypatch):
        """
        A forced os.replace failure leaves any pre-existing CSV unmodified and
        propagates the error, with no tmp file left behind (5.7, 5.6).
        """
        path = tmp_path / f"{EXPECTED_STEM}.csv"
        path.write_text("PRIOR CONTENT\n")

        def boom(src, dst):
            raise OSError("forced replace failure")

        monkeypatch.setattr(common_geo.os, "replace", boom)

        with pytest.raises(OSError, match="forced replace failure"):
            write_csv(_shortlist_frame(), path)

        # Pre-existing output is intact; no half-written file surfaced (5.7).
        assert path.read_text() == "PRIOR CONTENT\n"
        assert list(tmp_path.glob("*.tmp")) == []

    def test_geojson_failure_leaves_prior_output_unmodified(self, tmp_path, monkeypatch):
        path = tmp_path / f"{EXPECTED_STEM}.geojson"
        path.write_text('{"prior": true}\n')

        def boom(src, dst):
            raise OSError("forced replace failure")

        monkeypatch.setattr(common_geo.os, "replace", boom)

        with pytest.raises(OSError, match="forced replace failure"):
            write_geojson(_shortlist_frame(), path)

        assert path.read_text() == '{"prior": true}\n'
        assert list(tmp_path.glob("*.tmp")) == []


# ---------------------------------------------------------------------------
# Documented geometry choice for the report (Requirement 5.4)
# ---------------------------------------------------------------------------


class TestGeometryChoice:
    def test_invalid_geometry_choice_rejected_before_write(self, tmp_path):
        """
        An unknown geometry choice raises before any file is written, naming the
        invalid choice (5.4).
        """
        path = tmp_path / "bad.geojson"
        with pytest.raises(ValueError, match="hexagon"):
            write_geojson(_shortlist_frame(), path, geometry="hexagon")
        # Nothing written on the fail-fast path.
        assert not path.exists()
        assert list(tmp_path.glob("*.tmp")) == []

    def test_centroid_choice_recorded_as_geometry_type(self, tmp_path):
        """The default centroid choice is stated as Point geometry_type (5.4)."""
        path = tmp_path / "centroid.geojson"
        write_geojson(_shortlist_frame(), path, geometry="centroid")

        collection = json.loads(path.read_text())
        assert collection["geometry_type"] == "centroid"
        assert collection["features"][0]["geometry"]["type"] == "Point"

    def test_polygon_choice_recorded_as_geometry_type(self, tmp_path):
        """The polygon choice is stated as Polygon geometry_type (5.4)."""
        path = tmp_path / "polygon.geojson"
        write_geojson(_shortlist_frame(), path, geometry="polygon")

        collection = json.loads(path.read_text())
        assert collection["geometry_type"] == "polygon"
        assert collection["features"][0]["geometry"]["type"] == "Polygon"

    def test_geometry_choices_are_the_documented_set(self):
        """The documented choices are exactly centroid + polygon (5.4)."""
        assert set(config.GEOMETRY_CHOICES) == {"centroid", "polygon"}
        assert config.DEFAULT_GEOMETRY == "centroid"
