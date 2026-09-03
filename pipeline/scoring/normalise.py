"""
Directional min-max normalisation (S1-10, Requirements 4 and 7.3).

Criteria are measured in different units — m/s, km, degrees, boolean — so
they cannot be summed until each is rescaled to a common [0, 1] range where
1 is most favourable and 0 is least favourable. This module is the rescaling
step and nothing else: pure functions of (values, bounds, direction), with no
I/O and no dependence on the weights.

Two rules deserve their names spelled out, because both are places where a
naive implementation would either crash or quietly lie:

  CONSTANT CRITERION. If a criterion has the same value for every eligible
  cell, (v - min) / (max - min) is 0/0. Rather than divide by zero or drop
  the criterion, every cell is assigned the documented
  `config.CONSTANT_CRITERION_VALUE` and the criterion is FLAGGED as constant
  so the method report can tell the reader it carried no discriminating
  information on that run. A constant criterion shifts every score by the
  same amount and cannot change the ranking.

  BOOLEAN CRITERION. A boolean uses its definitional {False -> 0.0,
  True -> 1.0} domain, not the observed population min/max. This matters when
  a boolean is uniform: an all-False `inside_rez` should score 0 for every
  cell ("no cell is in a REZ"), not trigger the constant fill and hand every
  cell full marks for a benefit none of them has.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from . import config
from .weights import Criterion


@dataclass(frozen=True)
class Bounds:
    """
    The normalisation bounds applied to one criterion, plus what was observed.

    `lo`/`hi` are the bounds actually used by the arithmetic; `observed_min`/
    `observed_max` are the raw eligible-population extremes. They differ only
    for boolean criteria, which use their definitional domain. Both are
    reported so a reader can see the rule that was applied and the data it
    was applied to.
    """

    feature: str
    lo: float
    hi: float
    observed_min: float | None
    observed_max: float | None
    is_boolean: bool
    is_constant: bool  # min == max over the eligible population -> constant fill
    n_observed: int  # eligible cells with a non-null value for this criterion

    @property
    def rule(self) -> str:
        """One-line description of the rule applied, for the method report."""
        if self.is_boolean:
            return "boolean domain {False -> 0.0, True -> 1.0}"
        if self.is_constant:
            return (
                f"CONSTANT over the eligible population -> every cell assigned "
                f"{config.CONSTANT_CRITERION_VALUE}"
            )
        return "linear min-max over the eligible population"


def is_boolean_series(values: pd.Series) -> bool:
    """
    True for a boolean criterion, including one that round-tripped through a
    GeoPackage as an object column of Python bools.
    """
    if pd.api.types.is_bool_dtype(values):
        return True
    if values.dtype == object:
        present = values.dropna()
        if len(present) and all(isinstance(v, bool) for v in present):
            return True
    return False


def as_float(values: pd.Series) -> pd.Series:
    """
    Coerce a criterion column to float, preserving nulls.

    Booleans become 0.0/1.0. Anything non-numeric becomes NaN, which the
    scorer treats as a missing value for that cell rather than as a zero —
    a missing feature must not masquerade as the worst possible value.
    """
    if is_boolean_series(values):
        return values.astype("object").map(
            lambda v: float(v) if isinstance(v, bool) else pd.NA
        ).astype(float)
    return pd.to_numeric(values, errors="coerce").astype(float)


def compute_bounds(
    eligible: pd.DataFrame,
    criteria: Sequence[Criterion],
) -> dict[str, Bounds]:
    """
    Per-criterion normalisation bounds from the ELIGIBLE population only.

    Excluded cells never influence a bound (Requirements 4.3, 7.3): the score
    compares candidate sites against each other, so an ineligible cell's
    extreme value must not stretch the scale the candidates are measured on.

    Bounds are computed fresh from the data on every run — never hard-coded.
    """
    bounds: dict[str, Bounds] = {}
    for criterion in criteria:
        raw = eligible[criterion.feature]
        boolean = is_boolean_series(raw)
        values = as_float(raw)
        present = values.dropna()

        observed_min = float(present.min()) if len(present) else None
        observed_max = float(present.max()) if len(present) else None

        if boolean:
            lo, hi = config.BOOLEAN_BOUNDS
            constant = False
        elif observed_min is None:
            # No eligible cell has a value for this criterion. There is no
            # scale to build, so it is treated as constant: every cell gets
            # the documented fill and the report flags it.
            lo = hi = 0.0
            constant = True
        else:
            lo, hi = observed_min, observed_max
            constant = lo == hi

        bounds[criterion.feature] = Bounds(
            feature=criterion.feature,
            lo=float(lo),
            hi=float(hi),
            observed_min=observed_min,
            observed_max=observed_max,
            is_boolean=boolean,
            is_constant=constant,
            n_observed=int(len(present)),
        )
    return bounds


def normalise_value(value: float, lo: float, hi: float, direction: str) -> float:
    """
    Scalar normalisation — the formula in its plainest form.

    higher_is_better:  (v - lo) / (hi - lo)
    lower_is_better:   1 - (v - lo) / (hi - lo)
    lo == hi:          config.CONSTANT_CRITERION_VALUE (never divides by zero)

    The result is clamped to the inclusive [0, 1] range, so a value outside
    the bounds (possible only if bounds are supplied from another population)
    saturates rather than pushing a score out of range.
    """
    if direction not in config.DIRECTIONS:
        raise ValueError(
            f"unknown direction {direction!r}; expected one of {config.DIRECTIONS}"
        )
    if value != value:  # NaN
        return float("nan")
    if hi == lo:
        return float(config.CONSTANT_CRITERION_VALUE)
    scaled = (value - lo) / (hi - lo)
    if direction == config.LOWER_IS_BETTER:
        scaled = 1.0 - scaled
    return float(min(1.0, max(0.0, scaled)))


def normalise_series(values: pd.Series, bounds: Bounds, direction: str) -> pd.Series:
    """
    Vectorised normalisation of one criterion column to [0, 1].

    Nulls stay null: a cell missing this criterion is excluded from that
    cell's weighted average rather than scored as if the feature were at its
    worst. Identical inputs always give identical outputs — the operation is
    a pure function of the values, the bounds and the direction.
    """
    if direction not in config.DIRECTIONS:
        raise ValueError(
            f"unknown direction {direction!r}; expected one of {config.DIRECTIONS}"
        )
    numeric = as_float(values)

    if bounds.hi == bounds.lo:
        # Constant criterion: documented fill, no division. Nulls stay null.
        scaled = pd.Series(
            float(config.CONSTANT_CRITERION_VALUE), index=numeric.index, dtype=float
        ).where(numeric.notna())
        return scaled

    scaled = (numeric - bounds.lo) / (bounds.hi - bounds.lo)
    if direction == config.LOWER_IS_BETTER:
        scaled = 1.0 - scaled
    return scaled.clip(lower=0.0, upper=1.0)
