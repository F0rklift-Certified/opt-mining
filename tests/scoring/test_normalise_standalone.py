"""
Standalone unit tests for the feature-normalisation component (S2-04).

These exercise `pipeline.scoring.normalise` as an INDEPENDENT component —
DataFrame in, normalised DataFrame out — without loading any pipeline output,
without writing anything, and (crucially) without importing the scoring
weights/`Criterion` types except where a test deliberately proves the scoring
`Criterion` also satisfies the decoupled `SpecLike` contract.

The normalisation method and its outlier/missing/constant/boolean policies are
frozen in the decision-engine specification §5 (Frozen_Decisions F9–F14). This
module pins the shipped implementation of §5 against the standalone surface:

  * §5.1 directional linear min-max, clamped [0, 1];
  * §5.2 bounds from the rows passed in, fixed per call;
  * §5.3 no outlier treatment — true min/max, saturation clamp only;
  * §5.4 missing values stay null, never zero-/worst-imputed;
  * §5.5 constant feature -> CONSTANT_CRITERION_VALUE, flagged, no /0;
  * §5.6 boolean definitional {False -> 0.0, True -> 1.0} domain.

`test_scoring.py::TestNormalisation` already covers several of these through
the `Criterion` path; the value here is the decoupled `NormSpec`/
`normalise_frame` surface and the boundary/degenerate cases (saturation clamp,
all-null column, normalised_frame == normalise_frame) the ticket names.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from pipeline.scoring import config as scfg
from pipeline.scoring.normalise import (
    Bounds,
    NormSpec,
    SpecLike,
    compute_bounds,
    normalise_frame,
    normalise_series,
    normalise_value,
)

TOL = 1e-12


# ---------------------------------------------------------------------------
# The decoupled contract: NormSpec + SpecLike (Task 1)
# ---------------------------------------------------------------------------


class TestNormSpec:
    def test_valid_directions_are_accepted(self):
        assert NormSpec("wind_speed", scfg.HIGHER_IS_BETTER).direction == (
            scfg.HIGHER_IS_BETTER
        )
        assert NormSpec("slope_deg", scfg.LOWER_IS_BETTER).direction == (
            scfg.LOWER_IS_BETTER
        )

    def test_invalid_direction_is_rejected_at_construction(self):
        """A bad direction must fail where the spec is built, not deep in the maths."""
        with pytest.raises(ValueError, match="unknown direction"):
            NormSpec("wind_speed", "sideways")

    def test_normspec_is_frozen(self):
        spec = NormSpec("wind_speed", scfg.HIGHER_IS_BETTER)
        with pytest.raises(Exception):
            spec.feature = "other"  # type: ignore[misc]

    def test_normspec_satisfies_speclike(self):
        assert isinstance(NormSpec("f", scfg.HIGHER_IS_BETTER), SpecLike)

    def test_the_scoring_criterion_also_satisfies_speclike(self):
        """
        The whole point of the Protocol: the scoring `Criterion` flows through
        the standalone normaliser unchanged, so there is ONE implementation.
        """
        from pipeline.scoring.weights import Criterion

        criterion = Criterion("wind_speed", 0.35, scfg.HIGHER_IS_BETTER, "resource")
        assert isinstance(criterion, SpecLike)

    def test_normalise_path_does_not_import_the_weights_module(self):
        """
        The normalisation module must not depend on the scoring weights layer
        (the decoupling the ticket requires). `Criterion` is only imported by a
        test that deliberately proves the structural fit.
        """
        import pipeline.scoring.normalise as norm_mod

        source = norm_mod.__spec__.origin
        text = open(source, encoding="utf-8").read()
        assert "from .weights import" not in text
        assert "import weights" not in text


# ---------------------------------------------------------------------------
# compute_bounds accepts either spec type (Task 1)
# ---------------------------------------------------------------------------


class TestComputeBoundsAcceptsBothSpecTypes:
    def _df(self) -> pd.DataFrame:
        return pd.DataFrame({"wind_speed": [6.0, 8.0, 10.0]})

    def test_normspec_produces_correct_bounds_without_weights(self):
        bounds = compute_bounds(self._df(), [NormSpec("wind_speed", scfg.HIGHER_IS_BETTER)])
        b = bounds["wind_speed"]
        assert b.lo == pytest.approx(6.0)
        assert b.hi == pytest.approx(10.0)
        assert not b.is_boolean and not b.is_constant
        assert b.n_observed == 3

    def test_criterion_and_normspec_give_identical_bounds(self):
        from pipeline.scoring.weights import Criterion

        df = self._df()
        via_spec = compute_bounds(df, [NormSpec("wind_speed", scfg.HIGHER_IS_BETTER)])
        via_crit = compute_bounds(df, [Criterion("wind_speed", 1.0, scfg.HIGHER_IS_BETTER, "r")])
        assert via_spec["wind_speed"] == via_crit["wind_speed"]

    def test_bounds_dataclass_fields_are_unchanged(self):
        """Guard the public Bounds shape consumers (report.py) rely on."""
        fields = {f for f in Bounds.__dataclass_fields__}
        assert fields == {
            "feature",
            "lo",
            "hi",
            "observed_min",
            "observed_max",
            "is_boolean",
            "is_constant",
            "n_observed",
        }


# ---------------------------------------------------------------------------
# The standalone normalise_frame: DataFrame in, DataFrame out (Task 2)
# ---------------------------------------------------------------------------


class TestNormaliseFrame:
    def test_higher_is_better_hand_computed(self):
        df = pd.DataFrame({"f": [0.0, 5.0, 10.0]})
        out = normalise_frame(df, [NormSpec("f", scfg.HIGHER_IS_BETTER)])
        np.testing.assert_allclose(out["norm_f"], [0.0, 0.5, 1.0], atol=TOL)

    def test_lower_is_better_inverts(self):
        df = pd.DataFrame({"f": [0.0, 5.0, 10.0]})
        out = normalise_frame(df, [NormSpec("f", scfg.LOWER_IS_BETTER)])
        np.testing.assert_allclose(out["norm_f"], [1.0, 0.5, 0.0], atol=TOL)

    def test_one_named_column_per_spec_in_order(self):
        df = pd.DataFrame(
            {"wind_speed": [1.0, 2.0], "slope_deg": [10.0, 20.0], "other": [9, 9]}
        )
        specs = [
            NormSpec("wind_speed", scfg.HIGHER_IS_BETTER),
            NormSpec("slope_deg", scfg.LOWER_IS_BETTER),
        ]
        out = normalise_frame(df, specs)
        assert list(out.columns) == ["norm_wind_speed", "norm_slope_deg"]

    def test_output_is_index_aligned_to_input(self):
        df = pd.DataFrame({"f": [0.0, 10.0]}, index=["cell_9", "cell_3"])
        out = normalise_frame(df, [NormSpec("f", scfg.HIGHER_IS_BETTER)])
        assert list(out.index) == ["cell_9", "cell_3"]

    def test_nulls_stay_null_and_are_not_zero_imputed(self):
        """§5.4 — a missing value stays null, never scored as the worst value."""
        df = pd.DataFrame({"f": [0.0, np.nan, 10.0]})
        out = normalise_frame(df, [NormSpec("f", scfg.HIGHER_IS_BETTER)])
        assert out["norm_f"].isna().tolist() == [False, True, False]
        assert out["norm_f"].iloc[0] == pytest.approx(0.0)

    def test_supplied_bounds_are_reused_and_out_of_range_saturates(self):
        """
        §5.2/§5.3 — bounds may be supplied by the caller; a value outside them
        saturates at 0 or 1 (the only clamp) rather than pushing the component
        out of [0, 1].
        """
        df = pd.DataFrame({"f": [-5.0, 5.0, 15.0]})  # bounds deliberately [0, 10]
        bounds = {
            "f": Bounds(
                feature="f",
                lo=0.0,
                hi=10.0,
                observed_min=-5.0,
                observed_max=15.0,
                is_boolean=False,
                is_constant=False,
                n_observed=3,
            )
        }
        out = normalise_frame(df, [NormSpec("f", scfg.HIGHER_IS_BETTER)], bounds=bounds)
        np.testing.assert_allclose(out["norm_f"], [0.0, 0.5, 1.0], atol=TOL)

    def test_result_is_deterministic(self):
        df = pd.DataFrame({"f": [1.0, 4.0, 9.0]})
        specs = [NormSpec("f", scfg.HIGHER_IS_BETTER)]
        pd.testing.assert_frame_equal(
            normalise_frame(df, specs), normalise_frame(df, specs)
        )


# ---------------------------------------------------------------------------
# Boundary and degenerate cases mirroring §5.3–§5.6 (Task 4)
# ---------------------------------------------------------------------------


class TestBoundaryAndDegenerateCases:
    def test_min_and_max_map_to_the_endpoints(self):
        """§5.1 — the population min and max land exactly on 0.0 and 1.0."""
        df = pd.DataFrame({"f": [3.0, 7.0]})
        out = normalise_frame(df, [NormSpec("f", scfg.HIGHER_IS_BETTER)])
        assert out["norm_f"].iloc[0] == pytest.approx(0.0)
        assert out["norm_f"].iloc[1] == pytest.approx(1.0)

    def test_constant_feature_is_flagged_and_filled_without_divide_by_zero(self):
        """§5.5 — min == max fills CONSTANT_CRITERION_VALUE, flagged, no /0."""
        df = pd.DataFrame({"f": [7.0, 7.0, 7.0]})
        specs = [NormSpec("f", scfg.HIGHER_IS_BETTER)]
        bounds = compute_bounds(df, specs)["f"]
        assert bounds.is_constant
        out = normalise_frame(df, specs)
        assert (out["norm_f"] == scfg.CONSTANT_CRITERION_VALUE).all()

    def test_all_null_column_is_treated_as_constant(self):
        """
        §5.4/§5.5 — a feature with no value over the passed rows has no scale;
        it is treated as constant (bounds 0/0, flagged), and a null value still
        stays null rather than being filled.
        """
        df = pd.DataFrame({"f": [np.nan, np.nan]})
        specs = [NormSpec("f", scfg.HIGHER_IS_BETTER)]
        bounds = compute_bounds(df, specs)["f"]
        assert bounds.is_constant
        assert bounds.lo == 0.0 and bounds.hi == 0.0
        assert bounds.observed_min is None and bounds.n_observed == 0
        out = normalise_frame(df, specs)
        assert out["norm_f"].isna().all()  # nulls stay null, not filled

    def test_boolean_uses_definitional_domain_all_false_scores_zero(self):
        """
        §5.6 — an all-False boolean scores 0 for every cell (honest "none in a
        REZ"), NOT the constant fill of §5.5 that would hand every cell 1.0.
        """
        df = pd.DataFrame({"inside_rez": [False, False, False]})
        specs = [NormSpec("inside_rez", scfg.HIGHER_IS_BETTER)]
        bounds = compute_bounds(df, specs)["inside_rez"]
        assert bounds.is_boolean and not bounds.is_constant
        out = normalise_frame(df, specs)
        assert (out["norm_inside_rez"] == 0.0).all()

    def test_boolean_maps_false_zero_true_one_and_inverts_when_lower_is_better(self):
        """§5.6 — {False -> 0.0, True -> 1.0}, with the direction applied after."""
        df = pd.DataFrame({"b": [False, True]})
        higher = normalise_frame(df, [NormSpec("b", scfg.HIGHER_IS_BETTER)])
        lower = normalise_frame(df, [NormSpec("b", scfg.LOWER_IS_BETTER)])
        np.testing.assert_allclose(higher["norm_b"], [0.0, 1.0], atol=TOL)
        np.testing.assert_allclose(lower["norm_b"], [1.0, 0.0], atol=TOL)

    def test_scalar_normalise_value_at_lo_mid_hi(self):
        """§5.1 — the scalar formula in its plainest form, at both directions."""
        assert normalise_value(0.0, 0.0, 10.0, scfg.HIGHER_IS_BETTER) == pytest.approx(0.0)
        assert normalise_value(5.0, 0.0, 10.0, scfg.HIGHER_IS_BETTER) == pytest.approx(0.5)
        assert normalise_value(10.0, 0.0, 10.0, scfg.HIGHER_IS_BETTER) == pytest.approx(1.0)
        assert normalise_value(10.0, 0.0, 10.0, scfg.LOWER_IS_BETTER) == pytest.approx(0.0)

    def test_scalar_null_stays_null(self):
        result = normalise_value(float("nan"), 0.0, 10.0, scfg.HIGHER_IS_BETTER)
        assert result != result  # NaN

    def test_scalar_constant_uses_the_documented_fill(self):
        assert normalise_value(7.0, 7.0, 7.0, scfg.HIGHER_IS_BETTER) == (
            scfg.CONSTANT_CRITERION_VALUE
        )


# ---------------------------------------------------------------------------
# Single source of truth: the scoring path IS the standalone path (Task 3)
# ---------------------------------------------------------------------------


class TestScoringPathDelegatesToStandalone:
    def test_normalised_frame_equals_normalise_frame(self):
        """
        `score.normalised_frame` must be the same computation as the standalone
        `normalise_frame` — a divergent second normaliser is exactly what the
        project rules forbid.
        """
        from pipeline.scoring.score import normalised_frame
        from pipeline.scoring.weights import Criterion

        df = pd.DataFrame(
            {
                "wind_speed": [6.0, 8.0, 10.0],
                "slope_deg": [5.0, 10.0, 20.0],
            }
        )
        criteria = [
            Criterion("wind_speed", 0.35, scfg.HIGHER_IS_BETTER, "resource"),
            Criterion("slope_deg", 0.10, scfg.LOWER_IS_BETTER, "terrain"),
        ]
        bounds = compute_bounds(df, criteria)

        via_score = normalised_frame(df, criteria, bounds)
        via_standalone = normalise_frame(df, criteria, bounds=bounds)
        pd.testing.assert_frame_equal(via_score, via_standalone)

    def test_a_criterion_shaped_duck_type_flows_through(self):
        """Any object with feature/direction works — no concrete type required."""

        @dataclass(frozen=True)
        class DuckSpec:
            feature: str
            direction: str

        df = pd.DataFrame({"f": [0.0, 10.0]})
        out = normalise_frame(df, [DuckSpec("f", scfg.HIGHER_IS_BETTER)])
        np.testing.assert_allclose(out["norm_f"], [0.0, 1.0], atol=TOL)
