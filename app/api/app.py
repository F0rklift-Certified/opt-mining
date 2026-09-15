"""
Backend_App — FastAPI application entry point (S3-01a scaffold).

Constructs a single ``FastAPI()`` instance and registers exactly the six frozen
S2-08 routes as thin delegating handlers (CONTRACT.md §2 endpoint mapping):

    POST /runs                            -> run_analysis
    GET  /runs/{run_id}/results           -> get_ranked_results
    GET  /runs/{run_id}/sites/{cell_id}   -> get_site_detail
    GET  /runs/{run_id}/exclusions        -> get_exclusions
    POST /scenario-comparison             -> compare_scenarios
    GET  /data-quality                    -> get_data_quality

Each handler is a PURE mapping layer (CONTRACT.md §1, §7-P3; Requirement 2.4,
8.2; combined-sprint AC4): it parses the request, calls the matching
`pipeline.service` operation with the request's parameters passed through
UNCHANGED (the display filters `top_n`/`min_score` go straight into
`get_ranked_results`, which owns them — CONTRACT.md §4.2), and serialises the
returned dataclass via its `to_dict()`, which is already shaped to CONTRACT.md
§5. This module holds NO weight literals, NO criteria list, and NO
normalisation, ranking, or threshold arithmetic — every decision value traces
to a materialised engine output served by the service layer.

The Pydantic models from `app/api/models.py` type each request/response so the
auto-generated OpenAPI schema (`/openapi.json`, docs at `/docs`, `/redoc`)
describes the frozen contract field-for-field. The `to_dict()` payloads the
operations return already match those models, so FastAPI validates and
serialises them into the declared `response_model`.

CORS (task 4.2) and the centralised service-exception -> HTTP-code mapping
(task 4.3) are installed once, above the routes:
  * task 4.2 — env-driven CORS middleware (`settings.get_cors_allow_origins()`);
  * task 4.3 — a single fault-class -> HTTP-status table maps the service fault
    taxonomy to the frozen CONTRACT.md §6 codes (422 invalid weights/unknown
    scenario, 404 missing run/cell, 503 missing/unreadable engine output whose
    body names the missing input). It never turns an empty-but-valid result
    into an error and never fabricates a 200 — the empty-but-valid cases (top-N
    over the eligible count, an all-excluding `min_score`) raise no exception
    and flow through as a normal 200.

Run (dev):  uvicorn app:app --reload --port 8000   (from app/api/)
"""

from __future__ import annotations

# All six frozen operations are surfaced from the service package (the two
# grounding-gap operations were closed by tasks 1.2-1.4). app.py imports them
# from that single public boundary and only delegates — it never decides.
from pipeline.service import (
    compare_scenarios,
    get_data_quality,
    get_exclusions,
    get_ranked_results,
    get_site_detail,
    run_analysis,
)

# The service fault taxonomy, imported as CONCRETE exception classes so the
# HTTP mapping catches the exception types directly — never string-matches an
# error message (design.md "Error Handling"; a small explicit taxonomy in the
# decision layer, not the transport layer). `ScoringConfigError` (a ValueError
# subclass) signals invalid weights / unknown scenario; `RunNotFoundError` and
# `CellNotFoundError` (LookupError subclasses) signal a missing Run / cell_id;
# `EngineOutputError` signals a missing/unreadable materialised engine output.
from pipeline.scoring.weights import ScoringConfigError
from pipeline.service.runs import (
    CellNotFoundError,
    EngineOutputError,
    RunNotFoundError,
)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# `app/api/` is run as the working directory (`uvicorn app:app` per the design
# run command and the api Dockerfile), so `models` and `settings` are sibling
# top-level modules rather than a package — a plain absolute import matches how
# the app is actually launched (dev + Compose). `settings` owns the env-driven
# CORS origins (no origin literal lives in this module — Requirement 4.2).
import settings
from models import (
    DataQualityStatus,
    ExcludedRow,
    RankedRow,
    RunHandle,
    RunRequest,
    ScenarioComparison,
    ScenarioComparisonRequest,
    SiteDetail,
)

app = FastAPI(
    title="Opt-Mining Decision_Service",
    description=(
        "The frozen S2-08 Decision_Service exposed over HTTP + OpenAPI. Six "
        "operations, one per endpoint; the API delegates to the pure "
        "`pipeline.service` operations and holds no decision logic "
        "(CONTRACT.md §1, §2)."
    ),
    version="1.0",
)

# ---------------------------------------------------------------------------
# Task 4.2 — env-driven CORS middleware (Requirement 4.1, 4.2).
# The allowed origins come ONLY from `settings.get_cors_allow_origins()`, which
# parses the `CORS_ALLOW_ORIGINS` env var — no origin literal appears in this
# module. The frontend↔backend boundary is HTTP (4.1); CORS is configured from
# the environment rather than hard-coded (4.2, Property 3).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Task 4.3 — centralised service-exception -> HTTP-code mapping (CONTRACT.md §6,
# Requirement 2.4, 4.1).
#
# The service operations signal faults by raising the typed exceptions imported
# above; the mapping from each fault CLASS to its frozen HTTP status lives here
# in ONE place (a single table) so it is applied uniformly across all six
# endpoints and cannot drift per-endpoint. The handlers catch the concrete
# exception classes — not error-string patterns — so the fault classification
# stays in the decision layer where it is raised, and the transport layer only
# maps it (design.md "Error Handling").
#
#   | Fault                                   | Exception          | HTTP |
#   | --------------------------------------- | ------------------ | ---- |
#   | Invalid weights / unknown scenario      | ScoringConfigError | 422  |
#   | Requested Run not found                 | RunNotFoundError   | 404  |
#   | Requested cell_id not in the Run        | CellNotFoundError  | 404  |
#   | Missing/unreadable engine output        | EngineOutputError  | 503  |
#
# Each handler returns a JSON body that NAMES the fault (the exception message,
# which already identifies the bad weights/scenario, the missing run/cell, or —
# for 503 — the missing input the operation could not read: CONTRACT.md §6
# "naming the missing input"). No handler ever converts an empty-but-valid
# result into an error, and none fabricates a 200: the empty-but-valid cases
# (top-N over the eligible count, an all-excluding `min_score`) raise no
# exception at all — the service returns an empty list, which flows straight
# through as a normal 200 (CONTRACT.md §6, §7-P4). FastAPI/Pydantic still
# emits its own 422 for a schema-invalid request body before any handler runs,
# consistent with the contract's 422 for invalid weights.

# The single fault-class -> HTTP-status table. `ScoringConfigError` is checked
# by its own class rather than by its ValueError base so a stray ValueError
# from elsewhere is not silently mapped to 422.
_STATUS_FOR_FAULT: dict[type[Exception], int] = {
    ScoringConfigError: 422,   # invalid weights / unknown scenario (no Run created)
    RunNotFoundError: 404,     # missing Run
    CellNotFoundError: 404,    # missing cell_id
    EngineOutputError: 503,    # missing/unreadable engine output (body names it)
}


def _fault_response(exc: Exception, status_code: int) -> JSONResponse:
    """Uniform error body naming the fault (CONTRACT.md §6).

    The exception message is the service layer's own fault description — it
    already names the invalid weights/scenario, the missing run/cell, or the
    missing/unreadable input — so it is carried through verbatim as `detail`.
    """
    return JSONResponse(
        status_code=status_code,
        content={"detail": str(exc), "error": type(exc).__name__},
    )


def _register_fault_handler(exc_type: type[Exception], status_code: int) -> None:
    """Bind one exception class to its frozen HTTP status, closing over the code."""

    async def handler(_request: Request, exc: Exception) -> JSONResponse:
        return _fault_response(exc, status_code)

    app.add_exception_handler(exc_type, handler)


for _fault_type, _status in _STATUS_FOR_FAULT.items():
    _register_fault_handler(_fault_type, _status)


# ---------------------------------------------------------------------------
# The six frozen routes (CONTRACT.md §2). Each is a thin, uniform delegator:
# parse -> call the matching pipeline.service operation with unchanged args ->
# serialise the returned dataclass via to_dict(). No decision arithmetic.
# ---------------------------------------------------------------------------


@app.post("/runs", response_model=RunHandle)
def create_run(request: RunRequest) -> dict:
    """`run_analysis` — materialise a Run under the given weights or scenario.

    Passes `weights` / `scenario` straight to the operation; the engine parser
    is the single validator (CONTRACT.md §3, §5). No one-of check or weight
    interpretation is done here.
    """
    weights = request.weights.model_dump() if request.weights is not None else None
    handle = run_analysis(weights=weights, scenario=request.scenario)
    return handle.to_dict()


@app.get("/runs/{run_id}/results", response_model=list[RankedRow])
def read_ranked_results(
    run_id: str,
    top_n: int | None = None,
    min_score: float | None = None,
) -> list[dict]:
    """`get_ranked_results` — the Run's ranked rows, optionally display-filtered.

    `top_n` / `min_score` are passed straight through to the operation, which
    owns the pure display-selection (CONTRACT.md §4.2). This layer never
    re-scores, re-ranks, or thresholds.
    """
    rows = get_ranked_results(run_id, top_n=top_n, min_score=min_score)
    return [row.to_dict() for row in rows]


@app.get("/runs/{run_id}/sites/{cell_id}", response_model=SiteDetail)
def read_site_detail(run_id: str, cell_id: str) -> dict:
    """`get_site_detail` — one cell's full detail for a Run."""
    detail = get_site_detail(run_id, cell_id)
    return detail.to_dict()


@app.get("/runs/{run_id}/exclusions", response_model=list[ExcludedRow])
def read_exclusions(run_id: str) -> list[dict]:
    """`get_exclusions` — the Run's excluded cells with their reasons."""
    rows = get_exclusions(run_id)
    return [row.to_dict() for row in rows]


@app.post("/scenario-comparison", response_model=ScenarioComparison)
def create_scenario_comparison(request: ScenarioComparisonRequest) -> dict:
    """`compare_scenarios` — per-cell rank comparison of two named scenarios."""
    comparison = compare_scenarios(request.scenario_a, request.scenario_b)
    return comparison.to_dict()


@app.get("/data-quality", response_model=DataQualityStatus)
def read_data_quality() -> dict:
    """`get_data_quality` — the frozen dataset's S2-02 Data_Quality_Status."""
    status = get_data_quality()
    return status.to_dict()
