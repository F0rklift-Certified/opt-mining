"""
S3-01a backend startup smoke test.

Startup is an external, deterministic behaviour, so this is a smoke test
(design §Testing Strategy → "Backend up (smoke)"), not a property test. It pins
the two things Requirements 2.1, 2.2 and 5.3 promise about the Backend_App:

* the FastAPI application actually constructs and starts (Requirement 2.1 — the
  Backend_App is a FastAPI app exposing the S2-08 operations over HTTP); and
* its auto-generated OpenAPI surface is reachable — ``/openapi.json`` and
  ``/docs`` both return HTTP 200 (Requirement 2.2 — a machine-readable
  OpenAPI_Schema at ``/openapi.json`` with browsable docs at ``/docs``;
  Requirement 5.3 — following the documented run commands makes ``/docs`` and
  ``/openapi.json`` reachable).

The app is imported and driven through FastAPI's ``TestClient`` (Starlette's
in-process WSGI/ASGI test transport), which runs the app's startup exactly as
``uvicorn app:app`` would but without binding a socket — so this is a fast unit
smoke, and the socket-binding, documented-command variant is the separate
integration test (task 9.2).

**Validates: Requirements 2.1, 2.2, 5.3**

Import layout: ``app/api/`` is launched with its own directory as the working
directory (``uvicorn app:app`` per the design run command and the api
Dockerfile), so ``app.py`` imports its ``models`` / ``settings`` siblings as
top-level modules. This test puts ``app/api/`` on ``sys.path`` and imports
``app`` exactly as that launch does, mirroring the sibling-import convention the
env-config property test already uses to load ``app/api/settings.py`` by path.
``conftest.py`` has already put the repo root on ``sys.path`` so ``import
pipeline.service`` (which ``app.py`` delegates to) resolves.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# app/api/ is on sys.path so `import app` picks up the FastAPI entry point and
# its sibling `models` / `settings` modules resolve exactly as `uvicorn app:app`
# launches them (working dir = app/api/). The repo root is already on sys.path
# via conftest.py, so app.py's `import pipeline.service` delegation resolves.
REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "app" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

import app as backend_app  # noqa: E402  (path insert must precede the import)


@pytest.fixture(scope="module")
def client() -> TestClient:
    """A TestClient over the Backend_App.

    Constructing the client runs the app's startup in-process (no socket bound),
    which is the smoke: if the FastAPI app fails to construct or start, this
    fixture — and therefore every test — fails here (Requirement 2.1).
    """
    with TestClient(backend_app.app) as test_client:
        yield test_client


def test_backend_app_is_a_fastapi_application():
    """The Backend_App entry point is a FastAPI application (Requirement 2.1)."""
    assert isinstance(backend_app.app, FastAPI), (
        "app.app must be a FastAPI application (Requirement 2.1)"
    )


def test_openapi_json_is_reachable_and_200(client: TestClient):
    """`/openapi.json` returns 200 and a machine-readable schema (Requirement 2.2, 5.3)."""
    response = client.get("/openapi.json")
    assert response.status_code == 200, (
        f"/openapi.json must return 200 (Requirement 2.2, 5.3); "
        f"got {response.status_code}"
    )
    schema = response.json()
    # A minimal shape check so a 200 that is not actually the OpenAPI document
    # cannot pass — the schema must declare the OpenAPI version and some paths.
    assert "openapi" in schema, "/openapi.json must publish the OpenAPI version"
    assert schema.get("paths"), "/openapi.json must declare the app's paths"


def test_docs_is_reachable_and_200(client: TestClient):
    """`/docs` returns 200 (browsable OpenAPI documentation) (Requirement 2.2, 5.3)."""
    response = client.get("/docs")
    assert response.status_code == 200, (
        f"/docs must return 200 (Requirement 2.2, 5.3); got {response.status_code}"
    )
