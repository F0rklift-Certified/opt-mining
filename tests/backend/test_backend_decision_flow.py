"""
S2-09 cross-module backend test suite.

The feature tickets own detailed unit tests for their individual modules.  This
suite adds the two safeguards S2-09 owns:

* a tiny controlled case whose scores and ranks are hand-computed; and
* a deterministic integration run over the frozen S2-02 NSW dataset, covering
  eligibility/exclusions, normalisation, scoring, ranking, explanations and
  scenario re-ranking.

The frozen-data assertions intentionally pin both the input SHA-256 and a small
result snapshot.  An intentional dataset or decision-rule change therefore
requires an explicit review and snapshot update instead of silently changing
the ranking produced in CI.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pytest

from pipeline.common.geo import sha256_file
from pipeline.explanation.engine import (
    CellConfidence,
    CellExplanationInput,
    CriterionView,
    explain_cell,
)
from pipeline.explanation.load import load_explanation_inputs
from pipeline.explanation.templates import load_templates
from pipeline.explanation.write import build_explanations
from pipeline.scoring import config as scoring_config
from pipeline.scoring.load import load_integrated
from pipeline.scoring.normalise import Bounds, compute_bounds
from pipeline.scoring.scenarios import (
    Scenario,
    ScenarioComparison,
    compare_scenarios,
    load_scenarios,
)
from pipeline.scoring.score import eligible_mask, score_and_rank
from pipeline.scoring.weights import Criterion, WeightsConfig, load_weights
from pipeline.scoring.write import build_scored_table, write_scored_table


FROZEN_INTEGRATED_SHA256 = (
    "b7cd3d261abfdedd613301e0e2fdd07e3381178deb8ce8aff506a066117a1e61"
)
FROZEN_ROWS = 47_311
FROZEN_ELIGIBLE_ROWS = 1_233
FROZEN_EXCLUDED_ROWS = 46_078

EXPECTED_BASELINE_TOP_FIVE = (
    ("S30.186_E151.636", 0.9324172958364101),
    ("S30.636_E151.586", 0.9304033540651924),
    ("S30.086_E151.686", 0.9241267054330178),
    ("S30.236_E151.586", 0.9237187266324157),
    ("S30.286_E151.636", 0.9236170726352617),
)
EXPECTED_WIND_LED_TOP_FIVE = (
    "S30.086_E151.686",
    "S30.086_E151.736",
    "S30.186_E151.636",
    "S30.236_E151.586",
    "S30.286_E151.636",
)
EXPECTED_GRID_LED_TOP_FIVE = (
    "S30.636_E151.586",
    "S30.286_E151.636",
    "S30.136_E151.686",
    "S30.236_E151.586",
    "S30.286_E151.686",
)
EXPECTED_SCENARIO_RANK_CHANGES = 1_228
EXPECTED_EXPLANATION_SHA256 = (
    "36b82695ba4ec1c78e260399891d4050034d8077650cc5fe4de2d71152bdba4b"
)
TOLERANCE = 1e-12


def _explanation_digest(records: list[dict]) -> str:
    """Stable digest of the ordered, structured explanation output."""
    payload = json.dumps(
        records,
        ensure_ascii=False,
        sort_keys=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class FrozenBackendRun:
    """One complete in-memory decision run over the frozen NSW dataset."""

    features: pd.DataFrame
    mask: pd.Series
    weights: WeightsConfig
    bounds: dict[str, Bounds]
    scored: pd.DataFrame
    explanation_inputs: object
    explanations: list[dict]
    scenarios: dict[str, Scenario]
    comparison: ScenarioComparison


@pytest.fixture(scope="module")
def frozen_backend_run(tmp_path_factory) -> FrozenBackendRun:
    """
    Run the real decision components once over the committed S2-02 baseline.

    The scored artefact is written only to pytest's temporary directory.  It is
    then loaded by the real explanation input path, which reconciles persisted
    contributions with freshly recomputed values before explanations are built.
    No tracked DATA output is modified by this test.
    """
    weights = load_weights(scoring_config.DEFAULT_WEIGHTS_PATH)
    features = load_integrated(scoring_config.INTEGRATED_PATH, weights.criteria)
    mask = eligible_mask(features)
    bounds = compute_bounds(features.loc[mask], weights.criteria)
    scored = score_and_rank(features, weights, bounds=bounds)

    output_dir = tmp_path_factory.mktemp("s2_09_backend")
    scored_gpkg = output_dir / "scored.gpkg"
    scored_csv = output_dir / "scored.csv"
    scored_table = build_scored_table(features, scored, weights)
    write_scored_table(scored_table, scored_gpkg, scored_csv)

    explanation_inputs = load_explanation_inputs(
        scored_table_path=scored_gpkg,
        integrated_path=scoring_config.INTEGRATED_PATH,
        weights_path=scoring_config.DEFAULT_WEIGHTS_PATH,
    )
    templates = load_templates()
    explanations = build_explanations(
        explanation_inputs.cells,
        templates,
        explanation_inputs.excluded_cells,
    )

    scenarios = load_scenarios()
    comparison = compare_scenarios(
        features,
        scenarios["wind_led"],
        scenarios["grid_led"],
    )
    return FrozenBackendRun(
        features=features,
        mask=mask,
        weights=weights,
        bounds=bounds,
        scored=scored,
        explanation_inputs=explanation_inputs,
        explanations=explanations,
        scenarios=scenarios,
        comparison=comparison,
    )


# ---------------------------------------------------------------------------
# Controlled, hand-computed case
# ---------------------------------------------------------------------------
# Eligible bounds are wind [0, 10] and distance [0, 10].  X is excluded and
# deliberately extreme, so it must not stretch either bound.
#
# Wind-led weights (0.75 wind, 0.25 distance; distance is lower-is-better):
#   A: 0.75*1.0 + 0.25*0.0 = 0.75   -> rank 1
#   C: 0.75*0.5 + 0.25*0.5 = 0.50   -> rank 2 (tie by cell_id)
#   D: 0.75*0.5 + 0.25*0.5 = 0.50   -> rank 3
#   B: 0.75*0.0 + 0.25*1.0 = 0.25   -> rank 4
#   X: excluded -> null score and rank
#
# Grid-led reverses the weights (0.25, 0.75), so B rises to rank 1 and A falls
# to rank 4 while C/D remain tied at ranks 2/3.


def _controlled_features() -> pd.DataFrame:
    return pd.DataFrame(
        {
            # Deliberately not sorted: rank ties must use cell_id, not row order.
            "cell_id": ["D", "B", "A", "C", "X"],
            "wind_speed": [5.0, 0.0, 10.0, 5.0, 999.0],
            "dist_transmission_km": [5.0, 0.0, 10.0, 5.0, -999.0],
            "eligible": [True, True, True, True, False],
            "data_confidence": ["high"] * 5,
        }
    )


def _controlled_weights(wind: float, grid: float, config_id: str) -> WeightsConfig:
    return WeightsConfig(
        criteria=(
            Criterion(
                "wind_speed",
                wind,
                scoring_config.HIGHER_IS_BETTER,
                "resource quality",
            ),
            Criterion(
                "dist_transmission_km",
                grid,
                scoring_config.LOWER_IS_BETTER,
                "connection distance",
            ),
        ),
        confidence_discount=False,
        confidence_factors={"high": 1.0, "medium": 0.9, "low": 0.8},
        config_id=config_id,
    )


def test_controlled_case_matches_hand_computed_scores_ranks_and_tie_break():
    features = _controlled_features()
    weights = _controlled_weights(0.75, 0.25, "controlled-wind")
    scored = score_and_rank(features, weights).set_index("cell_id")

    assert scored.loc["A", scoring_config.SCORE_COLUMN] == pytest.approx(0.75)
    assert scored.loc["C", scoring_config.SCORE_COLUMN] == pytest.approx(0.50)
    assert scored.loc["D", scoring_config.SCORE_COLUMN] == pytest.approx(0.50)
    assert scored.loc["B", scoring_config.SCORE_COLUMN] == pytest.approx(0.25)
    assert scored.loc[["A", "C", "D", "B"], scoring_config.RANK_COLUMN].tolist() == [
        1,
        2,
        3,
        4,
    ]

    contribution_columns = list(weights.contribution_columns)
    assert scored.loc["A", contribution_columns].tolist() == pytest.approx([0.75, 0.0])
    assert scored.loc["B", contribution_columns].tolist() == pytest.approx([0.0, 0.25])
    assert scored.loc["C", contribution_columns].sum() == pytest.approx(0.50)
    assert scored.loc["X", [scoring_config.SCORE_COLUMN, scoring_config.RANK_COLUMN]].isna().all()
    assert scored.loc["X", contribution_columns].isna().all()


def test_controlled_case_explanation_uses_scoring_intermediates():
    features = _controlled_features()
    weights = _controlled_weights(0.75, 0.25, "controlled-wind")
    bounds = compute_bounds(features.loc[features["eligible"]], weights.criteria)
    scored = score_and_rank(features, weights, bounds=bounds).set_index("cell_id")
    row = scored.loc["A"]
    cell = CellExplanationInput(
        cell_id="A",
        criteria=tuple(
            CriterionView(
                feature=criterion.feature,
                contribution=float(row[criterion.contribution_column]),
                norm=float(row[f"norm_{criterion.feature}"]),
                bounds=bounds[criterion.feature],
            )
            for criterion in weights.criteria
        ),
        order=weights.features,
        confidence=CellConfidence("high", "—"),
    )

    explanation = explain_cell(cell, load_templates())
    assert explanation["positive_factors"] == ["Strong wind resource (top decile)"]
    assert explanation["weaknesses"] == ["Distant from transmission (limited)"]
    assert explanation["data_quality_notes"] == ["Confidence: high"]
    assert explanation == explain_cell(cell, load_templates())


def test_controlled_case_scenario_re_ranking_matches_hand_computation():
    features = _controlled_features()
    wind = Scenario(
        "wind_led",
        "Wind-led",
        "controlled wind preference",
        _controlled_weights(0.75, 0.25, "controlled-wind"),
    )
    grid = Scenario(
        "grid_led",
        "Grid-led",
        "controlled grid preference",
        _controlled_weights(0.25, 0.75, "controlled-grid"),
    )
    rows = {row.cell_id: row for row in compare_scenarios(features, wind, grid).rows}

    assert (rows["A"].rank_a, rows["A"].rank_b, rows["A"].rank_delta) == (1, 4, -3)
    assert (rows["B"].rank_a, rows["B"].rank_b, rows["B"].rank_delta) == (4, 1, 3)
    assert (rows["C"].rank_a, rows["C"].rank_b) == (2, 2)
    assert (rows["D"].rank_a, rows["D"].rank_b) == (3, 3)
    assert "X" not in rows


# ---------------------------------------------------------------------------
# Frozen S2-02 dataset integration guarantees
# ---------------------------------------------------------------------------


def test_frozen_dataset_identity_and_exclusion_population(frozen_backend_run):
    run = frozen_backend_run
    manifest_path = Path("DATA/integration/metadata/integration_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))["derived_features"][0]

    assert manifest["sha256_gpkg"] == FROZEN_INTEGRATED_SHA256
    assert sha256_file(scoring_config.INTEGRATED_PATH) == FROZEN_INTEGRATED_SHA256
    assert len(run.features) == FROZEN_ROWS
    assert int(run.mask.sum()) == FROZEN_ELIGIBLE_ROWS
    assert int((~run.mask).sum()) == FROZEN_EXCLUDED_ROWS


def test_excluded_cells_never_score_or_influence_normalisation(frozen_backend_run):
    run = frozen_backend_run
    decision_columns = [
        scoring_config.SCORE_COLUMN,
        scoring_config.RANK_COLUMN,
        *run.weights.contribution_columns,
    ]
    assert run.scored.loc[~run.mask, decision_columns].isna().all().all()

    # Poison every excluded criterion value.  If an excluded row leaks into a
    # bound, at least one eligible normalised value, score or rank will change.
    poisoned = run.features.copy(deep=True)
    for index, criterion in enumerate(run.weights.criteria, start=1):
        column = criterion.feature
        if pd.api.types.is_bool_dtype(poisoned[column]):
            poisoned.loc[~run.mask, column] = ~poisoned.loc[~run.mask, column]
        else:
            poisoned.loc[~run.mask, column] = (-1.0 if index % 2 else 1.0) * 1e12

    rerun = score_and_rank(poisoned, run.weights)
    compare_columns = [
        *(f"norm_{feature}" for feature in run.weights.features),
        *run.weights.contribution_columns,
        scoring_config.SCORE_COLUMN,
        scoring_config.RANK_COLUMN,
    ]
    pd.testing.assert_frame_equal(
        run.scored.loc[run.mask, compare_columns],
        rerun.loc[run.mask, compare_columns],
        check_exact=True,
    )
    assert rerun.loc[~run.mask, decision_columns].isna().all().all()


def test_frozen_contributions_reconstruct_every_total_score(frozen_backend_run):
    run = frozen_backend_run
    eligible = run.scored.loc[run.mask]
    contribution_sum = eligible[list(run.weights.contribution_columns)].sum(axis=1)
    pd.testing.assert_series_equal(
        contribution_sum,
        eligible[scoring_config.SCORE_COLUMN],
        check_names=False,
        rtol=0.0,
        atol=scoring_config.RECONCILE_TOLERANCE,
    )


def test_frozen_full_flow_matches_reviewed_result_snapshot(frozen_backend_run):
    run = frozen_backend_run
    ranked = run.scored.loc[run.mask].sort_values(scoring_config.RANK_COLUMN)
    actual_top = list(
        ranked[[scoring_config.CELL_ID_COLUMN, scoring_config.SCORE_COLUMN]]
        .head(5)
        .itertuples(index=False, name=None)
    )
    assert [cell_id for cell_id, _ in actual_top] == [
        cell_id for cell_id, _ in EXPECTED_BASELINE_TOP_FIVE
    ]
    assert [score for _, score in actual_top] == pytest.approx(
        [score for _, score in EXPECTED_BASELINE_TOP_FIVE], abs=TOLERANCE
    )

    assert len(run.explanations) == FROZEN_ROWS
    assert _explanation_digest(run.explanations) == EXPECTED_EXPLANATION_SHA256

    rows = run.comparison.rows
    assert len(rows) == FROZEN_ELIGIBLE_ROWS
    assert sum(row.rank_delta != 0 for row in rows) == EXPECTED_SCENARIO_RANK_CHANGES
    assert tuple(row.cell_id for row in rows[:5]) == EXPECTED_WIND_LED_TOP_FIVE
    assert tuple(
        row.cell_id for row in sorted(rows, key=lambda item: item.rank_b)[:5]
    ) == EXPECTED_GRID_LED_TOP_FIVE


def test_same_input_is_deterministic_across_all_decision_outputs(frozen_backend_run):
    run = frozen_backend_run
    second_scored = score_and_rank(run.features.copy(deep=True), run.weights)
    pd.testing.assert_frame_equal(run.scored, second_scored, check_exact=True)

    templates = load_templates()
    second_explanations = build_explanations(
        run.explanation_inputs.cells,
        templates,
        run.explanation_inputs.excluded_cells,
    )
    assert second_explanations == run.explanations

    second_comparison = compare_scenarios(
        run.features.copy(deep=True),
        run.scenarios["wind_led"],
        run.scenarios["grid_led"],
    )
    assert second_comparison.to_dict() == run.comparison.to_dict()


def test_explanations_cover_ranked_and_excluded_paths(frozen_backend_run):
    run = frozen_backend_run
    by_cell = {record["cell_id"]: record for record in run.explanations}
    top_cell = EXPECTED_BASELINE_TOP_FIVE[0][0]
    top_explanation = by_cell[top_cell]

    assert top_explanation["eligible"] is True
    assert top_explanation["positive_factors"]
    assert top_explanation["headline"]
    assert top_explanation["data_quality_notes"]

    excluded_id = str(run.features.loc[~run.mask, "cell_id"].iloc[0])
    excluded_explanation = by_cell[excluded_id]
    assert excluded_explanation["eligible"] is False
    assert excluded_explanation["exclusion_reasons"]
    assert "positive_factors" not in excluded_explanation
    assert "weaknesses" not in excluded_explanation
