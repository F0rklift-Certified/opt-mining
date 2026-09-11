"""
Feature normalisation — directional min-max (S1-10 R4/R7.3; S2-04).

Features are measured in different units — m/s, km, degrees, boolean, a 0–1
proxy — so they cannot be summed until each is rescaled to a common [0, 1]
range where 1 is most favourable and 0 is least favourable. This module is
the rescaling step and nothing else: pure functions of (values, bounds,
direction), with no I/O and no dependence on the weights or the scoring
stage. That independence is the point — it can be exercised on any in-memory
DataFrame.

STANDALONE COMPONENT (S2-04)
----------------------------
The normaliser is usable on its own, DataFrame in -> normalised DataFrame
out, without a `Criterion` or a weights file:

    from pipeline.scoring.normalise import NormSpec, normalise_frame
    out = normalise_frame(df, [NormSpec(feature_name, "higher_is_better")])
    # -> DataFrame with a `norm_{feature_name}` column in [0, 1]

`NormSpec(feature, direction)` is the decoupled per-feature contract, and
`SpecLike` is the structural Protocol both `NormSpec` and the scoring
`Criterion` satisfy — so the scoring stage and this standalone surface run
the SAME code (`score.normalised_frame` delegates to `normalise_frame`).
There is deliberately no second implementation.

THE METHOD (frozen: decision-engine spec §5, F9–F14)
-----------------------------------------------------
Each feature is rescaled by a LINEAR min-max transform with its Direction
applied inside the transform, then clamped to [0, 1] (§5.1):

    higher_is_better:  n = (v - lo) / (hi - lo)
    lower_is_better:   n = 1 - (v - lo) / (hi - lo)

Bounds `lo`/`hi` are the min/max of the ROWS PASSED IN — the eligible
population when the scoring stage calls it — computed fresh each call, never
hard-coded (§5.2). Passing the eligible rows is what makes the bounds a
property of the analysis run, not of any downstream display filter: a user
narrowing the map re-filters the *view*, it does not call the normaliser with
a narrower frame, so no cell's normalised value moves.

POLICIES (each frozen in spec §5; authoritative source is that document)
------------------------------------------------------------------------
  OUTLIERS (§5.3). None. The true min/max set the scale — no trimming,
  winsorising or percentile capping. The only clamp is the [0, 1] saturation
  guard, which matters solely when bounds from another population are
  supplied; within one call every value maps inside [0, 1] by construction.

  MISSING VALUES (§5.4). A null (or non-numeric -> NaN) stays NULL. It is
  never imputed to zero or the worst value, so a data gap is left out of that
  cell's weighted average rather than masquerading as an unfavourable
  measurement.

  CONSTANT FEATURE (§5.5). If a feature has one value over the passed rows,
  (v - lo) / (hi - lo) is 0/0. Rather than divide by zero or drop the
  feature, every cell is assigned `config.CONSTANT_CRITERION_VALUE` (1.0) and
  the feature is FLAGGED as constant so the method report can say it carried
  no discriminating information on that run. A constant feature shifts every
  score by the same amount and cannot change the ranking. A feature with NO
  value over the passed rows is treated the same way (bounds 0/0, flagged).

  BOOLEAN FEATURE (§5.6). A boolean uses its definitional {False -> 0.0,
  True -> 1.0} domain, not the observed extremes. This matters when a boolean
  is uniform: an all-False `inside_rez` should score 0 for every cell ("no
  cell is in a REZ"), not trigger the constant fill and hand every cell full
  marks for a benefit none of them has.

The per-feature Direction table and a prose statement of these policies live
in `pipeline/scoring/README.md`; the frozen contract they restate is
decision-engine spec §5, and the shipped Directions are in
`pipeline/scoring/scoring_weights.yaml`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import pandas as pd

from . import config


@runtime_checkable
class SpecLike(Protocol):
    """
    The structural contract this module needs from a "criterion".

    Anything carrying a `feature` column name and a `direction` string can be
    normalised — the scoring `Criterion` satisfies this by having both
    attributes, and so does the standalone `NormSpec` below. Declaring the
    dependency as a Protocol rather than importing `Criterion` is what keeps
    this module free of the weights/scoring layer: the normaliser is a pure
    rescaling component that neither loads data nor knows about weights.
    """

    @property
    def feature(self) -> str: ...

    @property
    def direction(self) -> str: ...


@dataclass(frozen=True)
class NormSpec:
    """
    A standalone normalisation instruction: one feature column and its
    Direction. This is the decoupled contract callers use when they do NOT
    have (and should not need) a scoring `Criterion` — a DataFrame column name
    plus whether higher or lower is more favourable is all the normaliser
    requires.

    `direction` is validated at construction against `config.DIRECTIONS`
    (`higher_is_better` / `lower_is_better`), so an invalid direction fails
    where the spec is built rather than deep inside the arithmetic.
    """

    feature: str
    direction: str

    def __post_init__(self) -> None:
        if self.direction not in config.DIRECTIONS:
            raise ValueError(
                f"unknown direction {self.direction!r} for feature "
                f"{self.feature!r}; expected one of {config.DIRECTIONS}"
            )


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
    criteria: Sequence[SpecLike],
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


def normalise_frame(
    df: pd.DataFrame,
    specs: Sequence[SpecLike],
    *,
    bounds: Mapping[str, Bounds] | None = None,
) -> pd.DataFrame:
    """
    The standalone normalisation entry point: DataFrame in, normalised
    DataFrame out.

    Given a feature table `df` and a sequence of `specs` (each a `NormSpec`,
    or any object exposing `feature`/`direction` — the scoring `Criterion`
    qualifies), return a new DataFrame aligned to `df.index` with one column
    per spec named `norm_{feature}`, each directional min-max normalised to
    `[0, 1]` where 1 is most favourable. This function neither loads data nor
    knows about weights, so it can be exercised on any in-memory frame.

    Bounds are computed FROM THE ROWS PASSED IN and fixed for this call
    (§5.2): the caller decides which population defines the scale — pass the
    eligible rows to reproduce the scoring bounds, and the same rows always
    yield the same normalised values. A downstream display filter re-filters
    the *view*; it does not call this with a narrower frame and so cannot move
    a cell's normalised value. The frozen policies are inherited unchanged
    from the shared core (`compute_bounds` / `normalise_series`):

      * outliers      — none; the true min/max of the passed rows set the
                        scale, with only the `[0, 1]` saturation clamp (§5.3);
      * missing values — a null stays null and is left out of the result for
                        that cell, never imputed to zero or the worst value
                        (§5.4);
      * constant       — a feature with one value over the passed rows is
                        filled with `config.CONSTANT_CRITERION_VALUE` and
                        flagged, never divided by zero (§5.5);
      * boolean        — a boolean feature uses its definitional
                        `{False -> 0.0, True -> 1.0}` domain, not the observed
                        extremes (§5.6).

    The authoritative frozen specification of this method is decision-engine
    spec §5; this is the shipped implementation of it.

    `bounds` may be supplied to reuse bounds computed elsewhere — the scoring
    stage computes them once so the method report and the scores cannot
    disagree. When omitted they are computed from the rows of `df`.
    """
    if bounds is None:
        bounds = compute_bounds(df, specs)
    return pd.DataFrame(
        {
            f"norm_{spec.feature}": normalise_series(
                df[spec.feature], bounds[spec.feature], spec.direction
            )
            for spec in specs
        },
        index=df.index,
    )
