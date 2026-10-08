"""
Contract / integration tests for the S2-08 Decision_Service FastAPI app
(``pipeline.service.app``) against the REAL engine on the frozen dataset
(task 8.1, Requirement 8.1-8.5).

These are the end-to-end tests that exercise the published HTTP surface — the
same surface the Sprint 3 web application generates its typed client from — over
the actual decision engine, rather than the hand-written Scored_Tables the
operation-level unit tests use. They drive each endpoint through FastAPI's
``TestClient`` (in-process, no network) and assert the CONTRACT.md guarantees
hold on real materialised output:

* 8.1 — every Service_Operation is reachable over its endpoint and returns the
  contract-shaped result on the frozen dataset.
* 8.2 — ranked results and site detail return the IDENTICAL score/rank for the
  same ``cell_id`` in a Run (the one-engine-output guarantee, Property P1).
* 8.3 — a Display_Filter changes the returned SET but never a cell's score or
  rank (filter invariance, Property P2).
* 8.4 — ``compare_scenarios`` reuses the engine and returns a per-cell rank
  comparison (Property P5).
* 8.5 — honest failure: a missing Run -> 404, a missing ``cell_id`` -> 404, a
  missing engine output -> 503 (CONTRACT.md §6, Property P6).

Also asserts the OpenAPI schema is published at ``/openapi.json`` and documents
all six endpoints (Requirement 6.1, 6.4).

HERMETIC AND CI-SAFE. The per-Run materialisation store (``RUNS_DIR``) is
redirected to a temp directory so the tests never touch ``DATA/service/`` and
leave no residue. The engine-backed tests skip gracefully when the frozen
integrated table is absent (exactly as the operation-level engine tests do), so
the suite passes in a checkout without the built dataset while still exercising
the real engine wherever it is available (including CI once the dataset is
present).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.scoring import config as scoring_config
from pipeline.service import config as service_config

# fastapi/httpx are S2-08 dependencies (requirements.txt); skip the whole module
# with a clear reason if the transport layer is somehow not installed, rather
# than erroring at collection.
fastapi_testclient = pytest.importorskip(
    "fastapi.testclient",
    reason="fastapi/httpx not installed (S2-08 transport deps in requirements.txt)",
)
TestClient = fastapi_testclient.TestClient

from pipeline.service.app import app  # noqa: E402  (after importorskip)

INTEGRATED_PATH = Path(scoring_config.INTEGRATED_PATH)
ENGINE_INPUT_AVAILABLE = INTEGRATED_PATH.exists()
requires_engine_input = pytest.mark.skipif(
    not ENGINE_INPUT_AVAILABLE,
    reason=f"integrated feature table not built: {INTEGRATED_PATH}",
)

ELIGIBILITY_TABLE_PATH = Path(service_config.ELIGIBILITY_TABLE_PATH)
requires_eligibility_table = pytest.mark.skipif(
    not ELIGIBILITY_TABLE_PATH.exists(),
    reason=f"Eligibility_Table not built: {ELIGIBILITY_TABLE_PATH}",
)

# A named Scenario present in the packaged scenarios.yaml (CONTRACT.md §3/§4).
SCENARIO_A = "wind_led"
SCENARIO_B = "grid_led"


@pytest.fixture
def runs_store(tmp_path, monkeypatch):
    """
    Redirect the per-Run materialisation store to a temp directory.

    ``runs.py`` reads ``config.RUNS_DIR`` at call time, so patching it here keeps
    every Run these tests materialise inside ``tmp_path`` — the suite is
    hermetic and never writes under ``DATA/service/`` (CI-safe).
    """
    store = tmp_path / "runs"
    monkeypatch.setattr(service_config, "RUNS_DIR", store)
    return store


@pytest.fixture
def client(runs_store) -> TestClient:
    """A ``TestClient`` over the FastAPI app, with the Run store redirected."""
    return TestClient(app)


# --------------------------------------------------------------------------- #
# The published OpenAPI contract (Requirement 6.1, 6.4).                       #
#                                                                             #
# These do not need the built dataset — the schema is generated from the app   #
# declaration, so they run everywhere and pin the frozen endpoint surface.     #
# --------------------------------------------------------------------------- #

EXPECTED_PATHS = {
    ("/runs", "post"),
    ("/runs/{run_id}/results", "get"),
    ("/runs/{run_id}/sites/{cell_id}", "get"),
    ("/runs/{run_id}/exclusions", "get"),
    ("/scenario-comparison", "post"),
    ("/data-quality", "get"),
}


def test_openapi_schema_is_published(client):
    """The machine-readable contract is served at /openapi.json (Requirement 6.1)."""
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema.get("openapi", "").startswith("3."), "expected an OpenAPI 3.x schema"
    assert "paths" in schema


def test_openapi_documents_all_six_endpoints(client):
    """All six Service_Operations map to their contract endpoints (CONTRACT.md §2)."""
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]

    present = {
        (path, method)
        for path, item in paths.items()
        for method in item
    }
    missing = EXPECTED_PATHS - present
    assert not missing, f"OpenAPI schema is missing endpoints: {sorted(missing)}"


def test_docs_are_browsable(client):
    """The Swagger UI docs page is served (CONTRACT.md §2)."""
    response = client.get("/docs")
    assert response.status_code == 200


# --------------------------------------------------------------------------- #
# 8.1 — each operation reachable over the real engine on the frozen dataset.   #
# --------------------------------------------------------------------------- #


@requires_engine_input
def test_run_analysis_endpoint_returns_a_handle(client):
    """POST /runs materialises a Run and returns a contract RunHandle (1.1)."""
    response = client.post("/runs", json={"scenario": SCENARIO_A})

    assert response.status_code == 200
    handle = response.json()
    assert handle["run_id"]
    assert handle["scenario"] == SCENARIO_A
    assert handle["weights_id"] == SCENARIO_A


@requires_engine_input
def test_run_analysis_accepts_explicit_weights(client):
    """POST /runs accepts an explicit weights configuration (Requirement 4.1)."""
    body = {
        "weights": {
            "criteria": [
                {"feature": "wind_speed", "weight": 0.5,
                 "direction": "higher_is_better", "rationale": "resource"},
                {"feature": "dist_transmission_km", "weight": 0.1,
                 "direction": "lower_is_better", "rationale": "connection cost"},
                {"feature": "demand_proxy", "weight": 0.1,
                 "direction": "higher_is_better", "rationale": "offtake"},
                {"feature": "dist_substation_km", "weight": 0.1,
                 "direction": "lower_is_better", "rationale": "interconnection"},
                {"feature": "slope_deg", "weight": 0.1,
                 "direction": "lower_is_better", "rationale": "civil works"},
                {"feature": "inside_rez", "weight": 0.1,
                 "direction": "higher_is_better", "rationale": "policy signal"},
            ]
        }
    }
    response = client.post("/runs", json=body)

    assert response.status_code == 200
    handle = response.json()
    assert handle["run_id"]
    # An explicit-weights Run carries no scenario and a content-derived id.
    assert handle["scenario"] is None
    assert handle["weights_id"]


@requires_engine_input
def test_ranked_results_endpoint_serves_the_run(client):
    """GET /runs/{id}/results returns ranked rows over the real Scored_Table (1.2)."""
    run_id = client.post("/runs", json={"scenario": SCENARIO_A}).json()["run_id"]

    response = client.get(f"/runs/{run_id}/results")

    assert response.status_code == 200
    rows = response.json()
    assert rows, "a real Run has at least one eligible cell"
    ranks = [row["rank"] for row in rows]
    assert ranks == sorted(ranks), "rows are ordered ascending by rank"
    assert ranks[0] == 1
    for row in rows:
        assert 0.0 <= row["suitability_score"] <= 1.0
        assert row["key_components"], "each ranked row carries its components"


@requires_engine_input
@requires_eligibility_table
def test_exclusions_endpoint_serves_excluded_cells(client):
    """GET /runs/{id}/exclusions returns excluded cells with reasons (1.4)."""
    run_id = client.post("/runs", json={"scenario": SCENARIO_A}).json()["run_id"]

    response = client.get(f"/runs/{run_id}/exclusions")

    assert response.status_code == 200
    rows = response.json()
    assert rows, "the frozen dataset excludes cells"
    for row in rows:
        assert row["reason_codes"], "every excluded cell names a machine code"
        assert row["reason_text"], "every excluded cell names a human reason"


def test_data_quality_endpoint_serves_status_or_fails_honestly(client):
    """
    GET /data-quality surfaces the S2-02 status (1.6, 5.1-5.3).

    The Data_Quality_Status is the S2-02 Validation_Result sidecar. When it has
    been materialised the endpoint returns a 200 with the verdict + per-check
    records; when it is absent the service FAILS HONESTLY with a 503 naming the
    missing input rather than fabricating a passing verdict (Requirement 5.3,
    7.3). Both are contract-correct, so this test accepts either and asserts the
    corresponding shape.
    """
    dq_path = service_config.data_quality_result_path()
    response = client.get("/data-quality")

    if dq_path.exists():
        assert response.status_code == 200
        status = response.json()
        assert isinstance(status["passed"], bool)
        assert isinstance(status["checks"], list)
        for check in status["checks"]:
            assert set(check) >= {"name", "expected", "observed", "passed"}
    else:
        assert response.status_code == 503
        assert "Data_Quality_Status is missing" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# 8.2 — one engine output: ranked results and site detail agree (Property P1). #
# --------------------------------------------------------------------------- #


@requires_engine_input
def test_ranked_results_and_site_detail_agree_on_score_and_rank(client):
    """
    For the same ``cell_id`` in a Run, GET /results and GET /sites/{cell_id}
    return the IDENTICAL score and rank (Requirement 2.3, 8.2 / Property P1).
    """
    run_id = client.post("/runs", json={"scenario": SCENARIO_A}).json()["run_id"]
    rows = client.get(f"/runs/{run_id}/results").json()
    assert rows

    # Check the top cell and a mid-ranked cell, so the guarantee is exercised
    # across the ranking rather than only at rank 1.
    sample = [rows[0], rows[len(rows) // 2], rows[-1]]
    for row in sample:
        detail = client.get(f"/runs/{run_id}/sites/{row['cell_id']}").json()
        assert detail["suitability_score"] == row["suitability_score"]
        assert detail["rank"] == row["rank"]
        assert detail["eligible"] is True
        # The detail's contributions are the same shares the ranked row exposes.
        assert detail["contributions"] == row["key_components"]
        # A verbatim S2-06 explanation is served for the cell.
        assert detail["explanation"].get("cell_id") == row["cell_id"]


# --------------------------------------------------------------------------- #
# 8.3 — a Display_Filter changes the set but never scores/ranks (Property P2).  #
# --------------------------------------------------------------------------- #


@requires_engine_input
def test_top_n_filter_changes_set_but_not_scores_or_ranks(client):
    """top_n narrows the returned set to a rank-order prefix; values unchanged."""
    run_id = client.post("/runs", json={"scenario": SCENARIO_A}).json()["run_id"]
    unfiltered = client.get(f"/runs/{run_id}/results").json()
    assert len(unfiltered) > 5, "need enough cells to see top_n narrow the set"
    by_cell = {row["cell_id"]: row for row in unfiltered}

    filtered = client.get(f"/runs/{run_id}/results", params={"top_n": 5}).json()

    # The SET changed: exactly the five lowest-rank cells, in rank order.
    assert len(filtered) == 5
    assert [r["cell_id"] for r in filtered] == [r["cell_id"] for r in unfiltered[:5]]
    # But no score or rank changed for any surviving cell (no re-score).
    for row in filtered:
        assert row["suitability_score"] == by_cell[row["cell_id"]]["suitability_score"]
        assert row["rank"] == by_cell[row["cell_id"]]["rank"]


@requires_engine_input
def test_min_score_filter_changes_set_but_not_scores_or_ranks(client):
    """min_score narrows the set to cells above the threshold; values unchanged."""
    run_id = client.post("/runs", json={"scenario": SCENARIO_A}).json()["run_id"]
    unfiltered = client.get(f"/runs/{run_id}/results").json()
    by_cell = {row["cell_id"]: row for row in unfiltered}

    # A threshold strictly between the min and max score, so it excludes some
    # cells but keeps others — a real change to the returned set.
    scores = sorted(row["suitability_score"] for row in unfiltered)
    threshold = scores[len(scores) // 2]

    filtered = client.get(
        f"/runs/{run_id}/results", params={"min_score": threshold}
    ).json()

    assert 0 < len(filtered) < len(unfiltered), "the threshold changed the set"
    for row in filtered:
        assert row["suitability_score"] >= threshold
        # Ranks and scores are the engine's, preserved under the filter.
        assert row["suitability_score"] == by_cell[row["cell_id"]]["suitability_score"]
        assert row["rank"] == by_cell[row["cell_id"]]["rank"]


@requires_engine_input
def test_all_excluding_threshold_is_empty_but_valid(client):
    """An all-excluding threshold returns an empty 200, not an error (3.4)."""
    run_id = client.post("/runs", json={"scenario": SCENARIO_A}).json()["run_id"]

    response = client.get(f"/runs/{run_id}/results", params={"min_score": 2.0})

    assert response.status_code == 200
    assert response.json() == []


@requires_engine_input
def test_top_n_beyond_eligible_count_returns_all_no_padding(client):
    """top_n over the eligible count returns every eligible cell, no padding (3.3)."""
    run_id = client.post("/runs", json={"scenario": SCENARIO_A}).json()["run_id"]
    unfiltered = client.get(f"/runs/{run_id}/results").json()

    filtered = client.get(
        f"/runs/{run_id}/results", params={"top_n": len(unfiltered) + 1000}
    ).json()

    assert len(filtered) == len(unfiltered)
    assert [r["cell_id"] for r in filtered] == [r["cell_id"] for r in unfiltered]


# --------------------------------------------------------------------------- #
# 8.4 — compare_scenarios reuses the engine, returns a rank comparison (P5).   #
# --------------------------------------------------------------------------- #


@requires_engine_input
def test_scenario_comparison_returns_per_cell_rank_comparison(client):
    """
    POST /scenario-comparison compares two scenarios' ranks per cell (1.5, 8.4).

    Each scenario's ranks must equal what an independent run of that scenario
    produces via GET /results — proving the comparison REUSES the engine rather
    than running a second scorer (Property P5).
    """
    response = client.post(
        "/scenario-comparison",
        json={"scenario_a": SCENARIO_A, "scenario_b": SCENARIO_B},
    )

    assert response.status_code == 200
    comparison = response.json()
    assert comparison["labels"] == {"a": SCENARIO_A, "b": SCENARIO_B}
    rows = comparison["rows"]
    assert rows, "the comparison covers the eligible population"

    # rank_delta is exactly rank_a - rank_b where both are present, else null.
    for row in rows:
        if row["rank_a"] is not None and row["rank_b"] is not None:
            assert row["rank_delta"] == row["rank_a"] - row["rank_b"]
        else:
            assert row["rank_delta"] is None

    # ENGINE REUSE: the ranks in the comparison equal each scenario's own Run.
    run_a = client.post("/runs", json={"scenario": SCENARIO_A}).json()["run_id"]
    ranks_a = {r["cell_id"]: r["rank"] for r in client.get(f"/runs/{run_a}/results").json()}
    for row in rows:
        if row["rank_a"] is not None:
            assert ranks_a.get(row["cell_id"]) == row["rank_a"]


# --------------------------------------------------------------------------- #
# 8.5 — honest failure (CONTRACT.md §6, Property P6).                          #
# --------------------------------------------------------------------------- #


def test_missing_run_results_returns_404(client):
    """A missing Run -> 404 naming the Run (Requirement 7.1)."""
    response = client.get("/runs/nope000000000000/results")

    assert response.status_code == 404
    assert "nope000000000000" in response.json()["detail"]


def test_missing_run_site_detail_returns_404(client):
    """A missing Run on the site-detail path -> 404 (Requirement 7.1)."""
    response = client.get("/runs/nope000000000000/sites/c1")

    assert response.status_code == 404
    assert "nope000000000000" in response.json()["detail"]


@requires_engine_input
def test_missing_cell_id_returns_404(client):
    """A missing cell_id in a real Run -> 404 naming the cell (Requirement 7.2)."""
    run_id = client.post("/runs", json={"scenario": SCENARIO_A}).json()["run_id"]

    response = client.get(f"/runs/{run_id}/sites/NOPE_CELL")

    assert response.status_code == 404
    assert "NOPE_CELL" in response.json()["detail"]


def test_missing_engine_output_returns_503(client, monkeypatch, tmp_path):
    """
    A missing materialised engine output -> 503 naming the input (Requirement
    7.3). Here the explanation output is pointed at a non-existent file, so the
    site-detail read fails honestly rather than fabricating a result.
    """
    # Materialise a real Run so the Scored_Table exists, then break one input.
    if not ENGINE_INPUT_AVAILABLE:
        pytest.skip(f"integrated feature table not built: {INTEGRATED_PATH}")

    run_id = client.post("/runs", json={"scenario": SCENARIO_A}).json()["run_id"]
    top_cell = client.get(f"/runs/{run_id}/results").json()[0]["cell_id"]

    monkeypatch.setattr(
        service_config, "EXPLANATION_PATH", tmp_path / "absent_explanations.json"
    )

    response = client.get(f"/runs/{run_id}/sites/{top_cell}")

    assert response.status_code == 503
    assert "Explanation output is missing" in response.json()["detail"]


def test_unknown_scenario_returns_422(client):
    """An unknown scenario -> 422; no Run created (Requirement 4.4)."""
    response = client.post("/runs", json={"scenario": "no_such_scenario"})

    assert response.status_code == 422
    assert "no_such_scenario" in response.json()["detail"]


def test_invalid_weights_returns_422(client):
    """A negative weight -> 422 from the engine's own parser; no Run (Requirement 4.4)."""
    body = {
        "weights": {
            "criteria": [
                {"feature": "wind_speed", "weight": -1.0,
                 "direction": "higher_is_better", "rationale": "invalid"},
            ]
        }
    }
    response = client.post("/runs", json=body)

    assert response.status_code == 422


def test_scenario_comparison_unknown_scenario_returns_422(client):
    """An unknown scenario on the comparison path -> 422 (Requirement 4.4)."""
    response = client.post(
        "/scenario-comparison",
        json={"scenario_a": SCENARIO_A, "scenario_b": "no_such_scenario"},
    )

    assert response.status_code == 422
    assert "no_such_scenario" in response.json()["detail"]
