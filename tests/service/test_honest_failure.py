"""
Uniform honest-failure tests across ALL six S2-08 Service_Operations
(task 7.1, CONTRACT.md §6, Requirement 7.1–7.4, Property P6).

The per-operation test modules (``test_results.py``, ``test_quality.py``,
``test_run_analysis.py``, ``test_scenarios.py``) each pin the honest-failure
behaviour of one operation. THIS module is the cross-cutting audit the task 7.1
asks for: it asserts the SAME honest-failure contract holds CONSISTENTLY across
every operation, so the error handling cannot drift between them
(holistic-project-awareness — one error contract, applied uniformly).

The contract under test is CONTRACT.md §6 / §7 P6:

  * Missing Run              → ``RunNotFoundError`` NAMING the ``run_id`` (7.1);
  * Unknown ``cell_id``      → ``CellNotFoundError`` NAMING the ``cell_id`` (7.2);
  * Missing engine output    → ``EngineOutputError`` NAMING the input path (7.3);
  * Invalid weights/scenario → ``ScoringConfigError`` naming the fault, no Run (4.4);
  * Empty-but-valid          → an empty set with NO error, clearly distinguished
                               from the error conditions above (7.4).

Every read operation that keys on a Run (``get_ranked_results``,
``get_site_detail``, ``get_exclusions``) is driven through the SAME two failure
modes with a table-driven parametrisation, so a regression in any one is caught
here even if its own module's coverage lapses. The empty-but-valid cases are
asserted SIDE BY SIDE with the error cases (7.4): the point of the requirement
is that the service DISTINGUISHES them, so the two are proven distinct in one
place.

Hermeticity: the per-Run store (``service_config.RUNS_DIR``) and the shared
engine-output paths (explanation, eligibility, data-quality) are redirected to a
temp directory per test via ``monkeypatch``, so the real ``DATA/service/`` tree
is never touched and no built dataset is required.
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point

from pipeline import validate as validate_module
from pipeline.scoring import config as scoring_config
from pipeline.scoring.weights import ScoringConfigError
from pipeline.service import (
    compare_scenarios,
    config as service_config,
    get_data_quality,
    get_exclusions,
    get_ranked_results,
    get_site_detail,
)
from pipeline.service.runs import (
    CellNotFoundError,
    EngineOutputError,
    RunNotFoundError,
)

# A run_id that is guaranteed absent from any store — reused so the assertion
# that the error NAMES the missing run has a concrete string to match on.
MISSING_RUN_ID = "missingrun000000"


@pytest.fixture
def runs_store(tmp_path, monkeypatch):
    """Redirect the per-Run materialisation store to a temp directory."""
    store = tmp_path / "runs"
    monkeypatch.setattr(service_config, "RUNS_DIR", store)
    return store


def _write_manifest_only(store: Path, run_id: str) -> Path:
    """
    Materialise a Run directory with ONLY its ``run.json`` manifest — no
    Scored_Table — so the Run "exists" but its engine output is missing. This
    is the honest-failure case 7.3 (a required materialised output is absent).
    """
    target = store / run_id
    target.mkdir(parents=True, exist_ok=True)
    manifest = {"run_id": run_id, "weights_id": run_id, "scenario": None}
    (target / service_config.RUN_MANIFEST_FILENAME).write_text(
        json.dumps(manifest) + "\n", encoding="utf-8"
    )
    return target


def _materialise_one_eligible_cell(
    store: Path,
    tmp_path: Path,
    run_id: str,
    monkeypatch,
    *,
    cell_id: str = "c1",
    score: float = 0.9,
) -> None:
    """
    Materialise a complete single-eligible-cell Run: a Scored_Table, the
    integrated table it "scored", the S2-06 explanation output, and a manifest.

    Enough for every read operation to succeed for ``cell_id`` — so the
    empty-but-valid and unknown-cell cases can be exercised against a real,
    readable Run rather than a broken one.
    """
    target = store / run_id
    target.mkdir(parents=True, exist_ok=True)

    scored = gpd.GeoDataFrame(
        [{"cell_id": cell_id, "suitability_score": score, "rank": 1,
          "contrib_wind_speed": score}],
        geometry=[Point(150.0, -30.0)],
        crs=scoring_config.STORAGE_CRS,
    )
    scored.to_file(
        target / service_config.SCORED_GPKG_FILENAME,
        driver="GPKG",
        layer=service_config.SCORED_LAYER,
    )

    integrated_path = tmp_path / f"integrated_{run_id}.gpkg"
    gpd.GeoDataFrame(
        [{"cell_id": cell_id, "eligible": True, "wind_speed": 9.0}],
        geometry=[Point(150.0, -30.0)],
        crs=scoring_config.STORAGE_CRS,
    ).to_file(integrated_path, driver="GPKG", layer=service_config.INTEGRATED_LAYER)

    explanation_path = tmp_path / f"explanations_{run_id}.json"
    explanation_path.write_text(
        json.dumps([
            {"cell_id": cell_id, "eligible": True, "headline": "H",
             "positive_factors": [], "weaknesses": [], "proxy_caveats": [],
             "data_quality_notes": []},
        ]) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(service_config, "EXPLANATION_PATH", explanation_path)

    manifest = {
        "run_id": run_id,
        "weights_id": run_id,
        "scenario": None,
        "criteria": [
            {"feature": "wind_speed", "weight": 1.0, "direction": "higher_is_better"}
        ],
        "integrated_path": str(integrated_path),
        "integrated_layer": service_config.INTEGRATED_LAYER,
    }
    (target / service_config.RUN_MANIFEST_FILENAME).write_text(
        json.dumps(manifest) + "\n", encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# 7.1 — Missing Run: EVERY run-keyed read op raises RunNotFoundError NAMING    #
# the run, uniformly. This is the cross-operation consistency the task wants.  #
# --------------------------------------------------------------------------- #

# The run-keyed read operations, as (name, callable-taking-a-run_id) pairs.
RUN_KEYED_OPERATIONS = [
    ("get_ranked_results", lambda run_id: get_ranked_results(run_id)),
    ("get_site_detail", lambda run_id: get_site_detail(run_id, "c1")),
    ("get_exclusions", lambda run_id: get_exclusions(run_id)),
]


@pytest.mark.parametrize(
    "op_name, op",
    RUN_KEYED_OPERATIONS,
    ids=[name for name, _ in RUN_KEYED_OPERATIONS],
)
def test_missing_run_raises_naming_the_run_uniformly(runs_store, op_name, op):
    """
    Requirement 7.1 / P6 — a missing Run yields ``RunNotFoundError`` naming the
    ``run_id`` from EVERY run-keyed operation, never an empty success. Asserting
    all three in one parametrised test proves the behaviour is uniform: the same
    error type, and the missing ``run_id`` named in the message.
    """
    with pytest.raises(RunNotFoundError) as exc_info:
        op(MISSING_RUN_ID)
    # The error NAMES the missing run (not a bare "not found") so the UI can
    # present a real, specific error.
    assert MISSING_RUN_ID in str(exc_info.value)


# --------------------------------------------------------------------------- #
# 7.3 — Missing engine output: a run that EXISTS but whose required            #
# materialised output is absent raises EngineOutputError NAMING the input.     #
# --------------------------------------------------------------------------- #


def test_missing_scored_table_names_the_input(runs_store):
    """7.3 — the Run exists but its Scored_Table is missing (get_ranked_results)."""
    _write_manifest_only(runs_store, "runnoscored00001")
    with pytest.raises(EngineOutputError, match="Scored_Table is missing"):
        get_ranked_results("runnoscored00001")


def test_missing_scored_table_names_the_input_for_detail(runs_store):
    """7.3 — the Run exists but its Scored_Table is missing (get_site_detail)."""
    _write_manifest_only(runs_store, "runnoscored00002")
    with pytest.raises(EngineOutputError, match="Scored_Table is missing"):
        get_site_detail("runnoscored00002", "c1")


def test_missing_eligibility_table_names_the_input(runs_store, tmp_path, monkeypatch):
    """7.3 — the Run exists but the shared Eligibility_Table is missing."""
    _write_manifest_only(runs_store, "runnoelig0000001")
    monkeypatch.setattr(
        service_config, "ELIGIBILITY_TABLE_PATH", tmp_path / "absent_eligibility.gpkg"
    )
    with pytest.raises(EngineOutputError, match="Eligibility_Table is missing"):
        get_exclusions("runnoelig0000001")


def test_missing_explanation_output_names_the_input(runs_store, tmp_path, monkeypatch):
    """7.3 — a readable Run whose S2-06 explanation output is missing."""
    _materialise_one_eligible_cell(runs_store, tmp_path, "runnoexpl0000001", monkeypatch)
    monkeypatch.setattr(
        service_config, "EXPLANATION_PATH", tmp_path / "absent_explanations.json"
    )
    with pytest.raises(EngineOutputError, match="Explanation output is missing"):
        get_site_detail("runnoexpl0000001", "c1")


def test_missing_data_quality_status_names_the_input(tmp_path, monkeypatch):
    """
    7.3 / 5.3 — a missing Data_Quality_Status names the input rather than
    fabricating a passing verdict. A missing status is NEVER silently "passed".
    """
    monkeypatch.setattr(
        validate_module,
        "DEFAULT_VALIDATION_RESULT_PATH",
        tmp_path / "integrated_input_validation.json",
        raising=True,
    )
    with pytest.raises(EngineOutputError, match="Data_Quality_Status is missing"):
        get_data_quality()


# --------------------------------------------------------------------------- #
# 7.2 — Unknown cell_id in an existing Run raises CellNotFoundError NAMING     #
# the cell (distinct from a missing Run, which names the run).                 #
# --------------------------------------------------------------------------- #


def test_unknown_cell_id_names_the_cell(runs_store, tmp_path, monkeypatch):
    """7.2 / P6 — an unknown cell in a real Run names the missing cell_id."""
    _materialise_one_eligible_cell(runs_store, tmp_path, "runcell000000001", monkeypatch)
    with pytest.raises(CellNotFoundError) as exc_info:
        get_site_detail("runcell000000001", "NO_SUCH_CELL")
    assert "NO_SUCH_CELL" in str(exc_info.value)


# --------------------------------------------------------------------------- #
# 4.4 — Invalid weights / unknown scenario: an error naming the fault, no Run. #
# --------------------------------------------------------------------------- #


def test_unknown_scenario_run_analysis_creates_no_run(runs_store):
    """4.4 — run_analysis rejects an unknown scenario and materialises no Run."""
    from pipeline.service import run_analysis

    with pytest.raises(ScoringConfigError, match="unknown scenario"):
        run_analysis(scenario="does_not_exist")
    assert not runs_store.exists() or not any(runs_store.iterdir())


def test_unknown_scenario_compare_scenarios_creates_no_run(runs_store):
    """4.4 — compare_scenarios rejects an unknown scenario and materialises no Run."""
    with pytest.raises(ScoringConfigError, match="unknown scenario"):
        compare_scenarios("does_not_exist", "wind_led")
    assert not runs_store.exists() or not any(runs_store.iterdir())


# --------------------------------------------------------------------------- #
# 7.4 — Empty-but-valid is DISTINGUISHED from an error. The empty results      #
# below are asserted side by side with the error cases above: an all-excluding #
# threshold, a top-N over the count, and a Run with no exclusions each return  #
# an empty set with NO error — the honest counterpart to the failures above.   #
# --------------------------------------------------------------------------- #


def test_all_excluding_threshold_is_empty_not_error(runs_store, tmp_path, monkeypatch):
    """7.4 / 3.4 — a min_score that excludes every cell returns [], never an error."""
    _materialise_one_eligible_cell(
        runs_store, tmp_path, "runempty00000001", monkeypatch, score=0.5
    )
    # A threshold above the only cell's score excludes it — empty-but-valid.
    result = get_ranked_results("runempty00000001", min_score=0.9)
    assert result == []


def test_top_n_over_count_returns_all_no_padding(runs_store, tmp_path, monkeypatch):
    """7.4 / 3.3 — a top_n beyond the eligible count returns all, no padding, no error."""
    _materialise_one_eligible_cell(
        runs_store, tmp_path, "runempty00000002", monkeypatch
    )
    result = get_ranked_results("runempty00000002", top_n=99)
    assert [r.cell_id for r in result] == ["c1"]  # the one eligible cell, no padding


def test_no_exclusions_returns_empty_not_error(runs_store, tmp_path, monkeypatch):
    """7.4 — a Run whose cells are all eligible returns an empty exclusion set."""
    _materialise_one_eligible_cell(
        runs_store, tmp_path, "runempty00000003", monkeypatch
    )
    # Hand-write an all-eligible Eligibility_Table so get_exclusions has nothing
    # to return — an empty-but-valid result, not an error.
    eligibility_path = tmp_path / "eligibility_all_eligible.gpkg"
    gpd.GeoDataFrame(
        [{"cell_id": "c1", "eligible": True, "exclusion_reason": None,
          "triggered_rules": None, "exclusion_reasons": None}],
        geometry=[Point(150.0, -30.0)],
        crs=scoring_config.STORAGE_CRS,
    ).to_file(eligibility_path, driver="GPKG")
    monkeypatch.setattr(service_config, "ELIGIBILITY_TABLE_PATH", eligibility_path)

    result = get_exclusions("runempty00000003")
    assert result == []


def test_empty_result_and_missing_run_are_distinct_conditions(runs_store, tmp_path, monkeypatch):
    """
    7.4 — the CORE distinction: an empty-but-valid result and a missing-Run
    error are two different outcomes from the SAME operation. An all-excluding
    threshold on a real Run returns ``[]``; the same call on a missing Run
    raises. The service never conflates the two (no misleading empty success).
    """
    _materialise_one_eligible_cell(
        runs_store, tmp_path, "runempty00000004", monkeypatch, score=0.5
    )

    # Empty-but-valid: a real Run, a threshold that legitimately excludes all.
    assert get_ranked_results("runempty00000004", min_score=0.9) == []

    # Error: the SAME operation on a Run that does not exist raises, naming it —
    # a real error, not an empty list.
    with pytest.raises(RunNotFoundError, match=MISSING_RUN_ID):
        get_ranked_results(MISSING_RUN_ID, min_score=0.9)
