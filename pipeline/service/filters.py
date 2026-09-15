"""
Display_Filters over a Run's fixed ranked output (S2-08, CONTRACT.md §4.2, §7).

This module is the SELECTION core of the ranked-results operation and nothing
else: pure functions of ``(list[RankedRow], parameter)`` with NO file I/O, NO
engine access, and NO arithmetic on a cell's score or rank. That is the whole
point of the Decision_Service being a "thin read-and-serve layer" — a
Display_Filter changes WHICH cells are shown, never their values (CONTRACT.md
§1, Requirement 3.1, 3.2 / Property P2). The service holds no code path by which
a filter could re-run normalisation or scoring, so the map and the ranking table
always represent one engine output.

The two filters mirror the S1-11 shortlist stage's two rules so the service
agrees with the rest of the pipeline on what "top-N" and "eligible-only" mean:

  TOP-N (``top_n``). Reuses the ``pipeline/shortlist/select.py``
  selection-by-rank pattern: order by the engine's own ``rank`` with a STABLE
  sort and take the first ``min(top_n, n)`` rows, so ties and gaps are preserved
  exactly and no rank is re-derived (shortlist ``select_shortlist``). Because
  ``get_ranked_results`` already returns only eligible cells ordered ascending
  by rank, this is a clamped prefix of that list — the take is clamped to the
  eligible count, so a ``top_n`` larger than the eligible count returns EVERY
  eligible cell with no padding (Requirement 3.3, CONTRACT.md §6).

  MINIMUM SCORE (``min_score``). A pure threshold over the fixed
  ``suitability_score`` values: keep the cells whose score is ``>= min_score``.
  A threshold that excludes every cell returns an EMPTY list, not an error — an
  empty-but-valid result (Requirement 3.4, CONTRACT.md §6).

When both are supplied, the threshold is applied first and the top-N is taken
over the survivors (CONTRACT.md §4.2); ranks are unchanged either way.
"""

from __future__ import annotations

from .models import RankedRow


def apply_min_score(rows: list[RankedRow], min_score: float) -> list[RankedRow]:
    """
    Keep only the cells whose ``suitability_score`` is ``>= min_score``
    (CONTRACT.md §4.2, Requirement 3.1, 3.2, 3.4).

    PURE: a threshold selection over the fixed ``rows`` — the same ``RankedRow``
    objects are carried through unchanged, so every returned cell keeps the
    engine's ``suitability_score`` and ``rank`` exactly (Property P2). No score
    or rank is ever recomputed; the input order (ascending ``rank``) is
    preserved because this is a filter, not a sort.

    A threshold that excludes every cell returns an EMPTY list, not an error —
    an empty-but-valid result (Requirement 3.4, CONTRACT.md §6).
    """
    return [row for row in rows if row.suitability_score >= min_score]


def apply_top_n(rows: list[RankedRow], top_n: int) -> list[RankedRow]:
    """
    Keep the ``min(top_n, len(rows))`` lowest-``rank`` cells, in rank order
    (CONTRACT.md §4.2, Requirement 3.1, 3.2, 3.3).

    Reuses the ``pipeline/shortlist/select.py`` selection-by-rank pattern
    (``select_shortlist``): order by the engine's own ``rank`` with a STABLE
    sort and take the first ``take = min(top_n, n)`` rows. ``rows`` from
    ``get_ranked_results`` is already ascending by ``rank`` and eligible-only,
    so this is a clamped prefix — the sort is a defensive restatement of that
    invariant (ties and gaps preserved, no rank re-derived) rather than a
    re-ranking.

    PURE: the same ``RankedRow`` objects are carried through, so every returned
    cell keeps the engine's ``suitability_score`` and ``rank`` exactly (Property
    P2). The take is CLAMPED to the eligible count and never padded, so a
    ``top_n`` larger than the eligible count returns EVERY eligible cell — an
    empty-but-valid result rather than a padded one (Requirement 3.3,
    CONTRACT.md §6).

    Raises
    ------
    ValueError
        ``top_n`` is not a positive integer. Per CONTRACT.md §4.2 the query
        parameter is ``integer > 0``; a zero, negative or non-integer value is
        an invalid filter, distinct from a valid ``top_n`` that merely exceeds
        the eligible count (which returns all eligible cells). ``bool`` is
        rejected explicitly since it is an ``int`` subclass but not a count,
        mirroring ``shortlist.config.resolve_top_n``.
    """
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0:
        raise ValueError(
            f"top_n must be a positive integer; got {top_n!r}."
        )

    # Stable sort by the engine's own rank: rows are already ascending by rank
    # and eligible-only, so this preserves that order exactly (ties and gaps
    # intact) and never re-derives a rank — mirroring shortlist select_shortlist.
    ordered = sorted(rows, key=lambda row: row.rank)

    # Clamp the take to the available count — never pad (Requirement 3.3).
    take = min(top_n, len(ordered))
    return ordered[:take]


def apply_display_filter(
    rows: list[RankedRow],
    top_n: int | None = None,
    min_score: float | None = None,
) -> list[RankedRow]:
    """
    Apply an optional Display_Filter over a Run's fixed ranked ``rows``
    (CONTRACT.md §4.2, Requirement 3.1, 3.2, 3.3, 3.4).

    A pure selection over the fixed Run output: it never re-runs normalisation
    or scoring and never alters a cell's score or rank (Property P2). When both
    parameters are given, the ``min_score`` threshold is applied FIRST and the
    ``top_n`` is taken over the survivors (CONTRACT.md §4.2); the result is the
    same ``RankedRow`` objects, still ascending by ``rank``.

    * ``min_score is None`` and ``top_n is None`` → ``rows`` unchanged.
    * A threshold that excludes every cell → an EMPTY list (Requirement 3.4).
    * A ``top_n`` beyond the survivor count → all survivors, no padding
      (Requirement 3.3).

    Parameters
    ----------
    rows :
        The Run's ranked rows from ``get_ranked_results`` — eligible-only and
        ordered ascending by ``rank``.
    top_n :
        Optional positive integer; keep the ``top_n`` lowest-``rank`` survivors.
    min_score :
        Optional threshold; keep cells with ``suitability_score >= min_score``.

    Returns
    -------
    list[RankedRow]
        The surviving rows, ranks and scores unchanged, ascending by ``rank``.
    """
    selected = rows
    if min_score is not None:
        selected = apply_min_score(selected, min_score)
    if top_n is not None:
        selected = apply_top_n(selected, top_n)
    return selected
