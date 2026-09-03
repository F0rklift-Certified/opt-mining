"""
Rank assignment (S1-10, Requirement 8).

Scored cells are ordered from most to least suitable so a planner can read
the strongest candidates off the top of the table.

TIE-BREAK. Ties are broken by ASCENDING `cell_id`. The rule matters more than
which rule it is: without a documented tie-break, two cells with identical
scores would be ordered by whatever order the rows happened to arrive in, and
a rerun could silently swap them. `cell_id` is stable, unique and independent
of the scores, so the ordering is a deterministic permutation that repeated
runs reproduce exactly.

Because every tie is broken, `rank` is a strict 1..n ordering over the scored
cells — no two cells share a rank, and no rank is skipped.

Excluded cells receive a NULL rank and take no part in the ordering.
Ineligible land is never ranked as if it were developable.
"""

from __future__ import annotations

import pandas as pd

from . import config


def assign_ranks(scored: pd.DataFrame) -> pd.Series:
    """
    Dense 1..n rank over cells with a non-null `suitability_score`.

    Rank 1 is the highest-scoring cell. Cells without a score (excluded, or
    eligible but with no usable criterion) get a null rank.

    Returns a Series aligned to `scored.index`, nullable-integer typed so a
    rank is a whole number and a missing rank is genuinely missing rather
    than a float NaN masquerading as one.
    """
    scores = scored[config.SCORE_COLUMN]
    ranked = scores.notna()

    order = (
        scored.loc[ranked, [config.CELL_ID_COLUMN]]
        .assign(_score=scores.loc[ranked])
        .sort_values(
            by=["_score", config.CELL_ID_COLUMN],
            ascending=[False, True],
            kind="mergesort",  # stable, so the sort itself adds no ambiguity
        )
    )

    ranks = pd.Series(pd.NA, index=scored.index, dtype="Int64")
    ranks.loc[order.index] = range(1, len(order) + 1)
    return ranks
