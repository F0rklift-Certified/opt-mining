"""
Tests for the S2-08 run-analysis Service_Operation
(``pipeline.service.run_analysis``).

`run_analysis` accepts an explicit weights configuration OR a named Scenario,
drives the S2-05 scoring engine UNCHANGED with those weights, materialises the
Run, and returns a ``RunHandle`` (Requirement 1.1, 4.1, 4.3). On invalid
weights/scenario it raises and creates no Run (Requirement 4.4).

These exercise the real engine against the frozen integrated feature table
(``DATA/integration/optmining_integrated-features_2026_nsw.gpkg``); if that
input is absent the engine tests skip rather than fail, so the suite stays
runnable on a checkout without the built dataset.

Hermeticity: the per-Run materialisation directory
(``pipeline.service.config.RUNS_DIR``) is redirected to a throwaway temp
directory for every test via the ``runs_store`` fixture, so the real
``DATA/service/`` tree is never written.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from pipeline.scoring import config as scoring_config
from pipeline.scoring.weights import ScoringConfigError, load_weights
from pipeline.service import run_analysis
from pipeline.service import config as service_config
from pipeline.service import runs as runs_module
from pipeline.service.models import RunHandle

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


def _valid_weights_dict() -> dict:
    """A valid explicit weights config over the six frozen criteria.

    Derived from the packaged default weights so the test never hard-codes a
    weight literal or a criteria set of its own.
    """
    weights = load_weights(scoring_config.DEFAULT_WEIGHTS_PATH)
    return {
        "criteria": [
            {
                "feature": c.feature,
                "weight": c.weight,
                "direction": c.direction,
                "rationale": c.rationale,
            }
            for c in weights.criteria
        ]
    }


# --------------------------------------------------------------------------- #
# Input contract: exactly one of weights / scenario                           #
# --------------------------------------------------------------------------- #


def test_neither_weights_nor_scenario_raises_and_creates_no_run(runs_store):
    with pytest.raises(ScoringConfigError, match="exactly one"):
        run_analysis()
    assert not runs_store.exists() or not any(runs_store.iterdir())


def test_both_weights_and_scenario_raises_and_creates_no_run(runs_store):
    with pytest.raises(ScoringConfigError, match="exactly one"):
        run_analysis(weights=_valid_weights_dict(), scenario="wind_led")
    assert not runs_store.exists() or not any(runs_store.iterdir())


# --------------------------------------------------------------------------- #
# Invalid weights / scenario -> error, no Run (Requirement 4.4)               #
# --------------------------------------------------------------------------- #


def test_unknown_scenario_raises_naming_the_fault(runs_store):
    with pytest.raises(ScoringConfigError, match="unknown scenario"):
        run_analysis(scenario="does_not_exist")
    assert not runs_store.exists() or not any(runs_store.iterdir())


def test_negative_weight_rejected_by_engine_parser(runs_store):
    bad = _valid_weights_dict()
    bad["criteria"][0]["weight"] = -1.0
    with pytest.raises(ScoringConfigError):
        run_analysis(weights=bad)
    assert not runs_store.exists() or not any(runs_store.iterdir())


def test_zero_weight_sum_rejected(runs_store):
    bad = _valid_weights_dict()
    for c in bad["criteria"]:
        c["weight"] = 0.0
    with pytest.raises(ScoringConfigError):
        run_analysis(weights=bad)
    assert not runs_store.exists() or not any(runs_store.iterdir())


def test_missing_rationale_rejected(runs_store):
    bad = _valid_weights_dict()
    bad["criteria"][0].pop("rationale")
    with pytest.raises(ScoringConfigError):
        run_analysis(weights=bad)


def test_invalid_direction_rejected(runs_store):
    bad = _valid_weights_dict()
    bad["criteria"][0]["direction"] = "sideways"
    with pytest.raises(ScoringConfigError):
        run_analysis(weights=bad)


# --------------------------------------------------------------------------- #
# Valid runs against the real engine (Requirement 1.1, 4.1, 4.3)              #
# --------------------------------------------------------------------------- #


@requires_engine_input
def test_scenario_run_returns_handle_and_materialises(runs_store):
    handle = run_analysis(scenario="wind_led")

    assert isinstance(handle, RunHandle)
    assert handle.scenario == "wind_led"
    assert handle.weights_id == "wind_led"
    assert handle.run_id

    run_dir = runs_store / handle.run_id
    assert (run_dir / service_config.SCORED_GPKG_FILENAME).exists()
    assert (run_dir / service_config.SCORED_CSV_FILENAME).exists()
    assert (run_dir / service_config.RUN_MANIFEST_FILENAME).exists()


@requires_engine_input
def test_explicit_weights_run_returns_handle_with_content_derived_id(runs_store):
    handle = run_analysis(weights=_valid_weights_dict())

    assert isinstance(handle, RunHandle)
    assert handle.scenario is None
    assert handle.weights_id  # content-derived id for explicit weights
    assert (runs_store / handle.run_id / service_config.RUN_MANIFEST_FILENAME).exists()


@requires_engine_input
def test_same_request_is_idempotent_and_reuses_the_run(runs_store):
    first = run_analysis(scenario="grid_led")
    second = run_analysis(scenario="grid_led")
    assert first.run_id == second.run_id
    # exactly one materialised run directory
    assert [p.name for p in runs_store.iterdir()] == [first.run_id]


@requires_engine_input
def test_different_scenarios_materialise_distinct_runs(runs_store):
    wind = run_analysis(scenario="wind_led")
    grid = run_analysis(scenario="grid_led")
    assert wind.run_id != grid.run_id
    assert {p.name for p in runs_store.iterdir()} == {wind.run_id, grid.run_id}


@requires_engine_input
def test_equivalent_weights_are_content_addressed_to_one_run(runs_store):
    """Two explicit-weights requests that differ only in rationale prose (which
    changes no score) resolve to the same content-addressed Run."""
    a = _valid_weights_dict()
    b = copy.deepcopy(a)
    for c in b["criteria"]:
        c["rationale"] = c["rationale"] + " (reworded, same weights)"

    ha = run_analysis(weights=a)
    hb = run_analysis(weights=b)
    assert ha.run_id == hb.run_id
    assert ha.weights_id == hb.weights_id
