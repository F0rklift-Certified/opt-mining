"""
The Scoring_Function — pure weighted MCDA (S1-10, Requirements 5, 7, 9, 10).

`score_frame` is a PURE function: an in-memory DataFrame and a WeightsConfig
go in, a scored DataFrame comes out. It opens no files, reads no globals that
can change between runs, and holds no state. That is what makes the scoring
model independently replaceable — swapping this module for a different
scoring approach requires no change to the loader, the writer or the
orchestrator (Constitution: "Each component should be independently
replaceable without requiring changes to adjacent layers").

THE MODEL
---------
For every ELIGIBLE cell, and for each configured criterion i:

    norm_i    = normalise(value_i, bounds_i, direction_i)     -> [0, 1]
    contrib_i = weight_i * norm_i / W_cell
    score     = SUM_i contrib_i                               -> [0, 1]

where W_cell is the sum of the weights actually APPLIED to that cell. The
contributions are therefore additive shares of the final score, which is the
explainability contract: `contrib_wind_speed` is literally how many points
of the cell's score came from wind.

WHY W_cell IS PER-CELL. A criterion with no value for a given cell is
excluded from that cell's weighted average rather than scored as zero.
Scoring a missing feature as zero would silently punish a cell for a gap in
the data instead of for a property of the land — the Constitution's "never
let poor data pass as good" cuts both ways, and the honest treatment is to
average over the evidence that exists and let the carried-through confidence
value flag the gap. On the current NSW data no eligible cell is missing a
criterion, so W_cell equals the full weight sum for every scored cell.

NOT CIRCULAR. `wind_speed` enters only as an input criterion. Nothing here
predicts wind from wind-derived features, and no wind prediction column is
emitted (Constitution: "Never build a circular model").
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from . import config
from .normalise import Bounds, compute_bounds, normalise_series
from .rank import assign_ranks
from .weights import Criterion, WeightsConfig


def eligible_mask(features: pd.DataFrame) -> pd.Series:
    """
    Boolean eligibility per row, with nulls treated as NOT eligible.

    An unknown eligibility is not an eligibility. A cell whose `eligible`
    value is missing is left unscored rather than admitted to the ranking on
    the strength of a null.
    """
    values = features[config.ELIGIBLE_COLUMN]
    return pd.Series(
        [bool(v) if v is not None and v == v else False for v in values],
        index=features.index,
        dtype=bool,
    )


def normalised_frame(
    features: pd.DataFrame,
    criteria: Sequence[Criterion],
    bounds: Mapping[str, Bounds],
) -> pd.DataFrame:
    """
    One normalised column per criterion, named `norm_{feature}`, on the rows
    given. Exposed separately so tests and the method report can inspect the
    intermediate values that produced a score.
    """
    return pd.DataFrame(
        {
            f"norm_{c.feature}": normalise_series(
                features[c.feature], bounds[c.feature], c.direction
            )
            for c in criteria
        },
        index=features.index,
    )


def score_frame(
    features: pd.DataFrame,
    weights: WeightsConfig,
    *,
    bounds: Mapping[str, Bounds] | None = None,
) -> pd.DataFrame:
    """
    Score every eligible cell. PURE — no file I/O, no mutation of `features`.

    Returns a frame aligned to `features.index` containing:
        cell_id, suitability_score, confidence,
        contrib_{feature}  (one per criterion),
        norm_{feature}     (intermediates; dropped before write),
        raw_score          (pre-discount score),
        confidence_factor, applied_weight, n_criteria_applied

    Excluded cells (`eligible` false or null) receive a null score and null
    contributions, and take no part in the normalisation bounds (6.4, 7.2).

    `bounds` may be supplied to reuse bounds computed elsewhere (the stage
    computes them once so the method report and the scores cannot disagree);
    when omitted they are computed from the eligible rows of `features`.
    """
    criteria = weights.criteria
    mask = eligible_mask(features)
    eligible = features.loc[mask]

    if bounds is None:
        bounds = compute_bounds(eligible, criteria)

    out = pd.DataFrame(index=features.index)
    out[config.CELL_ID_COLUMN] = features[config.CELL_ID_COLUMN]
    out[config.CONFIDENCE_COLUMN] = features[config.CONFIDENCE_COLUMN]

    norms = normalised_frame(eligible, criteria, bounds)
    for column in norms.columns:
        out[column] = np.nan
    out.loc[mask, norms.columns] = norms

    # Per-cell denominator: the weights of the criteria that actually have a
    # value for this cell. Criteria with a null value contribute neither a
    # numerator term nor a share of the denominator.
    applied = pd.Series(0.0, index=features.index, dtype=float)
    n_applied = pd.Series(0, index=features.index, dtype=int)
    for criterion in criteria:
        present = out[f"norm_{criterion.feature}"].notna()
        applied += present.astype(float) * criterion.weight
        n_applied += present.astype(int)
    out["applied_weight"] = applied.where(mask)
    out["n_criteria_applied"] = n_applied.where(mask)

    # A cell with no usable criterion has no denominator; it stays null
    # rather than becoming a divide-by-zero infinity. Validation reports any
    # such cell explicitly, so this can never pass silently.
    scorable = mask & (applied > 0)

    raw = pd.Series(np.nan, index=features.index, dtype=float)
    raw.loc[scorable] = 0.0
    for criterion in criteria:
        share = (
            criterion.weight * out[f"norm_{criterion.feature}"] / applied.where(scorable)
        )
        out[criterion.contribution_column] = share.where(scorable)
        raw.loc[scorable] = raw.loc[scorable] + share.loc[scorable].fillna(0.0)

    out["raw_score"] = raw.clip(lower=0.0, upper=1.0)

    # Optional confidence discount, applied identically to the score and to
    # every contribution so the contributions still reconstruct the score.
    if weights.confidence_discount:
        factor = out[config.CONFIDENCE_COLUMN].map(
            lambda v: weights.factor_for(v)
        ).astype(float)
    else:
        factor = pd.Series(1.0, index=features.index, dtype=float)
    out["confidence_factor"] = factor.where(scorable)

    out[config.SCORE_COLUMN] = (out["raw_score"] * factor).clip(lower=0.0, upper=1.0)
    if weights.confidence_discount:
        for criterion in criteria:
            column = criterion.contribution_column
            out[column] = out[column] * factor

    return out


def score_and_rank(
    features: pd.DataFrame,
    weights: WeightsConfig,
    *,
    bounds: Mapping[str, Bounds] | None = None,
) -> pd.DataFrame:
    """
    The complete pure core: score, then rank. Still no file I/O.

    Convenience for callers and tests that want the finished per-cell result
    in one call; `run()` uses it so the shipped stage and the tested core are
    the same code path.
    """
    scored = score_frame(features, weights, bounds=bounds)
    scored[config.RANK_COLUMN] = assign_ranks(scored)
    return scored


def summarise(scored: pd.DataFrame, features: pd.DataFrame) -> dict:
    """Counts the method report and the run summary both need."""
    mask = eligible_mask(features)
    scores = scored[config.SCORE_COLUMN]
    confidence = scored[config.CONFIDENCE_COLUMN]
    return {
        "n_cells": int(len(scored)),
        "n_eligible": int(mask.sum()),
        "n_excluded": int((~mask).sum()),
        "n_scored": int(scores.notna().sum()),
        "n_unscorable_eligible": int((mask & scores.isna()).sum()),
        "confidence_counts": {
            level: int((confidence == level).sum()) for level in config.CONFIDENCE_LEVELS
        },
        "scored_confidence_counts": {
            level: int((confidence[scores.notna()] == level).sum())
            for level in config.CONFIDENCE_LEVELS
        },
        "score_min": float(scores.min()) if scores.notna().any() else None,
        "score_max": float(scores.max()) if scores.notna().any() else None,
        "score_mean": float(scores.mean()) if scores.notna().any() else None,
    }
