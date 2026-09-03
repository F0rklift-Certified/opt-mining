"""
Pure summary statistics for the S1-11 shortlist stage (Requirement 6).

This module is the SUMMARY core of the shortlist stage and nothing else: a
single pure function of two in-memory frames — the S1-10 Scored_Table and the
assembled Shortlist — returning a frozen ``SummaryStats``. There is NO file
I/O here and NO dependence on the writers or the grid loader, so the statistics
logic is independently testable — frames in, stats out — and the caller
(`run.py`) is responsible for rendering the result into the Summary_Report and
the metadata sidecar.

Three rules deserve their names spelled out, because each is a place where a
naive implementation would silently report the wrong population:

  ELIGIBLE-ONLY SCORE DISTRIBUTION. The ``min`` / ``max`` / ``mean`` / ``std``
  of ``suitability_score`` are computed over the ELIGIBLE_Cell population only
  — rows with a non-null ``suitability_score`` AND a non-null ``rank`` — never
  over the whole Scored_Table. An Excluded_Cell (null score / null rank) is
  never mixed into the distribution, so perturbing an Excluded_Cell's stored
  value can never move the reported statistics (Requirement 6.1, 6.6).

  COUNT POPULATIONS ARE DISTINCT. Three counts are reported for the run and
  they are NOT the same population (Requirement 6.5):
    * ``n_cells``    — total rows in the Scored_Table (the full grid).
    * ``n_scored``   — rows with a non-null ``suitability_score``.
    * ``n_eligible`` — rows with a non-null ``suitability_score`` AND a
                       non-null ``rank`` (the shortlist-candidate population).

  EMPTY POPULATION IS HONEST, NOT A CRASH. When no cell is eligible (or the
  shortlist is empty), the score distribution and the geographic ranges are
  reported as ``None`` rather than fabricated numbers or a raised exception,
  so the downstream writers still emit a headered, disclaimer-carrying report
  (Requirement 3.6 spirit / 6).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import config
from .coords import GRID_COORDINATE_COLUMNS
from .select import eligible_cells

# Column names, resolved from the documented schema so a rename in config
# propagates here rather than drifting.
_RANK_COL = config.SHORTLIST_COLUMNS[0]  # "rank"
_SCORE_COL = config.SHORTLIST_COLUMNS[2]  # "suitability_score"
_CONFIDENCE_COL = config.SHORTLIST_COLUMNS[3]  # "confidence"
_LAT_COL = GRID_COORDINATE_COLUMNS[0]  # "centroid_lat"
_LON_COL = GRID_COORDINATE_COLUMNS[1]  # "centroid_lon"

# The optional REZ context column, reported among the top sites WHERE the
# upstream layer has supplied it (Requirement 6.3, 4.3).
_REZ_COL = config.OPTIONAL_CONTEXT_COLUMNS[0]  # "rez"


@dataclass(frozen=True)
class SummaryStats:
    """
    Descriptive statistics for one shortlist run (Requirement 6).

    All fields are plain Python scalars / containers (no pandas objects) so the
    result serialises cleanly into the Summary_Report and the JSON metadata
    sidecar without leaking a frame reference.

    Fields:
      score_dist       ``{"min", "max", "mean", "std"}`` of ``suitability_score``
                       over the ELIGIBLE_Cell population ONLY, excluding
                       Excluded_Cell values (Requirement 6.1, 6.6). Each value
                       is ``None`` when there are no eligible cells.
      lat_range        ``(min, max)`` of the shortlisted ``centroid_lat``
                       (Requirement 6.2); ``(None, None)`` for an empty
                       shortlist.
      lon_range        ``(min, max)`` of the shortlisted ``centroid_lon``
                       (Requirement 6.2); ``(None, None)`` for an empty
                       shortlist.
      rez_represented  Sorted list of the distinct REZs represented among the
                       shortlisted top sites, WHERE a ``rez`` column is
                       available; an empty list when it is not (Requirement
                       6.3).
      confidence_dist  ``{"high": n, "low": n}`` — the count of shortlisted
                       cells at each ``confidence`` value (Requirement 6.4).
      n_cells          Total cells in the Scored_Table for the run
                       (Requirement 6.5).
      n_eligible       Eligible_Cells (non-null score AND rank) for the run
                       (Requirement 6.5).
      n_scored         Scored cells (non-null ``suitability_score``) for the
                       run (Requirement 6.5).
    """

    score_dist: dict
    lat_range: tuple
    lon_range: tuple
    rez_represented: list
    confidence_dist: dict
    n_cells: int
    n_eligible: int
    n_scored: int


def _score_distribution(eligible: pd.DataFrame) -> dict:
    """
    ``min`` / ``max`` / ``mean`` / ``std`` of ``suitability_score`` over the
    ELIGIBLE_Cell population only (Requirement 6.1, 6.6).

    The distribution is computed exclusively from ``eligible`` — the frame of
    rows with a non-null score AND rank — so an Excluded_Cell value is never
    included. When ``eligible`` is empty each statistic is ``None`` rather than
    NaN or a fabricated number, so the report reads honestly (Requirement 6).

    ``std`` uses the pandas default sample standard deviation (ddof=1); with a
    single eligible cell it is undefined and reported as ``None``.
    """
    if eligible.empty:
        return {"min": None, "max": None, "mean": None, "std": None}

    scores = eligible[_SCORE_COL]
    std = scores.std()  # sample std (ddof=1); NaN for a single value
    return {
        "min": float(scores.min()),
        "max": float(scores.max()),
        "mean": float(scores.mean()),
        "std": None if pd.isna(std) else float(std),
    }


def _range(values: pd.Series) -> tuple:
    """
    ``(min, max)`` of a numeric series, or ``(None, None)`` when the series is
    empty (an empty shortlist). Used for the geographic spread (Requirement
    6.2).
    """
    if values.empty:
        return (None, None)
    return (float(values.min()), float(values.max()))


def _confidence_distribution(shortlist: pd.DataFrame) -> dict:
    """
    Count the shortlisted cells at each ``confidence`` value in the documented
    vocabulary (``high``, ``low``) (Requirement 6.4).

    Every level in ``config.CONFIDENCE_LEVELS`` is present in the result with
    an explicit zero when no shortlisted cell carries it, so a level never
    silently disappears from the report. The per-level counts sum to the
    shortlist row count for values within the vocabulary.
    """
    if _CONFIDENCE_COL in shortlist.columns and not shortlist.empty:
        counts = shortlist[_CONFIDENCE_COL].value_counts()
    else:
        counts = pd.Series(dtype="int64")
    return {level: int(counts.get(level, 0)) for level in config.CONFIDENCE_LEVELS}


def _rez_represented(shortlist: pd.DataFrame) -> list:
    """
    The distinct REZs represented among the shortlisted top sites, WHERE a
    ``rez`` column is available on the shortlist frame (Requirement 6.3).

    Returns a sorted list of the distinct non-null ``rez`` values, or an empty
    list when the optional column is absent or the shortlist is empty. Absence
    of the column is not an error — the REZ context is optional (Requirement
    4.3).
    """
    if _REZ_COL not in shortlist.columns or shortlist.empty:
        return []
    distinct = shortlist[_REZ_COL].dropna().unique().tolist()
    return sorted(distinct, key=str)


def compute_summary(scored: pd.DataFrame, shortlist: pd.DataFrame) -> SummaryStats:
    """
    Compute the ``SummaryStats`` for one shortlist run (Requirement 6).

    PURE — takes the S1-10 Scored_Table and the assembled Shortlist as
    in-memory frames, returns a frozen ``SummaryStats``; NO file I/O and no
    mutation of the inputs.

    ``scored`` is the full Scored_Table (one row per grid cell); ``shortlist``
    is the selected, coordinate-joined top sites.

    The score distribution is computed over the ELIGIBLE_Cell population of
    ``scored`` only — rows with a non-null ``suitability_score`` AND a non-null
    ``rank`` — so Excluded_Cell values are excluded from ``min`` / ``max`` /
    ``mean`` / ``std`` (Requirement 6.1, 6.6). The geographic ranges and the
    confidence distribution are computed over the shortlisted top sites
    (Requirement 6.2, 6.4), and the REZ context is reported WHERE available
    (Requirement 6.3).

    Three distinct run counts are reported (Requirement 6.5):
      * ``n_cells``    — every row of ``scored`` (the full grid).
      * ``n_scored``   — rows with a non-null ``suitability_score``.
      * ``n_eligible`` — rows with a non-null score AND a non-null ``rank``.

    Handles the empty-shortlist / zero-eligible case gracefully: the score
    distribution and the ranges are reported as ``None`` rather than NaN or a
    raised exception, so the downstream writers still emit honest, headered,
    disclaimer-carrying outputs (Requirement 3.6 spirit / 6).
    """
    eligible = eligible_cells(scored)

    n_cells = int(len(scored))
    n_scored = int(scored[_SCORE_COL].notna().sum()) if _SCORE_COL in scored.columns else 0
    n_eligible = int(len(eligible))

    if _LAT_COL in shortlist.columns:
        lat_range = _range(shortlist[_LAT_COL])
    else:
        lat_range = (None, None)
    if _LON_COL in shortlist.columns:
        lon_range = _range(shortlist[_LON_COL])
    else:
        lon_range = (None, None)

    return SummaryStats(
        score_dist=_score_distribution(eligible),
        lat_range=lat_range,
        lon_range=lon_range,
        rez_represented=_rez_represented(shortlist),
        confidence_dist=_confidence_distribution(shortlist),
        n_cells=n_cells,
        n_eligible=n_eligible,
        n_scored=n_scored,
    )
