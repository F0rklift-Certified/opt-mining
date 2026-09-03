"""
Unit tests for the S1-12 sanity-stage input resolver and loader
(``pipeline.sanity.load``), covering the resolver rule and every loader error
condition (Requirements 1.2, 1.3, 1.4, 1.5, 1.6, 2.2, 3.5).

``pipeline.sanity.load`` is the SOLE file-reading path for the sanity stage. It
must:

  - resolve the latest timestamped Shortlist under ``DATA/shortlist/`` by the
    documented UTC rule, and HALT (raise) before any output when the directory
    has no Shortlist                                                   (1.6, 1.4)
  - HALT before any write on a missing/unreadable input (naming the path),
    an absent required column (naming the column AND the input), and a source
    with no resolvable CRS (naming the source)               (1.4, 1.5, 2.2, 3.5)
  - reuse ``cell_id`` byte-for-byte and never re-score or re-rank    (1.2, 1.3)

Fixtures are synthetic GeoDataFrames written to a ``tmp_path`` GeoPackage /
GeoJSON, mirroring the loader-fault conventions in
``tests/shortlist/test_shortlist_loader.py`` and ``tests/test_scoring.py``. The
tests build a self-contained input set under ``tmp_path`` and drive
``load_inputs`` through a ``SanityInputs`` bundle so no real ``DATA/`` file is
read and no default output location is ever touched.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point, Polygon

from pipeline.sanity import config
from pipeline.sanity.load import (
    SanityInputs,
    _require_resolvable_crs,
    load_inputs,
    resolve_shortlist,
    split_eligible,
)


# ---------------------------------------------------------------------------
# Synthetic input builders
# ---------------------------------------------------------------------------


def _scored_frame() -> gpd.GeoDataFrame:
    """A small well-formed Scored_Table: a mix of eligible and excluded cells.

    Two eligible cells (non-null score AND rank) and one excluded cell (null
    score/rank) so :func:`split_eligible` has both populations to separate.
    ``cell_id`` values are strings that must survive the round-trip byte-for-byte.
    """
    return gpd.GeoDataFrame(
        {
            "cell_id": ["C000", "C001", "C002"],
            "suitability_score": [0.9, 0.4, None],
            "rank": [1.0, 2.0, None],
        },
        geometry=[Point(150 + i, -30) for i in range(3)],
        crs="EPSG:4326",
    )


def _integrated_frame() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "cell_id": ["C000", "C001", "C002"],
            "wind_speed": [8.0, 7.0, 6.0],
            "slope_deg": [2.0, 3.0, 4.0],
            "dist_transmission_km": [5.0, 10.0, 15.0],
            "protected": [False, False, True],
            "eligible": [True, True, False],
        },
        geometry=[Point(150 + i, -30) for i in range(3)],
        crs="EPSG:4326",
    )


def _grid_frame() -> gpd.GeoDataFrame:
    def _cell(i: int) -> Polygon:
        x, y = 150 + i, -30
        return Polygon([(x, y), (x + 0.05, y), (x + 0.05, y + 0.05), (x, y + 0.05)])

    return gpd.GeoDataFrame(
        {
            "cell_id": ["C000", "C001", "C002"],
            "centroid_lat": [-29.975, -29.975, -29.975],
            "centroid_lon": [150.025, 151.025, 152.025],
        },
        geometry=[_cell(i) for i in range(3)],
        crs="EPSG:4326",
    )


def _wind_generators_frame() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"name": ["Farm A", "Farm B"]},
        geometry=[Point(150.02, -29.98), Point(151.02, -29.98)],
        crs="EPSG:4326",
    )


def _shortlist_frame() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "cell_id": ["C000", "C001"],
            "rank": [1, 2],
            "suitability_score": [0.9, 0.4],
        },
        geometry=[Point(150.02, -29.98), Point(151.02, -29.98)],
        crs="EPSG:4326",
    )


def _write_gpkg(path, frame: gpd.GeoDataFrame, layer: str | None = None):
    if layer is not None:
        frame.to_file(path, driver="GPKG", layer=layer)
    else:
        frame.to_file(path, driver="GPKG")
    return path


def _write_geojson(path, frame: gpd.GeoDataFrame):
    frame.to_file(path, driver="GeoJSON")
    return path


def _make_inputs(tmp_path, *, shortlist_path) -> SanityInputs:
    """Write a complete, well-formed input set under ``tmp_path`` and bundle it.

    Each producer is written to the layer the loader reads it from. The Shortlist
    path is passed in so a test can point it at either a resolved file or a
    directory-resolved one.
    """
    scored = _write_gpkg(tmp_path / "scored.gpkg", _scored_frame(), config.SCORED_LAYER)
    integrated = _write_gpkg(
        tmp_path / "integrated.gpkg", _integrated_frame(), config.INTEGRATED_LAYER
    )
    grid = _write_gpkg(tmp_path / "grid.gpkg", _grid_frame(), config.GRID_LAYER)
    wind = _write_geojson(tmp_path / "wind.geojson", _wind_generators_frame())
    return SanityInputs(
        scored_path=scored,
        shortlist_path=shortlist_path,
        integrated_path=integrated,
        wind_generators_path=wind,
        grid_path=grid,
    )


# ---------------------------------------------------------------------------
# resolve_shortlist — latest-timestamp rule and halt-on-empty (1.6, 1.4)
# ---------------------------------------------------------------------------


class TestResolveShortlist:
    def _touch(self, directory, stem, ext=".geojson"):
        path = directory / f"{stem}{ext}"
        path.write_text("{}")
        return path

    def test_picks_most_recent_date(self, tmp_path):
        """Among several dated Shortlists the most recent UTC date wins."""
        prefix = config.SHORTLIST_OUTPUT_PREFIX
        self._touch(tmp_path, f"{prefix}_20260101")
        self._touch(tmp_path, f"{prefix}_20260615")
        latest = self._touch(tmp_path, f"{prefix}_20261231")
        assert resolve_shortlist(tmp_path) == latest

    def test_time_component_breaks_same_day(self, tmp_path):
        """A finer T<HHMMSS> component within the same day is ordered correctly."""
        prefix = config.SHORTLIST_OUTPUT_PREFIX
        self._touch(tmp_path, f"{prefix}_20260615T010000")
        latest = self._touch(tmp_path, f"{prefix}_20260615T235959")
        assert resolve_shortlist(tmp_path) == latest

    def test_geojson_preferred_over_csv_on_same_stem(self, tmp_path):
        """A CSV/GeoJSON pair sharing a stem resolves to the geometry-carrying GeoJSON."""
        prefix = config.SHORTLIST_OUTPUT_PREFIX
        stem = f"{prefix}_20260615"
        self._touch(tmp_path, stem, ext=".csv")
        geojson = self._touch(tmp_path, stem, ext=".geojson")
        assert resolve_shortlist(tmp_path) == geojson

    def test_csv_only_run_still_resolves(self, tmp_path):
        prefix = config.SHORTLIST_OUTPUT_PREFIX
        csv = self._touch(tmp_path, f"{prefix}_20260615", ext=".csv")
        assert resolve_shortlist(tmp_path) == csv

    def test_non_matching_files_are_ignored(self, tmp_path):
        """A stray file not matching the naming convention is not mis-ranked."""
        prefix = config.SHORTLIST_OUTPUT_PREFIX
        self._touch(tmp_path, "random_notes", ext=".geojson")
        self._touch(tmp_path, f"{prefix}_notadate", ext=".geojson")
        latest = self._touch(tmp_path, f"{prefix}_20260101")
        assert resolve_shortlist(tmp_path) == latest

    def test_missing_directory_raises_naming_the_path(self, tmp_path):
        absent = tmp_path / "no_such_dir"
        with pytest.raises(FileNotFoundError, match=str(absent)):
            resolve_shortlist(absent)

    def test_empty_directory_raises_before_any_output(self, tmp_path):
        """A directory with no matching Shortlist halts, referencing the convention."""
        empty = tmp_path / "shortlist"
        empty.mkdir()
        with pytest.raises(FileNotFoundError, match="No Shortlist file"):
            resolve_shortlist(empty)

    def test_directory_with_only_non_matching_files_raises(self, tmp_path):
        directory = tmp_path / "shortlist"
        directory.mkdir()
        self._touch(directory, "unrelated", ext=".geojson")
        with pytest.raises(FileNotFoundError, match="No Shortlist file"):
            resolve_shortlist(directory)


# ---------------------------------------------------------------------------
# load_inputs — missing / unreadable inputs (1.4)
# ---------------------------------------------------------------------------


class TestMissingOrUnreadableInput:
    def test_missing_scored_raises_naming_source_and_path(self, tmp_path):
        shortlist = _write_geojson(tmp_path / "sl.geojson", _shortlist_frame())
        inputs = _make_inputs(tmp_path, shortlist_path=shortlist)
        missing = tmp_path / "absent_scored.gpkg"
        inputs = SanityInputs(
            scored_path=missing,
            shortlist_path=inputs.shortlist_path,
            integrated_path=inputs.integrated_path,
            wind_generators_path=inputs.wind_generators_path,
            grid_path=inputs.grid_path,
        )
        with pytest.raises(FileNotFoundError, match="Scored_Table"):
            load_inputs(inputs)

    def test_missing_grid_raises_naming_source(self, tmp_path):
        shortlist = _write_geojson(tmp_path / "sl.geojson", _shortlist_frame())
        good = _make_inputs(tmp_path, shortlist_path=shortlist)
        inputs = SanityInputs(
            scored_path=good.scored_path,
            shortlist_path=good.shortlist_path,
            integrated_path=good.integrated_path,
            wind_generators_path=good.wind_generators_path,
            grid_path=tmp_path / "absent_grid.gpkg",
        )
        with pytest.raises(FileNotFoundError, match="Analysis_Grid"):
            load_inputs(inputs)

    def test_missing_shortlist_file_raises(self, tmp_path):
        good = _make_inputs(tmp_path, shortlist_path=tmp_path / "absent_sl.geojson")
        with pytest.raises(FileNotFoundError, match="Shortlist not found"):
            load_inputs(good)

    def test_unreadable_scored_raises_naming_the_path(self, tmp_path):
        """A file that exists but is not a valid GeoPackage halts, naming the path."""
        shortlist = _write_geojson(tmp_path / "sl.geojson", _shortlist_frame())
        good = _make_inputs(tmp_path, shortlist_path=shortlist)
        corrupt = tmp_path / "corrupt.gpkg"
        corrupt.write_bytes(b"this is not a geopackage")
        inputs = SanityInputs(
            scored_path=corrupt,
            shortlist_path=good.shortlist_path,
            integrated_path=good.integrated_path,
            wind_generators_path=good.wind_generators_path,
            grid_path=good.grid_path,
        )
        with pytest.raises(RuntimeError, match=str(corrupt)):
            load_inputs(inputs)


# ---------------------------------------------------------------------------
# load_inputs — absent required column (naming the column AND the input) (1.5)
# ---------------------------------------------------------------------------


class TestAbsentRequiredColumn:
    @pytest.mark.parametrize("column", ["suitability_score", "rank"])
    def test_absent_scored_column_names_column_and_input(self, tmp_path, column):
        shortlist = _write_geojson(tmp_path / "sl.geojson", _shortlist_frame())
        good = _make_inputs(tmp_path, shortlist_path=shortlist)
        # Overwrite the well-formed Scored_Table with one missing a column.
        bad = tmp_path / "scored_bad.gpkg"
        _write_gpkg(bad, _scored_frame().drop(columns=[column]), config.SCORED_LAYER)
        inputs = SanityInputs(
            scored_path=bad,
            shortlist_path=good.shortlist_path,
            integrated_path=good.integrated_path,
            wind_generators_path=good.wind_generators_path,
            grid_path=good.grid_path,
        )
        with pytest.raises(ValueError) as excinfo:
            load_inputs(inputs)
        message = str(excinfo.value)
        assert column in message  # names the column (1.5)
        assert "Scored_Table" in message  # names the input it was expected in (1.5)

    def test_absent_integrated_column_names_column_and_input(self, tmp_path):
        shortlist = _write_geojson(tmp_path / "sl.geojson", _shortlist_frame())
        good = _make_inputs(tmp_path, shortlist_path=shortlist)
        bad = tmp_path / "integrated_bad.gpkg"
        _write_gpkg(
            bad, _integrated_frame().drop(columns=["wind_speed"]), config.INTEGRATED_LAYER
        )
        inputs = SanityInputs(
            scored_path=good.scored_path,
            shortlist_path=good.shortlist_path,
            integrated_path=bad,
            wind_generators_path=good.wind_generators_path,
            grid_path=good.grid_path,
        )
        with pytest.raises(ValueError) as excinfo:
            load_inputs(inputs)
        message = str(excinfo.value)
        assert "wind_speed" in message
        assert "Integrated_Feature_Table" in message

    def test_absent_wind_generator_name_names_column_and_input(self, tmp_path):
        shortlist = _write_geojson(tmp_path / "sl.geojson", _shortlist_frame())
        good = _make_inputs(tmp_path, shortlist_path=shortlist)
        bad = tmp_path / "wind_bad.geojson"
        _write_geojson(bad, _wind_generators_frame().drop(columns=["name"]))
        inputs = SanityInputs(
            scored_path=good.scored_path,
            shortlist_path=good.shortlist_path,
            integrated_path=good.integrated_path,
            wind_generators_path=bad,
            grid_path=good.grid_path,
        )
        with pytest.raises(ValueError) as excinfo:
            load_inputs(inputs)
        message = str(excinfo.value)
        assert config.REQUIRED_WIND_GENERATOR_ATTR in message
        assert "Wind_Generators" in message


# ---------------------------------------------------------------------------
# Unresolvable CRS on a spatial source (2.2, 3.5)
# ---------------------------------------------------------------------------


class TestUnresolvableCrs:
    def test_helper_raises_when_crs_absent_naming_source(self, tmp_path):
        """``_require_resolvable_crs`` refuses a source with no declared CRS."""
        frame = _grid_frame()
        frame = frame.set_crs(None, allow_override=True)
        path = tmp_path / "nocrs_grid.gpkg"
        frame.to_file(path, driver="GPKG", layer=config.GRID_LAYER)
        with pytest.raises(ValueError, match="no resolvable CRS"):
            _require_resolvable_crs(path, config.GRID_LAYER, "Analysis_Grid")

    def test_helper_returns_normalised_crs_when_present(self, tmp_path):
        path = _write_gpkg(tmp_path / "grid.gpkg", _grid_frame(), config.GRID_LAYER)
        crs = _require_resolvable_crs(path, config.GRID_LAYER, "Analysis_Grid")
        assert crs == "EPSG:4326"

    def test_grid_without_crs_halts_load_before_write(self, tmp_path):
        """A grid with no resolvable CRS halts the loader, naming the source."""
        shortlist = _write_geojson(tmp_path / "sl.geojson", _shortlist_frame())
        good = _make_inputs(tmp_path, shortlist_path=shortlist)
        bad = tmp_path / "grid_nocrs.gpkg"
        _grid_frame().set_crs(None, allow_override=True).to_file(
            bad, driver="GPKG", layer=config.GRID_LAYER
        )
        inputs = SanityInputs(
            scored_path=good.scored_path,
            shortlist_path=good.shortlist_path,
            integrated_path=good.integrated_path,
            wind_generators_path=good.wind_generators_path,
            grid_path=bad,
        )
        with pytest.raises(ValueError) as excinfo:
            load_inputs(inputs)
        message = str(excinfo.value)
        assert "no resolvable CRS" in message
        assert "Analysis_Grid" in message

    def test_wind_generators_without_crs_halts_load(self, tmp_path):
        shortlist = _write_geojson(tmp_path / "sl.geojson", _shortlist_frame())
        good = _make_inputs(tmp_path, shortlist_path=shortlist)
        bad = tmp_path / "wind_nocrs.gpkg"
        _wind_generators_frame().set_crs(None, allow_override=True).to_file(
            bad, driver="GPKG"
        )
        inputs = SanityInputs(
            scored_path=good.scored_path,
            shortlist_path=good.shortlist_path,
            integrated_path=good.integrated_path,
            wind_generators_path=bad,
            grid_path=good.grid_path,
        )
        with pytest.raises(ValueError) as excinfo:
            load_inputs(inputs)
        assert "no resolvable CRS" in str(excinfo.value)
        assert "Wind_Generators" in str(excinfo.value)


# ---------------------------------------------------------------------------
# cell_id byte-for-byte and no re-score / re-rank (1.2, 1.3)
# ---------------------------------------------------------------------------


class TestReadOnlyReuse:
    def test_cell_id_unchanged_byte_for_byte(self, tmp_path):
        """Loaded ``cell_id`` values match the source exactly, never re-derived."""
        shortlist = _write_geojson(tmp_path / "sl.geojson", _shortlist_frame())
        inputs = _make_inputs(tmp_path, shortlist_path=shortlist)
        loaded = load_inputs(inputs)
        expected = list(_scored_frame()["cell_id"])
        assert list(loaded.scored["cell_id"]) == expected
        # Grid / integrated cell_id sets are carried through identically too.
        assert list(loaded.grid["cell_id"]) == list(_grid_frame()["cell_id"])
        assert list(loaded.integrated["cell_id"]) == list(_integrated_frame()["cell_id"])

    def test_scores_and_ranks_are_reused_not_recomputed(self, tmp_path):
        """``suitability_score`` and ``rank`` are carried through exactly as written."""
        shortlist = _write_geojson(tmp_path / "sl.geojson", _shortlist_frame())
        inputs = _make_inputs(tmp_path, shortlist_path=shortlist)
        loaded = load_inputs(inputs)
        source = _scored_frame()
        pd.testing.assert_series_equal(
            loaded.scored["suitability_score"].reset_index(drop=True),
            source["suitability_score"].reset_index(drop=True),
            check_names=False,
        )
        pd.testing.assert_series_equal(
            loaded.scored["rank"].reset_index(drop=True),
            source["rank"].reset_index(drop=True),
            check_names=False,
        )

    def test_eligible_excluded_split_preserves_values(self, tmp_path):
        """The eligible/excluded split reuses score/rank unchanged (1.2, 1.3)."""
        scored = _scored_frame()
        eligible, excluded = split_eligible(scored)
        # Two eligible (non-null score AND rank), one excluded (null both).
        assert list(eligible["cell_id"]) == ["C000", "C001"]
        assert list(excluded["cell_id"]) == ["C002"]
        # Values are unchanged, not renumbered or recomputed.
        assert list(eligible["rank"]) == [1.0, 2.0]
        assert list(eligible["suitability_score"]) == [0.9, 0.4]

    def test_input_files_not_mutated_by_load(self, tmp_path):
        """Reading the inputs leaves the files byte-identical (read-only, 8.1)."""
        import hashlib

        shortlist = _write_geojson(tmp_path / "sl.geojson", _shortlist_frame())
        inputs = _make_inputs(tmp_path, shortlist_path=shortlist)
        paths = [
            inputs.scored_path,
            inputs.integrated_path,
            inputs.grid_path,
            inputs.wind_generators_path,
            shortlist,
        ]
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        load_inputs(inputs)
        after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        assert before == after
