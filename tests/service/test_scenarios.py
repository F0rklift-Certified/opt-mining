"""
Tests for the S2-08 ``compare_scenarios`` Service_Operation
(``pipeline.service.scenarios``).

The service ``compare_scenarios`` holds NO comparison or diff arithmetic. It
resolves the two Scenario keys through the ENGINE's own parser
(`pipeline.scoring.scenarios.load_scenarios`), delegates the whole comparison to
the ENGINE (`pipeline.scoring.scenarios.compare_scenarios`), and only MAPS the
engine's result onto the frozen S2-08 ``ScenarioComparison`` shape — keeping the
`labels` and each row's `{cell_id, rank_a, rank_b, rank_delta}`, and DROPPING
the engine's additive score fields (`score_a`, `score_b`, `score_delta`)
(CONTRACT.md §1, §5, §7-P3, Requirement 2.4, 8.2).

Two layers of coverage:

* Delegation + mapping unit tests that monkeypatch the engine comparator and the
  feature loader, so the projection is pinned deterministically without the
  built dataset: the engine is called, its labels + ranks are carried through
  verbatim, and its score fields are dropped.
* An engine-backed test against the real frozen integrated table, skipped when
  that input is absent, that confirms the operation serves a real comparison.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.scoring import config as scoring_config
from pipeline.scoring import scenarios as engine_scenarios
from pipeline.scoring.scenarios import ScenarioComparison as EngineScenarioComparison
from pipeline.scoring.scenarios import ScenarioRow as EngineScenarioRow
from pipeline.scoring.weights import ScoringConfigError
from pipeline.service import compare_scenarios
from pipeline.service import scenarios as service_scenarios
from pipeline.service.models import ScenarioComparison, ScenarioComparisonRow

INTEGRATED_PATH = Path(scoring_config.INTEGRATED_PATH)
ENGINE_INPUT_AVAILABLE = INTEGRATED_PATH.exists()
requires_engine_input = pytest.mark.skipif(
    not ENGINE_INPUT_AVAILABLE,
    reason=f"integrated feature table not built: {INTEGRATED_PATH}",
)


# --------------------------------------------------------------------------- #
# Delegation + mapping (deterministic, engine + loader monkeypatched).        #
# --------------------------------------------------------------------------- #


def test_delegates_to_engine_and_maps_result(monkeypatch):
    """The service resolves scenarios via the engine parser, delegates the
    comparison to the engine, and maps the engine rows onto the service model —
    keeping labels + ranks and dropping the additive score fields."""
    calls = {}

    # Stand-in "resolved scenario" objects; the service only reads
    # `.weights.criteria` off scenario A to spec the feature load.
    class _Weights:
        criteria = [{"feature": "wind_speed", "weight": 1.0, "direction": "higher_is_better"}]

    class _Scenario:
        weights = _Weights()

    fake_scenarios = {"wind_led": _Scenario(), "grid_led": _Scenario()}

    def _fake_load_scenarios(path):
        calls["scenarios_path"] = path
        return fake_scenarios

    sentinel_features = object()

    def _fake_load_integrated(path, criteria):
        calls["integrated_path"] = path
        calls["criteria"] = criteria
        return sentinel_features

    engine_result = EngineScenarioComparison(
        labels={"a": "Wind-led", "b": "Grid-led"},
        names={"a": "wind_led", "b": "grid_led"},
        rows=(
            EngineScenarioRow(
                cell_id="c1", rank_a=1, rank_b=3, rank_delta=-2,
                score_a=0.9, score_b=0.4, score_delta=0.5,
            ),
            EngineScenarioRow(
                cell_id="c2", rank_a=2, rank_b=1, rank_delta=1,
                score_a=0.6, score_b=0.8, score_delta=-0.2,
            ),
        ),
    )

    def _fake_engine_compare(features, resolved_a, resolved_b):
        calls["features"] = features
        calls["resolved_a"] = resolved_a
        calls["resolved_b"] = resolved_b
        return engine_result

    monkeypatch.setattr(service_scenarios, "load_scenarios", _fake_load_scenarios)
    monkeypatch.setattr(service_scenarios, "load_integrated", _fake_load_integrated)
    monkeypatch.setattr(
        service_scenarios, "_engine_compare_scenarios", _fake_engine_compare
    )

    result = compare_scenarios("wind_led", "grid_led")

    # The engine comparator was the one that produced the comparison, over the
    # engine-loaded feature table and the parser-resolved scenarios (delegation).
    assert calls["features"] is sentinel_features
    assert calls["resolved_a"] is fake_scenarios["wind_led"]
    assert calls["resolved_b"] is fake_scenarios["grid_led"]
    # The feature load used scenario A's criteria as the representative spec.
    assert calls["criteria"] == _Weights.criteria
    # The scenario/integrated paths came from the service config, not literals.
    assert calls["scenarios_path"] == service_scenarios.config.DEFAULT_SCENARIOS_PATH
    assert calls["integrated_path"] == service_scenarios.config.INTEGRATED_PATH

    # The mapping is faithful: it is the frozen service model, labels carried
    # through, and one ScenarioComparisonRow per engine row in engine order.
    assert isinstance(result, ScenarioComparison)
    assert result.labels == {"a": "Wind-led", "b": "Grid-led"}
    assert all(isinstance(r, ScenarioComparisonRow) for r in result.rows)
    assert [r.cell_id for r in result.rows] == ["c1", "c2"]
    assert [(r.rank_a, r.rank_b, r.rank_delta) for r in result.rows] == [
        (1, 3, -2),
        (2, 1, 1),
    ]


def test_engine_additive_score_fields_are_dropped(monkeypatch):
    """The §5 service shape drops the engine's score_a/score_b/score_delta; the
    mapped rows expose only cell_id + the three ranks (no score fields)."""

    class _Weights:
        criteria = [{"feature": "wind_speed", "weight": 1.0, "direction": "higher_is_better"}]

    class _Scenario:
        weights = _Weights()

    monkeypatch.setattr(
        service_scenarios,
        "load_scenarios",
        lambda path: {"wind_led": _Scenario(), "grid_led": _Scenario()},
    )
    monkeypatch.setattr(
        service_scenarios, "load_integrated", lambda path, criteria: object()
    )
    monkeypatch.setattr(
        service_scenarios,
        "_engine_compare_scenarios",
        lambda features, a, b: EngineScenarioComparison(
            labels={"a": "Wind-led", "b": "Grid-led"},
            names={"a": "wind_led", "b": "grid_led"},
            rows=(
                EngineScenarioRow(
                    cell_id="c1", rank_a=1, rank_b=2, rank_delta=-1,
                    score_a=0.9, score_b=0.5, score_delta=0.4,
                ),
            ),
        ),
    )

    result = compare_scenarios("wind_led", "grid_led")

    # The mapped row (and its serialised form) carries no additive score field,
    # and the engine's `names` mapping is not part of the frozen §5 shape.
    row_dict = result.rows[0].to_dict()
    assert set(row_dict) == {"cell_id", "rank_a", "rank_b", "rank_delta"}
    assert set(result.to_dict()) == {"labels", "rows"}
    for dropped in ("score_a", "score_b", "score_delta"):
        assert dropped not in row_dict


def test_empty_engine_result_maps_to_empty_but_valid(monkeypatch):
    """No cell ranked in both scenarios -> empty rows, not an error."""

    class _Weights:
        criteria = [{"feature": "wind_speed", "weight": 1.0, "direction": "higher_is_better"}]

    class _Scenario:
        weights = _Weights()

    monkeypatch.setattr(
        service_scenarios,
        "load_scenarios",
        lambda path: {"wind_led": _Scenario(), "grid_led": _Scenario()},
    )
    monkeypatch.setattr(
        service_scenarios, "load_integrated", lambda path, criteria: object()
    )
    monkeypatch.setattr(
        service_scenarios,
        "_engine_compare_scenarios",
        lambda features, a, b: EngineScenarioComparison(
            labels={"a": "Wind-led", "b": "Grid-led"}, names={}, rows=()
        ),
    )

    result = compare_scenarios("wind_led", "grid_led")

    assert isinstance(result, ScenarioComparison)
    assert result.rows == []


def test_unknown_scenario_raises_naming_the_fault(monkeypatch):
    """An unknown scenario key raises ScoringConfigError and no comparison is
    produced — the engine comparator is never reached."""

    class _Weights:
        criteria = []

    class _Scenario:
        weights = _Weights()

    monkeypatch.setattr(
        service_scenarios, "load_scenarios", lambda path: {"wind_led": _Scenario()}
    )

    def _must_not_be_called(*args, **kwargs):  # pragma: no cover - guard
        raise AssertionError("engine comparator called for an unknown scenario")

    monkeypatch.setattr(service_scenarios, "load_integrated", _must_not_be_called)
    monkeypatch.setattr(
        service_scenarios, "_engine_compare_scenarios", _must_not_be_called
    )

    with pytest.raises(ScoringConfigError, match="unknown scenario 'does_not_exist'"):
        compare_scenarios("does_not_exist", "wind_led")


# --------------------------------------------------------------------------- #
# Against the real engine (Requirement 1.5, 8.1, 8.2).                        #
# --------------------------------------------------------------------------- #


@requires_engine_input
def test_compare_scenarios_from_the_real_engine():
    """The two packaged scenarios compare over the real frozen integrated table,
    and the service result matches the engine's own comparison (ranks carried
    through verbatim, score fields dropped)."""
    result = compare_scenarios("wind_led", "grid_led")

    assert isinstance(result, ScenarioComparison)
    assert result.labels == {"a": "Wind-led", "b": "Grid-led"}
    assert result.rows, "the two scenarios share ranked cells on the frozen data"

    # Recompute the engine comparison directly and confirm the service mapped it
    # faithfully — same cells in the same order, same ranks, and rank_delta =
    # rank_a - rank_b carried through (never recomputed by the service).
    scenarios = engine_scenarios.load_scenarios(scoring_config.DEFAULT_SCENARIOS_PATH)
    from pipeline.scoring.load import load_integrated

    features = load_integrated(
        scoring_config.INTEGRATED_PATH, scenarios["wind_led"].weights.criteria
    )
    engine_result = engine_scenarios.compare_scenarios(
        features, scenarios["wind_led"], scenarios["grid_led"]
    )

    assert [r.cell_id for r in result.rows] == [
        str(row.cell_id) for row in engine_result.rows
    ]
    for mapped, engine_row in zip(result.rows, engine_result.rows):
        assert mapped.rank_a == engine_row.rank_a
        assert mapped.rank_b == engine_row.rank_b
        assert mapped.rank_delta == engine_row.rank_delta
        assert mapped.rank_delta == engine_row.rank_a - engine_row.rank_b
