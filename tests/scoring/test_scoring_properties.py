"""
Property-based tests for the S1-10 baseline suitability model.

Each test corresponds to one numbered property in the feature design document
and runs at least 100 generated examples. Where the unit tests in
`test_scoring.py` pin specific hand-computed numbers, these assert the
invariants that must hold for EVERY valid input — random mixes of eligible
and excluded cells, negative and zero criterion values, constant columns,
booleans, nulls, and both discount settings.

The pure Scoring_Function is exercised directly on in-memory frames, so no
test here touches the filesystem.
"""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from pipeline.scoring import config as scfg
from pipeline.scoring.normalise import compute_bounds, normalise_series
from pipeline.scoring.score import eligible_mask, score_and_rank, score_frame
from pipeline.scoring.weights import Criterion, WeightsConfig, load_weights

SETTINGS = settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)

FEATURES = ("wind_speed", "dist_transmission_km", "demand_proxy", "inside_rez")

finite = st.floats(
    min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False, width=32
)


@st.composite
def random_table(draw, min_rows=1, max_rows=25):
    """
    A synthetic integrated table: unique cell_ids, a random eligibility per
    cell, random criterion values (including negatives, zeros and columns that
    happen to be constant), a boolean criterion, and a random S1-09 confidence.
    """
    n = draw(st.integers(min_value=min_rows, max_value=max_rows))
    cell_ids = draw(
        st.lists(
            st.text(alphabet="ABCDEFGHIJ0123456789", min_size=1, max_size=6),
            min_size=n, max_size=n, unique=True,
        )
    )
    frame = pd.DataFrame({"cell_id": cell_ids})
    frame["eligible"] = draw(
        st.lists(st.booleans(), min_size=n, max_size=n)
    )
    for feature in ("wind_speed", "dist_transmission_km", "demand_proxy"):
        # Occasionally force a constant column to exercise the 0/0 path.
        if draw(st.booleans()):
            frame[feature] = draw(finite)
        else:
            frame[feature] = draw(st.lists(finite, min_size=n, max_size=n))
    frame["inside_rez"] = draw(st.lists(st.booleans(), min_size=n, max_size=n))
    frame["data_confidence"] = draw(
        st.lists(st.sampled_from(list(scfg.CONFIDENCE_LEVELS)), min_size=n, max_size=n)
    )
    return frame


@st.composite
def random_weights(draw, discount=None):
    """A valid weights config: non-negative weights with a positive sum."""
    features = draw(
        st.lists(st.sampled_from(FEATURES), min_size=1, max_size=len(FEATURES),
                 unique=True)
    )
    criteria = []
    for feature in features:
        criteria.append(
            Criterion(
                feature=feature,
                weight=draw(st.floats(min_value=0.0, max_value=10.0,
                                      allow_nan=False, width=32)),
                direction=draw(st.sampled_from(list(scfg.DIRECTIONS))),
                rationale=f"{feature} rationale",
            )
        )
    assume(sum(c.weight for c in criteria) > 0)
    if discount is None:
        discount = draw(st.booleans())
    return WeightsConfig(
        criteria=tuple(criteria),
        confidence_discount=discount,
        confidence_factors={"high": 1.0, "medium": 0.75, "low": 0.5},
        config_id="property-test",
    )


@st.composite
def _separable_table(draw, min_rows=2, max_rows=20):
    """
    A table with >= 2 eligible cells that are SEPARABLE on two criteria:
    `wind_speed` and `dist_transmission_km` are given anti-correlated ranks
    across the eligible cells, so a model that weights the first differently
    from the second is forced to score at least one eligible cell differently.

    This makes Property 5 half (b) a genuine assertion: if the output were
    driven by a hidden constant rather than the loaded weights, the two
    weightings would score identically and the test would fail.
    """
    n = draw(st.integers(min_value=min_rows, max_value=max_rows))
    cell_ids = [f"C{i:03d}" for i in range(n)]
    frame = pd.DataFrame({"cell_id": cell_ids})
    # Every cell eligible so there is always a separable eligible population.
    frame["eligible"] = True
    # wind_speed ascends, dist_transmission_km descends: the two criteria
    # rank the eligible cells in opposite orders, so emphasising one vs the
    # other cannot yield identical scores.
    frame["wind_speed"] = [float(i) for i in range(n)]
    frame["dist_transmission_km"] = [float(n - i) for i in range(n)]
    frame["demand_proxy"] = draw(st.lists(finite, min_size=n, max_size=n))
    frame["inside_rez"] = draw(st.lists(st.booleans(), min_size=n, max_size=n))
    frame["data_confidence"] = draw(
        st.lists(st.sampled_from(list(scfg.CONFIDENCE_LEVELS)), min_size=n, max_size=n)
    )
    return frame


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    # Feature: s1-10-baseline-suitability-model, Property 1: the Scored_Table
    # cell_id multiset equals the input cell_id set exactly — each appears
    # once, none missing, none duplicated, none invented — reused unchanged.
    @SETTINGS
    @given(table=random_table(), weights=random_weights())
    def test_property_1_cell_id_preservation(self, table, weights):
        scored = score_and_rank(table, weights)
        assert list(scored["cell_id"]) == list(table["cell_id"])
        assert not scored["cell_id"].duplicated().any()
        assert len(scored) == len(table)

    # Feature: s1-10-baseline-suitability-model, Property 2: directional
    # normalisation matches (v-lo)/(hi-lo) and its inversion, and a boolean
    # maps to the fixed [0, 1] endpoints for its direction.
    @SETTINGS
    @given(table=random_table(min_rows=2), weights=random_weights())
    def test_property_2_directional_normalisation(self, table, weights):
        eligible = table.loc[eligible_mask(table)]
        assume(len(eligible) > 0)
        bounds = compute_bounds(eligible, weights.criteria)
        for criterion in weights.criteria:
            b = bounds[criterion.feature]
            got = normalise_series(eligible[criterion.feature], b, criterion.direction)
            values = eligible[criterion.feature]
            if b.is_boolean:
                expected = values.astype(float)
                if criterion.direction == scfg.LOWER_IS_BETTER:
                    expected = 1.0 - expected
            elif b.hi == b.lo:
                expected = pd.Series(
                    scfg.CONSTANT_CRITERION_VALUE, index=values.index, dtype=float
                )
            else:
                expected = (values.astype(float) - b.lo) / (b.hi - b.lo)
                if criterion.direction == scfg.LOWER_IS_BETTER:
                    expected = 1.0 - expected
                expected = expected.clip(0.0, 1.0)
            np.testing.assert_allclose(
                got.to_numpy(dtype=float), expected.to_numpy(dtype=float), atol=1e-9
            )

    # Feature: s1-10-baseline-suitability-model, Property 3: every normalised
    # feature lies within the inclusive [0, 1] range.
    @SETTINGS
    @given(table=random_table(), weights=random_weights())
    def test_property_3_normalised_features_in_unit_interval(self, table, weights):
        scored = score_frame(table, weights)
        for criterion in weights.criteria:
            values = scored[f"norm_{criterion.feature}"].dropna()
            assert ((values >= 0.0) & (values <= 1.0)).all()

    # Feature: s1-10-baseline-suitability-model, Property 4: normalisation
    # bounds equal the eligible min/max and are unchanged when excluded-cell
    # values are perturbed.
    @SETTINGS
    @given(table=random_table(min_rows=2), weights=random_weights())
    def test_property_4_bounds_from_eligible_only(self, table, weights):
        mask = eligible_mask(table)
        assume(mask.any() and (~mask).any())
        eligible = table.loc[mask]
        before = compute_bounds(eligible, weights.criteria)

        perturbed = table.copy()
        for criterion in weights.criteria:
            if criterion.feature == "inside_rez":
                continue
            perturbed.loc[~mask, criterion.feature] = 1e9
        after = compute_bounds(perturbed.loc[mask], weights.criteria)

        for criterion in weights.criteria:
            assert before[criterion.feature].lo == after[criterion.feature].lo
            assert before[criterion.feature].hi == after[criterion.feature].hi
            b = before[criterion.feature]
            if not b.is_boolean and b.n_observed:
                values = eligible[criterion.feature].astype(float)
                assert b.lo == pytest.approx(values.min())
                assert b.hi == pytest.approx(values.max())

    # Feature: s1-10-baseline-suitability-model, Property 5: the score equals
    # SUM(weight_i * norm_i) / SUM(applied weights), recomputed independently.
    @SETTINGS
    @given(table=random_table(), weights=random_weights(discount=False))
    def test_property_5_weighted_sum_correctness(self, table, weights):
        scored = score_frame(table, weights)
        mask = eligible_mask(table)
        for idx in scored.index[mask]:
            numerator = 0.0
            denominator = 0.0
            for criterion in weights.criteria:
                norm = scored.loc[idx, f"norm_{criterion.feature}"]
                if pd.isna(norm):
                    continue
                numerator += criterion.weight * float(norm)
                denominator += criterion.weight
            observed = scored.loc[idx, scfg.SCORE_COLUMN]
            if denominator == 0:
                assert pd.isna(observed)
            else:
                assert observed == pytest.approx(numerator / denominator, abs=1e-9)

    # Feature: s1-10-baseline-suitability-model, Property 6: every eligible
    # cell's final score lies within the inclusive [0, 1] range.
    @SETTINGS
    @given(table=random_table(), weights=random_weights())
    def test_property_6_score_in_unit_interval(self, table, weights):
        scores = score_frame(table, weights)[scfg.SCORE_COLUMN].dropna()
        assert ((scores >= 0.0) & (scores <= 1.0)).all()

    # Feature: s1-10-baseline-suitability-model, Property 7: the per-criterion
    # contributions sum to the final score within tolerance, under both the
    # discount-enabled and discount-disabled settings.
    @SETTINGS
    @given(table=random_table(), weights=random_weights())
    def test_property_7_contributions_reconcile(self, table, weights):
        scored = score_frame(table, weights)
        scored_mask = scored[scfg.SCORE_COLUMN].notna()
        columns = list(weights.contribution_columns)
        reconstructed = scored.loc[scored_mask, columns].sum(axis=1, skipna=True)
        residual = (reconstructed - scored.loc[scored_mask, scfg.SCORE_COLUMN]).abs()
        assert (residual <= scfg.RECONCILE_TOLERANCE).all()

    # Feature: s1-10-baseline-suitability-model, Property 8: with discounting
    # enabled the final score equals raw x factor; with it disabled the final
    # score equals the raw weighted-sum score.
    @SETTINGS
    @given(table=random_table(), weights=random_weights(discount=False))
    def test_property_8_confidence_discount_relation(self, table, weights):
        from dataclasses import replace

        plain = score_frame(table, weights)
        discounted = score_frame(table, replace(weights, confidence_discount=True))

        np.testing.assert_allclose(
            plain[scfg.SCORE_COLUMN].dropna().to_numpy(),
            plain["raw_score"].dropna().to_numpy(),
            atol=1e-12,
        )
        mask = discounted[scfg.SCORE_COLUMN].notna()
        factors = discounted.loc[mask, scfg.CONFIDENCE_COLUMN].map(
            weights.confidence_factors
        )
        np.testing.assert_allclose(
            discounted.loc[mask, scfg.SCORE_COLUMN].to_numpy(),
            (plain.loc[mask, "raw_score"] * factors).to_numpy(),
            atol=1e-9,
        )

    # Feature: s1-10-baseline-suitability-model, Property 9: every eligible
    # cell receives a score, rank and contributions; every excluded cell
    # receives nulls and takes no part in the ordering.
    @SETTINGS
    @given(table=random_table(), weights=random_weights())
    def test_property_9_only_eligible_cells_are_scored(self, table, weights):
        scored = score_and_rank(table, weights)
        mask = eligible_mask(table).to_numpy()
        scores = scored[scfg.SCORE_COLUMN]
        ranks = scored[scfg.RANK_COLUMN]

        assert scores[~mask].isna().all()
        assert ranks[~mask].isna().all()
        for column in weights.contribution_columns:
            assert scored.loc[~mask, column].isna().all()

        # An eligible cell is scored unless NO criterion had a usable value.
        usable = scored["applied_weight"].fillna(0) > 0
        assert scores[mask & usable.to_numpy()].notna().all()
        assert ranks[mask & usable.to_numpy()].notna().all()

    # Feature: s1-10-baseline-suitability-model, Property 10: rank is a
    # contiguous 1..n ordering, descending by score with ties broken by
    # ascending cell_id, and no rank is assigned to an unscored cell.
    @SETTINGS
    @given(table=random_table(), weights=random_weights())
    def test_property_10_rank_ordering_and_tie_break(self, table, weights):
        scored = score_and_rank(table, weights)
        ranked = scored[scored[scfg.RANK_COLUMN].notna()]
        n = len(ranked)
        assert sorted(int(r) for r in ranked[scfg.RANK_COLUMN]) == list(range(1, n + 1))
        assert scored.loc[scored[scfg.SCORE_COLUMN].isna(), scfg.RANK_COLUMN].isna().all()

        ordered = ranked.sort_values(scfg.RANK_COLUMN)
        scores = ordered[scfg.SCORE_COLUMN].to_numpy()
        assert all(scores[i] >= scores[i + 1] - 1e-12 for i in range(len(scores) - 1))
        for _, group in ordered.groupby(scfg.SCORE_COLUMN, sort=False):
            ids = list(group["cell_id"])
            assert ids == sorted(ids)

    # Feature: s1-10-baseline-suitability-model, Property 11: confidence
    # equals the input composite flag for that cell_id and is always a value
    # from the S1-09 vocabulary — never fabricated.
    @SETTINGS
    @given(table=random_table(), weights=random_weights())
    def test_property_11_confidence_carried_through(self, table, weights):
        scored = score_frame(table, weights)
        assert list(scored[scfg.CONFIDENCE_COLUMN]) == list(table["data_confidence"])
        assert scored[scfg.CONFIDENCE_COLUMN].isin(list(scfg.CONFIDENCE_LEVELS)).all()

    # Feature: s1-10-baseline-suitability-model, Property 12: invalid weights
    # configurations are rejected, and two distinct valid configurations
    # produce scores determined by the loaded weights rather than a constant.
    @SETTINGS
    @given(
        table=random_table(min_rows=3),
        bad_direction=st.text(min_size=1, max_size=8).filter(
            lambda s: s not in scfg.DIRECTIONS
        ),
        bad_weight=st.floats(min_value=-100, max_value=-0.001, allow_nan=False),
    )
    def test_property_12_invalid_configs_rejected(self, table, bad_direction, bad_weight):
        from pipeline.scoring.weights import ScoringConfigError, parse_weights

        base = {
            "criteria": [
                {"feature": "wind_speed", "weight": 1.0,
                 "direction": scfg.HIGHER_IS_BETTER, "rationale": "r"}
            ]
        }
        bad = {"criteria": [dict(base["criteria"][0], direction=bad_direction)]}
        with pytest.raises(ScoringConfigError):
            parse_weights(bad)
        bad = {"criteria": [dict(base["criteria"][0], weight=bad_weight)]}
        with pytest.raises(ScoringConfigError):
            parse_weights(bad)
        bad = {"criteria": [dict(base["criteria"][0], weight=0.0)]}
        with pytest.raises(ScoringConfigError):
            parse_weights(bad)

    # Feature: s1-10-baseline-suitability-model, Property 13: wind_speed
    # affects the score only through its own contribution; it is never a
    # prediction target and no wind prediction column is emitted.
    @SETTINGS
    @given(table=random_table(min_rows=2), weights=random_weights(discount=False))
    def test_property_13_no_circular_modelling(self, table, weights):
        assume(any(c.feature == "wind_speed" for c in weights.criteria))
        scored = score_and_rank(table, weights)

        # No column claims to be a wind prediction or estimate.
        for column in scored.columns:
            lowered = column.lower()
            assert not (
                "wind" in lowered
                and any(word in lowered for word in ("pred", "estimate", "fitted", "hat"))
            )

        # Removing wind from the config removes exactly its contribution
        # column; every other criterion still contributes.
        others = tuple(c for c in weights.criteria if c.feature != "wind_speed")
        assume(others and sum(c.weight for c in others) > 0)
        from dataclasses import replace

        without = score_frame(table, replace(weights, criteria=others))
        assert "contrib_wind_speed" in scored.columns
        assert "contrib_wind_speed" not in without.columns

    # Feature: s1-10-baseline-suitability-model, Property 14: two runs over
    # identical inputs and an identical config produce identical normalised
    # features, scores, ranks and contributions.
    @SETTINGS
    @given(table=random_table(), weights=random_weights())
    def test_property_14_determinism(self, table, weights):
        first = score_and_rank(table, weights)
        second = score_and_rank(table.copy(), weights)
        pd.testing.assert_frame_equal(first, second)

    # Feature: s1-10-baseline-suitability-model, Property 15: a successful
    # run() returns summary paths that exist on disk. (Exercised as an
    # example test rather than a property — it is a single filesystem
    # contract, not a statement quantified over inputs.)

    # Feature: s1-10-baseline-suitability-model, Property 16: for any resolved
    # stage list containing both, integration precedes scoring.
    @SETTINGS
    @given(
        skip=st.lists(
            st.sampled_from(["wind", "geographic", "infrastructure", "demand", "grid"]),
            max_size=3, unique=True,
        )
    )
    def test_property_16_integration_precedes_scoring(self, skip):
        # A context manager rather than the monkeypatch fixture: Hypothesis
        # does not reset function-scoped fixtures between generated examples.
        from unittest.mock import patch

        from pipeline.__main__ import parse_args, resolve_stages

        argv = ["pipeline"]
        for domain in skip:
            argv += ["--skip", domain]
        with patch("sys.argv", argv):
            stages = resolve_stages(parse_args())
        if "integration" in stages and "scoring" in stages:
            assert stages.index("integration") < stages.index("scoring")


class TestRunPathsExist:
    """Property 15, as a single end-to-end example over a synthetic table."""

    def test_successful_run_returns_paths_that_exist(self, tmp_path, monkeypatch):
        import geopandas as gpd
        import yaml
        from shapely.geometry import Point

        from pipeline.scoring import config as module_config
        from pipeline.scoring import run as run_module

        frame = pd.DataFrame(
            {
                "cell_id": ["A", "B", "C"],
                "centroid_lat": [-30.0, -30.1, -30.2],
                "centroid_lon": [150.0, 150.1, 150.2],
                "wind_speed": [9.0, 7.0, 5.0],
                "dist_transmission_km": [1.0, 5.0, 9.0],
                "eligible": [True, True, False],
                "data_confidence": ["high", "medium", "low"],
            }
        )
        geo = gpd.GeoDataFrame(
            frame,
            geometry=[Point(lon, lat) for lon, lat in
                      zip(frame.centroid_lon, frame.centroid_lat)],
            crs="EPSG:4326",
        )
        integrated = tmp_path / "integrated.gpkg"
        geo.to_file(integrated, driver="GPKG", layer=module_config.INTEGRATED_LAYER)

        weights_path = tmp_path / "w.yaml"
        weights_path.write_text(yaml.safe_dump({
            "version": "test",
            "confidence_discount": False,
            "confidence_factors": {"high": 1.0, "medium": 0.9, "low": 0.8},
            "criteria": [
                {"feature": "wind_speed", "weight": 0.6,
                 "direction": "higher_is_better", "rationale": "resource"},
                {"feature": "dist_transmission_km", "weight": 0.4,
                 "direction": "lower_is_better", "rationale": "cost"},
            ],
        }), encoding="utf-8")

        outputs = tmp_path / "DATA" / "scoring"
        monkeypatch.setattr(module_config, "SCORING_DIR", outputs)
        monkeypatch.setattr(module_config, "SCORING_META_DIR", outputs / "metadata")

        summary = run_module.run(weights_path=weights_path, integrated_path=integrated)

        from pathlib import Path

        assert Path(summary["scored_table_path"]).exists()
        assert Path(summary["method_report_path"]).exists()
        assert summary["n_cells"] == 3
        assert summary["n_scored"] == 2
        assert summary["n_excluded"] == 1
        assert summary["weights_config_id"]
        assert summary["runtime_seconds"] >= 0


# ---------------------------------------------------------------------------
# S2-05 hardening — Property 5: Weights are data, not code
# ---------------------------------------------------------------------------
#
# Property 5 (design.md) has two halves that must BOTH hold:
#   (a) no weight numeric literal appears in `pipeline/scoring/` source; and
#   (b) changing the YAML weights changes the model output — the weights
#       genuinely flow from the configuration data through to the scores.
#
# The pre-existing `test_no_weight_literal_appears_in_the_scoring_source`
# (test_scoring.py) only checks that criterion FEATURE NAMES are absent from
# the source, and the "weights determine the output" claim previously lived
# only in a comment on Property 12. This class validates BOTH halves of
# Property 5 directly and is the S2-05 owner of the property.


def _scoring_source_files() -> list[Path]:
    """Every Python source file in the `pipeline/scoring/` package."""
    package = Path(scfg.__file__).parent
    return sorted(package.glob("*.py"))


def _default_weight_values() -> set[float]:
    """The distinct default criterion weights declared in the shipped YAML."""
    weights = load_weights(scfg.DEFAULT_WEIGHTS_PATH)
    return {float(c.weight) for c in weights.criteria}


def _numeric_literals(source: str) -> set[float]:
    """
    All numeric literals that appear in real CODE (not comments/docstrings).

    Parsing with the AST means comment text and triple-quoted documentation —
    where the model's formula and weights are legitimately DESCRIBED — are
    ignored; only executable literals count. Unary-minus constants (e.g.
    ``-1.0``) are folded so a negated literal is still caught.
    """
    tree = ast.parse(source)
    literals: set[float] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                and not isinstance(node.value, bool):
            literals.add(float(node.value))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) \
                and isinstance(node.operand, ast.Constant) \
                and isinstance(node.operand.value, (int, float)) \
                and not isinstance(node.operand.value, bool):
            literals.add(-float(node.operand.value))
    return literals


class TestProperty5WeightsAreData:
    """Property 5: weights are data, not code — both halves."""

    # Feature: s2-05-suitability-scoring-ranking, Property 5: Weights are data
    # Half (a): no weight numeric literal appears anywhere in the executable
    # source of `pipeline/scoring/`. The default weights live ONLY in
    # scoring_weights.yaml; the Python must not restate any of them as a code
    # literal. (AST-based, so the formula/weights DESCRIBED in docstrings and
    # comments are ignored — only real code literals are checked.)
    def test_property_5a_no_weight_literal_in_scoring_source(self):
        weight_values = _default_weight_values()
        assert weight_values, "expected the shipped YAML to declare weights"
        offenders: list[str] = []
        for module in _scoring_source_files():
            literals = _numeric_literals(module.read_text(encoding="utf-8"))
            clash = weight_values & literals
            if clash:
                offenders.append(f"{module.name}: {sorted(clash)}")
        assert not offenders, (
            "weight value(s) hard-coded as a literal in pipeline/scoring/ "
            f"source — weights must be data, not code: {offenders}"
        )

    # Feature: s2-05-suitability-scoring-ranking, Property 5: Weights are data
    # Half (b): changing the YAML weights changes the model output. For any
    # table with at least two eligible cells that are separable on two
    # criteria, a config that weights the FIRST criterion and one that weights
    # the SECOND produce different scores — proving the loaded weights, not a
    # hidden constant, drive the result.
    @SETTINGS
    @given(table=_separable_table())
    def test_property_5b_changing_weights_changes_output(self, table):
        c_first = Criterion("wind_speed", 1.0, scfg.HIGHER_IS_BETTER, "first")
        c_second = Criterion(
            "dist_transmission_km", 1.0, scfg.HIGHER_IS_BETTER, "second"
        )
        base = WeightsConfig(
            criteria=(c_first, c_second),
            confidence_discount=False,
            confidence_factors={"high": 1.0, "medium": 0.75, "low": 0.5},
            config_id="prop5-base",
        )
        # Emphasise the first criterion vs. emphasise the second.
        weights_a = replace(
            base,
            criteria=(replace(c_first, weight=9.0), replace(c_second, weight=1.0)),
        )
        weights_b = replace(
            base,
            criteria=(replace(c_first, weight=1.0), replace(c_second, weight=9.0)),
        )

        scores_a = score_frame(table, weights_a)[scfg.SCORE_COLUMN]
        scores_b = score_frame(table, weights_b)[scfg.SCORE_COLUMN]

        mask = eligible_mask(table)
        diff = (scores_a[mask] - scores_b[mask]).abs()
        # The table is constructed so the two criteria disagree on at least
        # one eligible cell; a genuine data-driven model must therefore score
        # that cell differently under the two weightings.
        assert (diff > 1e-9).any(), (
            "changing the weights left every eligible score unchanged — "
            "weights are not flowing from the config to the output"
        )


# ---------------------------------------------------------------------------
# S2-05 hardening — Property 1: Scores bounded
# ---------------------------------------------------------------------------
#
# Property 1 (design.md): every non-null `suitability_score` lies in the
# inclusive interval [0, 1].
#
# The pre-existing `test_property_6_score_in_unit_interval` asserts the same
# invariant, but it is tagged for the OLD feature
# `s1-10-baseline-suitability-model`. Following the precedent set by the
# S2-05 `TestProperty5WeightsAreData` class above, this class is the S2-05
# OWNER of Property 1: it is tagged for s2-05-suitability-scoring-ranking and
# asserts the bound on the full `score_and_rank` output (which nulls out
# excluded cells), over random mixes of eligible/excluded cells and with the
# confidence discount both on and off. The s1-10 test is left untouched.


class TestProperty1ScoresBounded:
    """Property 1: every non-null suitability_score is in [0, 1]."""

    # Feature: s2-05-suitability-scoring-ranking, Property 1: Scores bounded
    # Every non-null suitability_score produced by the full score_and_rank
    # pipeline lies in the inclusive [0, 1] interval, for any mix of eligible
    # and excluded cells and either confidence-discount setting.
    @SETTINGS
    @given(table=random_table(), weights=random_weights())
    def test_property_1_scores_bounded(self, table, weights):
        scored = score_and_rank(table, weights)
        scores = scored[scfg.SCORE_COLUMN]
        # Excluded cells are nulled out; only the non-null (scored) cells are
        # constrained. Drop the nulls and require every remaining score in [0, 1].
        non_null = scores.dropna()
        assert ((non_null >= 0.0) & (non_null <= 1.0)).all(), (
            "a non-null suitability_score fell outside [0, 1]: "
            f"min={non_null.min()!r}, max={non_null.max()!r}"
        )


# ---------------------------------------------------------------------------
# S2-05 hardening — Property 4 (scores half): Deterministic scoring
# ---------------------------------------------------------------------------
#
# Property 4 (design.md P4): two runs over identical inputs and weights
# produce identical scores AND ranks; ties resolve by ascending `cell_id`.
# The property has two halves, split across two tasks:
#   - the SCORES half (this class, task 3.3): two runs over identical inputs
#     and an identical Weights_Config yield identical SUITABILITY SCORES and
#     per-criterion CONTRIBUTIONS (Requirement 3.4); and
#   - the RANKING half (task 5.2): identical ranks with the ascending-cell_id
#     tie-break (Requirements 5.2, 5.4).
#
# The pre-existing `test_property_14_determinism` asserts full-frame equality
# but is tagged for the OLD feature `s1-10-baseline-suitability-model`.
# Following the precedent set by the S2-05 `TestProperty5WeightsAreData` and
# `TestProperty1ScoresBounded` classes above, this class is the S2-05 OWNER
# of Property 4's scores half: it is tagged for
# s2-05-suitability-scoring-ranking and asserts score+contribution
# determinism directly. The s1-10 test is left untouched.


class TestProperty4DeterministicScoring:
    """Property 4 (scores half): identical inputs + weights → identical scores."""

    # Feature: s2-05-suitability-scoring-ranking, Property 4: Deterministic scoring
    # Scores half: two runs of the pure Scoring_Function over identical inputs
    # and an identical Weights_Config return identical suitability scores and
    # identical per-criterion contributions — element-for-element, nulls in the
    # same places (Requirement 3.4). Exercised over random mixes of eligible
    # and excluded cells with the confidence discount both on and off; the
    # second run is fed an independent copy of the input so a run cannot see
    # any mutation left by the first.
    @SETTINGS
    @given(table=random_table(), weights=random_weights())
    def test_property_4_deterministic_scoring(self, table, weights):
        first = score_and_rank(table, weights)
        second = score_and_rank(table.copy(), weights)

        # The scores half asserts on the score plus every contribution column;
        # ranking determinism is task 5.2's scope and is asserted there.
        score_columns = [scfg.SCORE_COLUMN, *weights.contribution_columns]
        pd.testing.assert_frame_equal(
            first[score_columns],
            second[score_columns],
            check_exact=True,
        )


# ---------------------------------------------------------------------------
# S2-05 hardening — Property 3: Eligible-only
# ---------------------------------------------------------------------------
#
# Property 3 (design.md P3): every Eligible_Cell has a non-null
# score/rank/contributions; every Excluded_Cell has null
# score/rank/contributions and is absent from the ranking AND the
# normalisation bounds (Requirements 4.1, 4.2, 4.3).
#
# The pre-existing `test_property_9_only_eligible_cells_are_scored` and
# `test_property_4_bounds_from_eligible_only` assert these invariants, but
# they are tagged for the OLD feature `s1-10-baseline-suitability-model`.
# Following the precedent set by the S2-05 `TestProperty5WeightsAreData`,
# `TestProperty1ScoresBounded` and `TestProperty4DeterministicScoring`
# classes above, this class is the S2-05 OWNER of Property 3: it is tagged
# for s2-05-suitability-scoring-ranking and asserts all THREE facets of the
# eligible-only rule in one place. The s1-10 tests are left untouched.


class TestProperty3EligibleOnly:
    """Property 3: eligible cells scored; excluded cells null and off the ranking/bounds."""

    # Feature: s2-05-suitability-scoring-ranking, Property 3: Eligible-only
    # Facets (a) + (b): over random mixes of eligible/excluded cells and with
    # the confidence discount both on and off, the full score_and_rank output
    # gives every USABLE eligible cell a non-null score, rank and contribution
    # per criterion; every excluded cell (eligible false OR null) gets a null
    # score, null rank and null contributions, and no excluded cell appears in
    # the rank ordering (Requirements 4.1, 4.2). An eligible cell for which no
    # criterion had a usable value has no denominator and is legitimately
    # unscored — that is the documented applied_weight == 0 path, so the
    # non-null assertion is scoped to eligible cells with a positive applied
    # weight, exactly as the pure model defines "scored".
    @SETTINGS
    @given(table=random_table(), weights=random_weights())
    def test_property_3a_eligible_scored_excluded_null(self, table, weights):
        scored = score_and_rank(table, weights)
        mask = eligible_mask(table).to_numpy()
        scores = scored[scfg.SCORE_COLUMN]
        ranks = scored[scfg.RANK_COLUMN]
        contribution_columns = list(weights.contribution_columns)

        # (b) Every excluded cell: null score, null rank, null every contribution.
        assert scores[~mask].isna().all(), "an excluded cell has a non-null score"
        assert ranks[~mask].isna().all(), "an excluded cell has a non-null rank"
        for column in contribution_columns:
            assert scored.loc[~mask, column].isna().all(), (
                f"an excluded cell has a non-null contribution in {column}"
            )

        # (b) No excluded cell takes part in the ranking: the set of ranked
        # cell_ids is disjoint from the excluded cell_ids.
        ranked_ids = set(scored.loc[ranks.notna(), "cell_id"])
        excluded_ids = set(scored.loc[~mask, "cell_id"])
        assert ranked_ids.isdisjoint(excluded_ids), (
            "an excluded cell_id appears in the rank ordering"
        )

        # (a) Every eligible cell with a usable criterion is scored: non-null
        # score, non-null rank, and a non-null value in every contribution
        # column. (An eligible cell with applied_weight == 0 has no usable
        # criterion and is the documented unscored-eligible path.)
        usable = (scored["applied_weight"].fillna(0.0) > 0).to_numpy()
        eligible_scored = mask & usable
        assert scores[eligible_scored].notna().all(), (
            "a usable eligible cell was left with a null score"
        )
        assert ranks[eligible_scored].notna().all(), (
            "a usable eligible cell was left with a null rank"
        )
        for column in contribution_columns:
            assert scored.loc[eligible_scored, column].notna().all(), (
                f"a usable eligible cell has a null contribution in {column}"
            )

    # Feature: s2-05-suitability-scoring-ranking, Property 3: Eligible-only
    # Facet (c): the normalisation bounds are a function of the eligible
    # population ONLY. For any table with at least one eligible and one
    # excluded cell, perturbing the excluded cells' criterion values (here to
    # a large sentinel) leaves every criterion's lo/hi bound unchanged — the
    # excluded values take no part in the bounds (Requirement 4.3). Boolean
    # criteria use their fixed definitional domain and are exercised by the
    # non-boolean perturbation alongside the numeric criteria.
    @SETTINGS
    @given(table=random_table(min_rows=2), weights=random_weights())
    def test_property_3c_bounds_exclude_excluded_cells(self, table, weights):
        mask = eligible_mask(table)
        assume(mask.any() and (~mask).any())

        eligible = table.loc[mask]
        before = compute_bounds(eligible, weights.criteria)

        # Perturb ONLY the excluded rows' numeric criterion values to a large
        # sentinel; if the bounds leaked from excluded cells, hi would jump.
        perturbed = table.copy()
        for criterion in weights.criteria:
            if criterion.feature == "inside_rez":
                continue  # boolean domain is definitional, not population-derived
            perturbed.loc[~mask, criterion.feature] = 1e9
        after = compute_bounds(perturbed.loc[mask], weights.criteria)

        for criterion in weights.criteria:
            assert before[criterion.feature].lo == after[criterion.feature].lo, (
                f"lower bound for {criterion.feature} shifted when only "
                "excluded-cell values changed"
            )
            assert before[criterion.feature].hi == after[criterion.feature].hi, (
                f"upper bound for {criterion.feature} shifted when only "
                "excluded-cell values changed"
            )

# ---------------------------------------------------------------------------
# S2-05 hardening — Property 4 (ranking half): Deterministic ranking
# ---------------------------------------------------------------------------
#
# Property 4 (design.md P4): two runs over identical inputs and weights
# produce identical scores AND ranks; ties resolve by ascending `cell_id`.
# The property is split across two tasks:
#   - the SCORES half (TestProperty4DeterministicScoring, task 3.3): score +
#     contribution determinism (Requirement 3.4); and
#   - the RANKING half (this class, task 5.2): identical `rank` values across
#     two runs over identical inputs and an identical Weights_Config, with
#     score ties broken by ascending `cell_id` (Requirements 5.2, 5.4).
#
# The pre-existing `test_property_10_rank_ordering_and_tie_break` and
# `test_property_14_determinism` assert overlapping invariants but are tagged
# for the OLD feature `s1-10-baseline-suitability-model`. Following the
# precedent set by the S2-05 `TestProperty5WeightsAreData`,
# `TestProperty1ScoresBounded`, `TestProperty4DeterministicScoring` and
# `TestProperty3EligibleOnly` classes above, this class is the S2-05 OWNER of
# Property 4's ranking half: it is tagged for s2-05-suitability-scoring-ranking
# and asserts rank determinism and the tie-break directly. The s1-10 tests are
# left untouched.


@st.composite
def _tie_inducing_table(draw, min_rows=2, max_rows=20):
    """
    A synthetic integrated table deliberately engineered so that MANY eligible
    cells share the SAME suitability score, forcing the ascending-`cell_id`
    tie-break to actually decide the ranking.

    Every criterion value is drawn from a TINY discrete pool (a handful of
    repeated numbers) and the boolean criterion is likewise repeated, so
    distinct cells collapse onto identical normalised feature vectors and
    therefore identical scores. `cell_id`s are unique but generated in a
    SHUFFLED order (not already ascending), so a naive ranker that leaned on
    row/insertion order rather than the documented `cell_id` tie-break would
    produce a different, order-dependent ranking and fail the assertion.
    """
    n = draw(st.integers(min_value=min_rows, max_value=max_rows))
    # Unique, zero-padded cell_ids drawn in a shuffled (non-sorted) order so
    # the tie-break cannot accidentally coincide with arrival order.
    ids = [f"C{i:03d}" for i in range(n)]
    cell_ids = draw(st.permutations(ids))
    frame = pd.DataFrame({"cell_id": list(cell_ids)})

    # Mostly eligible, with the occasional excluded cell so the ranking is
    # exercised alongside the null-rank rule; guarantee >= 2 eligible cells so
    # a tie is possible.
    eligibility = draw(st.lists(st.booleans(), min_size=n, max_size=n))
    if sum(eligibility) < 2:
        eligibility = [True] * n
    frame["eligible"] = eligibility

    # A tiny discrete pool per criterion => heavy score collisions => ties.
    small_pool = st.sampled_from([0.0, 1.0, 2.0])
    for feature in ("wind_speed", "dist_transmission_km", "demand_proxy"):
        frame[feature] = draw(st.lists(small_pool, min_size=n, max_size=n))
    frame["inside_rez"] = draw(st.lists(st.booleans(), min_size=n, max_size=n))
    frame["data_confidence"] = draw(
        st.lists(st.sampled_from(list(scfg.CONFIDENCE_LEVELS)), min_size=n, max_size=n)
    )
    return frame


class TestProperty4DeterministicRanking:
    """Property 4 (ranking half): identical ranks across runs; ties by ascending cell_id."""

    # Feature: s2-05-suitability-scoring-ranking, Property 4: Deterministic ranking
    # (a) Determinism: two runs of the full score_and_rank pipeline over
    # identical inputs and an identical Weights_Config return identical `rank`
    # values — element-for-element, nulls (excluded cells) in the same places
    # (Requirement 5.4). The second run is fed an independent copy of the input
    # so no run can observe a mutation left by the other. Exercised over random
    # mixes of eligible/excluded cells with the confidence discount both on and
    # off.
    @SETTINGS
    @given(table=random_table(), weights=random_weights())
    def test_property_4_ranks_are_deterministic(self, table, weights):
        first = score_and_rank(table, weights)
        second = score_and_rank(table.copy(), weights)
        pd.testing.assert_series_equal(
            first[scfg.RANK_COLUMN],
            second[scfg.RANK_COLUMN],
            check_exact=True,
        )

    # Feature: s2-05-suitability-scoring-ranking, Property 4: Deterministic ranking
    # (b) Tie-break: over tables ENGINEERED to produce many equal scores, the
    # rank is a contiguous 1..n ordering over the scored (eligible, usable)
    # cells with a null rank on every unscored cell; ranks descend by score;
    # and within any group of cells sharing a score, the assigned ranks follow
    # ASCENDING `cell_id` (Requirement 5.2). This is asserted three ways:
    #   * the ranked cell_ids form the exact set 1..n with no gap or duplicate;
    #   * a cell with a strictly higher score always outranks a lower-scored one;
    #   * cells tied on score are ordered by ascending cell_id.
    # Because the tie-inducing strategy shuffles cell_ids, a ranker that used
    # arrival order instead of the documented tie-break would fail here.
    @SETTINGS
    @given(table=_tie_inducing_table(), weights=random_weights())
    def test_property_4_ties_break_by_ascending_cell_id(self, table, weights):
        scored = score_and_rank(table, weights)
        ranks = scored[scfg.RANK_COLUMN]
        scores = scored[scfg.SCORE_COLUMN]

        # Contiguous 1..n over exactly the scored cells; no rank on an unscored
        # (excluded, or eligible-but-no-usable-criterion) cell.
        ranked = scored[ranks.notna()]
        n = len(ranked)
        assert sorted(int(r) for r in ranked[scfg.RANK_COLUMN]) == list(range(1, n + 1)), (
            "rank is not a contiguous 1..n ordering over the scored cells"
        )
        assert scores[ranks.notna()].notna().all(), "a ranked cell has a null score"
        assert ranks[scores.isna()].isna().all(), "an unscored cell was assigned a rank"

        # Order by rank and verify the two ordering guarantees together.
        ordered = ranked.sort_values(scfg.RANK_COLUMN)
        ordered_scores = ordered[scfg.SCORE_COLUMN].to_numpy()
        # Non-increasing score down the ranking (rank 1 is the best).
        assert all(
            ordered_scores[i] >= ordered_scores[i + 1] - 1e-12
            for i in range(len(ordered_scores) - 1)
        ), "ranks are not ordered by descending score"
        # Within every tied-score group, cell_ids ascend as rank increases.
        for _, group in ordered.groupby(scfg.SCORE_COLUMN, sort=False):
            ids = list(group["cell_id"])
            assert ids == sorted(ids), (
                "cells tied on score are not ranked by ascending cell_id: "
                f"{ids}"
            )
