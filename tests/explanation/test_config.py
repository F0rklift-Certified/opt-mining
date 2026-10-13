"""
Config-composition tests for the S2-06a explanation stage.

The whole point of `explanation/config.py` is that its inputs are COMPOSED
from the producing domains' config, never re-typed as literals — so an
upstream rename propagates instead of silently drifting. These tests pin that
composition.

Feature: s2-06a-explanation-engine-eligible-cells
"""

from __future__ import annotations

from pipeline.explanation import config as ecfg
from pipeline.integration import config as icfg
from pipeline.scoring import config as scfg


def test_scored_table_input_is_the_scoring_output():
    """The sole score input is exactly the S2-05 Scored_Table."""
    assert ecfg.SCORED_TABLE_PATH == scfg.SCORING_DIR / scfg.OUTPUT_FILENAME
    assert ecfg.SCORED_TABLE_LAYER == scfg.OUTPUT_LAYER


def test_integrated_input_is_composed_from_scoring_config():
    """The integrated table (for recomputing norms) is the scoring stage's input."""
    assert ecfg.INTEGRATED_PATH == scfg.INTEGRATED_PATH
    assert ecfg.INTEGRATED_LAYER == scfg.INTEGRATED_LAYER
    # And that is the integration stage's own output — one source of truth.
    assert ecfg.INTEGRATED_PATH == icfg.INTEGRATION_DIR / icfg.OUTPUT_FILENAME


def test_column_names_are_carried_from_scoring():
    """Scored_Table column names are re-exported, never re-typed."""
    assert ecfg.CELL_ID_COLUMN == scfg.CELL_ID_COLUMN
    assert ecfg.SCORE_COLUMN == scfg.SCORE_COLUMN
    assert ecfg.RANK_COLUMN == scfg.RANK_COLUMN
    assert ecfg.OUTPUT_CONFIDENCE_COLUMN == scfg.OUTPUT_CONFIDENCE_COLUMN
    assert ecfg.CONTRIBUTION_PREFIX == scfg.CONTRIBUTION_PREFIX
    assert ecfg.ELIGIBLE_COLUMN == scfg.ELIGIBLE_COLUMN


def test_reconcile_tolerance_shared_with_scoring():
    assert ecfg.RECONCILE_TOLERANCE == scfg.RECONCILE_TOLERANCE


def test_vintage_matches_scoring_so_products_are_same_generation():
    assert ecfg.EXPLANATION_VINTAGE == scfg.SCORING_VINTAGE


def test_output_paths_follow_the_naming_convention():
    """{source}_{dataset}_{vintage}_{region}.{ext}, region slug 'nsw'."""
    assert ecfg.OUTPUT_FILENAME == f"optmining_site-explanations_{ecfg.EXPLANATION_VINTAGE}_nsw.json"
    assert ecfg.CSV_FILENAME == f"optmining_site-explanations_{ecfg.EXPLANATION_VINTAGE}_nsw.csv"
    assert ecfg.EXPLANATION_DIR == ecfg.PROJECT_ROOT / "DATA" / "explanation"
    assert ecfg.EXPLANATION_META_DIR == ecfg.EXPLANATION_DIR / "metadata"


def test_default_weights_path_is_the_scoring_weights():
    """Norms are recomputed with the SAME weights the scoring stage used."""
    assert ecfg.DEFAULT_WEIGHTS_PATH == scfg.DEFAULT_WEIGHTS_PATH


def test_default_templates_path_is_packaged_alongside_the_module():
    assert ecfg.DEFAULT_TEMPLATES_PATH.name == "explanation_templates.yaml"
    assert ecfg.DEFAULT_TEMPLATES_PATH.parent.name == "explanation"


def test_eligible_schema_fields_are_stable_and_ordered():
    # S2-06a fields first, then the two caveat fields S2-06b appends (both paths).
    assert ecfg.ELIGIBLE_FIELDS == (
        "cell_id", "eligible", "headline", "positive_factors", "weaknesses",
        "proxy_caveats", "data_quality_notes",
    )


def test_excluded_schema_fields_are_stable_and_ordered():
    # S2-06b excluded path: identity + eligibility + reasons + caveats.
    assert ecfg.EXCLUDED_FIELDS == (
        "cell_id", "eligible", "exclusion_reasons",
        "proxy_caveats", "data_quality_notes",
    )


def test_all_fields_is_the_csv_header_union():
    # The CSV header is the union; existing eligible columns keep their order,
    # the excluded-only field is appended last.
    assert ecfg.ALL_FIELDS == (
        "cell_id", "eligible", "headline", "positive_factors", "weaknesses",
        "proxy_caveats", "data_quality_notes", "exclusion_reasons",
    )


def test_s2_06b_input_columns_composed_from_upstream_config():
    """The excluded/confidence input columns are carried from upstream, never re-typed."""
    from pipeline.exclusions import config as xcfg
    from pipeline.exclusions import rules as xrules

    # Option B: the integrated table carries the two DELIMITED F16 reason forms,
    # not the paired JSON column; both names come from the exclusions config.
    assert ecfg.TRIGGERED_RULES_COLUMN == "triggered_rules"
    assert ecfg.EXCLUSION_REASON_COLUMN == "exclusion_reason"
    assert ecfg.TRIGGERED_RULES_COLUMN in xcfg.OUTPUT_COLUMNS
    assert ecfg.EXCLUSION_REASON_COLUMN in xcfg.OUTPUT_COLUMNS
    assert ecfg.REASON_DELIMITER == xrules.REASON_DELIMITER
    assert ecfg.CONFIDENCE_LEVEL_COLUMN == icfg.CONFIDENCE_COLUMNS[0]
    assert ecfg.CONFIDENCE_SCORE_COLUMN == icfg.CONFIDENCE_COLUMNS[1]
    assert ecfg.CONFIDENCE_NOTES_COLUMN == icfg.CONFIDENCE_COLUMNS[2]
    assert ecfg.CONFIDENCE_NO_NOTES == icfg.CONFIDENCE_NO_NOTES
    assert ecfg.CONFIDENCE_LEVELS == icfg.DATA_CONFIDENCE_LEVELS


def test_stage_identity():
    assert ecfg.STAGE_NAME == "explanation"
    assert ecfg.MODULE_NAME == "explanation.run"
