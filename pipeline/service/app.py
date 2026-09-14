"""
FastAPI transport shell for the Decision_Service (S2-08, CONTRACT.md §2).

This module is the HTTP surface the Sprint 3 web application integrates against.
It is a THIN TRANSPORT SHELL and nothing more: it maps each of the six
transport-agnostic Service_Operations in `pipeline.service`
(`run_analysis`, `get_ranked_results`, `get_site_detail`, `get_exclusions`,
`compare_scenarios`, `get_data_quality`) onto an HTTP endpoint, declares the
Pydantic request/response models the CONTRACT.md §5 data models describe, maps
the service's honest-failure exceptions onto the CONTRACT.md §6 HTTP statuses,
and lets FastAPI auto-generate the OpenAPI schema at `/openapi.json` (browsable
at `/docs` and `/redoc`).

IT HOLDS NO DECISION LOGIC AND NO OPERATION LOGIC. Every endpoint delegates to
the existing operation function unchanged and serialises its result via that
result's own `to_dict()` — the app neither re-scores, re-ranks nor
re-implements a read. The core functions stay pure of transport so they remain
unit-testable without the HTTP layer (CONTRACT.md §2); this shell is what the
FastAPI-generated OpenAPI schema — the authoritative machine-readable contract —
is produced from.

THE CONTRACT IS FROZEN (Requirement 6.5). These Pydantic models and this
endpoint mapping must CONFORM to CONTRACT.md, not change it. The
Sprint 3 typed client (S3-01b) is generated from the OpenAPI schema this file
emits, so any post-freeze shape change here is a cross-cutting event that ripples
into every Sprint 3 ticket (see CONTRACT.md §8 change-control).

Endpoint mapping (CONTRACT.md §2):

    1.1 run_analysis        POST /runs
    1.2 get_ranked_results  GET  /runs/{run_id}/results?top_n=&min_score=
    1.3 get_site_detail     GET  /runs/{run_id}/sites/{cell_id}
    1.4 get_exclusions      GET  /runs/{run_id}/exclusions
    1.5 compare_scenarios   POST /scenario-comparison
    1.6 get_data_quality    GET  /data-quality

Error mapping (CONTRACT.md §6):

    ScoringConfigError   -> 422  (invalid weights / unknown scenario; no Run)
    RunNotFoundError     -> 404  (missing Run)
    CellNotFoundError    -> 404  (missing cell_id)
    EngineOutputError    -> 503  (missing / unreadable materialised engine output)
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..scoring.weights import ScoringConfigError
from .quality import get_data_quality
from .results import get_exclusions, get_ranked_results, get_site_detail
from .run_analysis import run_analysis
from .runs import CellNotFoundError, EngineOutputError, RunNotFoundError
from .scenarios import compare_scenarios

# --------------------------------------------------------------------------- #
# Request / response models (CONTRACT.md §5).                                  #
#                                                                             #
# These mirror the transport-agnostic dataclasses in `models.py` (whose        #
# `to_dict()` output each endpoint returns) so the FastAPI-generated OpenAPI    #
# schema documents exactly the frozen contract shapes. They add NO logic —      #
# they are the declared surface the schema is generated from.                   #
# --------------------------------------------------------------------------- #


class Criterion(BaseModel):
    """One scored criterion in an explicit weights configuration (CONTRACT.md §5)."""

    feature: str = Field(..., description="One of the six frozen criteria (§3).")
    weight: float = Field(..., ge=0, description="Relative weight; not required to sum to one (§3).")
    direction: str = Field(
        ...,
        description='"higher_is_better" | "lower_is_better"; fixed per criterion (§3).',
    )
    rationale: str = Field(..., description="Non-empty rationale (weights-as-data contract).")


class Weights(BaseModel):
    """Explicit weights configuration for `run_analysis` (CONTRACT.md §5).

    Mirrors the `scoring_weights.yaml` / scenario `criteria` structure so it is
    validated by the SAME engine parser (`pipeline/scoring/weights.py`) — this
    model only shapes the request for the schema; the engine does the validating.
    """

    criteria: list[Criterion] = Field(..., description="One entry per scored criterion.")


class RunRequest(BaseModel):
    """Body of `POST /runs` (CONTRACT.md §4.1). Exactly one of `weights` / `scenario`."""

    weights: Weights | None = Field(None, description="Explicit weights configuration.")
    scenario: str | None = Field(
        None, description='A named Scenario key from scenarios.yaml (e.g. "wind_led").'
    )


class RunHandleModel(BaseModel):
    """`RunHandle` (CONTRACT.md §5, Requirement 6.2)."""

    run_id: str
    weights_id: str
    scenario: str | None = None


class RankedRowModel(BaseModel):
    """`RankedRow` (CONTRACT.md §5, Requirement 6.3)."""

    cell_id: str
    suitability_score: float
    rank: int
    key_components: dict[str, float] = Field(default_factory=dict)


class SiteDetailModel(BaseModel):
    """`SiteDetail` (CONTRACT.md §5, Requirement 6.2, 6.3)."""

    cell_id: str
    features: dict[str, Any] = Field(default_factory=dict)
    contributions: dict[str, float] = Field(default_factory=dict)
    suitability_score: float | None = None
    rank: int | None = None
    eligible: bool = False
    explanation: dict[str, Any] = Field(default_factory=dict)


class ExcludedRowModel(BaseModel):
    """`ExcludedRow` (CONTRACT.md §5, Requirement 1.4)."""

    cell_id: str
    reason_codes: list[str] = Field(default_factory=list)
    reason_text: str = ""


class ScenarioComparisonRowModel(BaseModel):
    """`ScenarioComparisonRow` (CONTRACT.md §5, Requirement 1.5)."""

    cell_id: str
    rank_a: int | None = None
    rank_b: int | None = None
    rank_delta: int | None = None


class ScenarioComparisonModel(BaseModel):
    """`ScenarioComparison` (CONTRACT.md §5, Requirement 1.5)."""

    labels: dict[str, str] = Field(default_factory=dict)
    rows: list[ScenarioComparisonRowModel] = Field(default_factory=list)


class ScenarioComparisonRequest(BaseModel):
    """Body of `POST /scenario-comparison` (CONTRACT.md §4.5)."""

    scenario_a: str = Field(..., description="A named Scenario key.")
    scenario_b: str = Field(..., description="A named Scenario key.")


class DataQualityCheckModel(BaseModel):
    """`DataQualityCheck` (CONTRACT.md §5)."""

    name: str
    expected: str
    observed: str
    passed: bool


class DataQualityStatusModel(BaseModel):
    """`DataQualityStatus` (CONTRACT.md §5, Requirement 6.2, 6.3)."""

    passed: bool
    checks: list[DataQualityCheckModel] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """The honest-failure error body (CONTRACT.md §6): a fault-naming message."""

    detail: str


# --------------------------------------------------------------------------- #
# The application.                                                             #
# --------------------------------------------------------------------------- #

app = FastAPI(
    title="Opt-Mining Decision_Service",
    version="1.0",
    description=(
        "The thin read-and-serve HTTP layer over the Opt-Mining decision "
        "engine (S2-08). It performs no decision logic: it serves the "
        "materialised engine outputs and applies only pure display-level "
        "selection. This OpenAPI schema is the frozen machine-readable "
        "contract the Sprint 3 web application generates its typed client "
        "from; see pipeline/service/CONTRACT.md for the narrated contract."
    ),
)


# --- Honest-failure exception handlers (CONTRACT.md §6) --------------------- #
#
# Each maps a service exception onto its contract HTTP status, carrying the
# fault-naming message through as the error `detail` so the Web_Application
# gets a real, named error rather than a misleading empty success (Property P6).


@app.exception_handler(ScoringConfigError)
async def _scoring_config_error_handler(
    _request: Request, exc: ScoringConfigError
) -> JSONResponse:
    """Invalid weights / unknown scenario -> 422; no Run created (Requirement 4.4)."""
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(RunNotFoundError)
async def _run_not_found_handler(
    _request: Request, exc: RunNotFoundError
) -> JSONResponse:
    """Missing Run -> 404, naming the Run (Requirement 7.1)."""
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(CellNotFoundError)
async def _cell_not_found_handler(
    _request: Request, exc: CellNotFoundError
) -> JSONResponse:
    """Missing cell_id -> 404, naming the cell (Requirement 7.2)."""
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(EngineOutputError)
async def _engine_output_error_handler(
    _request: Request, exc: EngineOutputError
) -> JSONResponse:
    """Missing / unreadable engine output -> 503, naming the input (Requirement 7.3)."""
    return JSONResponse(status_code=503, content={"detail": str(exc)})


# --- Endpoints (CONTRACT.md §2 mapping) ------------------------------------- #


@app.post(
    "/runs",
    response_model=RunHandleModel,
    responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    summary="run_analysis — execute the engine under weights or a scenario",
)
def post_runs(body: RunRequest) -> dict:
    """CONTRACT.md §4.1 — `run_analysis` (Requirement 1.1, 4.1, 4.3, 4.4).

    Drives the S2-05 scoring stage with the given weights/scenario UNCHANGED,
    materialises the Run, and returns its handle. Delegates entirely to
    `run_analysis`; the engine does all validation and scoring.
    """
    weights = body.weights.model_dump() if body.weights is not None else None
    handle = run_analysis(weights=weights, scenario=body.scenario)
    return handle.to_dict()


@app.get(
    "/runs/{run_id}/results",
    response_model=list[RankedRowModel],
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    summary="get_ranked_results — the Run's ranked results, with optional Display_Filter",
)
def get_results(
    run_id: str,
    top_n: int | None = Query(
        None, gt=0, description="Keep the top_n lowest-rank eligible cells (§4.2)."
    ),
    min_score: float | None = Query(
        None, description="Keep only cells with suitability_score >= min_score (§4.2)."
    ),
) -> list[dict]:
    """CONTRACT.md §4.2 — `get_ranked_results` (Requirement 1.2, 3.x, 6.3).

    A pure selection over the fixed Scored_Table; never re-scores or re-ranks.
    An empty result (top_n over the count, an all-excluding threshold) is an
    empty-but-valid 200, not an error (CONTRACT.md §6).
    """
    rows = get_ranked_results(run_id, top_n=top_n, min_score=min_score)
    return [row.to_dict() for row in rows]


@app.get(
    "/runs/{run_id}/sites/{cell_id}",
    response_model=SiteDetailModel,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    summary="get_site_detail — one cell's full detail for a Run",
)
def get_site(run_id: str, cell_id: str) -> dict:
    """CONTRACT.md §4.3 — `get_site_detail` (Requirement 1.3, 2.3, 6.2, 7.2).

    The score/rank served here are IDENTICAL to `get_ranked_results` for the
    same cell in the same Run (the one-engine-output guarantee, Property P1).
    An unknown cell_id yields a 404 naming the cell (Requirement 7.2).
    """
    return get_site_detail(run_id, cell_id).to_dict()


@app.get(
    "/runs/{run_id}/exclusions",
    response_model=list[ExcludedRowModel],
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    summary="get_exclusions — the Run's excluded cells and reasons",
)
def get_run_exclusions(run_id: str) -> list[dict]:
    """CONTRACT.md §4.4 — `get_exclusions` (Requirement 1.4).

    Returns the excluded cells with their machine- and human-readable reason(s)
    from the Eligibility_Table, carried through unchanged.
    """
    return [row.to_dict() for row in get_exclusions(run_id)]


@app.post(
    "/scenario-comparison",
    response_model=ScenarioComparisonModel,
    responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    summary="compare_scenarios — per-cell rank comparison of two scenarios",
)
def post_scenario_comparison(body: ScenarioComparisonRequest) -> dict:
    """CONTRACT.md §4.5 — `compare_scenarios` (Requirement 1.5, 4.3).

    Materialises each Scenario as its own S2-05 Run (the engine, reused — never
    a second scorer, Property P5) and returns a per-cell rank comparison.
    """
    comparison = compare_scenarios(body.scenario_a, body.scenario_b)
    return comparison.to_dict()


@app.get(
    "/data-quality",
    response_model=DataQualityStatusModel,
    responses={503: {"model": ErrorResponse}},
    summary="get_data_quality — the S2-02 data-quality status for a UI banner",
)
def get_quality() -> dict:
    """CONTRACT.md §4.6 — `get_data_quality` (Requirement 1.6, 5.1-5.3).

    Surfaces the S2-02 Data_Quality_Status verbatim so the Web_Application can
    render a data-quality banner; a missing status fails honestly (503).
    """
    return get_data_quality().to_dict()
