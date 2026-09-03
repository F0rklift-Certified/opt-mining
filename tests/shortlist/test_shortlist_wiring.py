"""
Registration and ordering wiring tests for the S1-11 `shortlist` stage.

Verifies the orchestrator plumbing rather than the stage's data logic:
- `shortlist` is registered in `config.STAGES` in the correct relative
  position (after `scoring`, before `validate`) and in `config.DOMAINS`;
- `_get_runner("shortlist")` returns the `pipeline.shortlist.run.run`
  callable and its signature conforms to `run(verbose=False, ...) -> dict`;
- `--only shortlist` / `--skip shortlist` resolve through `resolve_stages`;
- `--shortlist-top-n` is forwarded to `run()`'s `top_n` kwarg by
  `_build_kwargs`.

Conventions mirror tests/test_pipeline_structure.py: the argparse Namespace
is produced the same way the CLI produces it, by setting `sys.argv` and
calling `parse_args()`.
"""

import inspect

from pipeline import config

_BBOX = (150.0, -31.5, 152.0, -29.5)


# ---------------------------------------------------------------------------
# Stage registration and ordering
# ---------------------------------------------------------------------------


# Feature: s1-11-generate-ranked-shortlist, Property 16: Stage registration and ordering
def test_shortlist_stage_registration_and_ordering():
    """
    Property 16 — the `shortlist` stage is registered and dispatchable, its
    `run` conforms to `run(verbose=False, ...) -> dict`, and it is ordered
    after `scoring` and before `validate` in the stage sequence.
    Validates: Requirements 10.4, 10.7, 10.8.
    """
    # Registered and ordered after `scoring`, before `validate` (10.8).
    assert "shortlist" in config.STAGES
    assert (
        config.STAGES.index("scoring")
        < config.STAGES.index("shortlist")
        < config.STAGES.index("validate")
    )

    # Registered as a domain so --only/--skip resolve (10.7).
    assert "shortlist" in config.DOMAINS

    # Dispatchable to the shortlist run callable (10.4).
    from pipeline.__main__ import _get_runner
    from pipeline.shortlist.run import run as shortlist_run

    runner = _get_runner("shortlist")
    assert callable(runner)
    assert runner is shortlist_run
    assert runner.__module__ == "pipeline.shortlist.run"

    # Signature conforms to run(verbose=False, ...) -> dict: first parameter is
    # `verbose` and it defaults to False (the registered-stage contract).
    sig = inspect.signature(runner)
    params = list(sig.parameters.values())
    assert params, "run() must accept at least the `verbose` parameter"
    first = params[0]
    assert first.name == "verbose"
    assert first.default is False


# ---------------------------------------------------------------------------
# --only / --skip resolution (10.7)
# ---------------------------------------------------------------------------


def test_only_shortlist_resolves_single_stage():
    """--only shortlist resolves to exactly the shortlist stage (10.7)."""
    import sys

    sys.argv = ["test", "--only", "shortlist"]
    from pipeline.__main__ import parse_args, resolve_stages

    stages = resolve_stages(parse_args())
    assert stages == ["shortlist"]


def test_skip_shortlist_removes_stage_from_full_list():
    """--skip shortlist drops the shortlist stage from the full sequence (10.7)."""
    import sys

    sys.argv = ["test", "--skip", "shortlist"]
    from pipeline.__main__ import parse_args, resolve_stages

    stages = resolve_stages(parse_args())
    assert "shortlist" not in stages
    # Neighbouring stages are untouched, so only the shortlist entry was removed.
    assert "scoring" in stages
    assert "validate" in stages


# ---------------------------------------------------------------------------
# --shortlist-top-n → run()'s top_n kwarg (3.1, 3.3)
# ---------------------------------------------------------------------------


def test_shortlist_top_n_flag_maps_to_top_n_kwarg():
    """
    --shortlist-top-n maps to the run() `top_n` kwarg, and `verbose` is
    forwarded from the parsed args (3.1, 3.3, 10.5).
    """
    import sys

    sys.argv = ["test", "--only", "shortlist", "--shortlist-top-n", "37", "--verbose"]
    from pipeline.__main__ import _build_kwargs, parse_args

    args = parse_args()
    assert args.shortlist_top_n == 37

    kwargs = _build_kwargs("shortlist", args, _BBOX)
    assert kwargs["top_n"] == 37
    assert kwargs["verbose"] == args.verbose


def test_shortlist_top_n_flag_default_is_20():
    """The --shortlist-top-n flag defaults to 20 (3.1)."""
    import sys

    sys.argv = ["test", "--only", "shortlist"]
    from pipeline.__main__ import _build_kwargs, parse_args

    args = parse_args()
    assert args.shortlist_top_n == 20
    assert _build_kwargs("shortlist", args, _BBOX)["top_n"] == 20
