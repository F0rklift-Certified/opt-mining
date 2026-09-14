"""
Tests for the S2-08 ``get_ranked_results`` read operation
(``pipeline.service.results``).

`get_ranked_results` reads a materialised Run's S2-05 Scored_Table and returns
one ``RankedRow`` per eligible cell, ordered by ascending `rank`, carrying the
engine's `suitability_score`, `rank` and `contrib_{feature}` shares through
UNCHANGED (Requirement 1.2, 2.4, 6.3). It performs no scoring, normalisation or
ranking — the no-recompute guarantee (CONTRACT.md §1).

Two layers of coverage:

* Unit tests over a hand-written Scored_Table materialised into a temp Run
  directory — deterministic, no built dataset required. These pin the
  projection, the eligible-only rule, the rank ordering and the honest-failure
  behaviour.
* Engine-backed tests against the real frozen integrated table, skipped when
  that input is absent, that confirm the operation serves a real Run.
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point

from pipeline.scoring import config as scoring_config
from pipeline.service import config as service_config
from pipeline.service import get_ranked_results, get_site_detail, run_analysis
from pipeline.service.models import RankedRow, SiteDetail
from pipeline.service.runs import (
    CellNotFoundError,
    EngineOutputError,
    RunNotFoundError,
)

INTEGRATED_PATH = Path(scoring_config.INTEGRATED_PATH)
ENGINE_INPUT_AVAILABLE = INTEGRATED_PATH.exists()
requires_engine_input = pytest.mark.skipif(
    not ENGINE_INPUT_AVAILABLE,
    reason=f"integrated feature table not built: {INTEGRATED_PATH}",
)


@pytest.fixture
def runs_store(tmp_path, monkeypatch):
    """Redirect the per-Run materialisation store to a temp directory."""
    store = tmp_path / "runs"
    monkeypatch.setattr(service_config, "RUNS_DIR", store)
    return store


def _materialise_fake_run(store: Path, run_id: str, rows: list[dict]) -> None:
    """
    Write a minimal Scored_Table + manifest for a fake Run, so the read path
    can be exercised without running the engine.

    Each row dict carries at least `cell_id`, `suitability_score`, `rank` and
    any `contrib_*` columns; an excluded cell uses None for score and rank.
    """
    target = store / run_id
    target.mkdir(parents=True, exist_ok=True)

    frame = gpd.GeoDataFrame(
        rows,
        geometry=[Point(150.0 + i * 0.1, -30.0) for i in range(len(rows))],
        crs=scoring_config.STORAGE_CRS,
    )
    gpkg_path = target / service_config.SCORED_GPKG_FILENAME
    frame.to_file(gpkg_path, driver="GPKG", layer=service_config.SCORED_LAYER)

    manifest = {"run_id": run_id, "weights_id": run_id, "scenario": None}
    (target / service_config.RUN_MANIFEST_FILENAME).write_text(
        json.dumps(manifest) + "\n", encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# Projection over a hand-written Scored_Table (deterministic).                #
# --------------------------------------------------------------------------- #


def test_returns_ranked_rows_projected_from_the_table(runs_store):
    _materialise_fake_run(
        runs_store,
        "run0000000000abcd",
        [
            {"cell_id": "c2", "suitability_score": 0.4, "rank": 2,
             "contrib_wind_speed": 0.3, "contrib_slope_deg": 0.1},
            {"cell_id": "c1", "suitability_score": 0.9, "rank": 1,
             "contrib_wind_speed": 0.6, "contrib_slope_deg": 0.3},
        ],
    )

    result = get_ranked_results("run0000000000abcd")

    assert all(isinstance(r, RankedRow) for r in result)
    # Ordered by ascending rank (rank 1 first), regardless of table row order.
    assert [r.cell_id for r in result] == ["c1", "c2"]
    assert [r.rank for r in result] == [1, 2]
    assert result[0].suitability_score == 0.9
    # key_components keyed by feature (contrib_ prefix stripped), carried through.
    assert result[0].key_components == {"wind_speed": 0.6, "slope_deg": 0.3}


def test_excluded_cells_are_not_ranked(runs_store):
    _materialise_fake_run(
        runs_store,
        "runexcluded00000",
        [
            {"cell_id": "c1", "suitability_score": 0.9, "rank": 1,
             "contrib_wind_speed": 0.9},
            {"cell_id": "cX", "suitability_score": None, "rank": None,
             "contrib_wind_speed": None},
        ],
    )

    result = get_ranked_results("runexcluded00000")

    assert [r.cell_id for r in result] == ["c1"]


def test_all_excluded_returns_empty_but_valid(runs_store):
    _materialise_fake_run(
        runs_store,
        "runallexcluded00",
        [
            {"cell_id": "cX", "suitability_score": None, "rank": None,
             "contrib_wind_speed": None},
        ],
    )

    result = get_ranked_results("runallexcluded00")

    assert result == []  # empty-but-valid, not an error


def test_null_contribution_is_omitted_not_fabricated(runs_store):
    _materialise_fake_run(
        runs_store,
        "runnullcontrib00",
        [
            {"cell_id": "c1", "suitability_score": 0.5, "rank": 1,
             "contrib_wind_speed": 0.5, "contrib_demand_proxy": None},
        ],
    )

    result = get_ranked_results("runnullcontrib00")

    assert result[0].key_components == {"wind_speed": 0.5}


# --------------------------------------------------------------------------- #
# Honest failure (Requirement 7.1, 7.3).                                      #
# --------------------------------------------------------------------------- #


def test_missing_run_raises_naming_the_run(runs_store):
    with pytest.raises(RunNotFoundError, match="nope000000000000"):
        get_ranked_results("nope000000000000")


def test_missing_scored_table_raises_naming_the_input(runs_store):
    target = runs_store / "runnoscoredtable"
    target.mkdir(parents=True, exist_ok=True)
    manifest = {"run_id": "runnoscoredtable", "weights_id": "x", "scenario": None}
    (target / service_config.RUN_MANIFEST_FILENAME).write_text(
        json.dumps(manifest) + "\n", encoding="utf-8"
    )

    with pytest.raises(EngineOutputError, match="Scored_Table is missing"):
        get_ranked_results("runnoscoredtable")


# --------------------------------------------------------------------------- #
# Against the real engine (Requirement 1.2, 8.1).                             #
# --------------------------------------------------------------------------- #


@requires_engine_input
def test_ranked_results_from_a_real_run(runs_store):
    handle = run_analysis(scenario="wind_led")
    result = get_ranked_results(handle)

    assert result, "a real run should have at least one eligible cell"
    # Ranks are dense/ascending from 1 and strictly increasing under the sort.
    ranks = [r.rank for r in result]
    assert ranks == sorted(ranks)
    assert ranks[0] == 1
    # Every served score is in [0, 1] and every row carries its components.
    for r in result:
        assert 0.0 <= r.suitability_score <= 1.0
        assert r.key_components


# --------------------------------------------------------------------------- #
# get_site_detail — one cell's full detail (Requirement 1.3, 2.3, 6.2, 7.2).  #
#                                                                             #
# These pin the projection (score/rank from the Scored_Table, features +      #
# eligibility from the integrated table, S2-06 explanation carried verbatim), #
# the P1 consistency guarantee, and the honest-failure behaviour, over a      #
# hand-written Run so no built dataset is required.                           #
# --------------------------------------------------------------------------- #


def _materialise_fake_run_with_detail(
    store: Path,
    tmp_path: Path,
    run_id: str,
    scored_rows: list[dict],
    integrated_rows: list[dict],
    explanations: list[dict],
    monkeypatch,
    *,
    criteria: list[dict] | None = None,
) -> None:
    """
    Write a fake Run with everything ``get_site_detail`` reads: a Scored_Table,
    the integrated feature table the Run "scored", and the S2-06 explanation
    output — plus a manifest wiring the integrated path and the Run's criteria.
    The explanation path is redirected to a per-test file.
    """
    target = store / run_id
    target.mkdir(parents=True, exist_ok=True)

    scored = gpd.GeoDataFrame(
        scored_rows,
        geometry=[Point(150.0 + i * 0.1, -30.0) for i in range(len(scored_rows))],
        crs=scoring_config.STORAGE_CRS,
    )
    scored.to_file(
        target / service_config.SCORED_GPKG_FILENAME,
        driver="GPKG",
        layer=service_config.SCORED_LAYER,
    )

    integrated_path = tmp_path / f"integrated_{run_id}.gpkg"
    integrated = gpd.GeoDataFrame(
        integrated_rows,
        geometry=[Point(150.0 + i * 0.1, -30.0) for i in range(len(integrated_rows))],
        crs=scoring_config.STORAGE_CRS,
    )
    integrated.to_file(integrated_path, driver="GPKG", layer=service_config.INTEGRATED_LAYER)

    explanation_path = tmp_path / f"explanations_{run_id}.json"
    explanation_path.write_text(json.dumps(explanations) + "\n", encoding="utf-8")
    monkeypatch.setattr(service_config, "EXPLANATION_PATH", explanation_path)

    manifest = {
        "run_id": run_id,
        "weights_id": run_id,
        "scenario": None,
        "criteria": criteria
        if criteria is not None
        else [{"feature": "wind_speed", "weight": 1.0, "direction": "higher_is_better"}],
        "integrated_path": str(integrated_path),
        "integrated_layer": service_config.INTEGRATED_LAYER,
    }
    (target / service_config.RUN_MANIFEST_FILENAME).write_text(
        json.dumps(manifest) + "\n", encoding="utf-8"
    )


def test_site_detail_projects_all_three_sources(runs_store, tmp_path, monkeypatch):
    _materialise_fake_run_with_detail(
        runs_store,
        tmp_path,
        "rundetail0000001",
        scored_rows=[
            {"cell_id": "c1", "suitability_score": 0.8, "rank": 1,
             "contrib_wind_speed": 0.5, "contrib_slope_deg": 0.3},
        ],
        integrated_rows=[
            {"cell_id": "c1", "eligible": True,
             "wind_speed": 8.4, "slope_deg": 3.1},
        ],
        explanations=[
            {"cell_id": "c1", "eligible": True, "headline": "H",
             "positive_factors": ["Strong wind resource (top decile)"],
             "weaknesses": [], "proxy_caveats": [], "data_quality_notes": ["Confidence: high"]},
        ],
        monkeypatch=monkeypatch,
        criteria=[
            {"feature": "wind_speed", "weight": 0.6, "direction": "higher_is_better"},
            {"feature": "slope_deg", "weight": 0.4, "direction": "lower_is_better"},
        ],
    )

    detail = get_site_detail("rundetail0000001", "c1")

    assert isinstance(detail, SiteDetail)
    # Score, rank and contributions from the Scored_Table (no recompute).
    assert detail.suitability_score == 0.8
    assert detail.rank == 1
    assert detail.contributions == {"wind_speed": 0.5, "slope_deg": 0.3}
    # Input features + eligibility from the integrated table, verbatim.
    assert detail.features == {"wind_speed": 8.4, "slope_deg": 3.1}
    assert detail.eligible is True
    # The S2-06 explanation is carried through unchanged (fields not renamed).
    assert detail.explanation["headline"] == "H"
    assert detail.explanation["positive_factors"] == [
        "Strong wind resource (top decile)"
    ]


def test_site_detail_score_and_rank_match_ranked_results(runs_store, tmp_path, monkeypatch):
    """Property P1 — one engine output: same score/rank across operations (2.3)."""
    # Feature: s2-08-decision-service-api, Property 1: one engine output
    _materialise_fake_run_with_detail(
        runs_store,
        tmp_path,
        "runconsistent001",
        scored_rows=[
            {"cell_id": "c2", "suitability_score": 0.4, "rank": 2, "contrib_wind_speed": 0.4},
            {"cell_id": "c1", "suitability_score": 0.9, "rank": 1, "contrib_wind_speed": 0.9},
        ],
        integrated_rows=[
            {"cell_id": "c2", "eligible": True, "wind_speed": 6.0},
            {"cell_id": "c1", "eligible": True, "wind_speed": 9.0},
        ],
        explanations=[
            {"cell_id": "c1", "eligible": True, "headline": "H",
             "positive_factors": [], "weaknesses": [], "proxy_caveats": [],
             "data_quality_notes": []},
            {"cell_id": "c2", "eligible": True, "headline": "H",
             "positive_factors": [], "weaknesses": [], "proxy_caveats": [],
             "data_quality_notes": []},
        ],
        monkeypatch=monkeypatch,
    )

    ranked = {r.cell_id: r for r in get_ranked_results("runconsistent001")}
    for cell_id, row in ranked.items():
        detail = get_site_detail("runconsistent001", cell_id)
        assert detail.suitability_score == row.suitability_score
        assert detail.rank == row.rank
        # And the contributions the detail exposes match the ranked key_components.
        assert detail.contributions == row.key_components


def test_site_detail_for_an_excluded_cell(runs_store, tmp_path, monkeypatch):
    """An excluded cell carries null score/rank, eligible=False, and its excluded explanation."""
    _materialise_fake_run_with_detail(
        runs_store,
        tmp_path,
        "runexcldetail001",
        scored_rows=[
            {"cell_id": "c1", "suitability_score": 0.9, "rank": 1, "contrib_wind_speed": 0.9},
            {"cell_id": "cX", "suitability_score": None, "rank": None, "contrib_wind_speed": None},
        ],
        integrated_rows=[
            {"cell_id": "c1", "eligible": True, "wind_speed": 9.0},
            {"cell_id": "cX", "eligible": False, "wind_speed": None},
        ],
        explanations=[
            {"cell_id": "cX", "eligible": False,
             "exclusion_reasons": [{"code": "protected_area", "text": "Protected area"}],
             "proxy_caveats": [], "data_quality_notes": []},
        ],
        monkeypatch=monkeypatch,
    )

    detail = get_site_detail("runexcldetail001", "cX")

    assert detail.suitability_score is None
    assert detail.rank is None
    assert detail.eligible is False
    assert detail.features == {"wind_speed": None}
    # The excluded-path explanation is carried through verbatim.
    assert detail.explanation["eligible"] is False
    assert detail.explanation["exclusion_reasons"][0]["code"] == "protected_area"


def test_site_detail_unknown_cell_raises_naming_the_cell(runs_store, tmp_path, monkeypatch):
    _materialise_fake_run_with_detail(
        runs_store,
        tmp_path,
        "rununknowncell01",
        scored_rows=[
            {"cell_id": "c1", "suitability_score": 0.9, "rank": 1, "contrib_wind_speed": 0.9},
        ],
        integrated_rows=[{"cell_id": "c1", "eligible": True, "wind_speed": 9.0}],
        explanations=[
            {"cell_id": "c1", "eligible": True, "headline": "H",
             "positive_factors": [], "weaknesses": [], "proxy_caveats": [],
             "data_quality_notes": []},
        ],
        monkeypatch=monkeypatch,
    )

    with pytest.raises(CellNotFoundError, match="NOPE_CELL"):
        get_site_detail("rununknowncell01", "NOPE_CELL")


def test_site_detail_missing_run_raises_naming_the_run(runs_store):
    with pytest.raises(RunNotFoundError, match="nope000000000000"):
        get_site_detail("nope000000000000", "c1")


def test_site_detail_missing_explanation_output_names_the_input(runs_store, tmp_path, monkeypatch):
    # Point the explanation path at a file that does not exist.
    _materialise_fake_run_with_detail(
        runs_store,
        tmp_path,
        "runnoexpl0000001",
        scored_rows=[
            {"cell_id": "c1", "suitability_score": 0.9, "rank": 1, "contrib_wind_speed": 0.9},
        ],
        integrated_rows=[{"cell_id": "c1", "eligible": True, "wind_speed": 9.0}],
        explanations=[],
        monkeypatch=monkeypatch,
    )
    monkeypatch.setattr(
        service_config, "EXPLANATION_PATH", tmp_path / "absent_explanations.json"
    )

    with pytest.raises(EngineOutputError, match="Explanation output is missing"):
        get_site_detail("runnoexpl0000001", "c1")


# --------------------------------------------------------------------------- #
# Against the real engine (Requirement 1.3, 2.3, 8.1, 8.2).                    #
# --------------------------------------------------------------------------- #


@requires_engine_input
def test_site_detail_from_a_real_run_matches_ranked_results(runs_store):
    handle = run_analysis(scenario="wind_led")
    ranked = get_ranked_results(handle)
    assert ranked, "a real run should have at least one eligible cell"

    top = ranked[0]
    detail = get_site_detail(handle, top.cell_id)

    # P1 — the map (detail) and the table (ranked) show one engine output.
    assert detail.suitability_score == top.suitability_score
    assert detail.rank == top.rank
    assert detail.eligible is True
    # Features and a verbatim S2-06 explanation are served for the cell.
    assert detail.features
    assert detail.explanation.get("cell_id") == top.cell_id
