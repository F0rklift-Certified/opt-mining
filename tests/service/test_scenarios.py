"""
Tests for the S2-08 ``compare_scenarios`` Service_Operation
(``pipeline.service.scenarios``).

`compare_scenarios` materialises each named Scenario as its own S2-05 Run (via
``run_analysis``) and reads the two rankings back (via ``get_ranked_results``),
returning a per-cell rank comparison with ``rank_delta`` (Requirement 1.5, 4.3).
Each scenario's ranks are produced via the ENGINE, reused — NOT a second scorer
(Property P5): the operation performs no scoring or ranking, only the display
convenience ``rank_delta = rank_a - rank_b``.

Two layers of coverage:

* Unit tests over stubbed ``run_analysis`` / ``get_ranked_results`` so the
  join, the ordering, the ``rank_delta`` rule and the null-handling are pinned
  deterministically without running the engine. Stubbing these symbols also
  proves the operation goes THROUGH the engine reuse path rather than any second
  scorer.
* An engine-backed test against the real frozen integrated table, skipped when
  that input is absent, that confirms the comparison serves real Runs and that
  the two scenarios reuse the S2-05 engine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.scoring import config as scoring_config
from pipeline.scoring.weights import ScoringConfigError
from pipeline.service import compare_scenarios, get_ranked_results, run_analysis
from pipeline.service import config as service_config
from pipeline.service import scenarios as scenarios_module
from pipeline.service.models import (
    RankedRow,
    RunHandle,
    ScenarioComparison,
    ScenarioComparisonRow,
)

INTEGRATED_PATH = Path(scoring_config.INTEGRATED_PATH)
ENGINE_INPUT_AVAILABLE = INTEGRATED_PATH.exists()
requires_engine_input = pytest.mark.skipif(
    not ENGINE_INPUT_AVAILABLE,
    reason=f"integrated feature table not built: {INTEGRATED_PATH}",
)


@pytest.fixture
def runs_store(tmp_path, monkeypatch):
    """Redirect the per-Run materialisation store to a temp directory."""
    store = tmp_path / "runs"
    monkeypatch.setattr(service_config, "RUNS_DIR", store)
    return store


def _stub_engine(monkeypatch, ranks_by_scenario: dict[str, dict[str, int]]) -> list[str]:
    """
    Stub the engine reuse path in ``scenarios.py``.

    ``run_analysis(scenario=...)`` is replaced with a stub that returns a
    ``RunHandle`` for the scenario and records which scenarios were requested;
    ``get_ranked_results(handle)`` is replaced with a stub that returns
    ``RankedRow``s carrying the ranks the test specifies for that handle's
    scenario. Returns the list that captures the requested scenarios, so a test
    can assert the operation drove the engine per scenario.
    """
    requested: list[str] = []

    def fake_run_analysis(weights=None, scenario=None, *, verbose=False):
        requested.append(scenario)
        return RunHandle(run_id=f"run_{scenario}", weights_id=scenario, scenario=scenario)

    def fake_get_ranked_results(run, top_n=None, min_score=None):
        scenario = run.scenario
        ranks = ranks_by_scenario[scenario]
        return [
            RankedRow(
                cell_id=cell_id,
                suitability_score=1.0 / rank,
                rank=rank,
                key_components={},
            )
            for cell_id, rank in ranks.items()
        ]

    monkeypatch.setattr(scenarios_module, "run_analysis", fake_run_analysis)
    monkeypatch.setattr(scenarios_module, "get_ranked_results", fake_get_ranked_results)
    return requested


# --------------------------------------------------------------------------- #
# The join, ordering, rank_delta and null handling (deterministic, stubbed).   #
# --------------------------------------------------------------------------- #


def test_returns_labels_and_per_cell_rank_comparison(monkeypatch):
    _stub_engine(
        monkeypatch,
        {
            "wind_led": {"c1": 1, "c2": 2, "c3": 3},
            "grid_led": {"c1": 3, "c2": 1, "c3": 2},
        },
    )

    result = compare_scenarios("wind_led", "grid_led")

    assert isinstance(result, ScenarioComparison)
    assert result.labels == {"a": "wind_led", "b": "grid_led"}
    assert all(isinstance(r, ScenarioComparisonRow) for r in result.rows)

    by_cell = {r.cell_id: r for r in result.rows}
    # rank_a / rank_b are the engine ranks carried through unchanged.
    assert (by_cell["c1"].rank_a, by_cell["c1"].rank_b) == (1, 3)
    assert (by_cell["c2"].rank_a, by_cell["c2"].rank_b) == (2, 1)
    assert (by_cell["c3"].rank_a, by_cell["c3"].rank_b) == (3, 2)


def test_rank_delta_is_rank_a_minus_rank_b_when_both_present(monkeypatch):
    _stub_engine(
        monkeypatch,
        {
            "a": {"c1": 1, "c2": 5},
            "b": {"c1": 4, "c2": 2},
        },
    )

    result = compare_scenarios("a", "b")
    by_cell = {r.cell_id: r for r in result.rows}

    assert by_cell["c1"].rank_delta == 1 - 4  # -3: better (lower) under scenario_a
    assert by_cell["c2"].rank_delta == 5 - 2  # +3: better under scenario_b


def test_rows_ordered_by_ascending_rank_a(monkeypatch):
    _stub_engine(
        monkeypatch,
        {
            "a": {"c3": 3, "c1": 1, "c2": 2},
            "b": {"c1": 1, "c2": 2, "c3": 3},
        },
    )

    result = compare_scenarios("a", "b")

    assert [r.cell_id for r in result.rows] == ["c1", "c2", "c3"]


def test_cell_ranked_only_under_a_has_null_rank_b_and_delta(monkeypatch):
    _stub_engine(
        monkeypatch,
        {
            "a": {"c1": 1, "cOnlyA": 2},
            "b": {"c1": 1},
        },
    )

    result = compare_scenarios("a", "b")
    by_cell = {r.cell_id: r for r in result.rows}

    assert by_cell["cOnlyA"].rank_a == 2
    assert by_cell["cOnlyA"].rank_b is None
    assert by_cell["cOnlyA"].rank_delta is None


def test_cell_ranked_only_under_b_appears_with_null_rank_a(monkeypatch):
    _stub_engine(
        monkeypatch,
        {
            "a": {"c1": 1},
            "b": {"c1": 1, "cOnlyB": 2},
        },
    )

    result = compare_scenarios("a", "b")
    by_cell = {r.cell_id: r for r in result.rows}

    assert set(by_cell) == {"c1", "cOnlyB"}
    assert by_cell["cOnlyB"].rank_a is None
    assert by_cell["cOnlyB"].rank_b == 2
    assert by_cell["cOnlyB"].rank_delta is None
    # Cells ranked under a come first; the b-only cell follows.
    assert [r.cell_id for r in result.rows] == ["c1", "cOnlyB"]


def test_cell_excluded_under_both_takes_no_part(monkeypatch):
    _stub_engine(
        monkeypatch,
        {
            "a": {"c1": 1},
            "b": {"c1": 1},
        },
    )

    result = compare_scenarios("a", "b")

    assert [r.cell_id for r in result.rows] == ["c1"]


def test_drives_the_engine_once_per_scenario(monkeypatch):
    """Property P5 — each scenario's ranks come from the S2-05 engine, reused."""
    # Feature: s2-08-decision-service-api, Property 5: scenario reuse
    requested = _stub_engine(
        monkeypatch,
        {
            "wind_led": {"c1": 1},
            "grid_led": {"c1": 1},
        },
    )

    compare_scenarios("wind_led", "grid_led")

    # The operation materialised a Run per scenario via run_analysis (the engine
    # reuse path) rather than any second scorer.
    assert requested == ["wind_led", "grid_led"]


# --------------------------------------------------------------------------- #
# Honest failure — an unknown scenario is rejected by the engine parser.      #
# --------------------------------------------------------------------------- #


def test_unknown_scenario_raises_via_the_engine_parser(runs_store):
    with pytest.raises(ScoringConfigError, match="unknown scenario"):
        compare_scenarios("does_not_exist", "wind_led")
    # No Run was materialised for the invalid request.
    assert not runs_store.exists() or not any(runs_store.iterdir())


# --------------------------------------------------------------------------- #
# Against the real engine (Requirement 1.5, 4.3, 8.1, 8.4).                    #
# --------------------------------------------------------------------------- #


@requires_engine_input
def test_compare_scenarios_from_real_runs_reuses_the_engine(runs_store):
    result = compare_scenarios("wind_led", "grid_led")

    assert isinstance(result, ScenarioComparison)
    assert result.labels == {"a": "wind_led", "b": "grid_led"}
    assert result.rows, "the frozen dataset has eligible cells to compare"

    # The two scenarios reuse the S2-05 engine: the ranks compare_scenarios
    # surfaces are exactly those get_ranked_results returns for each Scenario's
    # own materialised Run (no second scorer).
    ranks_a = {r.cell_id: r.rank for r in get_ranked_results(run_analysis(scenario="wind_led"))}
    ranks_b = {r.cell_id: r.rank for r in get_ranked_results(run_analysis(scenario="grid_led"))}
    for row in result.rows:
        assert row.rank_a == ranks_a.get(row.cell_id)
        assert row.rank_b == ranks_b.get(row.cell_id)
        if row.rank_a is not None and row.rank_b is not None:
            assert row.rank_delta == row.rank_a - row.rank_b
        else:
            assert row.rank_delta is None

    # Ordered by ascending rank_a for the cells ranked under scenario_a.
    ranked_a = [r.rank_a for r in result.rows if r.rank_a is not None]
    assert ranked_a == sorted(ranked_a)
