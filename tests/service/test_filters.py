"""
Tests for the S2-08 Display_Filters (``pipeline.service.filters``).

The filters — ``apply_top_n``, ``apply_min_score`` and the combined
``apply_display_filter`` — are pure selections over a Run's fixed
``list[RankedRow]``. They change WHICH cells are returned but never a cell's
``suitability_score`` or ``rank`` (CONTRACT.md §4.2, §7 P2 / Requirement 3.1,
3.2). Top-N reuses the ``pipeline/shortlist/select.py`` selection-by-rank
pattern: order by the engine's own rank and take a clamped prefix, never padding
(Requirement 3.3). An all-excluding ``min_score`` returns an empty list, not an
error (Requirement 3.4).

Two layers of coverage:

* These unit tests over hand-built ``RankedRow`` lists pin the selection rules,
  the empty-but-valid edge cases, the no-padding clamp, the compose-order of the
  two filters, and the invalid-``top_n`` guard — no engine or materialised Run
  required.
* The wiring of ``get_ranked_results(run, top_n=, min_score=)`` to these filters
  is covered end-to-end (over a materialised Run) in ``test_results.py`` and by
  the P2/P4 property tests.
"""

from __future__ import annotations

import pytest

from pipeline.service.filters import (
    apply_display_filter,
    apply_min_score,
    apply_top_n,
)
from pipeline.service.models import RankedRow


def _rows() -> list[RankedRow]:
    """Three eligible cells, ascending by rank (as get_ranked_results returns)."""
    return [
        RankedRow(cell_id="c1", suitability_score=0.9, rank=1,
                  key_components={"wind_speed": 0.9}),
        RankedRow(cell_id="c2", suitability_score=0.6, rank=2,
                  key_components={"wind_speed": 0.6}),
        RankedRow(cell_id="c3", suitability_score=0.3, rank=3,
                  key_components={"wind_speed": 0.3}),
    ]


# --------------------------------------------------------------------------- #
# apply_top_n — selection by rank, clamped, no padding (Requirement 3.2, 3.3).#
# --------------------------------------------------------------------------- #


def test_top_n_keeps_the_n_lowest_rank_cells():
    result = apply_top_n(_rows(), 2)

    assert [r.cell_id for r in result] == ["c1", "c2"]
    assert [r.rank for r in result] == [1, 2]
    # Scores are carried through unchanged — never recomputed (P2).
    assert [r.suitability_score for r in result] == [0.9, 0.6]


def test_top_n_orders_by_rank_regardless_of_input_order():
    shuffled = list(reversed(_rows()))  # ranks 3, 2, 1
    result = apply_top_n(shuffled, 2)

    assert [r.rank for r in result] == [1, 2]


def test_top_n_beyond_eligible_count_returns_all_without_padding():
    """Requirement 3.3 — top-N over the count returns every eligible cell."""
    rows = _rows()
    result = apply_top_n(rows, 99)

    assert len(result) == len(rows)  # no padding
    assert [r.cell_id for r in result] == ["c1", "c2", "c3"]


def test_top_n_equal_to_count_returns_all():
    rows = _rows()
    result = apply_top_n(rows, 3)

    assert [r.cell_id for r in result] == ["c1", "c2", "c3"]


def test_top_n_over_empty_list_is_empty():
    assert apply_top_n([], 5) == []


@pytest.mark.parametrize("bad", [0, -1, -10, True, False, 1.5, "2", None])
def test_top_n_rejects_non_positive_integer(bad):
    """top_n is `integer > 0` per CONTRACT.md §4.2; bool is not a count."""
    with pytest.raises(ValueError, match="positive integer"):
        apply_top_n(_rows(), bad)


def test_top_n_does_not_mutate_the_input():
    rows = _rows()
    before = list(rows)
    apply_top_n(rows, 1)
    assert rows == before  # same objects, same order


# --------------------------------------------------------------------------- #
# apply_min_score — threshold, empty-but-valid (Requirement 3.2, 3.4).        #
# --------------------------------------------------------------------------- #


def test_min_score_keeps_cells_at_or_above_the_threshold():
    result = apply_min_score(_rows(), 0.6)

    # Inclusive threshold: the 0.6 cell survives.
    assert [r.cell_id for r in result] == ["c1", "c2"]
    assert [r.rank for r in result] == [1, 2]


def test_min_score_preserves_rank_order_and_values():
    result = apply_min_score(_rows(), 0.0)

    assert [r.rank for r in result] == [1, 2, 3]
    assert [r.suitability_score for r in result] == [0.9, 0.6, 0.3]


def test_min_score_excluding_every_cell_returns_empty_but_valid():
    """Requirement 3.4 — an all-excluding threshold returns [], not an error."""
    result = apply_min_score(_rows(), 1.0 + 1e-9)

    assert result == []


def test_min_score_does_not_mutate_the_input():
    rows = _rows()
    before = list(rows)
    apply_min_score(rows, 0.5)
    assert rows == before


# --------------------------------------------------------------------------- #
# apply_display_filter — the combined, optional filter (CONTRACT.md §4.2).     #
# --------------------------------------------------------------------------- #


def test_display_filter_no_params_returns_rows_unchanged():
    rows = _rows()
    result = apply_display_filter(rows)

    assert [r.cell_id for r in result] == ["c1", "c2", "c3"]


def test_display_filter_applies_threshold_then_top_n_over_survivors():
    """Both given: threshold first, then top-N over the survivors (§4.2)."""
    rows = _rows()
    # min_score 0.3 keeps all three; top_n 2 then keeps ranks 1 and 2.
    result = apply_display_filter(rows, top_n=2, min_score=0.3)

    assert [r.cell_id for r in result] == ["c1", "c2"]


def test_display_filter_top_n_applies_to_threshold_survivors_not_original():
    rows = _rows()
    # min_score 0.6 leaves {c1, c2}; top_n 5 over the 2 survivors returns both,
    # NOT the original three — the top-N is over the survivors (§4.2), no padding.
    result = apply_display_filter(rows, top_n=5, min_score=0.6)

    assert [r.cell_id for r in result] == ["c1", "c2"]


def test_display_filter_only_top_n():
    result = apply_display_filter(_rows(), top_n=1)
    assert [r.cell_id for r in result] == ["c1"]


def test_display_filter_only_min_score():
    result = apply_display_filter(_rows(), min_score=0.6)
    assert [r.cell_id for r in result] == ["c1", "c2"]


def test_display_filter_all_excluding_threshold_is_empty():
    assert apply_display_filter(_rows(), top_n=2, min_score=2.0) == []
