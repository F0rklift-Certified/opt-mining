"""
S3-09 end-to-end integration test — frozen integrated dataset -> decision
engine -> API/app output.

This is the single test the S3-09 acceptance criterion "integration tests cover
the end-to-end flow (frozen dataset -> engine -> app output)" names. It exercises
the WHOLE chain in-process, with NO network and NO Docker:

* the **frozen integrated dataset** committed under
  ``DATA/integration/optmining_integrated-features_2026_nsw.gpkg`` (git-tracked,
  so present in CI),
* the **decision engine** (score / rank / explain / exclude), which the
  ``pipeline.service`` layer re-materialises from that frozen table at request
  time, and
* the **API/app output** surface — the published FastAPI ``Decision_Service``
  (``pipeline.service.app``), the exact HTTP contract the Sprint 3 web
  application generates its typed client from — driven through FastAPI's
  ``TestClient``.

Because the frozen inputs are committed and the service runs in-process, the
test needs **no container**. It therefore carries **no** ``integration`` marker:
the ``integration`` marker is reserved for Docker/Compose-tier tests and both CI
pytest steps exclude it with ``-m "not integration"``. This module lives under
``tests/integration/`` so CI's **"Run remaining non-Docker tests"** step
(``pytest -v -m "not integration" --ignore=tests/backend``) collects and runs it.

HERMETIC AND CI-SAFE. The per-Run materialisation store (``RUNS_DIR``) is
redirected to a temp directory, so the test never writes under ``DATA/service/``
and leaves no residue — exactly as the S2-08 contract test
(``tests/service/test_contract_integration.py``) does. The module skips cleanly
in a checkout without the built dataset; it does NOT skip when the dataset is
present (as it is here and in CI).

The assertions here are deliberately **behavioural** — the ordered contract
surface of the end-to-end flow — rather than pinned to the snapshot literals in
``tests/backend/test_backend_decision_flow.py`` (that file owns the
pinned-snapshot guarantee; this test owns the API-surface flow guarantee), so
the two do not duplicate the same maintenance burden.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.scoring import config as scoring_config
from pipeline.service import config as service_config

# fastapi/httpx are S2-08 transport deps (requirements.txt + the CI
# `pip install httpx` step); skip the whole module with a clear reason if the
# transport layer is somehow absent rather than erroring at collection.
fastapi_testclient = pytest.importorskip(
    "fastapi.testclient",
    reason="fastapi/httpx not installed (S2-08 transport deps in requirements.txt)",
)
TestClient = fastapi_testclient.TestClient

from pipeline.service.app import app  # noqa: E402  (after importorskip)

# The frozen integrated dataset is the engine's sole feature input. It is
# git-tracked, so it is present here and in CI; the skip guards only a bare
# checkout that has not built the dataset.
INTEGRATED_PATH = Path(scoring_config.INTEGRATED_PATH)
requires_frozen_dataset = pytest.mark.skipif(
    not INTEGRATED_PATH.exists(),
    reason=f"frozen integrated dataset not built: {INTEGRATED_PATH}",
)

# A named Scenario present in the packaged scenarios.yaml.
SCENARIO = "wind_led"


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    """
    A ``TestClient`` over the FastAPI app with the per-Run store redirected.

    ``runs.py`` reads ``config.RUNS_DIR`` at call time, so patching it here keeps
    every Run this test materialises inside ``tmp_path`` — the test is hermetic
    and never writes under ``DATA/service/`` (CI-safe).
    """
    monkeypatch.setattr(service_config, "RUNS_DIR", tmp_path / "runs")
    return TestClient(app)


@requires_frozen_dataset
def test_frozen_dataset_flows_through_engine_to_app_output(client):
    """
    Drive the full flow end to end on the frozen dataset and assert the ordered
    API contract holds at every hop.

    (a) ``POST /runs`` materialises a Run over the frozen integrated table and
        returns a RunHandle.
    (b) ``GET /runs/{id}/results`` returns rank-ordered rows with
        ``0 <= suitability_score <= 1``, ``rank`` ascending from 1 and non-empty
        ``key_components`` — the engine's scored output surfaced by the app.
    (c) ``GET /runs/{id}/sites/{cell_id}`` for the top cell returns the IDENTICAL
        score and rank as its ranked row, ``eligible is True``,
        ``contributions == key_components`` and a verbatim S2-06 ``explanation``
        whose ``cell_id`` matches — the one-engine-output guarantee, proving the
        same frozen dataset flows through scoring -> explanation -> API.
    (d) ``GET /runs/{id}/exclusions`` returns excluded cells each carrying
        ``reason_codes`` + ``reason_text`` — the frozen exclusions surfaced.
    (e) ``GET /data-quality`` returns the S2-02 verdict shape (200-with-checks)
        or fails honestly with a 503 naming the missing input — both are
        contract-correct, exactly as the S2-08 contract test accepts.
    """
    # (a) Create a Run from the frozen integrated dataset.
    create = client.post("/runs", json={"scenario": SCENARIO})
    assert create.status_code == 200, create.text
    handle = create.json()
    run_id = handle["run_id"]
    assert run_id, "a materialised Run carries an id"
    assert handle["scenario"] == SCENARIO
    assert handle["weights_id"] == SCENARIO

    # (b) The ranked results are the engine's scored output, served in order.
    results = client.get(f"/runs/{run_id}/results")
    assert results.status_code == 200, results.text
    rows = results.json()
    assert rows, "the frozen dataset yields at least one eligible, scored cell"
    ranks = [row["rank"] for row in rows]
    assert ranks == sorted(ranks), "rows are ordered ascending by rank"
    assert ranks[0] == 1, "the top-ranked cell is rank 1"
    for row in rows:
        assert 0.0 <= row["suitability_score"] <= 1.0, "scores lie in [0, 1]"
        assert row["key_components"], "each ranked row carries its contributions"

    # (c) Site detail agrees with the ranked row for the SAME cell (one engine
    #     output, Property P1) and serves the verbatim S2-06 explanation — the
    #     frozen dataset has flowed through scoring AND explanation to the app.
    top = rows[0]
    detail = client.get(f"/runs/{run_id}/sites/{top['cell_id']}")
    assert detail.status_code == 200, detail.text
    site = detail.json()
    assert site["suitability_score"] == top["suitability_score"]
    assert site["rank"] == top["rank"]
    assert site["eligible"] is True
    assert site["contributions"] == top["key_components"]
    assert site["explanation"].get("cell_id") == top["cell_id"]

    # (d) The frozen exclusions are surfaced with machine + human reasons.
    exclusions = client.get(f"/runs/{run_id}/exclusions")
    assert exclusions.status_code == 200, exclusions.text
    excluded = exclusions.json()
    assert excluded, "the frozen dataset excludes cells (e.g. protected areas)"
    for row in excluded:
        assert row["reason_codes"], "every excluded cell names a machine code"
        assert row["reason_text"], "every excluded cell names a human reason"

    # (e) Data quality: the S2-02 verdict, or an honest 503 when absent.
    dq_path = service_config.data_quality_result_path()
    dq = client.get("/data-quality")
    if dq_path.exists():
        assert dq.status_code == 200, dq.text
        status = dq.json()
        assert isinstance(status["passed"], bool)
        assert isinstance(status["checks"], list)
        for check in status["checks"]:
            assert set(check) >= {"name", "expected", "observed", "passed"}
    else:
        assert dq.status_code == 503
        assert "Data_Quality_Status is missing" in dq.json()["detail"]
