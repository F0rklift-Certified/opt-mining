"""
`compare_scenarios` — the scenario-comparison Service_Operation (S2-08,
CONTRACT.md §4.5, Requirement 1.5).

Runs two named Scenarios over the engine's feature table and returns a per-cell
ranking comparison as a ``ScenarioComparison`` (the service model). It holds NO
comparison or diff arithmetic: it resolves the two Scenario keys through the
ENGINE's own scenario parser (`pipeline/scoring/scenarios.py::load_scenarios`),
delegates the whole comparison to the ENGINE
(`pipeline.scoring.scenarios.compare_scenarios`), and only MAPS the engine's
result onto the frozen service shape (CONTRACT.md §1, §7-P3, Requirement 2.4,
8.2). There is no second scenario comparator to drift from the engine's.

WHY A SEPARATE SERVICE MODEL. The engine's `ScenarioComparison`
(`pipeline.scoring.scenarios`) carries only cells ranked in BOTH runs — so every
rank is non-null — plus the additive score fields (`score_a`, `score_b`,
`score_delta`). The frozen S2-08 shape (CONTRACT.md §5) drops those additive
score fields and admits a cell ranked in only one scenario (each of `rank_a`,
`rank_b`, `rank_delta` is nullable). This module maps the engine rows onto that
service shape; the mapping neither renames a §5 field nor computes a value the
engine did not (the ranks and the delta are carried through as the engine set
them).

The transport-free `compare_scenarios(scenario_a, scenario_b)` here is the
operation the FastAPI `POST /scenario-comparison` endpoint (a later task) maps a
``ScenarioComparisonRequest`` onto — parsing two scenario keys and serialising
the returned ``ScenarioComparison``, with no decision logic of its own.
"""

from __future__ import annotations

from ..scoring.load import load_integrated
from ..scoring.scenarios import compare_scenarios as _engine_compare_scenarios
from ..scoring.scenarios import load_scenarios
from ..scoring.weights import ScoringConfigError
from . import config
from .models import ScenarioComparison, ScenarioComparisonRow


def compare_scenarios(
    scenario_a: str,
    scenario_b: str,
) -> ScenarioComparison:
    """
    Compare two named Scenarios' rankings and return a ``ScenarioComparison``
    (CONTRACT.md §4.5, Requirement 1.5, 2.3, 2.4, 8.2).

    Resolves both Scenario keys through the engine's own parser
    (`load_scenarios`), loads the engine's feature table, and DELEGATES the
    entire comparison to `pipeline.scoring.scenarios.compare_scenarios` — the
    two Scenarios are scored against ONE shared set of normalisation bounds so a
    rank change is attributable purely to the change in weighting (the S2-07
    consistency guarantee). This operation performs NO scoring, normalisation,
    ranking or diff arithmetic itself; it only maps the engine's result onto the
    frozen service model (Requirement 2.4, 8.2).

    The service model drops the engine's additive score fields (`score_a`,
    `score_b`, `score_delta`) and types each rank as nullable (CONTRACT.md §5);
    the engine returns only cells ranked in BOTH runs, so in practice every
    mapped rank is non-null and `rank_delta` is present, carried through as the
    engine computed it.

    Parameters
    ----------
    scenario_a :
        The first Scenario key from the packaged ``scenarios.yaml`` (e.g.
        ``"wind_led"``).
    scenario_b :
        The second Scenario key (e.g. ``"grid_led"``).

    Returns
    -------
    ScenarioComparison
        ``labels {a, b}`` plus one ``ScenarioComparisonRow`` per compared cell,
        in the engine's row order (scenario A's rank order). Empty ``rows`` when
        the two Scenarios share no ranked cell (an empty-but-valid result, not
        an error).

    Raises
    ------
    ScoringConfigError
        A ``ValueError`` subclass — when either Scenario key is unknown, or when
        the two Scenarios are not comparable (they score different criteria
        sets). The engine parser and comparator are the single validators; no
        comparison is produced in these cases.
    EngineOutputError
        The engine's integrated feature table is missing or unreadable — the
        error names the missing input rather than fabricating a result.
    """
    scenarios = load_scenarios(config.DEFAULT_SCENARIOS_PATH)

    resolved_a = _resolve_scenario(scenario_a, scenarios)
    resolved_b = _resolve_scenario(scenario_b, scenarios)

    # Load + validate the feature table with the ENGINE's own loader (the same
    # loader run_analysis uses); the two Scenarios share the same criteria set,
    # so scenario A's criteria are a representative spec for the load.
    features = load_integrated(config.INTEGRATED_PATH, resolved_a.weights.criteria)

    # DELEGATE the whole comparison to the engine — no diff arithmetic here.
    engine_result = _engine_compare_scenarios(features, resolved_a, resolved_b)

    # MAP the engine result onto the frozen service shape: keep the labels,
    # project each engine row to a ScenarioComparisonRow, and drop the additive
    # score fields the §5 shape does not carry. The ranks and rank_delta are
    # carried through exactly as the engine set them (nullable in the service
    # model, non-null in practice for a both-runs row).
    rows = [
        ScenarioComparisonRow(
            cell_id=str(row.cell_id),
            rank_a=row.rank_a,
            rank_b=row.rank_b,
            rank_delta=row.rank_delta,
        )
        for row in engine_result.rows
    ]

    return ScenarioComparison(labels=dict(engine_result.labels), rows=rows)


def _resolve_scenario(name: str, scenarios: dict):
    """
    Resolve a Scenario key to its validated ``Scenario`` via the engine parser.

    Raises ``ScoringConfigError`` naming the unknown key (and listing the known
    ones) rather than silently comparing against a missing Scenario — the same
    unknown-scenario fault ``run_analysis`` raises, so both operations reject an
    unknown scenario identically.
    """
    if name not in scenarios:
        known = ", ".join(sorted(scenarios)) or "(none)"
        raise ScoringConfigError(
            f"unknown scenario {name!r}; known scenarios: {known}"
        )
    return scenarios[name]
