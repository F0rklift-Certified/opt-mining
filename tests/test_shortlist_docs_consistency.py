"""
Documentation-consistency + orchestration smoke tests for the S1-11
`shortlist` stage (task 15.2).

`pipeline/config.py` is the single source of truth for stage order and domain
resolution, and `pipeline/shortlist/config.py` is the authoritative source for
the shortlist output-naming convention and the disclaimer / analysis-resolution
wording. The README and the data specification describe these to a reader.
These tests assert the prose matches the runtime configuration so the docs
cannot quietly drift out of step with behaviour.

Two families of assertions live here:

- Light orchestration smoke: `_get_runner("shortlist")` dispatches to
  `pipeline.shortlist.run.run`, and `--only shortlist` resolves to exactly the
  shortlist stage. (The full registration/ordering matrix lives in
  tests/test_shortlist_wiring.py; this file keeps the dispatch smoke light and
  focuses on doc-consistency.)
- Documentation consistency: config.STAGES ordering, the README stage-order
  block, the disclaimer / ~5 km resolution wording, and the output-naming
  convention are consistent between the code/config and the README / data
  specification.

The config-side assertions are unconditional. The doc-file assertions read the
REAL files and enforce the doc update that task 16.1 lands (README stage-order
table + expected-outputs; data-specification shortlist section). If 16.1 has
not yet landed, those doc-file assertions are expected to fail and flag the
outstanding documentation work; the config-side invariants still pass.

Conventions mirror tests/test_scoring_documentation.py (README stage-order
parsing) and tests/test_shortlist_wiring.py (argparse Namespace produced by
setting sys.argv and calling parse_args()).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import config as pcfg
from pipeline.shortlist import config as slcfg

PROJECT_ROOT = Path(__file__).resolve().parent.parent
README = PROJECT_ROOT / "pipeline" / "README.md"
SPEC = PROJECT_ROOT / "DATA" / "data-specification" / "sprint1_data_specification.md"


@pytest.fixture(scope="module")
def readme() -> str:
    return README.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def spec() -> str:
    return SPEC.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Orchestration smoke (light — full matrix is in test_shortlist_wiring.py)
# ---------------------------------------------------------------------------


class TestOrchestrationSmoke:
    def test_get_runner_dispatches_to_shortlist_run(self):
        """
        `_get_runner("shortlist")` returns the `pipeline.shortlist.run.run`
        callable — the orchestrator dispatch is wired.
        """
        from pipeline.__main__ import _get_runner
        from pipeline.shortlist.run import run as shortlist_run

        runner = _get_runner("shortlist")
        assert runner is shortlist_run
        assert runner.__module__ == "pipeline.shortlist.run"

    def test_only_shortlist_resolves_to_the_single_stage(self):
        """`--only shortlist` resolves to exactly `["shortlist"]`."""
        import sys

        sys.argv = ["x", "--only", "shortlist"]
        from pipeline.__main__ import parse_args, resolve_stages

        assert resolve_stages(parse_args()) == ["shortlist"]


# ---------------------------------------------------------------------------
# config.STAGES ordering (single source of truth)
# ---------------------------------------------------------------------------


class TestConfigStageOrder:
    def test_shortlist_registered_after_scoring_before_validate(self):
        """
        config.STAGES places `shortlist` after `scoring` and before
        `validate` — the Scored_Table producer is scheduled before this
        consumer (10.4, 10.8).
        """
        assert "shortlist" in pcfg.STAGES
        assert (
            pcfg.STAGES.index("scoring")
            < pcfg.STAGES.index("shortlist")
            < pcfg.STAGES.index("validate")
        )

    def test_shortlist_immediately_follows_scoring(self):
        assert pcfg.STAGES.index("shortlist") == pcfg.STAGES.index("scoring") + 1

    def test_shortlist_registered_as_domain(self):
        assert "shortlist" in pcfg.DOMAINS


# ---------------------------------------------------------------------------
# README stage-order documentation consistency
# ---------------------------------------------------------------------------


class TestReadmeStageOrder:
    """
    Parse the README "## Stage Execution Order" fenced block the same way
    test_scoring_documentation.py does, then assert the documented order
    agrees with config.STAGES for the scoring → shortlist → validate span.

    These read the REAL README and enforce task 16.1's stage-order update.
    """

    def _order_block(self, readme: str) -> str:
        start = readme.index("## Stage Execution Order")
        block_start = readme.index("```", start)
        block_end = readme.index("```", block_start + 3)
        return readme[block_start:block_end]

    def _documented_stages(self, readme: str) -> list[str]:
        """
        The stage names listed in the README order block, in order. Parsed per
        arrow-delimited token rather than by substring search: `validate` is a
        substring of `wind.validate` / `geographic.validate`, so a naive
        `.index()` finds the wrong occurrence.
        """
        block = self._order_block(readme)
        stages: list[str] = []
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("```"):
                continue
            for part in line.split("→"):
                part = part.strip()
                if not part:
                    continue
                name = part.split()[0].strip("`(),")
                if name:
                    stages.append(name)
        return stages

    def test_stage_execution_order_block_exists(self, readme):
        assert "## Stage Execution Order" in readme

    def test_readme_stage_order_block_lists_shortlist(self, readme):
        """
        Task 16.1 — the README stage-order block names `shortlist`. Guarded
        against 16.1: if the shortlist entry has not yet landed, this fails to
        flag the outstanding README update.
        """
        documented = self._documented_stages(readme)
        assert "shortlist" in documented, (
            "README '## Stage Execution Order' block omits `shortlist` — task "
            "16.1 must add it after `scoring`, before `validate`."
        )

    def test_readme_orders_scoring_shortlist_validate(self, readme):
        """
        The README lists scoring → shortlist → validate in that order, and the
        same order resolves at runtime in config.STAGES.
        """
        documented = self._documented_stages(readme)
        for stage in ("scoring", "shortlist", "validate"):
            assert stage in documented, (
                f"README stage-order block omits `{stage}` (task 16.1)."
            )

        positions = [documented.index(s) for s in ("scoring", "shortlist", "validate")]
        assert positions == sorted(positions), (
            f"README lists scoring/shortlist/validate out of order: {positions}"
        )

        runtime = [pcfg.STAGES.index(s) for s in ("scoring", "shortlist", "validate")]
        assert runtime == sorted(runtime), (
            "config.STAGES order does not match the README stage-order block"
        )

    def test_documented_order_matches_config_stages(self, readme):
        """
        Every stage the README's order block names that is also a runtime
        stage must appear in config.STAGES in the same relative order.
        """
        documented = [s for s in self._documented_stages(readme) if s in pcfg.STAGES]
        runtime_positions = [pcfg.STAGES.index(s) for s in documented]
        assert runtime_positions == sorted(runtime_positions), (
            f"README order {documented} disagrees with config.STAGES"
        )

    def test_readme_documents_the_shortlist_top_n_flag(self, readme):
        """Task 16.1 — the README CLI docs mention `--shortlist-top-n`."""
        assert "--shortlist-top-n" in readme, (
            "README CLI docs omit the `--shortlist-top-n` flag (task 16.1)."
        )


# ---------------------------------------------------------------------------
# Disclaimer / analysis-resolution wording consistency
# ---------------------------------------------------------------------------


class TestDisclaimerAndResolutionWording:
    def test_config_disclaimer_and_resolution_are_non_empty(self):
        """
        The Preliminary_Disclaimer and Analysis_Resolution statements exist and
        are non-empty in the authoritative shortlist config.
        """
        assert isinstance(slcfg.PRELIMINARY_DISCLAIMER, str)
        assert slcfg.PRELIMINARY_DISCLAIMER.strip()
        assert isinstance(slcfg.ANALYSIS_RESOLUTION, str)
        assert slcfg.ANALYSIS_RESOLUTION.strip()

    def test_config_resolution_states_the_5km_analysis_cell(self):
        """
        ANALYSIS_RESOLUTION states the ~5 km / 0.05 degree analysis cell,
        matching the data specification's analysis-cell statement.
        """
        resolution = slcfg.ANALYSIS_RESOLUTION.lower()
        assert "5 km" in resolution or "5km" in resolution
        assert "0.05" in resolution
        assert "degree" in resolution

    def test_config_disclaimer_states_not_a_site_approval(self):
        """The disclaimer makes clear the shortlist is not a site approval."""
        assert "not a site approval" in slcfg.PRELIMINARY_DISCLAIMER.lower()

    def test_spec_states_the_shortlist_resolution(self, spec):
        """
        Task 16.1 — the data specification states the ~5 km analysis
        resolution for the shortlist screening output. Guarded: fails to flag
        the outstanding spec update if 16.1 has not landed.
        """
        assert "shortlist" in spec.lower(), (
            "Data specification does not mention the shortlist yet (task 16.1)."
        )
        # The ~5 km / 0.05 degree analysis-cell statement is present in the
        # spec (it is a §3 grid property and restated for the shortlist).
        assert "0.05" in spec
        assert "5 km" in spec or "5km" in spec


# ---------------------------------------------------------------------------
# Expected-outputs / output-naming convention consistency
# ---------------------------------------------------------------------------


class TestOutputNamingConsistency:
    def test_config_output_prefix_and_region_slug(self):
        """
        The shortlist output-naming convention is authoritative in config:
        prefix `sprint1_shortlist`, region slug `nsw`.
        """
        assert slcfg.OUTPUT_PREFIX == "sprint1_shortlist"
        assert slcfg.REGION_SLUG == "nsw"

    def test_readme_expected_outputs_name_the_shortlist_files(self, readme):
        """
        Task 16.1 — the README expected-outputs table names the shortlist
        outputs using the `sprint1_shortlist_<UTCdate>.{csv,geojson}`
        convention. Guarded: fails to flag the outstanding README update if
        16.1 has not landed.
        """
        assert slcfg.OUTPUT_PREFIX in readme, (
            "README expected-outputs table omits the shortlist outputs "
            f"({slcfg.OUTPUT_PREFIX}_*) — task 16.1."
        )
        # Both the CSV and GeoJSON output extensions are named for the reader.
        assert ".csv" in readme
        assert ".geojson" in readme

    def test_spec_names_the_shortlist_outputs(self, spec):
        """
        Task 16.1 — the data specification names the shortlist output files
        (via the §8 change-control process). Guarded against 16.1.
        """
        assert slcfg.OUTPUT_PREFIX in spec, (
            "Data specification does not name the shortlist outputs "
            f"({slcfg.OUTPUT_PREFIX}_*) yet — task 16.1."
        )
