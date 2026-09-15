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

SCOPE (task 4.1 only): this module wires and delegates the six routes. Two
later tasks complete `app.py` and are deliberately NOT implemented here — they
have a clean seam below:
  * task 4.2 — env-driven CORS middleware (`settings.get_cors_allow_origins()`);
  * task 4.3 — the centralised service-exception -> HTTP-code mapping
    (CONTRACT.md §6: 422 invalid weights/unknown scenario, 404 missing
    run/cell, 503 missing/unreadable engine output). Until 4.3 lands, a service
    fault propagates as FastAPI's default 500; the empty-but-valid 200 cases
    (top-N over the eligible count, an all-excluding `min_score`) already flow
    through correctly because the service returns an empty list, never an error.

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

from fastapi import FastAPI

# `app/api/` is run as the working directory (`uvicorn app:app` per the design
# run command and the api Dockerfile), so `models` and `settings` are sibling
# top-level modules rather than a package — a plain absolute import matches how
# the app is actually launched (dev + Compose).
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
# Seam for task 4.2 — env-driven CORS middleware.
# Install CORSMiddleware with settings.get_cors_allow_origins() here (no origin
# literal in this module). Not implemented in task 4.1.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Seam for task 4.3 — centralised service-exception -> HTTP-code mapping.
# Register app.add_exception_handler(...) for the service fault taxonomy
# (RunNotFoundError/CellNotFoundError -> 404, ScoringConfigError -> 422,
# EngineOutputError -> 503) in ONE place here (CONTRACT.md §6). Not implemented
# in task 4.1.
# ---------------------------------------------------------------------------


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
