"""
Typed data models the Decision_Service operations return (S2-08, CONTRACT.md §5).

These are plain, transport-agnostic dataclasses so the operation functions stay
unit-testable without the FastAPI layer (a later task maps each to an HTTP
endpoint and re-declares them as Pydantic models for the OpenAPI schema — the
OpenAPI schema, not this module, is the authoritative machine-readable form per
CONTRACT.md §5). None of them carries decision logic: they are the shapes the
service serves, populated verbatim from materialised engine outputs.

Only `RunHandle` is needed by `run_analysis` (task 2.1); the remaining models
(RankedRow, SiteDetail, ExcludedRow, ScenarioComparison, DataQualityStatus) are
added by the read-operation tasks that produce them.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunHandle:
    """
    Identifies one materialised Run of the decision engine (CONTRACT.md §5).

    A Run is "execute the S2-05 scoring engine with these weights and
    materialise the outputs" (design.md). The handle is what the
    `GET /runs/{run_id}/...` read operations key on.

    Fields
    ------
    run_id :
        Identifier for the materialised Run, used in the read-operation paths.
        Content-derived from the resolved weights so that re-running the same
        weights (or the same scenario) resolves to the same Run rather than
        proliferating identical materialisations.
    weights_id :
        Stable identifier of the weight set used — the scenario key for a
        scenario Run, or a content-derived id (the SHA-256 of the resolved
        weights YAML) for an explicit-weights Run. This is the traceable
        weights identity the engine's method report and manifest also record.
    scenario :
        The named Scenario key when the Run was launched from one; ``None`` for
        an explicit-weights Run.
    """

    run_id: str
    weights_id: str
    scenario: str | None = None

    def to_dict(self) -> dict:
        """Serialise to the CONTRACT.md §5 `RunHandle` shape."""
        return {
            "run_id": self.run_id,
            "weights_id": self.weights_id,
            "scenario": self.scenario,
        }
