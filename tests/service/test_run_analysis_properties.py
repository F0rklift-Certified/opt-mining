"""
Property-based test for the S2-08 run-analysis operation — invalid input never
produces a Run.

# Feature: s2-08-decision-service-api, Property: invalid weights/scenario raise
# and create no Run (Requirement 4.4)

For any invalidity Hypothesis can construct — an unknown scenario name, or an
explicit weights configuration corrupted in one of the ways the engine parser
rejects (a negative weight, a NaN/non-numeric weight, all-zero weights, an
invalid direction, a missing rationale) — ``run_analysis`` must raise a
``ScoringConfigError`` and leave the per-Run materialisation store empty. No
invalid request may ever leave a materialised Run behind (Requirement 4.4).

**Validates: Requirements 4.4**

Runs at least 100 generated examples. Hermeticity: the materialisation store
(``pipeline.service.config.RUNS_DIR``) is redirected to a per-example temp
directory, so the real ``DATA/service/`` tree is never written; the store is
asserted empty after every generated invalid request.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.scoring import config as scoring_config
from pipeline.scoring.weights import ScoringConfigError, load_weights
from pipeline.service import run_analysis
from pipeline.service import config as service_config

_DEFAULT = load_weights(scoring_config.DEFAULT_WEIGHTS_PATH)


def _base_weights() -> dict:
    """A valid explicit weights config, from the packaged default weights."""
    return {
        "criteria": [
            {
                "feature": c.feature,
                "weight": c.weight,
                "direction": c.direction,
                "rationale": c.rationale,
            }
            for c in _DEFAULT.criteria
        ]
    }


def _corrupt_negative(w: dict) -> dict:
    w["criteria"][0]["weight"] = -1.0
    return w


def _corrupt_nan(w: dict) -> dict:
    w["criteria"][0]["weight"] = math.nan
    return w


def _corrupt_non_numeric(w: dict) -> dict:
    w["criteria"][0]["weight"] = "heavy"
    return w


def _corrupt_zero_sum(w: dict) -> dict:
    for c in w["criteria"]:
        c["weight"] = 0.0
    return w


def _corrupt_direction(w: dict) -> dict:
    w["criteria"][0]["direction"] = "sideways"
    return w


def _corrupt_missing_rationale(w: dict) -> dict:
    w["criteria"][0].pop("rationale")
    return w


_CORRUPTIONS = [
    _corrupt_negative,
    _corrupt_nan,
    _corrupt_non_numeric,
    _corrupt_zero_sum,
    _corrupt_direction,
    _corrupt_missing_rationale,
]


@settings(max_examples=120, deadline=None)
@given(
    # Either a bad explicit-weights request (an index into the corruptions) or
    # an unknown-scenario request (a generated name that is not a real preset).
    request=st.one_of(
        st.sampled_from(range(len(_CORRUPTIONS))).map(lambda i: ("weights", i)),
        st.text(min_size=0, max_size=24).map(lambda name: ("scenario", name)),
    )
)
def test_invalid_request_raises_and_materialises_no_run(request):
    kind, payload = request

    # Redirect the materialisation store per example with an explicit
    # save/restore (not a function-scoped fixture, which Hypothesis reuses
    # across examples) so the real DATA/service/ tree is never written.
    original_runs_dir = service_config.RUNS_DIR
    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "runs"
        service_config.RUNS_DIR = store
        try:
            if kind == "weights":
                bad = _CORRUPTIONS[payload](_base_weights())
                with pytest.raises(ScoringConfigError):
                    run_analysis(weights=bad)
            else:
                # Only names that are genuinely not presets are "invalid"; a
                # real preset name would be a valid request, so skip those.
                from pipeline.scoring.scenarios import load_scenarios

                known = load_scenarios(service_config.DEFAULT_SCENARIOS_PATH)
                if payload in known:
                    return
                with pytest.raises(ScoringConfigError):
                    run_analysis(scenario=payload)

            # No invalid request may leave a materialised Run behind.
            assert not store.exists() or not any(store.iterdir())
        finally:
            service_config.RUNS_DIR = original_runs_dir
