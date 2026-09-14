"""
Typed data models the Decision_Service operations return (S2-08, CONTRACT.md §5).

These are plain, transport-agnostic dataclasses so the operation functions stay
unit-testable without the FastAPI layer (a later task maps each to an HTTP
endpoint and re-declares them as Pydantic models for the OpenAPI schema — the
OpenAPI schema, not this module, is the authoritative machine-readable form per
CONTRACT.md §5). None of them carries decision logic: they are the shapes the
service serves, populated verbatim from materialised engine outputs.

`RunHandle` is needed by `run_analysis` (task 2.1) and `RankedRow` by
`get_ranked_results` (task 3.1); the remaining models (SiteDetail, ExcludedRow,
ScenarioComparison, DataQualityStatus) are added by the read-operation tasks
that produce them.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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


@dataclass(frozen=True)
class RankedRow:
    """
    One eligible cell's ranked result for a Run (CONTRACT.md §5, Requirement 6.3).

    A `RankedRow` is a verbatim projection of one row of the materialised
    S2-05 Scored_Table — never a recomputed value. `get_ranked_results`
    (`results.py`) reads the fixed Scored_Table and returns one `RankedRow`
    per eligible cell (a non-null `suitability_score` and `rank`); an excluded
    cell (null score / null rank) never becomes a `RankedRow`. The service
    performs no scoring, normalisation or ranking to produce these — the score
    and rank are the engine's, carried through unchanged (CONTRACT.md §1,
    Requirement 2.4).

    Fields
    ------
    cell_id :
        Analysis-cell id, copied byte-for-byte from the Scored_Table so it
        joins back to the analysis grid on `cell_id`.
    suitability_score :
        The S2-05 `suitability_score` in ``[0, 1]``, read from the table
        (never recomputed).
    rank :
        The S2-05 integer `rank` (1 = highest-ranked), read from the table and
        preserved under any Display_Filter (Requirement 3.2).
    key_components :
        The per-criterion component values for the cell — the `contrib_{feature}`
        shares from the Scored_Table — keyed by criterion `feature` (the
        `contrib_` prefix stripped). These sum to `suitability_score` within
        the engine's reconciliation tolerance; the service copies them through,
        it does not compute them.
    """

    cell_id: str
    suitability_score: float
    rank: int
    key_components: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialise to the CONTRACT.md §5 `RankedRow` shape."""
        return {
            "cell_id": self.cell_id,
            "suitability_score": self.suitability_score,
            "rank": self.rank,
            "key_components": dict(self.key_components),
        }
