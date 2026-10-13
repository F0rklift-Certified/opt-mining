"""
`compare_scenarios` — the scenario-comparison Service_Operation (S2-08,
CONTRACT.md §4.5).

Compares two named Scenarios and returns a per-cell rank comparison
(Requirement 1.5). Each scenario's ranks are produced via the **S2-05 engine**,
NOT a second scorer (Property P5, Requirement 4.3): this module materialises
each Scenario as its own Run through `run_analysis` (which drives the S2-05
scoring stage unchanged and reuses the Run store, idempotent by content) and
reads the two rankings back through `get_ranked_results` — the same fixed
Scored_Table projection every other read operation uses. There is no scoring,
normalisation or ranking arithmetic here; the only computation is the display
convenience `rank_delta = rank_a - rank_b`, a difference of two engine ranks.

Because both Runs score the SAME eligible population under the SAME criteria and
directions, their eligible-population normalisation bounds are identical, so a
rank change between the two columns is attributable PURELY to the weight
difference (CONTRACT.md §3, §4.5) — which is what makes the two Scenarios
comparable.

FAIL HONESTLY. An unknown Scenario is rejected by the ENGINE's own parser
(`run_analysis` -> `resolve_weights` -> `ScoringConfigError`), naming the fault
and creating no Run (Requirement 4.4). This module adds no duplicate scenario
validator; it relies on the same one `run_analysis` already uses.
"""

from __future__ import annotations

from .models import ScenarioComparison, ScenarioComparisonRow
from .results import get_ranked_results
from .run_analysis import run_analysis


def compare_scenarios(
    scenario_a: str | None,
    scenario_b: str | None,
    *,
    weights_a: dict | None = None,
    weights_b: dict | None = None,
    verbose: bool = False,
) -> ScenarioComparison:
    """
    Compare two weighting configurations, returning a per-cell rank comparison
    (CONTRACT.md §4.5, Requirement 1.5, 4.3).

    Each SIDE is EITHER a named Scenario key (from the packaged
    ``scenarios.yaml``) OR an explicit, user-edited ``weights`` configuration
    over the SAME six frozen criteria and directions. Each side is materialised
    as its own S2-05 Run via ``run_analysis`` — passing ``scenario=`` for a
    named side or ``weights=`` for a custom side — and its ranks are read back
    via ``get_ranked_results``. This is the ENGINE, reused, NOT a second scorer
    (Property P5): there is no scoring, normalisation or ranking here, only the
    display convenience ``rank_delta = rank_a - rank_b``. Because both sides
    score the SAME eligible population under the SAME criteria and directions
    (only the weights differ), a rank change is attributable purely to the
    weight difference — which is what keeps the comparison valid.

    Exactly one input must be supplied PER SIDE: a side gives either its
    ``scenario_*`` key or its ``weights_*`` configuration, never both and never
    neither. The engine's own one-of guard (``resolve_weights`` via
    ``run_analysis``) enforces this and raises ``ScoringConfigError`` on a
    fault; no duplicate validator lives here.

    Parameters
    ----------
    scenario_a :
        A named Scenario key for side A (e.g. ``"wind_led"``), or ``None`` when
        side A is a custom weights configuration.
    scenario_b :
        A named Scenario key for side B, or ``None`` when side B is custom.
    weights_a :
        An explicit weights configuration for side A (shaped like the
        ``scenarios.yaml`` ``criteria`` structure), or ``None`` when side A is a
        named scenario. Validated by the ENGINE's parser via ``run_analysis``.
    weights_b :
        An explicit weights configuration for side B, or ``None`` when side B is
        a named scenario.
    verbose :
        Print a one-line note as each side's Run materialises.

    Returns
    -------
    ScenarioComparison
        ``labels`` carrying a readable key per side (the scenario key for a
        named side, or ``"custom_a"`` / ``"custom_b"`` for a custom side) and
        one ``ScenarioComparisonRow`` per cell eligible/ranked under at least
        one side. Each row carries the cell's rank under each side (``None``
        where not ranked) and ``rank_delta = rank_a - rank_b`` when both are
        present, ``None`` otherwise (CONTRACT.md §5). Rows are ordered by
        ascending ``rank_a``, with cells ranked only under side B following in
        ascending ``rank_b`` order.

    Raises
    ------
    ScoringConfigError
        A side is unknown, invalid, or supplies neither/both of its scenario
        key and weights — raised by the engine's own parser via
        ``run_analysis``, naming the fault and creating no Run (Requirement
        4.4). No duplicate validator lives here.
    RunNotFoundError, EngineOutputError
        Propagated from ``get_ranked_results`` if a materialised Run or its
        Scored_Table is missing/unreadable (Requirement 7.1, 7.3).
    """
    # Materialise each side as its own S2-05 Run (idempotent by content) and
    # read its ranks back through the fixed-table projection. THE ENGINE,
    # REUSED. Each side passes EITHER scenario= OR weights= so the engine's
    # exactly-one-of guard stays satisfied and bad input still raises
    # ScoringConfigError (-> 422) with no Run created.
    handle_a = run_analysis(weights=weights_a, scenario=scenario_a, verbose=verbose)
    handle_b = run_analysis(weights=weights_b, scenario=scenario_b, verbose=verbose)

    ranks_a = {row.cell_id: row.rank for row in get_ranked_results(handle_a)}
    ranks_b = {row.cell_id: row.rank for row in get_ranked_results(handle_b)}

    rows = _build_comparison_rows(ranks_a, ranks_b)

    return ScenarioComparison(
        labels={
            "a": scenario_a if scenario_a is not None else "custom_a",
            "b": scenario_b if scenario_b is not None else "custom_b",
        },
        rows=rows,
    )


def _build_comparison_rows(
    ranks_a: dict[str, int],
    ranks_b: dict[str, int],
) -> list[ScenarioComparisonRow]:
    """
    Join the two per-scenario rank maps into per-cell comparison rows.

    A cell appears once, keyed by ``cell_id``, if it is ranked under at least
    one Scenario. ``rank_delta`` is ``rank_a - rank_b`` only when BOTH ranks are
    present, else ``None`` (CONTRACT.md §5) — the sole arithmetic in the
    operation, a difference of two engine ranks (never a re-ranking).

    Ordering: cells ranked under ``scenario_a`` come first in ascending
    ``rank_a`` order (the ``scenario_a`` ranking), then cells ranked only under
    ``scenario_b`` in ascending ``rank_b`` order — a deterministic, readable
    order for the comparison table with no reliance on dict insertion order.
    """
    rows: list[ScenarioComparisonRow] = []

    # Cells ranked under scenario_a, in ascending rank_a order.
    for cell_id in sorted(ranks_a, key=lambda c: ranks_a[c]):
        rank_a = ranks_a[cell_id]
        rank_b = ranks_b.get(cell_id)
        rows.append(
            ScenarioComparisonRow(
                cell_id=cell_id,
                rank_a=rank_a,
                rank_b=rank_b,
                rank_delta=(rank_a - rank_b) if rank_b is not None else None,
            )
        )

    # Cells ranked only under scenario_b (no rank_a), in ascending rank_b order.
    only_b = [cell_id for cell_id in ranks_b if cell_id not in ranks_a]
    for cell_id in sorted(only_b, key=lambda c: ranks_b[c]):
        rows.append(
            ScenarioComparisonRow(
                cell_id=cell_id,
                rank_a=None,
                rank_b=ranks_b[cell_id],
                rank_delta=None,
            )
        )

    return rows
