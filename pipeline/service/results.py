"""
The read operations over a materialised Run's engine output (S2-08).

This module serves the S2-05 Scored_Table for a completed Run. It holds NO
decision logic: it does not score, normalise, rank or compute exclusions. It
reads the materialised Scored_Table the engine already wrote (`runs.py`
resolves the `run_id` to it) and PROJECTS it into the typed models the
contract defines, carrying every value through verbatim. This is the
no-recompute structural guarantee (CONTRACT.md §1, Requirement 2.4): the
score and rank a `cell_id` is served here are the engine's, read from the
fixed table — there is no arithmetic path by which they could differ from
what the engine computed.

`get_ranked_results` (task 3.1) is the first of these operations. The display
filters (top-N, minimum-score) it will accept are pure SELECTIONS over this
fixed output and are added by task 4.1; this module deliberately contains no
selection logic yet, only the read-and-project core every read operation
builds on.
"""

from __future__ import annotations

import pandas as pd

from ..scoring import config as _scoring_config
from .models import RankedRow, RunHandle
from .runs import load_scored_table


def _run_id_of(run: RunHandle | str) -> str:
    """Accept either a ``RunHandle`` or a bare ``run_id`` string."""
    return run.run_id if isinstance(run, RunHandle) else str(run)


def _key_components(row: pd.Series, contribution_columns: list[str]) -> dict[str, float]:
    """
    The per-criterion component values for a cell, keyed by criterion `feature`.

    Reads the `contrib_{feature}` columns of the Scored_Table verbatim and
    strips the documented `contrib_` prefix so the keys are the criterion
    feature names (CONTRACT.md §5 `RankedRow.key_components`). A null
    contribution (a criterion with no value for the cell) is omitted rather
    than coerced to a fabricated 0.0.
    """
    prefix = _scoring_config.CONTRIBUTION_PREFIX
    components: dict[str, float] = {}
    for column in contribution_columns:
        value = row[column]
        if pd.isna(value):
            continue
        feature = column[len(prefix):] if column.startswith(prefix) else column
        components[feature] = float(value)
    return components


def get_ranked_results(run: RunHandle | str) -> list[RankedRow]:
    """
    Return the ranked results for a Run as a projection of its fixed
    Scored_Table (CONTRACT.md §4.2, Requirement 1.2, 2.4, 6.3).

    Reads the materialised S2-05 Scored_Table for the Run and returns one
    ``RankedRow`` per ELIGIBLE cell — a row with BOTH a non-null
    ``suitability_score`` AND a non-null ``rank`` — ordered ascending by
    ``rank`` (rank 1 first). An excluded cell (null score / null rank) takes
    no part in the ranking and is never returned, exactly as the engine
    scored it; ineligible land is never ranked as if it were developable
    (CONTRACT.md §3).

    NO RECOMPUTE. The `suitability_score`, `rank` and `contrib_{feature}`
    values are read from the table and carried through unchanged; this
    function performs no scoring, normalisation or ranking arithmetic
    (Requirement 2.4). The rank ordering uses a STABLE sort on the engine's
    own `rank`, so ties and gaps are preserved exactly as the engine assigned
    them — no rank is ever re-derived.

    Parameters
    ----------
    run :
        The Run to read, as the ``RunHandle`` returned by ``run_analysis`` or
        its bare ``run_id`` string.

    Returns
    -------
    list[RankedRow]
        The eligible cells' ranked rows, ordered by ascending `rank`. Empty
        when the Run has no eligible cell (an empty-but-valid result, not an
        error — CONTRACT.md §6).

    Raises
    ------
    RunNotFoundError
        The Run has no materialisation on disk (Requirement 7.1).
    EngineOutputError
        The Run's Scored_Table is missing or unreadable — the error names the
        missing input rather than fabricating a result (Requirement 7.3).
    """
    run_id = _run_id_of(run)
    table = load_scored_table(run_id)

    cell_col = _scoring_config.CELL_ID_COLUMN
    score_col = _scoring_config.SCORE_COLUMN
    rank_col = _scoring_config.RANK_COLUMN

    # ELIGIBLE-ONLY: a row is ranked iff it has both a score and a rank. This
    # mirrors the shortlist stage's eligible_cells rule so the service agrees
    # with the rest of the pipeline on what "ranked" means.
    frame = pd.DataFrame(table.drop(columns=[table.geometry.name], errors="ignore"))
    eligible = frame[frame[score_col].notna() & frame[rank_col].notna()]

    # Order by the engine's own rank with a stable sort — never re-derive it.
    ordered = eligible.sort_values(by=rank_col, ascending=True, kind="stable")

    contribution_columns = [
        c for c in ordered.columns
        if c.startswith(_scoring_config.CONTRIBUTION_PREFIX)
    ]

    rows: list[RankedRow] = []
    for _, row in ordered.iterrows():
        rows.append(
            RankedRow(
                cell_id=str(row[cell_col]),
                suitability_score=float(row[score_col]),
                rank=int(row[rank_col]),
                key_components=_key_components(row, contribution_columns),
            )
        )
    return rows
