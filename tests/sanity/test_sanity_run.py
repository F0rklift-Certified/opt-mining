"""
Property + unit tests for the S1-12 sanity-stage ``run()`` contract (task 12.2).

``pipeline.sanity.run.run`` is the terminal stage's entry point: it validates
the requested Spot_Check_Cells count, resolves + loads the five Sprint 1 inputs
READ-ONLY, runs the four plausibility checks, and writes the Validation_Report
(plus, optionally, the Results_Sidecar) and its derived-product provenance.

These tests exercise the WHOLE-RUN invariants over a full synthetic input set
written under ``tmp_path`` — a Scored_Table, an Integrated_Feature_Table, an
Analysis_Grid, a Wind_Generators GeoJSON, and a shortlist directory holding one
timestamped ``sprint1_shortlist_<UTCdate>.geojson`` file — passed to ``run()``
via its ``scored_path`` / ``integrated_path`` / ``grid_path`` /
``wind_generators_path`` / ``shortlist_dir`` overrides.

``run()`` writes the report to ``config.REPORT_PATH``, the sidecar to
``config.SIDECAR_PATH`` and provenance under ``config.SANITY_DIR`` — FIXED
absolute paths, not parameters. ``run.py`` (and ``report.py``) read those as
``config.<ATTR>`` at call time via the ``config`` module, so a fixture
monkeypatches those module attributes to point under ``tmp_path`` and no real
``outputs/`` or ``DATA/sanity/`` is ever touched. This mirrors the output-dir
redirection pattern in ``tests/shortlist/test_shortlist_run.py`` and
``tests/scoring/test_scoring.py``.

Covers:
  * Property 10 — inputs are read-only and the model is never adjusted (SHA-256
    of all five inputs unchanged pre/post run).                Validates 1.3, 8.x
  * Property 14 — regeneration is deterministic (two runs -> identical
    structured results).                                       Validates 12.3
  * Property 15 — a successful run returns an existing report path (and any
    sidecar path) on disk.                                     Validates 9.2
  * Property 6 — an invalid Spot_Check_Cells count halts before any write,
    naming the count, leaving no partial output.               Validates 4.5
  * Unit — signature introspection; a forced fatal condition raises + returns no
    dict + writes no output; ``wind_generators_path`` / ``spot_cells`` overrides
    take effect.                                               Validates 9.1, 9.3, 12.4
"""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

import geopandas as gpd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from shapely.geometry import Point, Polygon

from pipeline.sanity import config
from pipeline.sanity.run import run

# ---------------------------------------------------------------------------
# Synthetic full input set
# ---------------------------------------------------------------------------
#
# A small NSW-ish grid of `N_CELLS` square cells laid out in a row, each 0.05
# degrees wide (the analysis-cell size). Wind-farm points and landmark cells are
# placed inside these cells so the containment join has real work to do.

_N_CELLS = 12
_CELL_DEG = 0.05
_ORIGIN_LAT = -33.0
_ORIGIN_LON = 150.0


def _cell_id(i: int) -> str:
    return f"C{i:04d}"


def _cell_polygon(i: int) -> Polygon:
    x = _ORIGIN_LON + i * _CELL_DEG
    y = _ORIGIN_LAT
    return Polygon(
        [(x, y), (x + _CELL_DEG, y), (x + _CELL_DEG, y + _CELL_DEG), (x, y + _CELL_DEG)]
    )


def _cell_centroid(i: int) -> tuple[float, float]:
    lon = _ORIGIN_LON + i * _CELL_DEG + _CELL_DEG / 2
    lat = _ORIGIN_LAT + _CELL_DEG / 2
    return lat, lon


def _scored_frame() -> gpd.GeoDataFrame:
    """Scored_Table: every cell eligible (non-null score AND rank), with a
    monotonic score spread so the distribution / spot-cell span is well-defined.
    """
    scores = [round(0.05 + 0.9 * i / (_N_CELLS - 1), 4) for i in range(_N_CELLS)]
    # Rank 1 = highest score.
    order = sorted(range(_N_CELLS), key=lambda i: -scores[i])
    rank = [0] * _N_CELLS
    for r, i in enumerate(order, start=1):
        rank[i] = r
    return gpd.GeoDataFrame(
        {
            "cell_id": [_cell_id(i) for i in range(_N_CELLS)],
            "suitability_score": scores,
            "rank": [float(r) for r in rank],
        },
        geometry=[_cell_polygon(i) for i in range(_N_CELLS)],
        crs="EPSG:4326",
    )


def _integrated_frame() -> gpd.GeoDataFrame:
    """Integrated_Feature_Table: wind_speed rises with cell index (positive
    correlation with score), plus the other required feature columns."""
    return gpd.GeoDataFrame(
        {
            "cell_id": [_cell_id(i) for i in range(_N_CELLS)],
            "wind_speed": [6.0 + 0.2 * i for i in range(_N_CELLS)],
            "slope_deg": [2.0 + 0.1 * i for i in range(_N_CELLS)],
            "dist_transmission_km": [5.0 + i for i in range(_N_CELLS)],
            "protected": [False] * _N_CELLS,
            "eligible": [True] * _N_CELLS,
        },
        geometry=[_cell_polygon(i) for i in range(_N_CELLS)],
        crs="EPSG:4326",
    )


def _grid_frame() -> gpd.GeoDataFrame:
    lats_lons = [_cell_centroid(i) for i in range(_N_CELLS)]
    return gpd.GeoDataFrame(
        {
            "cell_id": [_cell_id(i) for i in range(_N_CELLS)],
            "centroid_lat": [ll[0] for ll in lats_lons],
            "centroid_lon": [ll[1] for ll in lats_lons],
        },
        geometry=[_cell_polygon(i) for i in range(_N_CELLS)],
        crs="EPSG:4326",
    )


def _wind_generators_frame() -> gpd.GeoDataFrame:
    """Two wind-farm points placed at the centroids of two grid cells so each
    locates cleanly to a Containing_Cell."""
    c0 = _cell_centroid(2)
    c1 = _cell_centroid(9)
    return gpd.GeoDataFrame(
        {"name": ["Farm North", "Farm South"]},
        geometry=[Point(c0[1], c0[0]), Point(c1[1], c1[0])],
        crs="EPSG:4326",
    )


def _shortlist_frame() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "cell_id": [_cell_id(i) for i in range(3)],
            "rank": [1, 2, 3],
            "suitability_score": [0.95, 0.9, 0.85],
        },
        geometry=[Point(*reversed(_cell_centroid(i))) for i in range(3)],
        crs="EPSG:4326",
    )


def _write_gpkg(path: Path, frame: gpd.GeoDataFrame, layer: str | None = None) -> Path:
    if layer is not None:
        frame.to_file(path, driver="GPKG", layer=layer)
    else:
        frame.to_file(path, driver="GPKG")
    return path


def _write_geojson(path: Path, frame: gpd.GeoDataFrame) -> Path:
    frame.to_file(path, driver="GeoJSON")
    return path


class _Inputs:
    """A bundle of the five on-disk input paths for a run."""

    def __init__(self, scored, integrated, grid, wind, shortlist_dir):
        self.scored_path = scored
        self.integrated_path = integrated
        self.grid_path = grid
        self.wind_generators_path = wind
        self.shortlist_dir = shortlist_dir

    def all_input_paths(self, resolved_shortlist: Path) -> list[Path]:
        return [
            self.scored_path,
            self.integrated_path,
            self.grid_path,
            self.wind_generators_path,
            resolved_shortlist,
        ]

    def run_kwargs(self) -> dict:
        return dict(
            scored_path=self.scored_path,
            integrated_path=self.integrated_path,
            grid_path=self.grid_path,
            wind_generators_path=self.wind_generators_path,
            shortlist_dir=self.shortlist_dir,
        )


@pytest.fixture
def inputs(tmp_path) -> _Inputs:
    """Write a complete, well-formed synthetic input set under ``tmp_path``.

    The shortlist lives in its own directory under a single timestamped
    ``sprint1_shortlist_<UTCdate>.geojson`` file so ``resolve_shortlist`` picks
    it deterministically.
    """
    in_dir = tmp_path / "inputs"
    in_dir.mkdir()
    shortlist_dir = in_dir / "shortlist"
    shortlist_dir.mkdir()

    scored = _write_gpkg(in_dir / "scored.gpkg", _scored_frame(), config.SCORED_LAYER)
    integrated = _write_gpkg(
        in_dir / "integrated.gpkg", _integrated_frame(), config.INTEGRATED_LAYER
    )
    grid = _write_gpkg(in_dir / "grid.gpkg", _grid_frame(), config.GRID_LAYER)
    wind = _write_geojson(in_dir / "wind.geojson", _wind_generators_frame())
    _write_geojson(
        shortlist_dir / f"{config.SHORTLIST_OUTPUT_PREFIX}_20260101.geojson",
        _shortlist_frame(),
    )
    return _Inputs(scored, integrated, grid, wind, shortlist_dir)


@pytest.fixture
def redirect_outputs(tmp_path, monkeypatch):
    """Point every FIXED sanity output location under ``tmp_path``.

    ``run.py`` and ``report.py`` read ``config.REPORT_PATH`` / ``SIDECAR_PATH``
    / ``SANITY_DIR`` / ``SANITY_META_DIR`` as ``config.<ATTR>`` at call time, so
    patching the ``config`` module attributes redirects all writes here. The
    dirs are NOT pre-created so the fail-before-write assertions can confirm a
    fatal run leaves no output on disk.
    """
    out_dir = tmp_path / "outputs"
    sanity_dir = tmp_path / "DATA" / "sanity"
    meta_dir = sanity_dir / "metadata"
    report_path = out_dir / "sprint1_validation_report.md"
    sidecar_path = sanity_dir / config.SIDECAR_FILENAME

    monkeypatch.setattr(config, "REPORT_PATH", report_path)
    monkeypatch.setattr(config, "SIDECAR_PATH", sidecar_path)
    monkeypatch.setattr(config, "SANITY_DIR", sanity_dir)
    monkeypatch.setattr(config, "SANITY_META_DIR", meta_dir)
    return {
        "out_dir": out_dir,
        "sanity_dir": sanity_dir,
        "meta_dir": meta_dir,
        "report_path": report_path,
        "sidecar_path": sidecar_path,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _output_paths_present(redirect) -> list[Path]:
    """Any headline output artefacts that exist on disk (report / sidecar /
    provenance / manifest / register)."""
    present: list[Path] = []
    for key in ("report_path", "sidecar_path"):
        p = redirect[key]
        if p.exists():
            present.append(p)
    sanity_dir = redirect["sanity_dir"]
    if sanity_dir.exists():
        present.extend(sorted(sanity_dir.rglob("*")))
    out_dir = redirect["out_dir"]
    if out_dir.exists():
        present.extend(sorted(out_dir.rglob("*")))
    return present


def _deterministic_view(result: dict) -> dict:
    """Drop the wall-clock-dependent keys so two runs over fixed inputs compare
    equal on the structured results only (located cells, percentiles, exclusion
    pass/fail, selected spot cells, distribution statistics)."""
    volatile = {"runtime_seconds", "run_timestamp"}
    return {k: v for k, v in result.items() if k not in volatile}


# ---------------------------------------------------------------------------
# run() contract: signature + returns a dict (Requirement 9.1)
# ---------------------------------------------------------------------------


class TestRunContract:
    def test_verbose_is_first_param_defaulting_to_false(self):
        """First parameter is ``verbose`` defaulting to ``False`` (9.1)."""
        sig = inspect.signature(run)
        params = list(sig.parameters.values())
        assert params[0].name == "verbose"
        assert params[0].default is False

    def test_successful_run_returns_a_dict(self, inputs, redirect_outputs):
        """A successful run returns a summary dict (9.1)."""
        result = run(**inputs.run_kwargs())
        assert isinstance(result, dict)
        # Carries the documented summary keys.
        for key in (
            "report_path",
            "sidecar_path",
            "resolved_shortlist_path",
            "n_cells",
            "n_eligible",
            "n_known_farms",
            "check1_pass",
            "check4_pass",
            "run_timestamp",
        ):
            assert key in result

    def test_no_real_output_location_is_written(self, inputs, redirect_outputs):
        """Every written path lands under the monkeypatched tmp dirs."""
        result = run(**inputs.run_kwargs())
        assert str(redirect_outputs["out_dir"]) in result["report_path"]
        assert str(redirect_outputs["sanity_dir"]) in result["sidecar_path"]


# ---------------------------------------------------------------------------
# Property 15 — a successful run returns an existing report path (Req. 9.2)
# ---------------------------------------------------------------------------


class TestReportPathExists:
    # Feature: s1-12-validation-sanity-check, Property 15: Successful run returns
    # an existing report path — the returned report_path (and any sidecar_path)
    # exist on disk after run() returns.
    # Validates: Requirements 9.2
    def test_report_and_sidecar_exist_on_disk_after_return(self, inputs, redirect_outputs):
        result = run(write_sidecar=True, **inputs.run_kwargs())
        assert Path(result["report_path"]).exists()
        assert result["sidecar_path"] is not None
        assert Path(result["sidecar_path"]).exists()

    def test_report_exists_and_sidecar_is_none_when_disabled(self, inputs, redirect_outputs):
        """With the sidecar disabled the report still exists and sidecar_path is None."""
        result = run(write_sidecar=False, **inputs.run_kwargs())
        assert Path(result["report_path"]).exists()
        assert result["sidecar_path"] is None
        assert not redirect_outputs["sidecar_path"].exists()


# ---------------------------------------------------------------------------
# Property 10 — inputs read-only, model never adjusted (Req. 1.3, 8.1-8.3)
# ---------------------------------------------------------------------------


class TestInputsReadOnly:
    # Feature: s1-12-validation-sanity-check, Property 10: Inputs are read-only
    # and the model is never adjusted — after a run over any inputs and any check
    # outcome, the byte content of every input is unchanged, no score/rank is
    # recomputed, and no criteria weight / normalisation bound / exclusion rule /
    # scoring parameter is altered.
    # Validates: Requirements 1.3, 8.1, 8.2, 8.3
    #
    # A full end-to-end run (five GeoPackage/GeoJSON reads + four spatial checks
    # + three writes) is expensive, so a small example count is used with the
    # sidecar toggled to exercise both write branches; the read-only invariant is
    # a per-run byte comparison and does not need a large input space.
    @settings(
        max_examples=8,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
    )
    @given(
        spot_cells=st.integers(min_value=config.SPOT_CHECK_MIN, max_value=config.SPOT_CHECK_MAX),
        write_sidecar=st.booleans(),
    )
    def test_all_inputs_unchanged_byte_for_byte(
        self, inputs, redirect_outputs, spot_cells, write_sidecar
    ):
        # Resolve the shortlist path the run will read so it is fingerprinted too.
        from pipeline.sanity.load import resolve_shortlist

        resolved_shortlist = resolve_shortlist(inputs.shortlist_dir)
        input_paths = inputs.all_input_paths(resolved_shortlist)

        before = {p: _sha256(p) for p in input_paths}
        run(spot_cells=spot_cells, write_sidecar=write_sidecar, **inputs.run_kwargs())
        after = {p: _sha256(p) for p in input_paths}

        assert before == after, "run() mutated a read-only input"

    def test_scored_table_score_and_rank_columns_unchanged(self, inputs, redirect_outputs):
        """The Scored_Table's suitability_score / rank are never re-scored or
        re-ranked by a run (1.3): its bytes are identical afterwards."""
        before = _sha256(inputs.scored_path)
        run(**inputs.run_kwargs())
        assert _sha256(inputs.scored_path) == before


# ---------------------------------------------------------------------------
# Property 14 — regeneration is deterministic / idempotent (Req. 12.3)
# ---------------------------------------------------------------------------


class TestDeterministicRegeneration:
    # Feature: s1-12-validation-sanity-check, Property 14: Regeneration is
    # deterministic (idempotent) — two runs over fixed inputs produce identical
    # structured results (located cells, percentiles, exclusion pass/fail,
    # selected spot cells, distribution statistics).
    # Validates: Requirements 12.3
    #
    # A single fixed input set is used (the fixture is deterministic); a full run
    # is expensive so this compares the two structured-result dicts rather than
    # sweeping a large input space, with the volatile wall-clock keys dropped.
    def test_two_runs_produce_identical_structured_results(self, inputs, redirect_outputs):
        first = _deterministic_view(run(**inputs.run_kwargs()))
        second = _deterministic_view(run(**inputs.run_kwargs()))
        assert first == second

    @settings(
        max_examples=6,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
    )
    @given(
        spot_cells=st.integers(min_value=config.SPOT_CHECK_MIN, max_value=config.SPOT_CHECK_MAX)
    )
    def test_deterministic_for_any_valid_spot_cell_count(
        self, inputs, redirect_outputs, spot_cells
    ):
        first = _deterministic_view(run(spot_cells=spot_cells, **inputs.run_kwargs()))
        second = _deterministic_view(run(spot_cells=spot_cells, **inputs.run_kwargs()))
        assert first == second
        # The deterministic selection always records exactly `spot_cells` cells.
        assert first["n_spot_cells"] == spot_cells


# ---------------------------------------------------------------------------
# Property 6 — invalid Spot_Check_Cells rejected before any write (Req. 4.5)
# ---------------------------------------------------------------------------


class TestInvalidSpotCellsHaltsBeforeWrite:
    # Feature: s1-12-validation-sanity-check, Property 6: Invalid spot-cell count
    # is rejected before any write — a spot_cells outside [5, 10] halts before
    # writing any output, returns an error naming the invalid count, and leaves
    # no partial output on disk.
    # Validates: Requirements 4.5
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        bad=st.integers().filter(
            lambda n: not (config.SPOT_CHECK_MIN <= n <= config.SPOT_CHECK_MAX)
        )
    )
    def test_invalid_count_raises_naming_it_and_writes_nothing(
        self, inputs, redirect_outputs, bad
    ):
        with pytest.raises(ValueError) as excinfo:
            run(spot_cells=bad, **inputs.run_kwargs())
        # The error names the invalid count (4.5).
        assert str(bad) in str(excinfo.value)
        # Nothing was written: the count is validated before any input is opened
        # or any output dir is created.
        assert _output_paths_present(redirect_outputs) == []


# ---------------------------------------------------------------------------
# Unit — forced fatal condition raises, returns no dict, writes nothing (9.3)
# ---------------------------------------------------------------------------


class TestFatalConditionLeavesNoOutput:
    def test_missing_scored_table_raises_and_writes_nothing(self, inputs, redirect_outputs):
        """A missing Scored_Table halts run() before any write (1.4, 9.3)."""
        absent = inputs.scored_path.parent / "absent_scored.gpkg"
        kwargs = inputs.run_kwargs()
        kwargs["scored_path"] = absent
        with pytest.raises(FileNotFoundError, match="Scored_Table"):
            run(**kwargs)
        assert _output_paths_present(redirect_outputs) == []

    def test_missing_shortlist_dir_raises_and_writes_nothing(self, inputs, redirect_outputs):
        """An empty/absent shortlist dir halts run() before any write (1.4, 9.3)."""
        kwargs = inputs.run_kwargs()
        kwargs["shortlist_dir"] = inputs.shortlist_dir.parent / "no_shortlist_here"
        with pytest.raises(FileNotFoundError):
            run(**kwargs)
        assert _output_paths_present(redirect_outputs) == []

    def test_absent_required_column_raises_and_writes_nothing(self, inputs, redirect_outputs):
        """An Integrated_Feature_Table missing a required column halts before
        any write, and no dict is returned (1.5, 9.3)."""
        bad = inputs.integrated_path.parent / "integrated_bad.gpkg"
        _write_gpkg(
            bad, _integrated_frame().drop(columns=["wind_speed"]), config.INTEGRATED_LAYER
        )
        kwargs = inputs.run_kwargs()
        kwargs["integrated_path"] = bad
        with pytest.raises(ValueError) as excinfo:
            run(**kwargs)
        assert "wind_speed" in str(excinfo.value)
        assert _output_paths_present(redirect_outputs) == []


# ---------------------------------------------------------------------------
# Unit — supplied overrides take effect (Req. 9.3, 12.4)
# ---------------------------------------------------------------------------


class TestOverridesTakeEffect:
    def test_spot_cells_override_changes_recorded_count(self, inputs, redirect_outputs):
        """A supplied ``spot_cells`` overrides the default and drives the number
        of recorded Spot_Check_Cells (12.4)."""
        assert config.SPOT_CHECK_DEFAULT != config.SPOT_CHECK_MAX  # guard the test
        result = run(spot_cells=config.SPOT_CHECK_MAX, **inputs.run_kwargs())
        assert result["n_spot_cells"] == config.SPOT_CHECK_MAX

    def test_default_spot_cells_used_when_not_supplied(self, inputs, redirect_outputs):
        result = run(**inputs.run_kwargs())
        assert result["n_spot_cells"] == config.SPOT_CHECK_DEFAULT

    def test_wind_generators_path_override_is_used(self, inputs, redirect_outputs):
        """A supplied ``wind_generators_path`` override is read instead of the
        default: a single-farm override yields exactly one known farm (12.4)."""
        one_farm = gpd.GeoDataFrame(
            {"name": ["Solo Farm"]},
            geometry=[Point(*reversed(_cell_centroid(5)))],
            crs="EPSG:4326",
        )
        override = inputs.wind_generators_path.parent / "wind_override.geojson"
        _write_geojson(override, one_farm)
        kwargs = inputs.run_kwargs()
        kwargs["wind_generators_path"] = override
        result = run(**kwargs)
        assert result["n_known_farms"] == 1
