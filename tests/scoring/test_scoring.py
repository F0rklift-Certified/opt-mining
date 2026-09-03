"""
Unit tests for the S1-10 baseline suitability model (`pipeline.scoring`).

Everything here runs on small in-memory frames and tiny YAML files under
tmp_path — no pipeline outputs are read and nothing is written outside the
test's own directory.

The synthetic fixture is four cells with hand-computable values, so the
expected scores in `TestKnownInputsOutputs` are arithmetic anyone can check
on paper rather than golden numbers copied from a previous run.
"""

from __future__ import annotations

import copy
import inspect
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

yaml = pytest.importorskip("yaml")

from pipeline.scoring import config as scfg  # noqa: E402
from pipeline.scoring.normalise import (  # noqa: E402
    compute_bounds,
    normalise_series,
    normalise_value,
)
from pipeline.scoring.rank import assign_ranks  # noqa: E402
from pipeline.scoring.score import score_and_rank, score_frame  # noqa: E402
from pipeline.scoring.weights import (  # noqa: E402
    Criterion,
    ScoringConfigError,
    WeightsConfig,
    load_weights,
    parse_weights,
)

TOL = 1e-12  # documented numeric tolerance for the hand-computed expectations

_DEFAULT_RAW = yaml.safe_load(scfg.DEFAULT_WEIGHTS_PATH.read_text(encoding="utf-8"))


def _default_raw() -> dict:
    """Deep copy of the packaged YAML, for mutation in the fault tests."""
    return copy.deepcopy(_DEFAULT_RAW)


def _write(tmp_path: Path, obj, name="weights.yaml") -> Path:
    path = tmp_path / name
    path.write_text(
        obj if isinstance(obj, str) else yaml.safe_dump(obj), encoding="utf-8"
    )
    return path


def simple_config(**overrides) -> WeightsConfig:
    """
    Two criteria, one each way, weights 3 and 1 — so the weighted average is
    easy to do in your head: score = (3*a + 1*b) / 4.
    """
    base = dict(
        criteria=(
            Criterion("wind_speed", 3.0, scfg.HIGHER_IS_BETTER, "resource"),
            Criterion("dist_transmission_km", 1.0, scfg.LOWER_IS_BETTER, "cost"),
        ),
        confidence_discount=False,
        confidence_factors={"high": 1.0, "medium": 0.9, "low": 0.5},
        config_id="test",
    )
    base.update(overrides)
    return WeightsConfig(**base)


def simple_features() -> pd.DataFrame:
    """
    Four cells. Cell D is excluded, and its values are deliberately extreme so
    a test can prove they never touch the normalisation bounds.
    """
    return pd.DataFrame(
        {
            "cell_id": ["A", "B", "C", "D"],
            "wind_speed": [10.0, 5.0, 0.0, 999.0],
            "dist_transmission_km": [0.0, 5.0, 10.0, -999.0],
            "eligible": [True, True, True, False],
            "data_confidence": ["high", "high", "low", "high"],
        }
    )


# ---------------------------------------------------------------------------
# Packaged defaults (Requirement 3)
# ---------------------------------------------------------------------------


class TestPackagedDefaults:
    def test_default_weights_file_ships_and_loads(self):
        assert scfg.DEFAULT_WEIGHTS_PATH.name == "scoring_weights.yaml"
        assert scfg.DEFAULT_WEIGHTS_PATH.exists()
        weights = load_weights(scfg.DEFAULT_WEIGHTS_PATH)
        assert weights.weight_sum > 0
        assert len(weights.config_id) == 64  # sha256 hex

    def test_default_criteria_match_the_ticket(self):
        """Requirement 3.2 — the six criteria and their directions."""
        weights = load_weights(scfg.DEFAULT_WEIGHTS_PATH)
        directions = {c.feature: c.direction for c in weights.criteria}
        assert directions == {
            "wind_speed": scfg.HIGHER_IS_BETTER,
            "dist_transmission_km": scfg.LOWER_IS_BETTER,
            "dist_substation_km": scfg.LOWER_IS_BETTER,
            "demand_proxy": scfg.HIGHER_IS_BETTER,
            "slope_deg": scfg.LOWER_IS_BETTER,
            "inside_rez": scfg.HIGHER_IS_BETTER,
        }

    def test_every_default_criterion_has_a_non_empty_rationale(self):
        """Requirement 3.3 — a weight without a justification is an assertion."""
        for criterion in load_weights(scfg.DEFAULT_WEIGHTS_PATH).criteria:
            assert criterion.rationale.strip(), criterion.feature
            assert len(criterion.rationale) > 40, criterion.feature

    def test_every_default_criterion_is_a_real_integrated_table_column(self):
        """Requirement 3.4 — no default criterion may name a column that does not exist."""
        from pipeline.integration import config as icfg

        weights = load_weights(scfg.DEFAULT_WEIGHTS_PATH)
        for criterion in weights.criteria:
            assert criterion.feature in icfg.SCORED_FEATURE_COLUMNS, criterion.feature

    def test_no_weight_literal_appears_in_the_scoring_source(self):
        """
        Constitution: "Criteria weights are user inputs, never hard-coded
        constants." The weights live in YAML; the Python must not restate them.
        """
        weights = load_weights(scfg.DEFAULT_WEIGHTS_PATH)
        package = Path(scfg.__file__).parent
        for module in sorted(package.glob("*.py")):
            source = module.read_text(encoding="utf-8")
            code = "\n".join(
                line.split("#")[0] for line in source.splitlines()
            )
            for criterion in weights.criteria:
                assert f'"{criterion.feature}"' not in code or module.name in {
                    "config.py"
                }, f"{module.name} names the criterion {criterion.feature}"

    def test_config_constants(self):
        from pipeline.integration import config as icfg

        assert scfg.CONFIDENCE_COLUMN == "data_confidence"
        assert scfg.CONFIDENCE_LEVELS == icfg.DATA_CONFIDENCE_LEVELS
        assert scfg.OUTPUT_FILENAME == "optmining_suitability-score_2026_nsw.gpkg"
        assert scfg.CSV_FILENAME.endswith("_nsw.csv")
        assert scfg.CONTRIBUTION_PREFIX == "contrib_"
        assert scfg.RECONCILE_TOLERANCE == 1e-9
        assert scfg.STORAGE_CRS == "EPSG:4326"

    def test_output_filename_follows_the_naming_convention(self):
        """Requirement 6.5 — {source}_{dataset}_{vintage}_{region}.{ext}."""
        source, dataset, vintage, region = scfg.OUTPUT_FILENAME.split(".")[0].split("_")
        assert source == "optmining"
        assert dataset == "suitability-score"
        assert vintage.isdigit() and len(vintage) == 4
        assert region == "nsw"


# ---------------------------------------------------------------------------
# Weights config faults (Requirement 2)
# ---------------------------------------------------------------------------


class TestWeightsConfigFaults:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ScoringConfigError, match="not found"):
            load_weights(tmp_path / "nope.yaml")

    def test_unparsable_yaml_raises(self, tmp_path):
        path = _write(tmp_path, "criteria: [\n  - broken: {{{")
        with pytest.raises(ScoringConfigError, match="not valid YAML"):
            load_weights(path)

    def test_invalid_direction_names_the_criterion(self):
        raw = _default_raw()
        raw["criteria"][0]["direction"] = "sideways"
        with pytest.raises(ScoringConfigError, match="wind_speed.*sideways"):
            parse_weights(raw)

    def test_negative_weight_names_the_criterion(self):
        raw = _default_raw()
        raw["criteria"][1]["weight"] = -0.5
        with pytest.raises(ScoringConfigError, match="negative weight"):
            parse_weights(raw)

    @pytest.mark.parametrize("bad", ["heavy", None, True, [1]])
    def test_non_numeric_weight_rejected(self, bad):
        raw = _default_raw()
        raw["criteria"][0]["weight"] = bad
        with pytest.raises(ScoringConfigError):
            parse_weights(raw)

    def test_zero_weight_sum_raises(self):
        raw = _default_raw()
        for entry in raw["criteria"]:
            entry["weight"] = 0
        with pytest.raises(ScoringConfigError, match="sum to 0"):
            parse_weights(raw)

    def test_missing_rationale_raises(self):
        raw = _default_raw()
        raw["criteria"][0]["rationale"] = "   "
        with pytest.raises(ScoringConfigError, match="rationale"):
            parse_weights(raw)

    def test_duplicate_criterion_raises(self):
        raw = _default_raw()
        raw["criteria"].append(copy.deepcopy(raw["criteria"][0]))
        with pytest.raises(ScoringConfigError, match="duplicate"):
            parse_weights(raw)

    def test_empty_criteria_raises(self):
        with pytest.raises(ScoringConfigError, match="non-empty list"):
            parse_weights({"criteria": []})

    def test_discount_without_factors_for_every_level_raises(self):
        raw = _default_raw()
        raw["confidence_discount"] = True
        raw["confidence_factors"] = {"high": 1.0}
        with pytest.raises(ScoringConfigError, match="confidence_factors"):
            parse_weights(raw)

    def test_confidence_factor_above_one_raises(self):
        """A discount may reduce a score; it may never inflate one."""
        raw = _default_raw()
        raw["confidence_factors"]["high"] = 1.5
        with pytest.raises(ScoringConfigError, match="outside"):
            parse_weights(raw)

    def test_config_id_is_the_file_hash(self, tmp_path):
        a = _write(tmp_path, _default_raw(), "a.yaml")
        b = _write(tmp_path, _default_raw(), "b.yaml")
        changed = _default_raw()
        changed["criteria"][0]["weight"] = 0.99
        c = _write(tmp_path, changed, "c.yaml")
        assert load_weights(a).config_id == load_weights(b).config_id
        assert load_weights(a).config_id != load_weights(c).config_id


# ---------------------------------------------------------------------------
# Normalisation (Requirement 4, 15.1, 15.2, 15.7)
# ---------------------------------------------------------------------------


class TestNormalisation:
    def test_higher_is_better_hand_computed(self):
        """15.1 — values 0, 5, 10 over bounds [0, 10] give 0.0, 0.5, 1.0."""
        values = pd.Series([0.0, 5.0, 10.0])
        bounds = compute_bounds(
            pd.DataFrame({"f": values}),
            [Criterion("f", 1.0, scfg.HIGHER_IS_BETTER, "r")],
        )["f"]
        got = normalise_series(values, bounds, scfg.HIGHER_IS_BETTER)
        np.testing.assert_allclose(got, [0.0, 0.5, 1.0], atol=TOL)

    def test_lower_is_better_hand_computed(self):
        """15.2 — the same values invert to 1.0, 0.5, 0.0."""
        values = pd.Series([0.0, 5.0, 10.0])
        bounds = compute_bounds(
            pd.DataFrame({"f": values}),
            [Criterion("f", 1.0, scfg.LOWER_IS_BETTER, "r")],
        )["f"]
        got = normalise_series(values, bounds, scfg.LOWER_IS_BETTER)
        np.testing.assert_allclose(got, [1.0, 0.5, 0.0], atol=TOL)

    def test_scalar_matches_the_formula(self):
        assert normalise_value(2.0, 0.0, 8.0, scfg.HIGHER_IS_BETTER) == pytest.approx(0.25)
        assert normalise_value(2.0, 0.0, 8.0, scfg.LOWER_IS_BETTER) == pytest.approx(0.75)

    def test_constant_criterion_does_not_divide_by_zero(self):
        """15.7 — min == max is filled with the documented constant."""
        values = pd.Series([7.0, 7.0, 7.0])
        bounds = compute_bounds(
            pd.DataFrame({"f": values}),
            [Criterion("f", 1.0, scfg.HIGHER_IS_BETTER, "r")],
        )["f"]
        assert bounds.is_constant
        got = normalise_series(values, bounds, scfg.HIGHER_IS_BETTER)
        assert (got == scfg.CONSTANT_CRITERION_VALUE).all()
        assert normalise_value(7.0, 7.0, 7.0, scfg.HIGHER_IS_BETTER) == (
            scfg.CONSTANT_CRITERION_VALUE
        )

    def test_bounds_come_from_eligible_cells_only(self):
        """
        Requirement 4.3 / 7.3 — an excluded cell's extreme value must not
        stretch the scale the candidates are measured on.
        """
        features = simple_features()
        eligible = features[features["eligible"]]
        bounds = compute_bounds(eligible, simple_config().criteria)
        assert bounds["wind_speed"].lo == 0.0
        assert bounds["wind_speed"].hi == 10.0  # not 999 (cell D is excluded)
        assert bounds["dist_transmission_km"].lo == 0.0  # not -999

    def test_boolean_uses_its_definitional_domain(self):
        """
        Requirement 4.7 — an all-False boolean scores 0 for every cell, rather
        than triggering the constant fill and awarding full marks.
        """
        values = pd.Series([False, False, False])
        bounds = compute_bounds(
            pd.DataFrame({"inside_rez": values}),
            [Criterion("inside_rez", 1.0, scfg.HIGHER_IS_BETTER, "r")],
        )["inside_rez"]
        assert bounds.is_boolean and not bounds.is_constant
        got = normalise_series(values, bounds, scfg.HIGHER_IS_BETTER)
        assert (got == 0.0).all()

    def test_boolean_maps_false_zero_true_one(self):
        values = pd.Series([False, True])
        bounds = compute_bounds(
            pd.DataFrame({"b": values}), [Criterion("b", 1.0, scfg.HIGHER_IS_BETTER, "r")]
        )["b"]
        np.testing.assert_allclose(
            normalise_series(values, bounds, scfg.HIGHER_IS_BETTER), [0.0, 1.0], atol=TOL
        )
        np.testing.assert_allclose(
            normalise_series(values, bounds, scfg.LOWER_IS_BETTER), [1.0, 0.0], atol=TOL
        )

    def test_nulls_stay_null(self):
        values = pd.Series([0.0, np.nan, 10.0])
        bounds = compute_bounds(
            pd.DataFrame({"f": values}), [Criterion("f", 1.0, scfg.HIGHER_IS_BETTER, "r")]
        )["f"]
        got = normalise_series(values, bounds, scfg.HIGHER_IS_BETTER)
        assert got.isna().tolist() == [False, True, False]


# ---------------------------------------------------------------------------
# Scoring with known inputs and outputs (Requirement 15)
# ---------------------------------------------------------------------------


class TestKnownInputsOutputs:
    def test_weighted_score_hand_computed(self):
        """
        15.3 — with weights 3 (wind, higher) and 1 (distance, lower):

          A: wind 10 -> 1.0, dist 0  -> 1.0  =>  (3*1.0 + 1*1.0)/4 = 1.00
          B: wind 5  -> 0.5, dist 5  -> 0.5  =>  (3*0.5 + 1*0.5)/4 = 0.50
          C: wind 0  -> 0.0, dist 10 -> 0.0  =>  (3*0.0 + 1*0.0)/4 = 0.00
        """
        scored = score_frame(simple_features(), simple_config())
        got = scored.set_index("cell_id")[scfg.SCORE_COLUMN]
        assert got["A"] == pytest.approx(1.00, abs=TOL)
        assert got["B"] == pytest.approx(0.50, abs=TOL)
        assert got["C"] == pytest.approx(0.00, abs=TOL)

    def test_contributions_reconstruct_the_score(self):
        """15.4 — the explainability contract, on hand-computed numbers."""
        weights = simple_config()
        scored = score_frame(simple_features(), weights).set_index("cell_id")
        contributions = list(weights.contribution_columns)
        for cell in ("A", "B", "C"):
            total = scored.loc[cell, contributions].sum()
            assert total == pytest.approx(scored.loc[cell, scfg.SCORE_COLUMN], abs=TOL)
        # B's wind contribution is 3*0.5/4 = 0.375, distance is 1*0.5/4 = 0.125
        assert scored.loc["B", "contrib_wind_speed"] == pytest.approx(0.375, abs=TOL)
        assert scored.loc["B", "contrib_dist_transmission_km"] == pytest.approx(
            0.125, abs=TOL
        )

    def test_excluded_cell_is_null_throughout(self):
        """15.5 — null score, null rank, null contributions."""
        weights = simple_config()
        scored = score_and_rank(simple_features(), weights).set_index("cell_id")
        assert pd.isna(scored.loc["D", scfg.SCORE_COLUMN])
        assert pd.isna(scored.loc["D", scfg.RANK_COLUMN])
        for column in weights.contribution_columns:
            assert pd.isna(scored.loc["D", column])

    def test_rank_is_descending_by_score(self):
        """15.6 — rank 1 is the best cell; excluded cells are unranked."""
        scored = score_and_rank(simple_features(), simple_config()).set_index("cell_id")
        assert scored.loc["A", scfg.RANK_COLUMN] == 1
        assert scored.loc["B", scfg.RANK_COLUMN] == 2
        assert scored.loc["C", scfg.RANK_COLUMN] == 3
        assert pd.isna(scored.loc["D", scfg.RANK_COLUMN])

    def test_ties_break_by_ascending_cell_id(self):
        """15.6 — the documented tie-break makes equal scores deterministic."""
        features = pd.DataFrame(
            {
                "cell_id": ["zebra", "alpha", "mango"],
                "wind_speed": [5.0, 5.0, 5.0],
                "dist_transmission_km": [1.0, 1.0, 1.0],
                "eligible": [True, True, True],
                "data_confidence": ["high", "high", "high"],
            }
        )
        scored = score_and_rank(features, simple_config()).set_index("cell_id")
        assert scored.loc["alpha", scfg.RANK_COLUMN] == 1
        assert scored.loc["mango", scfg.RANK_COLUMN] == 2
        assert scored.loc["zebra", scfg.RANK_COLUMN] == 3

    def test_determinism_over_repeated_runs(self):
        """15.8 — identical inputs and config produce identical output."""
        features, weights = simple_features(), simple_config()
        first = score_and_rank(features, weights)
        second = score_and_rank(features, weights)
        pd.testing.assert_frame_equal(first, second)

    def test_scoring_function_is_pure_and_does_no_file_io(self, monkeypatch):
        """
        Requirement 5.5 — the scoring computation must not touch the
        filesystem, which is what makes it independently replaceable.
        """
        import builtins

        def explode(*args, **kwargs):
            raise AssertionError("score_frame performed file I/O")

        monkeypatch.setattr(builtins, "open", explode)
        features = simple_features()
        before = features.copy()
        score_frame(features, simple_config())
        pd.testing.assert_frame_equal(features, before)  # input not mutated

    def test_different_weights_change_the_scores(self):
        """
        Requirement 2.2 — scores follow the loaded weights, not a constant
        buried in the source.
        """
        features = simple_features()
        wind_heavy = score_frame(features, simple_config()).set_index("cell_id")
        flipped = simple_config(
            criteria=(
                Criterion("wind_speed", 1.0, scfg.HIGHER_IS_BETTER, "r"),
                Criterion("dist_transmission_km", 3.0, scfg.LOWER_IS_BETTER, "r"),
            )
        )
        dist_heavy = score_frame(features, flipped).set_index("cell_id")
        assert wind_heavy.loc["B", "contrib_wind_speed"] != pytest.approx(
            dist_heavy.loc["B", "contrib_wind_speed"]
        )


# ---------------------------------------------------------------------------
# Confidence (Requirement 10)
# ---------------------------------------------------------------------------


class TestConfidence:
    def test_confidence_is_carried_through_verbatim(self):
        scored = score_frame(simple_features(), simple_config()).set_index("cell_id")
        assert list(scored[scfg.CONFIDENCE_COLUMN]) == ["high", "high", "low", "high"]

    def test_discount_multiplies_score_and_contributions_alike(self):
        """
        Requirement 9.3 — applying the factor to both keeps the contributions
        reconcilable with the discounted score.
        """
        weights = simple_config(confidence_discount=True)
        scored = score_frame(simple_features(), weights).set_index("cell_id")
        undiscounted = score_frame(simple_features(), simple_config()).set_index("cell_id")

        # Cell B is `high` -> factor 1.0; cell C is `low` -> factor 0.5.
        assert scored.loc["B", scfg.SCORE_COLUMN] == pytest.approx(
            undiscounted.loc["B", scfg.SCORE_COLUMN], abs=TOL
        )
        for cell in ("A", "B", "C"):
            total = scored.loc[cell, list(weights.contribution_columns)].sum()
            assert total == pytest.approx(scored.loc[cell, scfg.SCORE_COLUMN], abs=TOL)

    def test_discount_scales_by_the_documented_factor(self):
        features = pd.DataFrame(
            {
                "cell_id": ["A", "B"],
                "wind_speed": [10.0, 10.0],
                "dist_transmission_km": [0.0, 0.0],
                "eligible": [True, True],
                "data_confidence": ["high", "low"],
            }
        )
        weights = simple_config(confidence_discount=True)
        scored = score_frame(features, weights).set_index("cell_id")
        assert scored.loc["A", scfg.SCORE_COLUMN] == pytest.approx(1.0, abs=TOL)
        assert scored.loc["B", scfg.SCORE_COLUMN] == pytest.approx(0.5, abs=TOL)


# ---------------------------------------------------------------------------
# Missing criterion values (documented rule; not specified by the ticket)
# ---------------------------------------------------------------------------


class TestMissingCriterionValues:
    def test_null_criterion_is_excluded_from_that_cells_average(self):
        """
        A missing feature is left out of the weighted average rather than
        scored as zero, so a data gap does not masquerade as an unfavourable
        measurement. Cell B has no wind value, so its score is decided by the
        distance criterion alone.
        """
        features = pd.DataFrame(
            {
                "cell_id": ["A", "B"],
                "wind_speed": [10.0, np.nan],
                "dist_transmission_km": [0.0, 10.0],
                "eligible": [True, True],
                "data_confidence": ["high", "high"],
            }
        )
        scored = score_frame(features, simple_config()).set_index("cell_id")
        # A: bounds are wind [10,10] (constant -> 1.0), dist [0,10].
        # B normalises dist 10 -> 0.0, and only the distance weight applies.
        assert scored.loc["B", scfg.SCORE_COLUMN] == pytest.approx(0.0, abs=TOL)
        assert pd.isna(scored.loc["B", "contrib_wind_speed"])
        assert scored.loc["B", "applied_weight"] == pytest.approx(1.0)

    def test_cell_with_no_usable_criterion_is_unscored_not_infinite(self):
        features = pd.DataFrame(
            {
                "cell_id": ["A", "B"],
                "wind_speed": [10.0, np.nan],
                "dist_transmission_km": [1.0, np.nan],
                "eligible": [True, True],
                "data_confidence": ["high", "high"],
            }
        )
        scored = score_and_rank(features, simple_config()).set_index("cell_id")
        assert pd.isna(scored.loc["B", scfg.SCORE_COLUMN])
        assert pd.isna(scored.loc["B", scfg.RANK_COLUMN])
        assert np.isfinite(scored.loc["A", scfg.SCORE_COLUMN])

    def test_null_eligibility_is_not_eligibility(self):
        features = simple_features()
        features["eligible"] = features["eligible"].astype(object)
        features.loc[0, "eligible"] = None
        scored = score_frame(features, simple_config()).set_index("cell_id")
        assert pd.isna(scored.loc["A", scfg.SCORE_COLUMN])


# ---------------------------------------------------------------------------
# Rank behaviour (Requirement 8)
# ---------------------------------------------------------------------------


class TestRanking:
    def test_rank_is_contiguous_over_scored_cells(self):
        scored = score_and_rank(simple_features(), simple_config())
        ranks = sorted(int(r) for r in scored[scfg.RANK_COLUMN].dropna())
        assert ranks == [1, 2, 3]

    def test_no_scored_cells_gives_no_ranks(self):
        features = simple_features()
        features["eligible"] = False
        scored = score_and_rank(features, simple_config())
        assert scored[scfg.RANK_COLUMN].isna().all()

    def test_assign_ranks_is_nullable_integer_typed(self):
        scored = score_frame(simple_features(), simple_config())
        ranks = assign_ranks(scored)
        assert str(ranks.dtype) == "Int64"


# ---------------------------------------------------------------------------
# Loader faults (Requirement 1, 10.4)
# ---------------------------------------------------------------------------


class TestLoaderFaults:
    def _frame(self, **drop):
        import geopandas as gpd
        from shapely.geometry import Point

        frame = simple_features()
        for column in drop.get("drop", []):
            frame = frame.drop(columns=[column])
        return gpd.GeoDataFrame(
            frame,
            geometry=[Point(150 + i, -30) for i in range(len(frame))],
            crs="EPSG:4326",
        )

    def _write_gpkg(self, tmp_path, frame, name="t.gpkg"):
        path = tmp_path / name
        frame.to_file(path, driver="GPKG", layer=scfg.INTEGRATED_LAYER)
        return path

    def test_missing_file_raises_naming_the_path(self, tmp_path):
        from pipeline.scoring.load import load_integrated

        with pytest.raises(FileNotFoundError, match="not found"):
            load_integrated(tmp_path / "absent.gpkg", simple_config().criteria)

    def test_absent_cell_id_raises(self, tmp_path):
        from pipeline.scoring.load import load_integrated

        path = self._write_gpkg(tmp_path, self._frame(drop=["cell_id"]))
        with pytest.raises(ValueError, match="cell_id"):
            load_integrated(path, simple_config().criteria)

    def test_absent_criterion_column_raises(self, tmp_path):
        from pipeline.scoring.load import load_integrated

        path = self._write_gpkg(tmp_path, self._frame(drop=["wind_speed"]))
        with pytest.raises(ValueError, match="wind_speed"):
            load_integrated(path, simple_config().criteria)

    def test_absent_eligible_column_raises(self, tmp_path):
        from pipeline.scoring.load import load_integrated

        path = self._write_gpkg(tmp_path, self._frame(drop=["eligible"]))
        with pytest.raises(ValueError, match="eligible"):
            load_integrated(path, simple_config().criteria)

    def test_absent_confidence_column_raises_rather_than_fabricating(self, tmp_path):
        """Requirement 10.4 — never invent a confidence value."""
        from pipeline.scoring.load import load_integrated

        path = self._write_gpkg(tmp_path, self._frame(drop=["data_confidence"]))
        with pytest.raises(ValueError, match="data_confidence"):
            load_integrated(path, simple_config().criteria)

    def test_duplicate_cell_id_raises(self, tmp_path):
        from pipeline.scoring.load import load_integrated

        frame = self._frame()
        frame.loc[1, "cell_id"] = "A"
        path = self._write_gpkg(tmp_path, frame)
        with pytest.raises(ValueError, match="duplicate"):
            load_integrated(path, simple_config().criteria)

    def test_wrong_crs_raises_rather_than_reprojecting(self, tmp_path):
        from pipeline.scoring.load import load_integrated

        frame = self._frame().to_crs("EPSG:3577")
        path = self._write_gpkg(tmp_path, frame)
        with pytest.raises(ValueError, match="EPSG:4326"):
            load_integrated(path, simple_config().criteria)


# ---------------------------------------------------------------------------
# Validation checks (Requirement 14)
# ---------------------------------------------------------------------------


class TestValidation:
    def _valid(self):
        features = simple_features()
        weights = simple_config()
        scored = score_and_rank(features, weights)
        from pipeline.scoring.write import build_scored_table

        import geopandas as gpd
        from shapely.geometry import Point

        geo = gpd.GeoDataFrame(
            features,
            geometry=[Point(150 + i, -30) for i in range(len(features))],
            crs="EPSG:4326",
        )
        return build_scored_table(geo, scored, weights), geo, weights

    def test_a_clean_table_passes_every_check(self):
        from pipeline.scoring.validate import validate

        table, features, weights = self._valid()
        result = validate(table, features, weights)
        assert result["failed"] == 0, result["failed_names"]
        assert result["total"] >= 8

    def test_every_check_reports_expected_observed_and_result(self):
        """The no-silent-passes rule: the evidence is always on the page."""
        from pipeline.scoring.validate import validate

        table, features, weights = self._valid()
        for check in validate(table, features, weights)["checks"]:
            assert check["name"] and check["expected"] and check["observed"]
            assert isinstance(check["passed"], bool)

    def test_out_of_range_score_fails(self):
        from pipeline.scoring.validate import validate

        table, features, weights = self._valid()
        table.loc[0, scfg.SCORE_COLUMN] = 1.5
        result = validate(table, features, weights)
        assert any("within [0, 1]" in n for n in result["failed_names"])

    def test_excluded_cell_with_a_score_fails(self):
        from pipeline.scoring.validate import validate

        table, features, weights = self._valid()
        table.loc[3, scfg.SCORE_COLUMN] = 0.5  # cell D is excluded
        result = validate(table, features, weights)
        assert any("Only eligible cells scored" in n for n in result["failed_names"])

    def test_broken_reconciliation_fails(self):
        from pipeline.scoring.validate import validate

        table, features, weights = self._valid()
        table.loc[0, "contrib_wind_speed"] = 0.99
        result = validate(table, features, weights)
        assert any("reconstruct the score" in n for n in result["failed_names"])

    def test_out_of_vocabulary_confidence_fails(self):
        from pipeline.scoring.validate import validate

        table, features, weights = self._valid()
        table.loc[0, scfg.OUTPUT_CONFIDENCE_COLUMN] = "excellent"
        result = validate(table, features, weights)
        assert any("vocabulary" in n for n in result["failed_names"])

    def test_non_contiguous_rank_fails(self):
        from pipeline.scoring.validate import validate

        table, features, weights = self._valid()
        table.loc[0, scfg.RANK_COLUMN] = 99
        result = validate(table, features, weights)
        assert result["failed"] >= 1

    def test_missing_row_fails(self):
        from pipeline.scoring.validate import validate

        table, features, weights = self._valid()
        result = validate(table.iloc[:-1], features, weights)
        assert any("One row per" in n for n in result["failed_names"])


# ---------------------------------------------------------------------------
# run() contract (Requirement 11)
# ---------------------------------------------------------------------------


class TestRunContract:
    def test_signature_matches_the_stage_contract(self):
        """Requirement 11.1 — first parameter `verbose`, defaulting to False."""
        from pipeline.scoring.run import run

        parameters = list(inspect.signature(run).parameters.values())
        assert parameters[0].name == "verbose"
        assert parameters[0].default is False
        names = {p.name for p in parameters}
        assert {"weights_path", "integrated_path", "confidence_discount"} <= names

    def test_bad_config_raises_before_writing_anything(self, tmp_path):
        """Requirement 11.3 / 2.5 — halt before any output is produced."""
        from pipeline.scoring.run import run

        raw = _default_raw()
        raw["criteria"][0]["direction"] = "sideways"
        bad = _write(tmp_path, raw)
        outputs = tmp_path / "out"
        with pytest.raises(ScoringConfigError):
            run(weights_path=bad, integrated_path=tmp_path / "missing.gpkg")
        assert not outputs.exists()

    def test_missing_input_raises_rather_than_returning_a_dict(self, tmp_path):
        from pipeline.scoring.run import run

        with pytest.raises(FileNotFoundError):
            run(integrated_path=tmp_path / "absent.gpkg")


# ---------------------------------------------------------------------------
# Orchestrator wiring (Requirement 11.4-11.8)
# ---------------------------------------------------------------------------


class TestOrchestratorWiring:
    def test_scoring_registered_after_integration_and_before_validate(self):
        from pipeline import config as pcfg

        assert "scoring" in pcfg.STAGES
        assert pcfg.STAGES.index("integration") < pcfg.STAGES.index("scoring")
        assert pcfg.STAGES.index("scoring") < pcfg.STAGES.index("validate")

    def test_scoring_is_a_domain(self):
        from pipeline import config as pcfg

        assert "scoring" in pcfg.DOMAINS

    def test_get_runner_returns_the_stage_run(self):
        from pipeline.__main__ import _get_runner
        from pipeline.scoring.run import run

        assert _get_runner("scoring") is run

    def test_scoring_weights_flag_exists_and_is_forwarded(self, monkeypatch):
        import sys

        from pipeline.__main__ import _build_kwargs, parse_args

        monkeypatch.setattr(
            sys, "argv",
            ["pipeline", "--only", "scoring", "--scoring-weights", "/tmp/w.yaml"],
        )
        args = parse_args()
        kwargs = _build_kwargs("scoring", args, (0, 0, 1, 1))
        assert kwargs["weights_path"] == Path("/tmp/w.yaml")
        assert kwargs["verbose"] is False

    def test_confidence_discount_flag_is_forwarded(self, monkeypatch):
        import sys

        from pipeline.__main__ import _build_kwargs, parse_args

        monkeypatch.setattr(
            sys, "argv", ["pipeline", "--only", "scoring", "--confidence-discount"]
        )
        kwargs = _build_kwargs("scoring", parse_args(), (0, 0, 1, 1))
        assert kwargs["confidence_discount"] is True

    def test_resolve_stages_orders_integration_before_scoring(self, monkeypatch):
        import sys

        from pipeline.__main__ import parse_args, resolve_stages

        monkeypatch.setattr(sys, "argv", ["pipeline"])
        stages = resolve_stages(parse_args())
        assert stages.index("integration") < stages.index("scoring")

    def test_subpackage_docstring_describes_the_stage_and_its_position(self):
        import pipeline.scoring as pkg

        doc = pkg.__doc__ or ""
        assert "scoring" in doc.lower()
        assert "integration" in doc.lower()
        assert "S1-10" in doc
