"""
Registration and ordering wiring tests for the S1-12 `sanity` stage.

Verifies the orchestrator plumbing rather than the stage's data logic:
- `sanity` is registered in `config.STAGES` as the TERMINAL entry (after
  `shortlist`) and in `config.DOMAINS` (deliberately distinct from the
  structural `validate` step);
- `_get_runner("sanity")` returns the `pipeline.sanity.run.run` callable;
- `--sanity-spot-cells` (default 8, validated to the inclusive range 5-10)
  and `--wind-generators` exist and are forwarded by `_build_kwargs` as
  `spot_cells` / `wind_generators_path`;
- resolved execution order places `sanity` after `shortlist` as the terminal
  stage (Property 16);
- the `pipeline.sanity.__init__` docstring describes the stage, its
  distinction from `validate`, and its terminal position.

Conventions mirror tests/shortlist/test_shortlist_wiring.py and
tests/common/test_pipeline_structure.py: the argparse Namespace is produced the
same way the CLI produces it, by setting `sys.argv` and calling `parse_args()`.

Requirements: 9.4, 9.5, 9.6, 9.7, 9.8, 9.9
"""

import argparse
import inspect

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline import config

_BBOX = (150.0, -31.5, 152.0, -29.5)


# ---------------------------------------------------------------------------
# Property 16 — resolved execution order places sanity after shortlist as the
# terminal stage.
# ---------------------------------------------------------------------------


def _fake_args(only=None, skip=None, skip_validate=False) -> argparse.Namespace:
    """A minimal Namespace exposing exactly the fields `resolve_stages` reads."""
    return argparse.Namespace(
        only=only,
        skip=list(skip) if skip else [],
        skip_validate=skip_validate,
    )


# The domains that can be dropped via `--skip` without disturbing the relative
# order of the surviving stages. `resolve_stages` preserves `config.STAGES`
# order, so any subset that keeps both `shortlist` and `sanity` must keep the
# invariant.
_SKIPPABLE_DOMAINS = [d for d in config.DOMAINS if d not in ("shortlist", "sanity")]


# Feature: s1-12-validation-sanity-check, Property 16: Resolved execution order places sanity after shortlist as the terminal stage
@settings(max_examples=150, deadline=None)
@given(
    skips=st.lists(st.sampled_from(_SKIPPABLE_DOMAINS), unique=True),
    skip_validate=st.booleans(),
)
def test_property_16_sanity_is_terminal_after_shortlist(skips, skip_validate):
    """
    Property 16 — for any resolved stage list containing both `shortlist` and
    `sanity`, `shortlist` index < `sanity` index AND `sanity` is the last entry.

    The generator varies `--skip` over any subset of the skippable domains
    (never skipping `shortlist` or `sanity`, so both always survive) plus the
    `--skip-validate` toggle. Because `resolve_stages` preserves `config.STAGES`
    order, the terminal invariant must hold for every such combination.

    Validates: Requirements 9.4, 9.9
    """
    from pipeline.__main__ import resolve_stages

    args = _fake_args(skip=skips, skip_validate=skip_validate)
    stages = resolve_stages(args)

    # Both survive because we never skip them.
    assert "shortlist" in stages
    assert "sanity" in stages

    # shortlist precedes sanity, and sanity is the terminal (last) entry.
    assert stages.index("shortlist") < stages.index("sanity")
    assert stages[-1] == "sanity"


def test_sanity_is_terminal_entry_of_config_stages():
    """`sanity` is the terminal entry of config.STAGES, after `shortlist` (9.4, 9.9)."""
    assert config.STAGES[-1] == "sanity"
    assert config.STAGES.index("sanity") > config.STAGES.index("shortlist")


# ---------------------------------------------------------------------------
# Stage registration and dispatch (9.4, 9.5)
# ---------------------------------------------------------------------------


def test_sanity_stage_registration_and_dispatch():
    """
    `sanity` is registered in `config.STAGES` (terminal) and `config.DOMAINS`,
    and `_get_runner("sanity")` returns a callable — the stage `run` (9.4, 9.5).
    """
    # Registered as the terminal stage after shortlist (9.4).
    assert "sanity" in config.STAGES
    assert config.STAGES.index("shortlist") < config.STAGES.index("sanity")
    assert config.STAGES[-1] == "sanity"

    # Registered as a domain so --only/--skip resolve; distinct from validate (9.5).
    assert "sanity" in config.DOMAINS
    assert "sanity" != "validate"

    # Dispatchable to the sanity run callable (9.4).
    from pipeline.__main__ import _get_runner
    from pipeline.sanity.run import run as sanity_run

    runner = _get_runner("sanity")
    assert callable(runner)
    assert runner is sanity_run
    assert runner.__module__ == "pipeline.sanity.run"

    # Signature conforms to run(verbose=False, ...) -> dict.
    sig = inspect.signature(runner)
    params = list(sig.parameters.values())
    assert params, "run() must accept at least the `verbose` parameter"
    first = params[0]
    assert first.name == "verbose"
    assert first.default is False


# ---------------------------------------------------------------------------
# --only / --skip resolution (9.5)
# ---------------------------------------------------------------------------


def test_only_sanity_resolves_single_stage():
    """--only sanity resolves to exactly the sanity stage (9.5)."""
    import sys

    sys.argv = ["test", "--only", "sanity"]
    from pipeline.__main__ import parse_args, resolve_stages

    stages = resolve_stages(parse_args())
    assert stages == ["sanity"]


def test_skip_sanity_removes_stage_from_full_list():
    """--skip sanity drops the sanity stage from the full sequence (9.5)."""
    import sys

    sys.argv = ["test", "--skip", "sanity"]
    from pipeline.__main__ import parse_args, resolve_stages

    stages = resolve_stages(parse_args())
    assert "sanity" not in stages
    # Neighbouring stages are untouched, so only the sanity entry was removed.
    assert "shortlist" in stages


# ---------------------------------------------------------------------------
# --sanity-spot-cells (default 8, validated 5-10) (9.6)
# ---------------------------------------------------------------------------


def test_sanity_spot_cells_default_is_8():
    """The --sanity-spot-cells flag defaults to 8 (9.6)."""
    import sys

    sys.argv = ["test", "--only", "sanity"]
    from pipeline.__main__ import parse_args

    args = parse_args()
    assert args.sanity_spot_cells == 8


@pytest.mark.parametrize("value", [5, 8, 10])
def test_sanity_spot_cells_accepts_in_range(value):
    """--sanity-spot-cells accepts the inclusive range 5-10 (9.6)."""
    import sys

    sys.argv = ["test", "--only", "sanity", "--sanity-spot-cells", str(value)]
    from pipeline.__main__ import parse_args

    args = parse_args()
    assert args.sanity_spot_cells == value


@pytest.mark.parametrize("value", [3, 11])
def test_sanity_spot_cells_rejects_out_of_range(value):
    """--sanity-spot-cells rejects values outside 5-10 (SystemExit on parse) (9.6)."""
    import sys

    sys.argv = ["test", "--only", "sanity", "--sanity-spot-cells", str(value)]
    from pipeline.__main__ import parse_args

    with pytest.raises(SystemExit):
        parse_args()


def test_sanity_spot_cells_maps_to_spot_cells_kwarg():
    """--sanity-spot-cells maps to the run() `spot_cells` kwarg (9.6)."""
    import sys

    sys.argv = ["test", "--only", "sanity", "--sanity-spot-cells", "10", "--verbose"]
    from pipeline.__main__ import _build_kwargs, parse_args

    args = parse_args()
    kwargs = _build_kwargs("sanity", args, _BBOX)
    assert kwargs["spot_cells"] == 10
    assert kwargs["verbose"] == args.verbose


def test_sanity_spot_cells_default_forwarded():
    """The default --sanity-spot-cells (8) is forwarded to run() (9.6)."""
    import sys

    sys.argv = ["test", "--only", "sanity"]
    from pipeline.__main__ import _build_kwargs, parse_args

    args = parse_args()
    assert _build_kwargs("sanity", args, _BBOX)["spot_cells"] == 8


# ---------------------------------------------------------------------------
# --wind-generators → run()'s wind_generators_path kwarg (9.7)
# ---------------------------------------------------------------------------


def test_wind_generators_flag_maps_to_wind_generators_path_kwarg():
    """--wind-generators maps to the run() `wind_generators_path` kwarg (9.7)."""
    import sys
    from pathlib import Path

    sys.argv = [
        "test",
        "--only",
        "sanity",
        "--wind-generators",
        "/tmp/ga_wind_generators.geojson",
    ]
    from pipeline.__main__ import _build_kwargs, parse_args

    args = parse_args()
    assert args.wind_generators == "/tmp/ga_wind_generators.geojson"

    kwargs = _build_kwargs("sanity", args, _BBOX)
    assert kwargs["wind_generators_path"] == Path("/tmp/ga_wind_generators.geojson")


def test_wind_generators_flag_absent_by_default():
    """Without --wind-generators, no wind_generators_path kwarg is forwarded (9.7)."""
    import sys

    sys.argv = ["test", "--only", "sanity"]
    from pipeline.__main__ import _build_kwargs, parse_args

    args = parse_args()
    assert args.wind_generators is None
    assert "wind_generators_path" not in _build_kwargs("sanity", args, _BBOX)


# ---------------------------------------------------------------------------
# Subpackage docstring (9.8)
# ---------------------------------------------------------------------------


def test_sanity_package_docstring_describes_stage_distinction_and_terminal_position():
    """
    The pipeline.sanity.__init__ docstring describes the stage, its distinction
    from the structural `validate` step, and its terminal position (9.8).
    """
    import pipeline.sanity as sanity_pkg

    doc = (sanity_pkg.__doc__ or "").lower()
    assert doc, "pipeline.sanity must have a module docstring"

    # Describes the stage itself.
    assert "sanity" in doc
    # Distinction from the structural `validate` step.
    assert "validate" in doc
    # Terminal position in the pipeline stage sequence.
    assert "terminal" in doc
