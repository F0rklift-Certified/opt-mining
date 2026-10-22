"""
S3-01a doc/example test — ADR-0003 and the documented run commands.

Covers the "ADR / docs" example checks in the S3-01a design's Testing Strategy:

* ``docs/adr/ADR-0003-web-stack-nextjs-fastapi-http-openapi.md`` exists, states
  the React/Next.js + FastAPI over HTTP/OpenAPI decision, and notes that it
  fixes the S2-08 ``Decision_Service`` boundary as HTTP + OpenAPI (not an
  in-process module);
* the ADR is referenced from
  ``Sprint-3-Tasks/S3-01a-Application-Shell-Scaffold.md``; and
* ``app/README.md`` documents the run commands: the ``uvicorn`` backend
  command, ``next dev``, ``next build`` / ``next start``, and the
  single-command ``docker compose up --build``.

These are documentation surfaces (fixed content, not universal properties), so
they are covered by example assertions rather than property-based tests.

Validates: Requirements 5.1, 5.2, 7.1, 7.2, 7.3
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def _collapse_ws(text: str) -> str:
    """Collapse all runs of whitespace to single spaces (line-wrap agnostic)."""
    return re.sub(r"\s+", " ", text)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

ADR_PATH = (
    PROJECT_ROOT
    / "docs"
    / "adr"
    / "ADR-0003-web-stack-nextjs-fastapi-http-openapi.md"
)
SPRINT3_DOC_PATH = (
    PROJECT_ROOT / "Sprint-3-Tasks" / "S3-01a-Application-Shell-Scaffold.md"
)
APP_README_PATH = PROJECT_ROOT / "app" / "README.md"


@pytest.fixture(scope="module")
def adr_text() -> str:
    assert ADR_PATH.exists(), f"ADR-0003 is missing at {ADR_PATH}"
    return ADR_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sprint3_doc_text() -> str:
    assert SPRINT3_DOC_PATH.exists(), (
        f"Sprint 3 task doc is missing at {SPRINT3_DOC_PATH}"
    )
    return SPRINT3_DOC_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app_readme_text() -> str:
    assert APP_README_PATH.exists(), f"app/README.md is missing at {APP_README_PATH}"
    return APP_README_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Requirement 7.1 — the ADR states the React/Next.js + FastAPI over
# HTTP/OpenAPI choice.
# ---------------------------------------------------------------------------


def test_adr_exists_and_states_the_stack_choice(adr_text: str):
    lowered = adr_text.lower()
    # The decision names both frameworks, the transport, and the contract form.
    assert "next.js" in lowered
    assert "react" in lowered
    assert "fastapi" in lowered
    assert "http" in lowered
    assert "openapi" in lowered

    # It is expressed as an explicit Decision (Context / Decision / Consequences
    # ADR form), not merely mentioned in passing.
    assert "## decision" in lowered


# ---------------------------------------------------------------------------
# Requirement 7.2 — the ADR notes the S2-08 boundary is fixed as HTTP + OpenAPI
# (not in-process).
# ---------------------------------------------------------------------------


def test_adr_notes_s2_08_boundary_fixed_as_http_openapi_not_in_process(adr_text: str):
    lowered = adr_text.lower()

    assert "s2-08" in lowered
    assert "decision_service" in lowered
    # The boundary is fixed as HTTP + OpenAPI ...
    assert "boundary" in lowered
    # ... and explicitly NOT an in-process module.
    assert "in-process" in lowered

    # The negation and the boundary sit together in one statement, so the ADR
    # actually contrasts HTTP + OpenAPI against an in-process module rather than
    # mentioning "in-process" incidentally elsewhere. Collapse whitespace first
    # so the check is agnostic to the ADR's Markdown line wrapping.
    collapsed = _collapse_ws(lowered)
    assert "http + openapi" in collapsed
    assert "not an in-process module" in collapsed


# ---------------------------------------------------------------------------
# Requirement 7.3 — the ADR is referenced from the Sprint 3 documentation.
# ---------------------------------------------------------------------------


def test_adr_referenced_from_sprint3_doc(sprint3_doc_text: str):
    # The Sprint 3 task doc links to the ADR file by its exact filename.
    assert "ADR-0003-web-stack-nextjs-fastapi-http-openapi.md" in sprint3_doc_text
    # And names it, so the reference is legible, not just a bare path.
    assert "ADR-0003" in sprint3_doc_text


# ---------------------------------------------------------------------------
# Requirements 5.1, 5.2 — app/README.md documents the run commands.
# ---------------------------------------------------------------------------


def test_readme_documents_the_uvicorn_backend_command(app_readme_text: str):
    # R5.1 — a command to run the Backend_App (uvicorn).
    assert "uvicorn app:app" in app_readme_text


def test_readme_documents_next_dev(app_readme_text: str):
    # R5.2 — the development command.
    assert "next dev" in app_readme_text


def test_readme_documents_next_build_and_next_start(app_readme_text: str):
    # R5.2 — the built/production commands.
    assert "next build" in app_readme_text
    assert "next start" in app_readme_text


def test_readme_documents_docker_compose_up_build(app_readme_text: str):
    # R6.3 / clean-environment single-command start.
    assert "docker compose up --build" in app_readme_text
