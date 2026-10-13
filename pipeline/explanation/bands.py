"""
Qualitative band derivation (S2-06a, design decision 3C).

A criterion's NORMALISED value (in [0, 1], where 1 is most favourable) is
mapped to a coarse qualitative band ("top decile" / "strong" / "moderate" /
"limited") for the narrative. The band thresholds and labels are DATA, held on
the `ExplanationTemplates` loaded from YAML — nothing here hard-codes a label.

This module is a thin, PURE rule layer over the templates and the scoring
stage's own normalisation policies. It introduces NO second normaliser: the
normalised values themselves are produced by `pipeline.scoring.normalise`
(reused in `load.py`); `bands.py` only classifies them, and only needs to know,
per criterion, whether it is boolean or constant so it can honour the same
policies `normalise.py` documents:

  * BOOLEAN (normalise §5.6). A boolean criterion has no meaningful decile; it
    is simply present or absent. `band_for` returns the templates' boolean
    label (`present` / `absent`) rather than a decile band.

  * CONSTANT (normalise §5.5). A criterion with one value over the eligible
    population carries no discriminating information — every cell is assigned
    the constant fill (`normalise.config.CONSTANT_CRITERION_VALUE`). Such a
    criterion is not reported as a distinguishing factor at all, so `band_for`
    returns `None` for it and the engine skips it. This mirrors the method
    report flagging a constant criterion as unable to change the ranking.

Everything is a pure function of (value, Bounds, templates): identical inputs
always yield identical labels, which is the determinism the explanation
contract requires.
"""

from __future__ import annotations

import math

from ..scoring.normalise import Bounds
from .templates import ExplanationTemplates


def is_constant(bounds: Bounds) -> bool:
    """
    True when a criterion carried no discriminating information on this run.

    A constant criterion (min == max over the eligible population, or no
    eligible value at all) is flagged by `scoring.normalise.compute_bounds`
    as `is_constant`. It shifts every cell's score by the same amount and
    cannot separate cells, so it is never surfaced as a factor.
    """
    return bool(bounds.is_constant)


def band_for(
    norm: float | None,
    bounds: Bounds,
    templates: ExplanationTemplates,
) -> str | None:
    """
    Qualitative band label for one criterion on one cell, or `None` when the
    criterion should not be surfaced as a distinguishing factor.

    Returns `None` when:
      - the normalised value is missing (the cell had no value for this
        criterion, so it took no part in the score — nothing to say about it), or
      - the criterion is constant over the eligible population (it cannot
        distinguish this cell from any other).

    For a BOOLEAN criterion the label is the templates' present/absent label,
    keyed off whether the normalised value is at its favourable end (1.0). For
    a continuous criterion the label is the templates' band whose `min_norm`
    the value clears (see `ExplanationTemplates.band_label`).
    """
    if norm is None or (isinstance(norm, float) and math.isnan(norm)):
        return None
    if is_constant(bounds):
        return None
    if bounds.is_boolean:
        # A boolean normalises to its definitional {0.0, 1.0} domain, so 1.0
        # is the favourable end regardless of direction handling upstream.
        return (
            templates.boolean_true_label
            if norm >= 1.0
            else templates.boolean_false_label
        )
    return templates.band_label(float(norm))
