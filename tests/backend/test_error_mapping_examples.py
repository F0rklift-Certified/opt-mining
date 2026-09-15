"""
Example tests for the CONTRACT.md §6 error-mapping rows (S3-01a, task 4.6).

Feature: s3-01a-application-shell-scaffold — Backend_App error mapping.

CONTRACT.md §6 freezes, per condition, both the HTTP status code the service
returns AND the guarantee that it fails *clearly* (naming the fault) rather than
returning a misleading empty success — and, conversely, that a genuinely
empty-but-valid result stays a `200`, never an error. Task 4.3 realises that
mapping in `app/api/app.py` as a single fault-class -> HTTP-status table:

    | Condition                                | Exception          | HTTP |
    | ---------------------------------------- | ------------------ | ---- |
    | Invalid weights / unknown Scenario       | ScoringConfigError | 422  |
    | Requested Run does not exist             | RunNotFoundError   | 404  |
    | Requested cell_id not in the Run         | CellNotFoundError  | 404  |
    | A materialised engine output is missing  | EngineOutputError  | 503  |
    | Top-N exceeds the eligible count         | (empty list)       | 200  |
    | min_score excludes every cell            | (empty list)       | 200  |

This module exercises EACH row against the real FastAPI app through a
`TestClient`, asserting the frozen status code and — for the error rows — a
fault-naming body. The five operations are driven to raise the specific fault
by monkeypatching the operation the handler calls on the loaded ``app`` module
(the handlers call the module-level names bound by ``from pipeline.service
import ...``); the two empty-but-valid rows monkeypatch the read operation to
return an empty list so the assertion is deterministic regardless of whether the
frozen dataset is materialised on the test machine.

`raise_server_exceptions=False` lets the app's registered exception handlers
produce the mapped HTTP responses (rather than TestClient re-raising), which is
exactly the transport-boundary behaviour under test.

Validates: Requirements 2.4.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# The service fault taxonomy — the concrete exception classes the app maps to
# the frozen §6 codes. Imported from the SAME modules app.py imports them from,
# so the test raises exactly the types the handlers are registered against.
from pipeline.scoring.weights import ScoringConfigError
from pipeline.service.runs import (
    CellNotFoundError,
    EngineOutputError,
    RunNotFoundError,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "app" / "api"
APP_PATH = API_DIR / "app.py"


def _load_app_module():
    """
    Load ``app/api/app.py`` as a standalone module, mirroring how the app is
    actually launched (``uvicorn app:app`` with working dir = ``app/api/``).

    `app.py` does plain absolute imports of its sibling ``settings`` / ``models``
    modules, so ``app/api/`` must be on ``sys.path`` for the load to succeed. A
    valid ``CORS_ALLOW_ORIGINS`` is set before import purely so middleware
    installation has a well-formed value; it does not affect the error mapping
    under test.
    """
    os.environ.setdefault("CORS_ALLOW_ORIGINS", "http://localhost:3000")
    api_dir = str(API_DIR)
    if api_dir not in sys.path:
        sys.path.insert(0, api_dir)
    spec = importlib.util.spec_from_file_location("optmining_api_app", APP_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load {APP_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def app_module():
    return _load_app_module()


@pytest.fixture()
def client(app_module):
    # raise_server_exceptions=False so the app's own exception handlers map the
    # service faults to their frozen HTTP responses instead of TestClient
    # re-raising the exception — that mapping is the behaviour under test.
    with TestClient(app_module.app, raise_server_exceptions=False) as test_client:
        yield test_client


def _assert_names_fault(body: dict, *needles: str) -> None:
    """A §6 error body must NAME the fault (never a bare/empty success)."""
    assert "detail" in body, f"error body must carry a `detail`: {body!r}"
    detail = body["detail"]
    assert isinstance(detail, str) and detail.strip(), (
        f"error `detail` must be a non-empty description: {body!r}"
    )
    for needle in needles:
        assert needle in detail, (
            f"error body must name the fault ({needle!r}); got {detail!r}"
        )


# ---------------------------------------------------------------------------
# 422 — invalid weights / unknown scenario (ScoringConfigError)
# ---------------------------------------------------------------------------


def test_422_invalid_weights_names_the_fault(client, app_module, monkeypatch):
    """
    Invalid weights -> `run_analysis` raises `ScoringConfigError`; the app maps
    it to `422` with a body naming the fault, and creates no Run (§6 row 1).
    """
    message = "criterion 'wind_speed' weight must be non-negative; got -0.5"

    def _raise(*_args, **_kwargs):
        raise ScoringConfigError(message)

    monkeypatch.setattr(app_module, "run_analysis", _raise)

    # A schema-VALID body (a well-formed weights object) so FastAPI does not
    # short-circuit with its own request-schema 422 — the 422 under test is the
    # operation's weight-SEMANTICS fault, not a request-shape failure.
    response = client.post(
        "/runs",
        json={
            "weights": {
                "criteria": [
                    {
                        "feature": "wind_speed",
                        "weight": -0.5,
                        "direction": "higher_is_better",
                        "rationale": "resource",
                    }
                ]
            }
        },
    )

    assert response.status_code == 422
    _assert_names_fault(response.json(), "wind_speed")


def test_422_unknown_scenario_names_the_fault(client, app_module, monkeypatch):
    """
    An unknown scenario -> `run_analysis` raises `ScoringConfigError`; mapped to
    `422` naming the bad scenario, no Run created (§6 row 1, scenario variant).
    """
    message = "unknown scenario 'nope'; known scenarios: grid_led, wind_led"

    def _raise(*_args, **_kwargs):
        raise ScoringConfigError(message)

    monkeypatch.setattr(app_module, "run_analysis", _raise)

    response = client.post("/runs", json={"scenario": "nope"})

    assert response.status_code == 422
    _assert_names_fault(response.json(), "nope")


def test_422_unknown_scenario_on_comparison_names_the_fault(
    client, app_module, monkeypatch
):
    """
    An unknown scenario given to `compare_scenarios` (`POST /scenario-comparison`)
    -> `ScoringConfigError` -> `422` naming the fault (§6 row 1, second route).
    """
    message = "unknown scenario 'ghost'; known scenarios: grid_led, wind_led"

    def _raise(*_args, **_kwargs):
        raise ScoringConfigError(message)

    monkeypatch.setattr(app_module, "compare_scenarios", _raise)

    response = client.post(
        "/scenario-comparison",
        json={"scenario_a": "ghost", "scenario_b": "wind_led"},
    )

    assert response.status_code == 422
    _assert_names_fault(response.json(), "ghost")


# ---------------------------------------------------------------------------
# 404 — missing Run (RunNotFoundError)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "operation"),
    [
        ("/runs/deadbeef/results", "get_ranked_results"),
        ("/runs/deadbeef/exclusions", "get_exclusions"),
        ("/runs/deadbeef/sites/S30.186_E151.636", "get_site_detail"),
    ],
)
def test_404_missing_run_names_the_run(client, app_module, monkeypatch, path, operation):
    """
    A read for a non-existent `run_id` -> `RunNotFoundError` -> `404` naming the
    missing Run, across every read route that resolves a Run (§6 row 2).
    """
    run_id = "deadbeef"

    def _raise(*_args, **_kwargs):
        raise RunNotFoundError(f"no materialised Run {run_id!r}")

    monkeypatch.setattr(app_module, operation, _raise)

    response = client.get(path)

    assert response.status_code == 404
    _assert_names_fault(response.json(), run_id)


# ---------------------------------------------------------------------------
# 404 — missing cell (CellNotFoundError): the Run exists, the cell does not
# ---------------------------------------------------------------------------


def test_404_missing_cell_names_the_cell(client, app_module, monkeypatch):
    """
    `get_site_detail` for a Run that exists but a `cell_id` that does not ->
    `CellNotFoundError` -> `404` naming the missing cell (§6 row 3).
    """
    cell_id = "S99.999_E999.999"

    def _raise(*_args, **_kwargs):
        raise CellNotFoundError(f"cell {cell_id!r} is not in Run 'abc123'")

    monkeypatch.setattr(app_module, "get_site_detail", _raise)

    response = client.get(f"/runs/abc123/sites/{cell_id}")

    assert response.status_code == 404
    _assert_names_fault(response.json(), cell_id)


# ---------------------------------------------------------------------------
# 503 — missing/unreadable engine output (EngineOutputError): body NAMES input
# ---------------------------------------------------------------------------


def test_503_missing_engine_output_names_the_missing_input(
    client, app_module, monkeypatch
):
    """
    An operation whose materialised engine output is absent/unreadable ->
    `EngineOutputError` -> `503`, and the body NAMES the missing input (§6 row 4;
    `get_data_quality` reads the S2-02 validation JSON).
    """
    missing_input = "DATA/integration/metadata/integrated_input_validation.json"

    def _raise(*_args, **_kwargs):
        raise EngineOutputError(f"data-quality input is missing: {missing_input}")

    monkeypatch.setattr(app_module, "get_data_quality", _raise)

    response = client.get("/data-quality")

    assert response.status_code == 503
    # The 503 body must NAME the missing input, not merely say "unavailable".
    _assert_names_fault(response.json(), missing_input)


# ---------------------------------------------------------------------------
# 200 — empty-but-valid: BOTH filter cases return an empty list, NOT an error
# ---------------------------------------------------------------------------


def test_200_top_n_beyond_eligible_count_is_empty_but_valid(
    client, app_module, monkeypatch
):
    """
    `top_n` beyond the eligible count is empty-but-valid: the service returns an
    (empty here) list and the app serves `200` with a JSON array — never an
    error, never a fabricated padding row (§6 row 5, Requirement 3.3).
    """
    captured: dict = {}

    def _empty(run_id, *, top_n=None, min_score=None):
        # Record the pass-through args to confirm the filter reached the
        # operation unchanged (the API adds no filtering of its own).
        captured["run_id"] = run_id
        captured["top_n"] = top_n
        captured["min_score"] = min_score
        return []

    monkeypatch.setattr(app_module, "get_ranked_results", _empty)

    response = client.get("/runs/abc123/results", params={"top_n": 100000})

    assert response.status_code == 200
    assert response.json() == []
    assert captured == {"run_id": "abc123", "top_n": 100000, "min_score": None}


def test_200_all_excluding_min_score_is_empty_but_valid(
    client, app_module, monkeypatch
):
    """
    A `min_score` threshold that excludes every cell is empty-but-valid: the
    service returns an empty list and the app serves `200` with `[]` — never a
    `404`/`503`/`422` (§6 row 6, Requirement 3.4).
    """
    captured: dict = {}

    def _empty(run_id, *, top_n=None, min_score=None):
        captured["run_id"] = run_id
        captured["top_n"] = top_n
        captured["min_score"] = min_score
        return []

    monkeypatch.setattr(app_module, "get_ranked_results", _empty)

    response = client.get("/runs/abc123/results", params={"min_score": 1.0})

    assert response.status_code == 200
    assert response.json() == []
    assert captured == {"run_id": "abc123", "top_n": None, "min_score": 1.0}
