"""
Backend_App — Pydantic request/response models (S3-01a scaffold).

STUB: filled in by task 3 (Implement the Backend_App Pydantic models). These
models mirror the transport-free dataclasses in `pipeline/service/models.py`
and CONTRACT.md §5 field-for-field, adding NO fields and NO semantics — they are
a serialisation mirror for the auto-generated OpenAPI schema, not a second
source of truth. Where the OpenAPI schema and CONTRACT.md ever disagree, the
OpenAPI schema is authoritative (CONTRACT.md preamble).

Planned models:
    Request:  RunRequest (weights|null, scenario|null),
              ScenarioComparisonRequest (scenario_a, scenario_b)
    Response: RunHandle, RankedRow, SiteDetail (carrying the S2-06
              Explanation_Structure verbatim), ExcludedRow, ScenarioComparison,
              DataQualityStatus
"""
