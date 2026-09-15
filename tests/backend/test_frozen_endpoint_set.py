"""
Property-based test for the Backend_App's route table — the declared endpoint
set is EXACTLY the six frozen S2-08 operations (Property 1).

# Feature: s3-01a-application-shell-scaffold, Property 1: Endpoint set matches
# exactly the six frozen operations

**Property 1.** For ALL routes declared by the Backend_App, each declared
``(method, path)`` pair is one of the six frozen S2-08 operations, and all six
are present. The mapping is bidirectional — no extra operation endpoint is
exposed, and none is missing:

    POST /runs
    GET  /runs/{run_id}/results
    GET  /runs/{run_id}/sites/{cell_id}
    GET  /runs/{run_id}/exclusions
    POST /scenario-comparison
    GET  /data-quality

The assertion is made against the published ``/openapi.json`` read through
FastAPI's ``TestClient`` — the same machine-readable contract the frontend and
any generated client consume (CONTRACT.md preamble: where the OpenAPI schema and
CONTRACT.md disagree, the schema is authoritative). Checking the schema rather
than ``app.routes`` therefore guards the frozen contract's surface directly and
catches an endpoint that is registered but not surfaced in the schema (or vice
versa). FastAPI's auto-generated documentation endpoints (``/openapi.json``,
``/docs``, ``/docs/oauth2-redirect``, ``/redoc``) are the schema-serving surface,
not decision operations, and are correctly absent from ``schema["paths"]`` — so
``schema["paths"]`` is exactly the operation table with no filtering needed.

**Validates: Requirements 2.2, 2.3**

The test has a generative half and an exactness half:

* **Executable/generative half (Hypothesis).** The declared ``(method, path)``
  pairs are read once from ``/openapi.json``. Hypothesis then samples individual
  declared pairs (``>= 100`` examples) and asserts each sampled pair is a member
  of the frozen six — so ANY extra route that slips into the schema is caught as
  a non-member on the example that samples it. This is the "for all declared
  routes, each is one of the six" direction stated by the property.

* **Exactness half.** A single set-equality assertion pins the declared set to
  the frozen set — catching both an extra route (set too large) and a missing
  one (set too small) at once, which is the bidirectional claim the property
  makes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# `app/api/` is launched with its own directory as the working dir
# (`uvicorn app:app`), so `app.py` imports `settings` / `models` as sibling
# top-level modules and imports `pipeline.service`. To load it under pytest we
# put `app/api/` on `sys.path` (so the sibling imports resolve) — conftest.py
# already puts the repo root on `sys.path` so `import pipeline` works. This
# mirrors how the app is actually run, without needing `app/api/` to be a
# package.
REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "app" / "api"


def _load_app():
    """Load `app/api/app.py` as a standalone module (matches launch layout)."""
    api_dir = str(API_DIR)
    if api_dir not in sys.path:
        sys.path.insert(0, api_dir)
    spec = importlib.util.spec_from_file_location(
        "optmining_api_app", API_DIR / "app.py"
    )
    assert spec is not None and spec.loader is not None, f"cannot load {API_DIR}/app.py"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- The six frozen S2-08 operations (CONTRACT.md §2, Requirement 2.3) --------
#
# Written verbatim from the contract, NOT derived from the app under test, so the
# test genuinely pins the route table to the frozen surface.
FROZEN_ENDPOINTS: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/runs"),
        ("GET", "/runs/{run_id}/results"),
        ("GET", "/runs/{run_id}/sites/{cell_id}"),
        ("GET", "/runs/{run_id}/exclusions"),
        ("POST", "/scenario-comparison"),
        ("GET", "/data-quality"),
    }
)


def _declared_endpoints() -> set[tuple[str, str]]:
    """Read the declared ``(METHOD, path)`` pairs from the published OpenAPI schema.

    Uses FastAPI's ``TestClient`` to fetch ``/openapi.json`` — the machine-readable
    contract, so the assertion guards the surface the frontend/client actually
    sees. ``schema["paths"]`` holds only the operation endpoints; FastAPI's own
    docs endpoints (``/openapi.json``, ``/docs``, ``/redoc``) are served outside
    the schema and so never appear here.
    """
    from fastapi.testclient import TestClient

    app_module = _load_app()
    with TestClient(app_module.app) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200, (
        f"/openapi.json must be reachable (Requirement 2.2); got {response.status_code}"
    )
    schema = response.json()
    return {
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        for method in operations
    }


# Resolve the declared set once at import time; every assertion reads from it.
DECLARED_ENDPOINTS: set[tuple[str, str]] = _declared_endpoints()


@settings(max_examples=150, deadline=None)
@given(data=st.data())
def test_property_1_every_declared_route_is_a_frozen_operation(data):
    """Each declared ``(method, path)`` pair is one of the six frozen operations.

    Samples individual declared routes generatively; ANY extra route in the
    schema is caught as a non-member on the example that draws it (Property 1,
    "for all declared routes, each is one of the six" — Requirement 2.2, 2.3).
    """
    # Feature: s3-01a-application-shell-scaffold, Property 1: Endpoint set matches
    # exactly the six frozen operations
    assert DECLARED_ENDPOINTS, "the app declared no OpenAPI operations at all"
    endpoint = data.draw(st.sampled_from(sorted(DECLARED_ENDPOINTS)))
    assert endpoint in FROZEN_ENDPOINTS, (
        f"declared route {endpoint[0]} {endpoint[1]} is not one of the six frozen "
        f"S2-08 operations — the API must expose EXACTLY the frozen contract "
        f"(Requirement 2.3); frozen set: {sorted(FROZEN_ENDPOINTS)}"
    )


def test_declared_endpoint_set_equals_the_six_frozen_operations_exactly():
    """The declared set equals the frozen set exactly — none extra, none missing.

    A single bidirectional set-equality: catches an extra route (superset) and a
    missing route (subset) at once (Property 1, Requirement 2.2, 2.3).
    """
    # Feature: s3-01a-application-shell-scaffold, Property 1: Endpoint set matches
    # exactly the six frozen operations
    declared = DECLARED_ENDPOINTS
    extra = declared - FROZEN_ENDPOINTS
    missing = FROZEN_ENDPOINTS - declared
    assert declared == FROZEN_ENDPOINTS, (
        "the declared endpoint set must equal EXACTLY the six frozen S2-08 "
        "operations (Requirement 2.2, 2.3).\n"
        f"  extra (declared but not frozen): {sorted(extra)}\n"
        f"  missing (frozen but not declared): {sorted(missing)}"
    )
    # Belt-and-braces: the frozen set is exactly six operations.
    assert len(declared) == 6, f"expected exactly 6 operations, got {len(declared)}"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
