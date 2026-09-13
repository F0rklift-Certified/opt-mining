"""
The deterministic explanation engine (S2-06a) — PURE rule/template core.

`explain_cell` maps ONE eligible cell to its structured Explanation dict. It is
PURE: a `CellExplanationInput` in, a dict out; it opens no files, reads no
globals that change between runs, and holds no state. That is what makes the
explanation deterministic — the same input always yields byte-identical text —
and independently testable without the loader, the writer or a Scored_Table.

WHAT IT DECIDES
---------------
- POSITIVE FACTORS: the criteria contributing the MOST points to this cell's
  S2-05 score. Ranked by the persisted `contrib_{feature}` value (never
  recomputed). A criterion is only offered as a positive factor if its band is
  favourable enough to phrase honestly (a constant or missing criterion has no
  band and is skipped). Capped at `config.MAX_POSITIVE_FACTORS`.
- WEAKNESSES: the criteria this cell scores POORLY on — a normalised value at
  or below `config.WEAKNESS_NORM_CEILING`. Ranked worst-first (lowest
  normalised value), capped at `config.MAX_WEAKNESSES`. A criterion already
  chosen as a positive factor is never also listed as a weakness.
- HEADLINE: the single screening-level headline from the templates, identical
  for every eligible cell.

Ranking ties (equal contribution, or equal normalised value) are broken by
ASCENDING feature name, so the ordering is a deterministic permutation exactly
as the scoring stage breaks rank ties by ascending cell_id.

The engine RANKS by contribution and BANDS by normalised value (design
decision 3C): contribution answers "which criteria carried this cell's score",
the band answers "how good is the cell on that criterion", and the phrase pairs
the two, e.g. "Strong wind resource (top decile)".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..scoring.normalise import Bounds
from . import config
from .bands import band_for
from .templates import ExplanationTemplates


@dataclass(frozen=True)
class CriterionView:
    """
    One criterion's per-cell facts, as the engine needs them.

    `contribution` is the persisted `contrib_{feature}` value (points this
    criterion added to the score); `norm` is the recomputed normalised value in
    [0, 1]; `bounds` carries the boolean/constant flags. All three come from the
    loader — the engine never recomputes them.
    """

    feature: str
    contribution: float | None
    norm: float | None
    bounds: Bounds


@dataclass(frozen=True)
class CellExplanationInput:
    """Everything the pure engine needs to explain one eligible cell."""

    cell_id: str
    criteria: tuple[CriterionView, ...]
    order: tuple[str, ...] = field(default=())  # configured feature order (tie context only)


def _favourable_enough(view: CriterionView) -> bool:
    """
    A criterion is offerable as a POSITIVE factor when it has a usable band —
    i.e. it is not missing and not constant. A boolean absent (norm 0.0) is
    handled by the caller (it is a weakness, not a positive).
    """
    return view.norm is not None and not view.bounds.is_constant


def _sort_key_positive(view: CriterionView) -> tuple:
    """Highest contribution first; ties broken by ascending feature name."""
    contrib = view.contribution if view.contribution is not None else float("-inf")
    return (-float(contrib), view.feature)


def _sort_key_weakness(view: CriterionView) -> tuple:
    """Lowest normalised value first; ties broken by ascending feature name."""
    norm = view.norm if view.norm is not None else float("inf")
    return (float(norm), view.feature)


def _phrase(positive: bool, view: CriterionView, templates: ExplanationTemplates) -> str:
    """Render one factor phrase: '<phrase> (<band>)', band omitted if None."""
    phrases = templates.phrases_for(view.feature)
    text = phrases.positive if positive else phrases.weakness
    band = band_for(view.norm, view.bounds, templates)
    if band is None:
        return text
    return f"{text} ({band})"


def _positive_candidates(cell: CellExplanationInput) -> list[CriterionView]:
    """The criteria offerable as positive factors, ranked best-first."""
    candidates = [
        v for v in cell.criteria
        if _favourable_enough(v)
        and v.norm is not None
        and float(v.norm) > config.WEAKNESS_NORM_CEILING
    ]
    candidates.sort(key=_sort_key_positive)
    return candidates[: config.MAX_POSITIVE_FACTORS]


def select_positive_factors(
    cell: CellExplanationInput,
    templates: ExplanationTemplates,
) -> list[str]:
    """
    The strongest positive factors, ranked by contribution, capped at
    `config.MAX_POSITIVE_FACTORS`. Only criteria with a usable, favourable band
    are offered: a criterion the cell scores poorly on is a weakness, not a
    strength, even if it happens to carry weight.
    """
    return [_phrase(True, v, templates) for v in _positive_candidates(cell)]


def select_weaknesses(
    cell: CellExplanationInput,
    templates: ExplanationTemplates,
    exclude: set[str],
) -> list[str]:
    """
    The important weaknesses: criteria whose normalised value is at or below
    `config.WEAKNESS_NORM_CEILING`, ranked worst-first, capped at
    `config.MAX_WEAKNESSES`. Constant and missing criteria are skipped (nothing
    honest to say); anything already chosen as a positive factor is excluded.
    """
    candidates = [
        v for v in cell.criteria
        if v.feature not in exclude
        and v.norm is not None
        and not v.bounds.is_constant
        and float(v.norm) <= config.WEAKNESS_NORM_CEILING
    ]
    candidates.sort(key=_sort_key_weakness)
    chosen = candidates[: config.MAX_WEAKNESSES]
    return [_phrase(False, v, templates) for v in chosen]


def explain_cell(
    cell: CellExplanationInput,
    templates: ExplanationTemplates,
) -> dict:
    """
    Build the eligible Explanation_Structure for one cell. PURE and
    deterministic.

    Returns a dict with exactly the eligible-path fields (S2-06b extends this
    with excluded/caveat fields — it must not rename these):

        {
          "cell_id": "NSW001",
          "eligible": true,
          "headline": "<screening headline>",
          "positive_factors": [...],
          "weaknesses": [...]
        }
    """
    positive_views = _positive_candidates(cell)
    positive = [_phrase(True, v, templates) for v in positive_views]
    positive_features = {v.feature for v in positive_views}
    weaknesses = select_weaknesses(cell, templates, exclude=positive_features)

    return {
        config.FIELD_CELL_ID: cell.cell_id,
        config.FIELD_ELIGIBLE: True,
        config.FIELD_HEADLINE: templates.headline,
        config.FIELD_POSITIVE_FACTORS: positive,
        config.FIELD_WEAKNESSES: weaknesses,
    }
