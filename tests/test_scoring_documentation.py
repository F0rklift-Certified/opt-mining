"""
Documentation-consistency tests (S1-10, Requirement 16.2 / 16.3).

`pipeline/config.py` is the single source of truth for stage order and domain
resolution. The README and the data specification describe that order to a
reader. These tests assert the prose matches the runtime configuration, so
documentation cannot quietly drift out of step with behaviour — the ticket
treats a mismatch as a validation failure, not a cosmetic one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipeline import config as pcfg
from pipeline.scoring import config as scfg

PROJECT_ROOT = Path(__file__).resolve().parent.parent
README = PROJECT_ROOT / "pipeline" / "README.md"
SPEC = PROJECT_ROOT / "DATA" / "data-specification" / "sprint1_data_specification.md"


@pytest.fixture(scope="module")
def readme() -> str:
    return README.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def spec() -> str:
    return SPEC.read_text(encoding="utf-8")


class TestReadmeStageOrder:
    def test_stage_execution_order_block_exists(self, readme):
        assert "## Stage Execution Order" in readme

    def _order_block(self, readme: str) -> str:
        start = readme.index("## Stage Execution Order")
        block_start = readme.index("```", start)
        block_end = readme.index("```", block_start + 3)
        return readme[block_start:block_end]

    def _documented_stages(self, readme: str) -> list[str]:
        """
        The stage names listed in the README order block, in order.

        Parsed per line rather than by substring search: `validate` is also a
        substring of `wind.validate` and `geographic.validate`, so a naive
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

    def test_scoring_listed_at_the_resolved_runtime_position(self, readme):
        """
        Requirement 16.2 / 16.3 — the documented position must match the
        position `config.STAGES` actually resolves at runtime.
        """
        documented = self._documented_stages(readme)
        assert "scoring" in documented, "README stage-order block omits the scoring stage"

        for stage in ("integration", "scoring", "validate"):
            assert stage in documented, stage

        positions = [documented.index(s) for s in ("integration", "scoring", "validate")]
        assert positions == sorted(positions), (
            f"README lists integration/scoring/validate out of order: {positions}"
        )

        runtime = [pcfg.STAGES.index(s) for s in ("integration", "scoring", "validate")]
        assert runtime == sorted(runtime), "config.STAGES order does not match the README"

    def test_documented_order_matches_config_stages(self, readme):
        """
        Every stage the README's order block names must appear in
        `config.STAGES`, in the same relative order.
        """
        documented = [s for s in self._documented_stages(readme) if s in pcfg.STAGES]
        runtime_positions = [pcfg.STAGES.index(s) for s in documented]
        assert runtime_positions == sorted(runtime_positions), (
            f"README order {documented} disagrees with config.STAGES"
        )

    def test_scoring_immediately_follows_integration_in_both(self, readme):
        assert pcfg.STAGES.index("scoring") == pcfg.STAGES.index("integration") + 1
        documented = self._documented_stages(readme)
        assert documented.index("scoring") == documented.index("integration") + 1

    def test_cli_documents_the_scoring_weights_flag(self, readme):
        assert "--scoring-weights" in readme
        assert "pipeline/scoring/scoring_weights.yaml" in readme

    def test_readme_states_the_model_rules(self, readme):
        """
        Requirement 16.4 — the formula, the weights source, the normalisation
        rule and the eligible-only rule must all be stated.
        """
        assert "MCDA" in readme or "multi-criteria" in readme.lower()
        assert "contrib_" in readme
        assert re.search(r"weights are user inputs", readme, re.IGNORECASE)
        assert re.search(r"min-max", readme, re.IGNORECASE)
        assert re.search(r"only eligible cells are scored", readme, re.IGNORECASE)

    def test_readme_names_the_scored_output(self, readme):
        assert scfg.OUTPUT_FILENAME in readme
        assert scfg.CSV_FILENAME in readme
        assert scfg.METHOD_REPORT_FILENAME in readme


class TestSpecificationConsistency:
    def test_spec_has_a_scoring_dataset_section(self, spec):
        """Requirement 16.1 — §4 dataset detail names the scored output."""
        assert "### 4.7 Baseline Suitability Score" in spec
        assert scfg.OUTPUT_FILENAME in spec

    def test_spec_pipeline_mapping_row_exists(self, spec):
        """Requirement 16.1 — §7 dataset → stage → criterion mapping."""
        mapping = spec[spec.index("## 7. Pipeline Mapping"):spec.index("## 8. Change Control")]
        assert "Baseline Suitability Score" in mapping
        assert "`scoring`" in mapping

    def test_spec_documents_the_stage_that_produces_it(self, spec):
        section = spec[spec.index("### 4.7"):spec.index("## 5. CRS Alignment Strategy")]
        assert "pipeline/scoring" in section
        assert "after `integration`" in section
        assert "EPSG:4326" in section

    def test_spec_records_the_weights_as_a_user_input(self, spec):
        section = spec[spec.index("### 4.7"):spec.index("## 5. CRS Alignment Strategy")]
        assert "scoring_weights.yaml" in section
        assert "not hard-coded" in section

    def test_spec_records_the_documented_deviations(self, spec):
        """
        Both deviations from the ticket must be visible to a reviewer in the
        change-control record, not only in the generated report.
        """
        change_control = spec[spec.index("## 8. Change Control"):]
        assert "Applied — Baseline Suitability Score" in change_control
        assert "Confidence vocabulary" in change_control
        assert "Null criterion values" in change_control

    def test_spec_version_and_history_are_in_step(self, spec):
        version = re.search(r"\*\*Version:\*\* ([\d.]+)", spec).group(1)
        assert version == "1.5"
        history = spec[spec.index("## Change History"):]
        assert f"| {version} |" in history
        assert "S1-10" in history

    def test_no_frozen_parameter_was_changed(self, spec):
        """
        The criteria weights are user config, not a §2 frozen decision, so
        the "Modifying a Frozen Parameter" process must NOT have been invoked.
        """
        change_control = spec[spec.index("## 8. Change Control"):]
        applied = change_control[change_control.index("Applied — Baseline Suitability Score"):]
        applied = applied[:applied.index("### Modifying a Frozen Parameter")]
        assert "not** triggered" in applied or "not triggered" in applied
