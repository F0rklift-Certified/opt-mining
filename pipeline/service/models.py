"""
Typed data models the Decision_Service operations return (S2-08, CONTRACT.md §5).

These are plain, transport-agnostic dataclasses so the operation functions stay
unit-testable without the FastAPI layer (a later task maps each to an HTTP
endpoint and re-declares them as Pydantic models for the OpenAPI schema — the
OpenAPI schema, not this module, is the authoritative machine-readable form per
CONTRACT.md §5). None of them carries decision logic: they are the shapes the
service serves, populated verbatim from materialised engine outputs.

`RunHandle` is needed by `run_analysis` (task 2.1), `RankedRow` by
`get_ranked_results` (task 3.1), `SiteDetail` by `get_site_detail` (task 3.2)
and `ExcludedRow` by `get_exclusions` (task 3.3); the remaining models
(ScenarioComparison, DataQualityStatus) are added by the read-operation tasks
that produce them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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


@dataclass(frozen=True)
class SiteDetail:
    """
    One cell's full detail for a Run (CONTRACT.md §5, Requirement 1.3, 6.2, 6.3).

    A `SiteDetail` is assembled ENTIRELY from materialised engine outputs — it
    is never recomputed (CONTRACT.md §1, Requirement 2.4). Its three sources are:

    * the Run's S2-05 Scored_Table — the `suitability_score`, `rank` and the
      per-criterion `contrib_{feature}` contributions, read from the SAME table
      `get_ranked_results` reads, so the two operations agree for a `cell_id`
      (the consistency guarantee, Requirement 2.3 / Property P1);
    * the S1-08 integrated feature table the Run scored — the cell's input
      `features` and its S2-03 `eligible` flag;
    * the S2-06 explanation output — the `explanation` (Explanation_Structure),
      carried through VERBATIM (its fields are neither renamed nor reordered,
      CONTRACT.md §5).

    Fields
    ------
    cell_id :
        Analysis-cell id, copied verbatim so it joins back to the grid.
    features :
        The cell's input feature values (e.g. ``wind_speed``,
        ``dist_transmission_km``, ``slope_deg``, ``inside_rez``), read from the
        integrated table the Run scored. Carried through unchanged.
    contributions :
        The per-criterion contribution shares (``contrib_{feature}``) from the
        Scored_Table, keyed by criterion `feature` (the ``contrib_`` prefix
        stripped). For an eligible cell these sum to ``suitability_score``
        within the engine's reconciliation tolerance; the service copies them
        through, it does not compute them. A null contribution (a criterion
        with no value for the cell) is omitted rather than fabricated as 0.0.
    suitability_score :
        The S2-05 score in ``[0, 1]``; IDENTICAL to what `get_ranked_results`
        returns for this cell in this Run (Requirement 2.3). ``None`` for an
        excluded cell (which carries no score).
    rank :
        The S2-05 integer rank (1 = highest-ranked); IDENTICAL to
        `get_ranked_results`. ``None`` for an excluded cell (which carries no
        rank).
    eligible :
        Whether the cell passed the S2-03 hard exclusions, read from the
        integrated table's `eligible` flag.
    explanation :
        The S2-06 Explanation_Structure for the cell, carried through verbatim
        (the eligible-path or excluded-path record exactly as S2-06 wrote it).
    """

    cell_id: str
    features: dict[str, Any] = field(default_factory=dict)
    contributions: dict[str, float] = field(default_factory=dict)
    suitability_score: float | None = None
    rank: int | None = None
    eligible: bool = False
    explanation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialise to the CONTRACT.md §5 `SiteDetail` shape."""
        return {
            "cell_id": self.cell_id,
            "features": dict(self.features),
            "contributions": dict(self.contributions),
            "suitability_score": self.suitability_score,
            "rank": self.rank,
            "eligible": self.eligible,
            "explanation": dict(self.explanation),
        }


@dataclass(frozen=True)
class ExcludedRow:
    """
    One excluded cell's eligibility reason(s) for a Run (CONTRACT.md §5,
    Requirement 1.4).

    An `ExcludedRow` is a verbatim projection of one EXCLUDED row of the S2-03
    Eligibility_Table — never a recomputed value. `get_exclusions`
    (`results.py`) reads the materialised Eligibility_Table and returns one
    `ExcludedRow` per cell the engine flagged ineligible (`eligible == False`);
    an eligible cell never becomes an `ExcludedRow`. The service performs no
    exclusion arithmetic — the codes and text are the engine's, carried through
    unchanged (CONTRACT.md §1, Requirement 2.4).

    Both the machine-readable `reason_codes` and the human-readable
    `reason_text` are derived from the SAME `exclusion_reasons` JSON pairs the
    exclusions stage wrote (a list of ``{"code", "text"}`` produced from one
    rule evaluation), so the two forms of an `ExcludedRow` can never disagree
    with each other or with the engine's `triggered_rules` / `exclusion_reason`
    columns.

    Fields
    ------
    cell_id :
        Analysis-cell id, copied verbatim from the Eligibility_Table so it
        joins back to the analysis grid on `cell_id`.
    reason_codes :
        The machine-readable exclusion rule codes for the cell — the
        `exclusion_reasons[].code` (equivalently `triggered_rules`) vocabulary
        from S2-03 (Decision_Engine_Spec §6 / F16), in rule-config order. A
        cell can carry more than one code.
    reason_text :
        The human-readable reason(s) for the cell — the
        `exclusion_reasons[].text` values joined in rule-config order with the
        exclusions stage's own reason delimiter, identical to the engine's
        `exclusion_reason` column.
    """

    cell_id: str
    reason_codes: list[str] = field(default_factory=list)
    reason_text: str = ""

    def to_dict(self) -> dict:
        """Serialise to the CONTRACT.md §5 `ExcludedRow` shape."""
        return {
            "cell_id": self.cell_id,
            "reason_codes": list(self.reason_codes),
            "reason_text": self.reason_text,
        }
