"""
Property-based test for the S1-11 pure summary core (Property 12).

This test corresponds to numbered Property 12 in the feature design document
and runs at least 100 generated examples. The pure summary function under test
(`pipeline.shortlist.summary.compute_summary`) is exercised directly on
in-memory pandas DataFrames, so this test touches no filesystem: it validates
the RULE that the score distribution (`min`/`max`/`mean`/`std`) is computed
over the ELIGIBLE_Cell population only — rows with a non-null
`suitability_score` AND a non-null `rank` — and never mixes in Excluded_Cell
values (Requirement 6.1, 6.6).

Eligibility is by (non-null score AND non-null rank), NOT by a null score
alone. The S1-10 Excluded_Cell convention is null score AND null rank, but a
row with a non-null score yet a null rank is ALSO non-eligible: this test
generates exactly such rows (non-null score, null rank) so it proves the
eligibility gate keys on BOTH fields, not just the score. Perturbing the score
of any non-eligible row must never move the reported distribution.

It lives in a dedicated module (separate from the other property tests over the
pure core) so the property files can grow file-by-file without concurrent-write
conflicts, following the style of tests/test_shortlist_select_p1.py.
"""

from __future__ import annotations

import math

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.shortlist import config
from pipeline.shortlist.select import eligible_cells, select_shortlist
from pipeline.shortlist.summary import compute_summary

SETTINGS = settings(max_examples=200, deadline=None)

_SCORE_COL = config.SHORTLIST_COLUMNS[2]  # "suitability_score"
_RANK_COL = config.SHORTLIST_COLUMNS[0]  # "rank"

_rank = st.integers(min_value=1, max_value=15)
_score = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)
_confidence = st.sampled_from(config.CONFIDENCE_LEVELS)


@st.composite
def _scored_tables(draw):
    """Build a Scored_Table DataFrame mixing eligible and non-eligible rows.

    Each row is one of three kinds, so the test proves eligibility keys on BOTH
    fields rather than the score alone:

      * ELIGIBLE       — non-null ``suitability_score`` AND non-null ``rank``.
      * EXCLUDED        — null score AND null rank (the S1-10 convention).
      * SCORED-NO-RANK  — non-null ``suitability_score`` but null ``rank``.
                          This is a NON-eligible row that nonetheless carries a
                          real score, so a naive "score is not null" gate would
                          wrongly fold its value into the distribution.

    The table may be empty and may contain zero eligible rows — both are legal
    inputs to the summary core.
    """
    n = draw(st.integers(min_value=0, max_value=25))

    rows = []
    for cell_id in range(n):
        kind = draw(st.sampled_from(["eligible", "excluded", "scored_no_rank"]))
        if kind == "eligible":
            rank = draw(_rank)
            score = draw(_score)
        elif kind == "excluded":
            rank = None
            score = None
        else:  # scored_no_rank: NON-eligible but score present
            rank = None
            score = draw(_score)
        rows.append(
            {
                "rank": rank,
                "cell_id": cell_id,
                "suitability_score": score,
                "confidence": draw(_confidence),
            }
        )

    frame = pd.DataFrame(rows, columns=list(config.SHORTLIST_COLUMNS[:4]))
    if not frame.empty:
        frame["rank"] = frame["rank"].astype("Int64")

    # Shuffle so the test never relies on eligible rows being contiguous.
    if n > 1:
        perm = draw(st.permutations(list(range(n))))
        frame = frame.iloc[list(perm)].reset_index(drop=True)

    return frame


def _minimal_shortlist(scored: pd.DataFrame) -> pd.DataFrame:
    """A minimal assembled Shortlist for the second argument of compute_summary.

    ``compute_summary``'s ``score_dist`` depends only on ``scored``; the
    ``shortlist`` argument feeds the geographic / confidence / rez fields. We
    build a plausible one via the pure ``select_shortlist`` and attach trivial
    centroid columns so the summary's range logic has something valid to read,
    keeping the test focused on ``score_dist``.
    """
    shortlist = select_shortlist(scored, config.DEFAULT_TOP_N).copy()
    # Attach documented coordinate columns so the geographic-range branch is
    # exercised on real (if trivial) values rather than skipped.
    shortlist["centroid_lat"] = -30.0
    shortlist["centroid_lon"] = 150.0
    return shortlist


def _assert_dist_equal(reported: dict, expected: dict):
    """Assert two score_dist dicts agree, tolerant of float rounding and None."""
    assert set(reported) == {"min", "max", "mean", "std"}
    for key in ("min", "max", "mean", "std"):
        r = reported[key]
        e = expected[key]
        if e is None:
            assert r is None, f"{key}: expected None, got {r!r}"
        else:
            assert r is not None, f"{key}: expected {e!r}, got None"
            assert math.isclose(r, e, rel_tol=1e-9, abs_tol=1e-12), (
                f"{key}: reported {r!r} != expected {e!r}"
            )


def _expected_dist(scored: pd.DataFrame) -> dict:
    """Independent recomputation of the eligible-only score distribution.

    Eligible = non-null suitability_score AND non-null rank. Recomputed with a
    plain boolean mask, not via the module under test, so it is a genuine
    independent oracle.
    """
    mask = scored[_SCORE_COL].notna() & scored[_RANK_COL].notna()
    scores = scored.loc[mask, _SCORE_COL].astype(float)
    if scores.empty:
        return {"min": None, "max": None, "mean": None, "std": None}
    std = scores.std()  # sample std (ddof=1); NaN for a single value
    return {
        "min": float(scores.min()),
        "max": float(scores.max()),
        "mean": float(scores.mean()),
        "std": None if pd.isna(std) else float(std),
    }


# Feature: s1-11-generate-ranked-shortlist, Property 12: Score distribution is computed over eligible cells only
@SETTINGS
@given(scored=_scored_tables(), delta=st.floats(min_value=-100.0, max_value=100.0,
                                                allow_nan=False, allow_infinity=False))
def test_property_12_score_distribution_is_eligible_only(scored, delta):
    shortlist = _minimal_shortlist(scored)

    # 1. Reported score_dist equals an independent eligible-only recomputation
    #    (Requirement 6.1, 6.6).
    stats = compute_summary(scored, shortlist)
    expected = _expected_dist(scored)
    _assert_dist_equal(stats.score_dist, expected)

    # 2. Perturbing the scores of NON-eligible rows (null rank — whether the
    #    score is null or, as generated here, a real value) must never move the
    #    reported distribution. Eligibility keys on (non-null score AND non-null
    #    rank), so a scored-but-unranked row is excluded and its value is inert
    #    (Requirement 6.6).
    perturbed = scored.copy()
    noneligible_mask = ~(perturbed[_SCORE_COL].notna() & perturbed[_RANK_COL].notna())
    # Overwrite every non-eligible row's score with a wildly perturbed value,
    # including rows that previously had a real (unranked) score.
    perturbed.loc[noneligible_mask, _SCORE_COL] = delta

    perturbed_shortlist = _minimal_shortlist(perturbed)
    perturbed_stats = compute_summary(perturbed, perturbed_shortlist)

    # The eligible population is untouched, so the distribution is unchanged.
    _assert_dist_equal(perturbed_stats.score_dist, stats.score_dist)

    # And it still matches the independent oracle computed over the ORIGINAL
    # eligible rows (perturbation left them alone).
    _assert_dist_equal(perturbed_stats.score_dist, expected)

    # Sanity: the eligible count is invariant under the perturbation, i.e. we
    # only ever touched non-eligible rows.
    assert len(eligible_cells(perturbed)) == len(eligible_cells(scored))
