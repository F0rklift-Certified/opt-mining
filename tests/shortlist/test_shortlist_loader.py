"""
Unit tests for the S1-11 Scored_Table loader error conditions (Requirement
1.4, 1.5).

`pipeline.shortlist.load.load_scored_table` is the SOLE file-reading path for
score data in the shortlist stage. It must halt BEFORE the stage writes
anything, naming the fault, on:

  - a missing file            -> FileNotFoundError, naming the path   (1.4)
  - an unreadable file        -> RuntimeError, naming the path        (1.4)
  - any absent required column -> ValueError, naming the column       (1.5)
    (cell_id / suitability_score / rank / confidence)

Fixtures are synthetic geopandas GeoDataFrames written to a `tmp_path`
GeoPackage, mirroring the loader-fault conventions in
`tests/test_scoring.py::TestLoaderFaults`.
"""

from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import Point

from pipeline.shortlist import config
from pipeline.shortlist.load import REQUIRED_SCORE_COLUMNS, load_scored_table


# ---------------------------------------------------------------------------
# Synthetic Scored_Table fixtures
# ---------------------------------------------------------------------------


def _scored_frame(drop: tuple[str, ...] = ()) -> gpd.GeoDataFrame:
    """A small, well-formed synthetic Scored_Table, optionally dropping columns.

    Carries the full REQUIRED_SCORE_COLUMNS set plus geometry in EPSG:4326.
    """
    n = 3
    data = {
        "cell_id": [f"C{i:03d}" for i in range(n)],
        "suitability_score": [0.9, 0.5, 0.1],
        "rank": [1, 2, 3],
        "confidence": ["high", "low", "high"],
    }
    for column in drop:
        data.pop(column, None)
    frame = gpd.GeoDataFrame(
        data,
        geometry=[Point(150 + i, -30) for i in range(n)],
        crs="EPSG:4326",
    )
    return frame


def _write_gpkg(tmp_path, frame: gpd.GeoDataFrame, name: str = "scored.gpkg"):
    path = tmp_path / name
    frame.to_file(path, driver="GPKG", layer=config.SCORED_LAYER)
    return path


def _no_output_written(tmp_path) -> bool:
    """The shortlist stage's default output locations must be untouched.

    A loader fault must halt before any write; nothing should appear under the
    shortlist output dir as a side effect of the fixtures under tmp_path.
    """
    return not (tmp_path / config.SHORTLIST_DIR.name).exists()


# ---------------------------------------------------------------------------
# Missing / unreadable file (Requirement 1.4)
# ---------------------------------------------------------------------------


class TestMissingOrUnreadableFile:
    def test_missing_file_raises_naming_the_path(self, tmp_path):
        """A missing Scored_Table halts with FileNotFoundError naming the path."""
        absent = tmp_path / "absent.gpkg"
        with pytest.raises(FileNotFoundError, match=str(absent)):
            load_scored_table(absent)
        # No output was written before the halt.
        assert _no_output_written(tmp_path)

    def test_missing_file_error_says_not_found(self, tmp_path):
        absent = tmp_path / "absent.gpkg"
        with pytest.raises(FileNotFoundError, match="not found"):
            load_scored_table(absent)

    def test_unreadable_file_raises_runtimeerror_naming_the_path(self, tmp_path):
        """A file that exists but is not a valid GeoPackage halts, naming the path.

        The loader wraps any read failure in a RuntimeError that names the path
        (1.4) rather than propagating the raw driver error.
        """
        garbage = tmp_path / "corrupt.gpkg"
        garbage.write_bytes(b"this is not a geopackage")
        with pytest.raises(RuntimeError, match=str(garbage)):
            load_scored_table(garbage)
        assert _no_output_written(tmp_path)


# ---------------------------------------------------------------------------
# Absent required columns (Requirement 1.5)
# ---------------------------------------------------------------------------


class TestAbsentRequiredColumn:
    @pytest.mark.parametrize("column", REQUIRED_SCORE_COLUMNS)
    def test_absent_required_column_raises_naming_the_column(self, tmp_path, column):
        """Each absent required column halts with a ValueError naming that column."""
        path = _write_gpkg(tmp_path, _scored_frame(drop=(column,)))
        with pytest.raises(ValueError, match=column):
            load_scored_table(path)
        # The halt happens before any output is written.
        assert _no_output_written(tmp_path)

    def test_absent_cell_id_raises(self, tmp_path):
        path = _write_gpkg(tmp_path, _scored_frame(drop=("cell_id",)))
        with pytest.raises(ValueError, match="cell_id"):
            load_scored_table(path)

    def test_absent_suitability_score_raises(self, tmp_path):
        path = _write_gpkg(tmp_path, _scored_frame(drop=("suitability_score",)))
        with pytest.raises(ValueError, match="suitability_score"):
            load_scored_table(path)

    def test_absent_rank_raises(self, tmp_path):
        path = _write_gpkg(tmp_path, _scored_frame(drop=("rank",)))
        with pytest.raises(ValueError, match="rank"):
            load_scored_table(path)

    def test_absent_confidence_raises(self, tmp_path):
        path = _write_gpkg(tmp_path, _scored_frame(drop=("confidence",)))
        with pytest.raises(ValueError, match="confidence"):
            load_scored_table(path)


# ---------------------------------------------------------------------------
# Sanity: a well-formed table loads (guards against over-strict fixtures)
# ---------------------------------------------------------------------------


class TestWellFormedTableLoads:
    def test_complete_table_loads_and_carries_required_columns(self, tmp_path):
        path = _write_gpkg(tmp_path, _scored_frame())
        table = load_scored_table(path)
        for column in REQUIRED_SCORE_COLUMNS:
            assert column in table.columns
        assert len(table) == 3
