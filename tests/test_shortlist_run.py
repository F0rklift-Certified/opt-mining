"""
Property + unit tests for the S1-11 shortlist `run()` contract (task 11.2).

`pipeline.shortlist.run.run` is the stage entry point that wires the whole
stage together. These tests exercise the WHOLE-RUN invariants, over synthetic
GeoPackage inputs written under ``tmp_path``, with the stage's output
directories (``config.SHORTLIST_DIR`` / ``config.SHORTLIST_META_DIR``)
monkeypatched to ``tmp_path`` subdirs so no real ``DATA/`` is ever written:

  * the run() contract — first param ``verbose`` defaults to ``False``, it
    returns a dict carrying ``effective_top_n`` / ``n_eligible`` /
    ``n_shortlisted`` and the output paths, and the three output files exist on
    disk after a successful run (Requirements 10.1, 10.2).
  * Property 4 -> 3.5 — an invalid Top_N (0, negative, non-integer) halts run()
    BEFORE any output exists on disk.
  * Property 9 -> 5.5 — after a full run the CSV and GeoJSON ``cell_id``
    sequences match element-for-element.
  * Property 14 -> 8.5 — no emitted output omits BOTH the disclaimer and the
    resolution statement (the GeoJSON carries them in-band; the summary report
    and sidecar carry them for the CSV).
  * fatal conditions — a missing/unreadable Scored_Table or grid, and an
    unmatched shortlisted ``cell_id``, each halt run() with a clear error and
    leave no CSV/GeoJSON output in the (monkeypatched) output dir (Requirements
    1.4, 4.5, 10.3).

Fixture conventions follow ``tests/test_shortlist_loader.py`` and
``tests/test_shortlist_writers.py`` (synthetic geopandas frames written to a
GeoPackage with ``config.SCORED_LAYER`` / ``config.GRID_LAYER`` layer names);
the output-dir redirection follows the run()-level fail-before-write tests in
``tests/test_scoring.py::TestRunContract``.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import geopandas as gpd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from shapely.geometry import Point

from pipeline.shortlist import config
from pipeline.shortlist.run import run

# ---------------------------------------------------------------------------
# Synthetic input builders
# ---------------------------------------------------------------------------


def _scored_frame(n: int = 5) -> gpd.GeoDataFrame:
    """A small, well-formed synthetic Scored_Table (Point geometry, EPSG:4326).

    Carries the REQUIRED_SCORE_COLUMNS (cell_id, suitability_score, rank,
    confidence). Ranks are ascending 1..n; scores decrease with rank.
    """
    return gpd.GeoDataFrame(
        {
            "cell_id": [f"C{i:04d}" for i in range(1, n + 1)],
            "suitability_score": [round(0.95 - 0.1 * i, 4) for i in range(n)],
            "rank": list(range(1, n + 1)),
            "confidence": (["high", "low"] * n)[:n],
        },
        geometry=[Point(150.0 + 0.05 * i, -30.0 - 0.05 * i) for i in range(n)],
        crs="EPSG:4326",
    )


def _grid_frame(cell_ids) -> gpd.GeoDataFrame:
    """A matching Analysis_Grid with centroid_lat/centroid_lon per cell_id.

    Point geometry in EPSG:4326, one row per requested ``cell_id``. Coordinates
    are deterministic per index so the join is verifiable.
    """
    cell_ids = list(cell_ids)
    lats = [-30.0 - 0.05 * i for i in range(len(cell_ids))]
    lons = [150.0 + 0.05 * i for i in range(len(cell_ids))]
    return gpd.GeoDataFrame(
        {
            "cell_id": cell_ids,
            "centroid_lat": lats,
            "centroid_lon": lons,
        },
        geometry=[Point(lon, lat) for lon, lat in zip(lons, lats)],
        crs="EPSG:4326",
    )


def _write_scored(tmp_path: Path, frame: gpd.GeoDataFrame, name: str = "scored.gpkg") -> Path:
    path = tmp_path / name
    frame.to_file(path, driver="GPKG", layer=config.SCORED_LAYER)
    return path


def _write_grid(tmp_path: Path, frame: gpd.GeoDataFrame, name: str = "grid.gpkg") -> Path:
    path = tmp_path / name
    frame.to_file(path, driver="GPKG", layer=config.GRID_LAYER)
    return path


def _redirect_output_dirs(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """Point the stage's output dirs at tmp_path subdirs (no real DATA/ write).

    Returns (out_dir, meta_dir). The dirs are NOT pre-created here so the
    fail-before-write assertions can check that a fatal run leaves the output
    dir absent (or at least free of CSV/GeoJSON).
    """
    out_dir = tmp_path / "out"
    meta_dir = out_dir / "metadata"
    monkeypatch.setattr(config, "SHORTLIST_DIR", out_dir)
    monkeypatch.setattr(config, "SHORTLIST_META_DIR", meta_dir)
    return out_dir, meta_dir


def _synthetic_inputs(tmp_path: Path, n: int = 5) -> tuple[Path, Path]:
    """A matched Scored_Table + Analysis_Grid pair sharing the same cell_id set."""
    scored = _scored_frame(n)
    scored_path = _write_scored(tmp_path, scored)
    grid_path = _write_grid(tmp_path, _grid_frame(scored["cell_id"]))
    return scored_path, grid_path


def _output_files(out_dir: Path) -> list[Path]:
    """Any CSV/GeoJSON headline outputs present under the output dir."""
    if not out_dir.exists():
        return []
    return sorted(out_dir.glob("*.csv")) + sorted(out_dir.glob("*.geojson"))


# ---------------------------------------------------------------------------
# run() contract: signature, return dict, outputs on disk (10.1, 10.2)
# ---------------------------------------------------------------------------


class TestRunContract:
    def test_verbose_is_first_param_defaulting_to_false(self):
        """The registered-stage contract: first param ``verbose`` defaults to False (10.1)."""
        sig = inspect.signature(run)
        params = list(sig.parameters.values())
        assert params[0].name == "verbose"
        assert params[0].default is False

    def test_successful_run_returns_dict_with_counts_and_paths(self, tmp_path, monkeypatch):
        """
        A successful run returns a dict carrying the effective Top_N, the
        eligible / shortlisted counts, and the output paths (10.1, 10.2).
        """
        out_dir, _ = _redirect_output_dirs(tmp_path, monkeypatch)
        scored_path, grid_path = _synthetic_inputs(tmp_path, n=5)

        result = run(top_n=3, scored_path=scored_path, grid_path=grid_path)

        assert isinstance(result, dict)
        assert result["effective_top_n"] == 3
        assert result["n_eligible"] == 5
        assert result["n_shortlisted"] == 3
        for key in (
            "shortlist_csv_path",
            "shortlist_geojson_path",
            "summary_report_path",
        ):
            assert key in result and result[key]

    def test_three_outputs_exist_on_disk_after_success(self, tmp_path, monkeypatch):
        """The CSV, GeoJSON, and Summary_Report all exist on disk after return (10.2)."""
        _redirect_output_dirs(tmp_path, monkeypatch)
        scored_path, grid_path = _synthetic_inputs(tmp_path, n=5)

        result = run(top_n=3, scored_path=scored_path, grid_path=grid_path)

        assert Path(result["shortlist_csv_path"]).exists()
        assert Path(result["shortlist_geojson_path"]).exists()
        assert Path(result["summary_report_path"]).exists()

    def test_no_real_data_dir_is_written(self, tmp_path, monkeypatch):
        """Every output path lands under the monkeypatched tmp output dir."""
        out_dir, _ = _redirect_output_dirs(tmp_path, monkeypatch)
        scored_path, grid_path = _synthetic_inputs(tmp_path, n=5)

        result = run(top_n=3, scored_path=scored_path, grid_path=grid_path)

        assert str(out_dir) in result["shortlist_csv_path"]
        assert str(out_dir) in result["shortlist_geojson_path"]


# ---------------------------------------------------------------------------
# Property 4 -> 3.5: invalid Top_N halts before any output
# ---------------------------------------------------------------------------


class TestInvalidTopNHaltsBeforeWrite:
    # Feature: s1-11-generate-ranked-shortlist, Property 4: Invalid Top_N is
    # rejected before any write (non-positive-integer Top_N halts before writing
    # any output and returns an error identifying the invalid value, leaving no
    # partial output on disk).
    # Validates: Requirements 3.5
    @settings(max_examples=150, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        bad_top_n=st.one_of(
            st.integers(max_value=0),  # zero and negatives
            st.floats(allow_nan=False, allow_infinity=False),  # non-integers
            st.text(max_size=4),  # non-integer type
            st.booleans(),  # bool is an int subclass but not a valid count
        )
    )
    def test_invalid_top_n_raises_before_any_output(self, tmp_path, monkeypatch, bad_top_n):
        out_dir, _ = _redirect_output_dirs(tmp_path, monkeypatch)
        scored_path, grid_path = _synthetic_inputs(tmp_path, n=5)

        with pytest.raises(ValueError):
            run(top_n=bad_top_n, scored_path=scored_path, grid_path=grid_path)

        # The Top_N check runs first, before the output dir is even created, so
        # no CSV/GeoJSON output exists on disk (3.5).
        assert _output_files(out_dir) == []


# ---------------------------------------------------------------------------
# Property 9 -> 5.5: CSV and GeoJSON carry the same cell_id sequence
# ---------------------------------------------------------------------------


def _csv_cell_ids(csv_path: Path) -> list[str]:
    """The ordered cell_id column from a Shortlist_CSV."""
    lines = csv_path.read_text().splitlines()
    header = lines[0].split(",")
    idx = header.index("cell_id")
    return [line.split(",")[idx] for line in lines[1:]]


def _geojson_cell_ids(geojson_path: Path) -> list[str]:
    """The ordered cell_id feature-property sequence from a Shortlist_GeoJSON."""
    collection = json.loads(geojson_path.read_text())
    return [str(f["properties"]["cell_id"]) for f in collection["features"]]


class TestCsvGeojsonCellIdMatch:
    # Feature: s1-11-generate-ranked-shortlist, Property 9: CSV and GeoJSON carry
    # the same cell_id set in the same order (the ordered cell_id sequence in the
    # CSV equals, element-for-element, the ordered cell_id sequence in the
    # GeoJSON).
    # Validates: Requirements 5.5, 12.5
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
    )
    @given(n=st.integers(min_value=1, max_value=8), top_n=st.integers(min_value=1, max_value=12))
    def test_full_run_csv_geojson_cell_id_sequences_match(
        self, tmp_path, monkeypatch, n, top_n
    ):
        _redirect_output_dirs(tmp_path, monkeypatch)
        scored_path, grid_path = _synthetic_inputs(tmp_path, n=n)

        result = run(top_n=top_n, scored_path=scored_path, grid_path=grid_path)

        csv_ids = _csv_cell_ids(Path(result["shortlist_csv_path"]))
        geojson_ids = _geojson_cell_ids(Path(result["shortlist_geojson_path"]))
        # Element-for-element equality of the ordered cell_id sequences (5.5).
        assert csv_ids == geojson_ids
        # And the row count never exceeds the effective Top_N (sanity on sizing).
        assert len(csv_ids) == min(top_n, n)


# ---------------------------------------------------------------------------
# Property 14 -> 8.5: no output omits BOTH disclaimer and resolution
# ---------------------------------------------------------------------------


class TestDisclaimerAndResolutionCarried:
    # Feature: s1-11-generate-ranked-shortlist, Property 14: Every output carries
    # the disclaimer and resolution statement (no output omits both; GeoJSON
    # carries them in file-level metadata/properties; the CSV's disclaimer
    # travels via the Summary_Report and metadata sidecar).
    # Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 12.6
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
    )
    @given(n=st.integers(min_value=1, max_value=8), top_n=st.integers(min_value=1, max_value=12))
    def test_no_output_omits_both_disclaimer_and_resolution(
        self, tmp_path, monkeypatch, n, top_n
    ):
        _redirect_output_dirs(tmp_path, monkeypatch)
        scored_path, grid_path = _synthetic_inputs(tmp_path, n=n)

        result = run(top_n=top_n, scored_path=scored_path, grid_path=grid_path)

        # GeoJSON carries both in-band (8.3).
        collection = json.loads(Path(result["shortlist_geojson_path"]).read_text())
        assert collection["preliminary_disclaimer"] == config.PRELIMINARY_DISCLAIMER
        assert collection["analysis_resolution"] == config.ANALYSIS_RESOLUTION

        # The CSV's disclaimer + resolution travel via the Summary_Report (8.4).
        report = Path(result["summary_report_path"]).read_text()
        assert config.PRELIMINARY_DISCLAIMER in report
        assert config.ANALYSIS_RESOLUTION in report

        # ...and via the metadata sidecar (8.4).
        sidecar = json.loads(Path(result["metadata_sidecar_path"]).read_text())
        sidecar_text = json.dumps(sidecar)
        assert config.PRELIMINARY_DISCLAIMER in sidecar_text
        assert config.ANALYSIS_RESOLUTION in sidecar_text

        # Whole-run invariant: NO emitted output omits BOTH (8.5). The CSV alone
        # need not carry them, but the run collectively always does.
        assert config.PRELIMINARY_DISCLAIMER in report
        assert config.ANALYSIS_RESOLUTION in report


# ---------------------------------------------------------------------------
# Fatal conditions halt run() with no partial output (1.4, 4.5, 10.3)
# ---------------------------------------------------------------------------


class TestFatalConditionsLeaveNoOutput:
    def test_missing_scored_table_raises_and_writes_nothing(self, tmp_path, monkeypatch):
        """A nonexistent Scored_Table halts run(), naming the path, no output (1.4, 10.3)."""
        out_dir, _ = _redirect_output_dirs(tmp_path, monkeypatch)
        # A valid grid, but a missing Scored_Table.
        grid_path = _write_grid(tmp_path, _grid_frame([f"C{i:04d}" for i in range(1, 6)]))
        absent = tmp_path / "absent_scored.gpkg"

        with pytest.raises(FileNotFoundError, match=str(absent)):
            run(top_n=3, scored_path=absent, grid_path=grid_path)

        assert _output_files(out_dir) == []

    def test_unreadable_scored_table_raises_and_writes_nothing(self, tmp_path, monkeypatch):
        """An unreadable Scored_Table halts run() with no output (1.4, 10.3)."""
        out_dir, _ = _redirect_output_dirs(tmp_path, monkeypatch)
        grid_path = _write_grid(tmp_path, _grid_frame([f"C{i:04d}" for i in range(1, 6)]))
        garbage = tmp_path / "corrupt_scored.gpkg"
        garbage.write_bytes(b"this is not a geopackage")

        with pytest.raises(RuntimeError, match=str(garbage)):
            run(top_n=3, scored_path=garbage, grid_path=grid_path)

        assert _output_files(out_dir) == []

    def test_missing_grid_raises_and_writes_nothing(self, tmp_path, monkeypatch):
        """A missing Analysis_Grid halts run() with no output (10.3)."""
        out_dir, _ = _redirect_output_dirs(tmp_path, monkeypatch)
        scored_path = _write_scored(tmp_path, _scored_frame(5))
        absent_grid = tmp_path / "absent_grid.gpkg"

        with pytest.raises(FileNotFoundError, match=str(absent_grid)):
            run(top_n=3, scored_path=scored_path, grid_path=absent_grid)

        assert _output_files(out_dir) == []

    def test_unmatched_cell_id_raises_and_writes_nothing(self, tmp_path, monkeypatch):
        """
        A grid missing a shortlisted cell_id halts run() (unmatched -> ValueError)
        with no fabricated coordinate and no CSV/GeoJSON output (4.5, 10.3).
        """
        out_dir, _ = _redirect_output_dirs(tmp_path, monkeypatch)
        scored = _scored_frame(5)
        scored_path = _write_scored(tmp_path, scored)
        # Grid covers only a subset of the scored cell_ids, so the top-ranked
        # cells that WILL be shortlisted have no matching grid row.
        partial_ids = list(scored["cell_id"])[3:]  # drop the top 3 ranked cells
        grid_path = _write_grid(tmp_path, _grid_frame(partial_ids))

        with pytest.raises(ValueError, match="Analysis_Grid"):
            run(top_n=3, scored_path=scored_path, grid_path=grid_path)

        assert _output_files(out_dir) == []
