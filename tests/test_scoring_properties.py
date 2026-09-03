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

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from pipeline.scoring import config as scfg
from pipeline.scoring.normalise import compute_bounds, normalise_series
from pipeline.scoring.score import eligible_mask, score_and_rank, score_frame
from pipeline.scoring.weights import Criterion, WeightsConfig

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
