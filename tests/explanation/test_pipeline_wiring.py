"""
Pipeline-wiring tests for the S2-06a explanation stage.

Assert the stage is registered in the right place, dispatchable, and that the
CLI accepts --explanation-templates and threads it (plus --scoring-weights)
into the run kwargs.

Feature: s2-06a-explanation-engine-eligible-cells
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

import pytest

from pipeline import config as pcfg
from pipeline.__main__ import _build_kwargs, _get_runner, parse_args, resolve_stages


def test_explanation_registered_in_stages_and_domains():
    assert "explanation" in pcfg.STAGES
    assert "explanation" in pcfg.DOMAINS


def test_explanation_runs_after_scoring_before_shortlist():
    stages = pcfg.STAGES
    assert stages.index("scoring") < stages.index("explanation") < stages.index("shortlist")


def test_get_runner_resolves_explanation():
    runner = _get_runner("explanation")
    # It is the explanation stage's run(), not another stage's.
    assert runner.__module__ == "pipeline.explanation.run"
    assert runner.__name__ == "run"


def test_only_explanation_resolves_to_the_single_stage():
    with mock.patch.object(sys, "argv", ["prog", "--only", "explanation"]):
        args = parse_args()
    assert resolve_stages(args) == ["explanation"]


def test_cli_accepts_explanation_templates_and_threads_kwargs():
    with mock.patch.object(
        sys, "argv",
        [
            "prog", "--only", "explanation",
            "--explanation-templates", "my_templates.yaml",
            "--scoring-weights", "my_weights.yaml",
        ],
    ):
        args = parse_args()
    kwargs = _build_kwargs("explanation", args, bbox=pcfg.DEFAULT_BBOX)
    assert kwargs["templates_path"] == Path("my_templates.yaml")
    assert kwargs["weights_path"] == Path("my_weights.yaml")
    assert kwargs["verbose"] is False


def test_explanation_kwargs_default_to_none_when_flags_absent():
    with mock.patch.object(sys, "argv", ["prog", "--only", "explanation"]):
        args = parse_args()
    kwargs = _build_kwargs("explanation", args, bbox=pcfg.DEFAULT_BBOX)
    # No overrides -> only verbose; run() falls back to packaged defaults.
    assert "templates_path" not in kwargs
    assert "weights_path" not in kwargs
