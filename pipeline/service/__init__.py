"""
Decision_Service — the thin read-and-serve layer over the decision engine (S2-08).

This package is the single boundary between the Sprint 2 decision engine
(`pipeline/`) and the Sprint 3 web application. Its human-readable contract is
`CONTRACT.md` (frozen at the Sprint 2/3 boundary); its machine-readable form is
the FastAPI-generated OpenAPI schema (added by a later task).

THE SERVICE HOLDS NO DECISION LOGIC. It does not score, normalise, rank or
compute exclusions — those all live in the Sprint 2 engine stages (S2-03
exclusions, S2-04 normalisation, S2-05 scoring/ranking, S2-06 explanation, S2-07
scenarios). The service drives those stages through their existing
`run(...)`-style contract and serves their materialised outputs, applying only
pure display-level selection (top-N, minimum-score) over a completed Run. This
is the structural guarantee behind combined-sprint AC4: the Web_Application can
only call this service, so it has no code path by which to recompute a score, a
rank or an eligibility decision (see CONTRACT.md §1).

Modules:
    models       — The typed data models the operations return (RunHandle, …).
    runs         — The Run store: materialise a Run's engine outputs under a
                   per-run directory and resolve a `run_id` back to its
                   artefacts. No decision arithmetic; pure orchestration + I/O.
    run_analysis — `run_analysis(weights|scenario) -> RunHandle`: drives the
                   S2-05 scoring engine UNCHANGED under the given weights or a
                   named Scenario, materialises the Run, and returns a handle.
    results      — The read operations over a materialised Run's engine output.
                   `get_ranked_results(run) -> [RankedRow]` projects the fixed
                   Scored_Table; `get_site_detail(run, cell_id) -> SiteDetail`
                   serves one cell's full detail (features, contributions,
                   score, rank, eligibility, and the S2-06 Explanation_Structure
                   carried through verbatim); `get_exclusions(run) ->
                   [ExcludedRow]` serves the S2-03 Eligibility_Table's excluded
                   cells with their machine- and human-readable reasons. None
                   re-scores, re-ranks or re-evaluates an exclusion.
    filters      — The Display_Filters (top-N, minimum-score) `get_ranked_results`
                   accepts. PURE selections over the fixed `list[RankedRow]` a
                   Run produced: they change WHICH cells are shown but never a
                   cell's score or rank (CONTRACT.md §4.2, §7 P2). Top-N reuses
                   the `pipeline/shortlist/select.py` selection-by-rank pattern;
                   an all-excluding threshold or a top-N beyond the eligible
                   count returns an empty-but-valid set, never an error.
    scenarios    — `compare_scenarios(scenario_a, scenario_b) -> ScenarioComparison`:
                   the scenario-comparison operation. DELEGATES the whole
                   comparison to the S2-07 engine
                   (`pipeline.scoring.scenarios.compare_scenarios`) and only maps
                   its result onto the frozen service shape — no comparison or
                   diff arithmetic of its own (CONTRACT.md §4.5, §7-P3).
    data_quality — `get_data_quality() -> DataQualityStatus`: the data-quality
                   read operation. READS the S2-02 Validation_Result JSON the
                   `validate` stage wrote and projects it verbatim onto the
                   typed status — no validation of its own; an absent result is
                   an honest fault, never a green banner (CONTRACT.md §5, §6).
"""

from .data_quality import get_data_quality
from .filters import apply_display_filter, apply_min_score, apply_top_n
from .models import (
    DataQualityStatus,
    ExcludedRow,
    RankedRow,
    RunHandle,
    ScenarioComparison,
    SiteDetail,
)
from .results import get_exclusions, get_ranked_results, get_site_detail
from .run_analysis import run_analysis
from .scenarios import compare_scenarios

__all__ = [
    "DataQualityStatus",
    "ExcludedRow",
    "RankedRow",
    "RunHandle",
    "ScenarioComparison",
    "SiteDetail",
    "apply_display_filter",
    "apply_min_score",
    "apply_top_n",
    "compare_scenarios",
    "get_data_quality",
    "get_exclusions",
    "get_ranked_results",
    "get_site_detail",
    "run_analysis",
]
