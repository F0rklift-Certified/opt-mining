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

`get_ranked_results` (task 3.1) and `get_site_detail` (task 3.2) are these
operations. `get_site_detail` serves one cell's full detail by projecting the
SAME Scored_Table `get_ranked_results` reads (so the two agree on a cell's
score and rank — the consistency guarantee, Requirement 2.3), joining the
input `features` and `eligible` flag from the integrated table the Run scored,
and carrying the S2-06 Explanation_Structure through VERBATIM. The display
filters (top-N, minimum-score) the ranked-results operation will accept are
pure SELECTIONS over this fixed output and are added by task 4.1; this module
deliberately contains no selection logic yet, only the read-and-project core
every read operation builds on.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..scoring import config as _scoring_config
from . import config as _service_config
from .models import RankedRow, RunHandle, SiteDetail
from .runs import (
    CellNotFoundError,
    load_explanations,
    load_integrated_table,
    load_scored_table,
)


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


def _opt_score(value: object) -> float | None:
    """The Scored_Table score as a float, or ``None`` for an excluded cell."""
    return None if pd.isna(value) else float(value)


def _opt_rank(value: object) -> int | None:
    """The Scored_Table rank as an int, or ``None`` for an excluded cell."""
    return None if pd.isna(value) else int(value)


def _features_for(
    row: pd.Series,
    feature_names: list[str],
) -> dict[str, Any]:
    """
    The cell's input feature values, keyed by criterion `feature`.

    Reads the Run's criteria feature columns from the integrated table VERBATIM
    (the values the engine scored). A null value is carried through as ``None``
    rather than dropped, so the caller can tell "this cell had no value for the
    criterion" from "the criterion is absent" — an excluded cell's missing
    feature is a fact the detail view surfaces, never fabricated.
    """
    features: dict[str, Any] = {}
    for name in feature_names:
        if name not in row.index:
            continue
        value = row[name]
        if pd.isna(value):
            features[name] = None
        elif isinstance(value, (bool,)):
            features[name] = bool(value)
        else:
            # Numpy scalars -> native Python types for a clean, serialisable dict.
            features[name] = getattr(value, "item", lambda: value)()
    return features


def get_site_detail(run: RunHandle | str, cell_id: str) -> SiteDetail:
    """
    Return one cell's full detail for a Run (CONTRACT.md §4.3, Requirement 1.3,
    2.3, 6.2, 7.2).

    Assembles the ``SiteDetail`` ENTIRELY from materialised engine outputs — it
    performs no scoring, normalisation, ranking or exclusion arithmetic
    (CONTRACT.md §1, Requirement 2.4):

    * `suitability_score`, `rank` and the per-criterion `contributions` are read
      from the SAME Scored_Table `get_ranked_results` reads, so the score and
      rank served here for a `cell_id` are IDENTICAL to those it returns for the
      same cell in the same Run (the consistency guarantee, Requirement 2.3 /
      Property P1). An excluded cell carries ``None`` for both;
    * `features` and `eligible` are read from the integrated feature table the
      Run scored (resolved from the Run's manifest), carried through verbatim;
    * `explanation` is the S2-06 Explanation_Structure for the cell, resolved by
      `cell_id` from the materialised explanation output and carried through
      VERBATIM — its fields are neither renamed nor reordered (CONTRACT.md §5).

    Parameters
    ----------
    run :
        The Run to read, as the ``RunHandle`` returned by ``run_analysis`` or
        its bare ``run_id`` string.
    cell_id :
        The analysis-cell id to detail.

    Returns
    -------
    SiteDetail
        The cell's features, contributions, score, rank, eligibility and S2-06
        explanation.

    Raises
    ------
    RunNotFoundError
        The Run has no materialisation on disk (Requirement 7.1).
    CellNotFoundError
        The `cell_id` is not present in the Run's Scored_Table — the error
        names the missing `cell_id` rather than returning an empty success
        (Requirement 7.2).
    EngineOutputError
        A required materialised engine output (the Scored_Table, the integrated
        table, or the explanation output) is missing or unreadable — the error
        names the missing input rather than fabricating a result (Requirement
        7.3).
    """
    run_id = _run_id_of(run)
    cell_id = str(cell_id)

    cell_col = _scoring_config.CELL_ID_COLUMN
    score_col = _scoring_config.SCORE_COLUMN
    rank_col = _scoring_config.RANK_COLUMN

    # Score / rank / contributions from the SAME table get_ranked_results reads.
    table = load_scored_table(run_id)
    scored = pd.DataFrame(table.drop(columns=[table.geometry.name], errors="ignore"))
    matches = scored[scored[cell_col] == cell_id]
    if matches.empty:
        raise CellNotFoundError(
            f"cell_id {cell_id!r} is not present in Run {run_id!r}; the Run's "
            f"Scored_Table has no such cell."
        )
    scored_row = matches.iloc[0]

    contribution_columns = [
        c for c in scored.columns
        if c.startswith(_scoring_config.CONTRIBUTION_PREFIX)
    ]
    contributions = _key_components(scored_row, contribution_columns)

    # Input features + eligibility from the integrated table the Run scored.
    integrated = load_integrated_table(run_id)
    geom_name = getattr(integrated, "geometry", None)
    geom_col = geom_name.name if geom_name is not None else None
    integrated_df = pd.DataFrame(
        integrated.drop(columns=[geom_col], errors="ignore")
        if geom_col is not None else integrated
    )
    feature_rows = integrated_df[integrated_df[cell_col] == cell_id]
    if feature_rows.empty:
        # The Scored_Table has the cell but the integrated input the Run
        # recorded does not — the two outputs are out of step; name the input.
        raise CellNotFoundError(
            f"cell_id {cell_id!r} is in Run {run_id!r} Scored_Table but absent "
            f"from the integrated feature table the Run scored; the engine "
            f"outputs are out of step for this cell."
        )
    feature_row = feature_rows.iloc[0]

    # The Run's criteria feature names come from its manifest (the criteria the
    # engine scored), so `features` follows the Run's configuration rather than
    # a fixed list. The contribution keys are the same criteria, so fall back to
    # them if a manifest is somehow criteria-less.
    feature_names = _run_feature_names(run_id)
    if not feature_names:
        feature_names = list(contributions.keys())
    features = _features_for(feature_row, feature_names)

    eligible = bool(feature_row[_service_config.ELIGIBLE_COLUMN]) \
        if _service_config.ELIGIBLE_COLUMN in feature_row.index else False

    # The S2-06 Explanation_Structure, resolved by cell_id and carried verbatim.
    explanation = load_explanations().get(cell_id, {})

    return SiteDetail(
        cell_id=cell_id,
        features=features,
        contributions=contributions,
        suitability_score=_opt_score(scored_row[score_col]),
        rank=_opt_rank(scored_row[rank_col]),
        eligible=eligible,
        explanation=explanation,
    )


def _run_feature_names(run_id: str) -> list[str]:
    """
    The criterion feature names the Run scored, from its manifest.

    These define the `features` set `get_site_detail` returns, so the detail
    follows the Run's own criteria configuration rather than a hard-coded list.
    Returns an empty list when the manifest records no criteria (the caller
    then falls back to the Scored_Table's contribution columns).
    """
    from .runs import load_run_manifest

    manifest = load_run_manifest(run_id)
    criteria = manifest.get("criteria", [])
    return [
        c["feature"]
        for c in criteria
        if isinstance(c, dict) and "feature" in c
    ]
