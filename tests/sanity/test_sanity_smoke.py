"""
Orchestrator + documentation-consistency smoke tests for the S1-12 `sanity`
stage (task 15.2).

This file has two concerns:

1. **Config / wiring smoke assertions** (independent of the docs; MUST pass
   now). A compact restatement of the orchestrator plumbing so a single smoke
   run confirms the stage is wired end-to-end:
     - `sanity` is the TERMINAL entry of `config.STAGES` and sits after
       `shortlist`, and is a member of `config.DOMAINS` (distinct from the
       structural `validate` step);
     - `_get_runner("sanity")` returns the `pipeline.sanity.run.run` callable
       whose signature is `run(verbose=False, ...) -> dict`;
     - `--sanity-spot-cells` (default 8, inclusive range 5-10) and
       `--wind-generators` exist and are forwarded by `_build_kwargs` as
       `spot_cells` / `wind_generators_path`;
     - the `pipeline.sanity.__init__` docstring describes the stage, its
       distinction from `validate`, and its terminal position.
   (The deeper wiring — Property 16 ordering, --only/--skip resolution, the
   argparse range rejection — is covered by tests/sanity/test_sanity_wiring.py,
   which task 13.4 owns. This file keeps a minimal overlapping smoke set so the
   documentation checks below have a self-contained "runtime configuration" to
   compare the README against.)

2. **Documentation-consistency assertions** (Requirement 14.2/14.3/14.5). The
   README (`pipeline/README.md`) stage-order block and CLI documentation, and
   the data specification, must name `sanity` as the terminal stage with its
   CLI flags and describe it as a preliminary-screening plausibility sanity
   check distinct from `pipeline/validate.py`.

   NOTE ON ORDERING (concurrency with task 16.1): task 16.1 UPDATES
   `pipeline/README.md` and the data specification to add the `sanity` stage.
   16.1 runs concurrently with this task, so at the moment this test file is
   authored the README does not yet mention `sanity`. These assertions are
   written to describe the README/spec **as they will exist once 16.1 lands**:
     - `sanity` present in the stage-order block as the terminal stage
       (matching the resolved runtime config: after `shortlist` and after
       `validate`);
     - the `--sanity-spot-cells` and `--wind-generators` CLI flags documented;
     - preliminary-screening plausibility-sanity-check language;
     - distinct-from-`pipeline/validate.py` language.
   The data-specification assertions already pass (the spec §4 entry landed
   ahead of the README). The README assertions may FAIL transiently until
   16.1's README edits are in the working tree; the orchestrator runs the full
   suite at the end, by which point 16.1 will have landed. Each
   README-dependent test carries a `pytest.mark` and a docstring note so the
   dependency is explicit.

   This test does NOT modify the README, config, or `__main__` — task 16.1 owns
   the documentation and the wiring is already implemented.

Requirements: 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 14.2, 14.3, 14.5
"""

import inspect
import re
import sys
from pathlib import Path

import pytest

from pipeline import config

_BBOX = (150.0, -31.5, 152.0, -29.5)

# Repository paths for the documentation files under test.
_PIPELINE_DIR = Path(config.__file__).resolve().parent
_PROJECT_ROOT = _PIPELINE_DIR.parent
_README_PATH = _PIPELINE_DIR / "README.md"
_DATA_SPEC_PATH = (
    _PROJECT_ROOT / "DATA" / "data-specification" / "sprint1_data_specification.md"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# Marker for assertions that depend on task 16.1 having updated pipeline/README.md.
# They are expected to pass once 16.1 lands; until then they may fail transiently.
depends_on_16_1 = pytest.mark.depends_on_16_1


# ===========================================================================
# 1. Config / wiring smoke assertions (MUST pass now)
# ===========================================================================


def test_smoke_sanity_is_terminal_in_stages_and_after_shortlist():
    """`sanity` is the terminal entry of config.STAGES, after `shortlist` (9.4, 9.9)."""
    assert config.STAGES[-1] == "sanity"
    assert config.STAGES.index("sanity") > config.STAGES.index("shortlist")


def test_smoke_sanity_is_a_domain_distinct_from_validate():
    """`sanity` is a resolvable domain and is not the structural `validate` (9.5)."""
    assert "sanity" in config.DOMAINS
    assert "sanity" != "validate"
    # The two concerns are separate keys — sanity is not aliased to validate.
    assert "validate" not in config.DOMAINS or "sanity" != "validate"


def test_smoke_get_runner_returns_sanity_run_callable():
    """`_get_runner("sanity")` returns the stage `run` with a dict-returning signature (9.4)."""
    from pipeline.__main__ import _get_runner
    from pipeline.sanity.run import run as sanity_run

    runner = _get_runner("sanity")
    assert callable(runner)
    assert runner is sanity_run
    assert runner.__module__ == "pipeline.sanity.run"

    sig = inspect.signature(runner)
    params = list(sig.parameters.values())
    assert params, "run() must accept at least the `verbose` parameter"
    assert params[0].name == "verbose"
    assert params[0].default is False


def test_smoke_sanity_spot_cells_default_and_forwarding():
    """`--sanity-spot-cells` defaults to 8 and forwards as `spot_cells` (9.6)."""
    sys.argv = ["test", "--only", "sanity"]
    from pipeline.__main__ import _build_kwargs, parse_args

    args = parse_args()
    assert args.sanity_spot_cells == 8
    assert _build_kwargs("sanity", args, _BBOX)["spot_cells"] == 8


@pytest.mark.parametrize("value", [5, 10])
def test_smoke_sanity_spot_cells_forwards_in_range(value):
    """An in-range `--sanity-spot-cells` (5-10) forwards as `spot_cells` (9.6)."""
    sys.argv = ["test", "--only", "sanity", "--sanity-spot-cells", str(value)]
    from pipeline.__main__ import _build_kwargs, parse_args

    args = parse_args()
    assert _build_kwargs("sanity", args, _BBOX)["spot_cells"] == value


def test_smoke_wind_generators_flag_forwards_as_path():
    """`--wind-generators` forwards to run() as the `wind_generators_path` kwarg (9.7)."""
    sys.argv = [
        "test",
        "--only",
        "sanity",
        "--wind-generators",
        "/tmp/ga_wind_generators.geojson",
    ]
    from pipeline.__main__ import _build_kwargs, parse_args

    args = parse_args()
    kwargs = _build_kwargs("sanity", args, _BBOX)
    assert kwargs["wind_generators_path"] == Path("/tmp/ga_wind_generators.geojson")


def test_smoke_wind_generators_flag_absent_by_default():
    """Without `--wind-generators`, no `wind_generators_path` kwarg is forwarded (9.7)."""
    sys.argv = ["test", "--only", "sanity"]
    from pipeline.__main__ import _build_kwargs, parse_args

    args = parse_args()
    assert args.wind_generators is None
    assert "wind_generators_path" not in _build_kwargs("sanity", args, _BBOX)


def test_smoke_sanity_package_docstring_describes_stage_distinction_and_terminal():
    """
    The `pipeline.sanity.__init__` docstring describes the stage, its distinction
    from the structural `validate` step, and its terminal position (9.8).
    """
    import pipeline.sanity as sanity_pkg

    doc = (sanity_pkg.__doc__ or "").lower()
    assert doc, "pipeline.sanity must have a module docstring"
    assert "sanity" in doc
    assert "validate" in doc
    assert "terminal" in doc


# ===========================================================================
# 2. Documentation-consistency assertions — data specification (already landed)
# ===========================================================================


def test_data_spec_names_sanity_stage_and_report():
    """
    The data specification names the `sanity` stage and its Validation_Report
    (Requirement 14.1/14.2 producer reference). This landed ahead of the README.
    """
    text = _read(_DATA_SPEC_PATH)
    lower = text.lower()
    assert "sanity" in lower, "data spec must name the sanity stage"
    assert "validation report" in lower or "validation_report" in lower


def test_data_spec_states_preliminary_screening_and_distinct_from_validate():
    """
    The data specification states the stage is a preliminary-screening
    plausibility sanity check and is distinct from `pipeline/validate.py`
    (14.4/14.5 documentation constraints).
    """
    text = _read(_DATA_SPEC_PATH)
    lower = text.lower()

    # Preliminary-screening plausibility sanity check language (14.4).
    assert "preliminary" in lower
    assert "plausibility sanity check" in lower or "plausibility" in lower
    assert "not a formal accuracy assessment" in lower
    assert "not a site approval" in lower

    # Distinct-from-validate language (14.5).
    assert "pipeline/validate.py" in text
    assert "distinct" in lower


# ===========================================================================
# 2. Documentation-consistency assertions — pipeline/README.md
#    (depends on task 16.1; see module docstring)
# ===========================================================================


def _readme_stage_order_block(text: str) -> str:
    """
    Return the fenced code block that holds the runtime stage-order sequence
    (the one that lists `wind.probe ... -> validate`), lower-cased. Falls back
    to the whole document if the specific block cannot be isolated.
    """
    for block in re.findall(r"```(.*?)```", text, flags=re.DOTALL):
        low = block.lower()
        if "wind.probe" in low and "validate" in low:
            return low
    return text.lower()


@depends_on_16_1
def test_readme_stage_order_lists_sanity_as_terminal_stage():
    """
    The README stage-order block lists `sanity` as the terminal stage at the
    resolved runtime position — after `shortlist` and after the structural
    `validate` — matching `config.STAGES` (Requirement 14.2, 14.3).

    DEPENDS ON TASK 16.1: 16.1 adds the `-> sanity` line to the README
    stage-order block. Until 16.1 lands this assertion fails transiently.
    """
    text = _read(_README_PATH)
    block = _readme_stage_order_block(text)

    assert "sanity" in block, (
        "README stage-order block must list the `sanity` stage "
        "(added by task 16.1)"
    )

    # Position must match the resolved runtime configuration: sanity is terminal,
    # appearing after both shortlist and validate.
    assert "shortlist" in block and "validate" in block
    assert block.rindex("sanity") > block.rindex("shortlist")
    assert block.rindex("sanity") > block.rindex("validate"), (
        "README must place `sanity` after `validate` to match config.STAGES "
        "(sanity is the terminal entry, after the structural validate)"
    )


@depends_on_16_1
def test_readme_documents_sanity_cli_flags():
    """
    The README CLI documentation lists the `--sanity-spot-cells` and
    `--wind-generators` flags (Requirement 14.2 — CLI flags documented).

    DEPENDS ON TASK 16.1.
    """
    text = _read(_README_PATH)
    assert "--sanity-spot-cells" in text, (
        "README CLI docs must document --sanity-spot-cells (added by task 16.1)"
    )
    assert "--wind-generators" in text, (
        "README CLI docs must document --wind-generators (added by task 16.1)"
    )


@depends_on_16_1
def test_readme_states_preliminary_screening_and_distinct_from_validate():
    """
    The README states the `sanity` stage is a preliminary-screening plausibility
    sanity check distinct from `pipeline/validate.py` (Requirement 14.4, 14.5).

    DEPENDS ON TASK 16.1.
    """
    text = _read(_README_PATH)
    lower = text.lower()

    assert "sanity" in lower
    # Preliminary-screening plausibility-sanity-check language (14.4).
    assert "preliminary" in lower
    assert "plausibility" in lower
    # Distinct-from-the-structural-validate language (14.5).
    assert "pipeline/validate.py" in text
    assert "distinct" in lower


@depends_on_16_1
def test_readme_matches_runtime_stage_name():
    """
    The README stage name for the terminal stage matches the resolved runtime
    stage key exactly — `sanity`, not `validate` (Requirement 14.3: the README
    name must match the runtime configuration).

    DEPENDS ON TASK 16.1.
    """
    text = _read(_README_PATH)
    block = _readme_stage_order_block(text)
    runtime_terminal = config.STAGES[-1]  # "sanity"
    assert runtime_terminal in block, (
        f"README stage-order block must use the runtime terminal stage key "
        f"{runtime_terminal!r}"
    )
