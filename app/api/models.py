"""
Backend_App — Pydantic request/response models (S3-01a scaffold).

These models mirror the transport-free dataclasses in
`pipeline/service/models.py` and CONTRACT.md §5 field-for-field, adding NO
fields and NO semantics — they are a serialisation mirror for the
auto-generated OpenAPI schema, not a second source of truth. Where the OpenAPI
schema and CONTRACT.md ever disagree, the OpenAPI schema is authoritative
(CONTRACT.md preamble).

They carry no decision logic and no validation of their own: `RunRequest` does
NOT validate weights (the engine parser `pipeline/scoring/weights.py` is the
single validator per CONTRACT.md §3/§5); the one-of `weights`/`scenario` rule is
enforced by `run_analysis`, not here — a schema-shape failure surfaces as
FastAPI's 422, a weight-semantics failure as the operation's 422 (CONTRACT.md
§6). The S2-06 `Explanation_Structure` is carried verbatim as a free-form
mapping (its eligible-path and excluded-path shapes differ; the service neither
renames nor reorders its fields, so the mirror does not constrain it).

Pydantic v2 (consistent with the pinned `fastapi==0.115.6`).

Mirrors:
    Request:  RunRequest (weights|null, scenario|null) with Weights/Criterion,
              ScenarioComparisonRequest (scenario_a, scenario_b)
    Response: RunHandle, RankedRow, SiteDetail (carrying the S2-06
              Explanation_Structure verbatim), ExcludedRow,
              ScenarioComparisonRow, ScenarioComparison, DataQualityCheck,
              DataQualityStatus
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class Criterion(BaseModel):
    """
    One scored criterion inside a `Weights` configuration (CONTRACT.md §5).

    Mirrors the `scoring_weights.yaml` / scenario `criteria` entry so it is
    validated by the SAME engine parser (`pipeline/scoring/weights.py`), never a
    duplicate validator — hence no field constraints (e.g. weight >= 0, the
    direction enum) are re-declared here.
    """

    feature: str
    weight: float
    direction: str
    rationale: str


class Weights(BaseModel):
    """
    Explicit weights configuration for `run_analysis` (CONTRACT.md §5).

    Mirrors the `scoring_weights.yaml` / scenario `criteria` structure so it is
    validated by the same engine parser, never a duplicate validator.
    """

    criteria: list[Criterion] = Field(default_factory=list)


class RunRequest(BaseModel):
    """
    Request body for `run_analysis` — `POST /runs` (CONTRACT.md §4.1, §5).

    Exactly one of `weights` / `scenario` must be given; that one-of rule is
    enforced by the `run_analysis` operation (which returns 422 on a fault),
    not by this model, so both fields are nullable here. The backend does NOT
    validate weights itself — it passes them to the engine parser.
    """

    weights: Weights | None = None
    scenario: str | None = None


class ScenarioComparisonRequest(BaseModel):
    """
    Request body for `compare_scenarios` — `POST /scenario-comparison`
    (CONTRACT.md §4.5, §5). Both scenario keys are required.
    """

    scenario_a: str
    scenario_b: str


# ---------------------------------------------------------------------------
# Response models (all mirror CONTRACT.md §5 / pipeline/service/models.py)
# ---------------------------------------------------------------------------


class RunHandle(BaseModel):
    """Identifies one materialised Run (CONTRACT.md §5)."""

    run_id: str
    weights_id: str
    scenario: str | None = None


class RankedRow(BaseModel):
    """One eligible cell's ranked result for a Run (CONTRACT.md §5)."""

    cell_id: str
    suitability_score: float
    rank: int
    key_components: dict[str, float] = Field(default_factory=dict)


class SiteDetail(BaseModel):
    """
    One cell's full detail for a Run (CONTRACT.md §5).

    `explanation` carries the S2-06 `Explanation_Structure` verbatim (the
    eligible-path or excluded-path record exactly as S2-06 wrote it); it is a
    free-form mapping so the mirror neither renames nor reorders S2-06's fields.
    """

    cell_id: str
    features: dict[str, Any] = Field(default_factory=dict)
    contributions: dict[str, float] = Field(default_factory=dict)
    suitability_score: float | None = None
    rank: int | None = None
    eligible: bool = False
    explanation: dict[str, Any] = Field(default_factory=dict)


class ExcludedRow(BaseModel):
    """One excluded cell's eligibility reason(s) for a Run (CONTRACT.md §5)."""

    cell_id: str
    reason_codes: list[str] = Field(default_factory=list)
    reason_text: str = ""


class ScenarioComparisonRow(BaseModel):
    """One cell's rank comparison across two scenarios (CONTRACT.md §5)."""

    cell_id: str
    rank_a: int | None = None
    rank_b: int | None = None
    rank_delta: int | None = None


class ScenarioComparison(BaseModel):
    """A per-cell ranking comparison between two scenarios (CONTRACT.md §5)."""

    labels: dict[str, str] = Field(default_factory=dict)
    rows: list[ScenarioComparisonRow] = Field(default_factory=list)


class DataQualityCheck(BaseModel):
    """One data-quality check record (CONTRACT.md §5, S2-02 shape)."""

    name: str
    expected: str
    observed: str
    passed: bool


class DataQualityStatus(BaseModel):
    """The S2-02 Data_Quality_Status for the frozen integrated dataset (CONTRACT.md §5)."""

    passed: bool = False
    checks: list[DataQualityCheck] = Field(default_factory=list)
