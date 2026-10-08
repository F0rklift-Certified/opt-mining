"""
`run_analysis` — the run-analysis Service_Operation (S2-08, CONTRACT.md §4.1).

Runs the decision engine under an explicit weights configuration OR a named
Scenario, materialises the outputs, and returns a ``RunHandle`` identifying the
Run (Requirement 1.1, 4.1). It drives the S2-05 scoring stage with those weights
UNCHANGED, reusing the engine — it duplicates no scoring, normalisation or
ranking logic (Requirement 4.3). If the supplied weights or Scenario are
invalid, it raises an error identifying the fault and returns NO Run
(Requirement 4.4).

The heavy lifting — resolving/validating the weights via the engine's own
parser, driving `score_and_rank`, and materialising the Scored_Table — lives in
`runs.py`; this module is the transport-agnostic operation entry point the
FastAPI `POST /runs` endpoint (a later task) maps onto.
"""

from __future__ import annotations

from .models import RunHandle
from .runs import materialise_run


def run_analysis(
    weights: dict | None = None,
    scenario: str | None = None,
    *,
    verbose: bool = False,
) -> RunHandle:
    """
    Execute the engine under the given weights or scenario and return a handle.

    Parameters
    ----------
    weights :
        An explicit weights configuration, shaped like the
        ``scoring_weights.yaml`` / scenario ``criteria`` structure (a mapping
        with a ``criteria`` list of ``{feature, weight, direction, rationale}``
        entries). Validated by the ENGINE's parser
        (`pipeline/scoring/weights.py::parse_weights`), never a duplicate
        validator. Mutually exclusive with ``scenario``.
    scenario :
        A named Scenario key from the packaged ``scenarios.yaml`` (e.g.
        ``"wind_led"``, ``"grid_led"``). Mutually exclusive with ``weights``.
    verbose :
        Print a one-line note as the Run materialises.

    Returns
    -------
    RunHandle
        Identifies the materialised Run for the read operations
        (`get_ranked_results`, `get_site_detail`, `get_exclusions`).

    Raises
    ------
    ScoringConfigError
        A ``ValueError`` subclass — when neither or both inputs are given, when
        a named scenario is unknown, or when an explicit weights configuration
        fails validation (a negative or non-numeric weight, weights summing to
        zero, an invalid direction, a duplicate or missing criterion, a missing
        rationale). No Run is created in any of these cases (Requirement 4.4).
    """
    return materialise_run(weights=weights, scenario=scenario, verbose=verbose)
