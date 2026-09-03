"""
Scored_Table validation (S1-10, Requirement 14) — no silent passes.

Every check records what it EXPECTED, what it OBSERVED and an explicit
pass/fail, and every check is written to the validation report whether it
passed or not. A check that only speaks up when it fails is a check nobody
can audit; the pipeline's rule is that the evidence is always on the page.

Fatal checks halt the stage. There are no WARN-tier checks here: unlike the
integration stage, which tolerates documented cross-layer discrepancies, a
scored table that fails any check below is simply wrong.
"""

from __future__ import annotations

import pandas as pd

from . import config
from .score import eligible_mask
from .weights import WeightsConfig

FATAL = "fatal"


def _check(checks: list[dict], name: str, expected, observed, passed: bool) -> None:
    checks.append(
        {
            "name": name,
            "expected": str(expected),
            "observed": str(observed),
            "passed": bool(passed),
            "severity": FATAL,
        }
    )


def validate(
    table: pd.DataFrame,
    features: pd.DataFrame,
    weights: WeightsConfig,
) -> dict:
    """
    Check the assembled Scored_Table against the integrated table it came from.

    Returns a summary dict: {"checks": [...], "passed": n, "failed": n,
    "total": n}. The caller decides whether to halt; this function never
    raises on a data fault, so the report can always be written first.
    """
    checks: list[dict] = []

    # --- 14.1 one row per integrated-table cell_id ---
    n_expected = int(len(features))
    n_observed = int(len(table))
    _check(checks, "One row per integrated-table cell_id",
           f"{n_expected:,} rows", f"{n_observed:,} rows", n_observed == n_expected)

    # --- 14.2 the cell_id sets are identical ---
    expected_ids = set(features[config.CELL_ID_COLUMN])
    observed_ids = set(table[config.CELL_ID_COLUMN])
    missing = expected_ids - observed_ids
    extra = observed_ids - expected_ids
    duplicated = int(table[config.CELL_ID_COLUMN].duplicated().sum())
    _check(checks, "Every cell_id present, none missing, none extra, none duplicated",
           "0 missing, 0 extra, 0 duplicated",
           f"{len(missing):,} missing, {len(extra):,} extra, {duplicated:,} duplicated",
           not missing and not extra and duplicated == 0)

    scores = table[config.SCORE_COLUMN]
    scored_mask = scores.notna()

    # --- 14.3 every non-null score lies in [0, 1] ---
    out_of_range = int((~scores[scored_mask].between(0.0, 1.0)).sum())
    _check(checks, "Every non-null suitability_score within [0, 1]",
           "0 out-of-range values", f"{out_of_range:,} out-of-range values",
           out_of_range == 0)

    # --- 14.4 eligible <-> scored, excluded <-> null ---
    # Aligned by cell_id rather than by row position, so a table that is
    # reordered or the wrong length still yields a reported FAIL rather than a
    # broadcasting exception. A validator that crashes tells you less than one
    # that fails.
    eligibility = pd.Series(
        eligible_mask(features).to_numpy(),
        index=features[config.CELL_ID_COLUMN],
    )
    eligible = (
        table[config.CELL_ID_COLUMN].map(eligibility).fillna(False).astype(bool)
    )
    excluded_with_score = int((~eligible & scored_mask).sum())
    eligible_without_score = int((eligible & ~scored_mask).sum())
    _check(checks, "Only eligible cells scored; every excluded cell null",
           "0 excluded-with-score, 0 eligible-without-score",
           f"{excluded_with_score:,} excluded-with-score, "
           f"{eligible_without_score:,} eligible-without-score",
           excluded_with_score == 0 and eligible_without_score == 0)

    # --- 14.5 contributions reconcile to the score ---
    contribution_columns = [c for c in weights.contribution_columns if c in table.columns]
    reconstructed = table.loc[scored_mask, contribution_columns].sum(axis=1, skipna=True)
    residual = (reconstructed - scores[scored_mask]).abs()
    violators = int((residual > config.RECONCILE_TOLERANCE).sum())
    worst = float(residual.max()) if len(residual) else 0.0
    _check(checks,
           "Per-criterion contributions reconstruct the score "
           f"(tolerance {config.RECONCILE_TOLERANCE:g})",
           "0 cells outside tolerance",
           f"{violators:,} cells outside tolerance (largest residual {worst:.3e})",
           violators == 0)

    # --- 14.5b one contribution column per configured criterion ---
    expected_columns = list(weights.contribution_columns)
    present = [c for c in expected_columns if c in table.columns]
    stray = [c for c in table.columns
             if c.startswith(config.CONTRIBUTION_PREFIX) and c not in expected_columns]
    _check(checks, "Exactly one contribution column per configured criterion",
           f"{len(expected_columns)} columns, 0 stray",
           f"{len(present)} present, {len(stray)} stray",
           len(present) == len(expected_columns) and not stray)

    # --- 14.6 the confidence vocabulary ---
    # The vocabulary is S1-09's, carried through unchanged. See config.py for
    # why this is three-valued rather than the ticket's assumed two.
    confidence = table[config.OUTPUT_CONFIDENCE_COLUMN]
    unknown = confidence[~confidence.isin(list(config.CONFIDENCE_LEVELS))]
    unknown_values = sorted({str(v) for v in unknown.unique()})
    _check(checks,
           f"confidence values within the S1-09 vocabulary "
           f"{list(config.CONFIDENCE_LEVELS)}",
           "0 out-of-vocabulary values",
           f"{len(unknown):,} out-of-vocabulary values"
           + (f" {unknown_values}" if unknown_values else ""),
           len(unknown) == 0)

    # --- 14.7 rank is a contiguous 1..n ordering over scored cells only ---
    ranks = table[config.RANK_COLUMN]
    ranked_mask = ranks.notna()
    n_scored = int(scored_mask.sum())
    ranked_values = sorted(int(r) for r in ranks[ranked_mask])
    contiguous = ranked_values == list(range(1, n_scored + 1))
    rank_on_unscored = int((ranked_mask & ~scored_mask).sum())
    _check(checks, "rank is a contiguous 1..n ordering over scored cells only",
           f"ranks 1..{n_scored:,}, 0 ranks on unscored cells",
           f"{len(ranked_values):,} ranks "
           f"({'contiguous' if contiguous else 'NOT contiguous'}), "
           f"{rank_on_unscored:,} on unscored cells",
           contiguous and rank_on_unscored == 0)

    # --- 14.7b rank ordering agrees with the scores and the tie-break ---
    if n_scored:
        ordered = (
            table.loc[scored_mask, [config.CELL_ID_COLUMN, config.SCORE_COLUMN,
                                    config.RANK_COLUMN]]
            .sort_values(config.RANK_COLUMN)
        )
        descending = ordered[config.SCORE_COLUMN].is_monotonic_decreasing
        tied = ordered[config.SCORE_COLUMN].duplicated(keep=False)
        tie_break_ok = True
        if tied.any():
            for _, group in ordered[tied].groupby(config.SCORE_COLUMN, sort=False):
                ids = list(group[config.CELL_ID_COLUMN])
                if ids != sorted(ids):
                    tie_break_ok = False
                    break
        _check(checks, "rank descends by score, ties broken by ascending cell_id",
               "monotonically decreasing scores, ties in cell_id order",
               f"{'decreasing' if descending else 'NOT decreasing'}, "
               f"tie-break {'holds' if tie_break_ok else 'VIOLATED'}",
               descending and tie_break_ok)

    return summarise_checks(checks)


def summarise_checks(checks: list[dict]) -> dict:
    """Pass/fail tallies over a check list (same shape as integration.merge)."""
    failed = [c for c in checks if not c["passed"]]
    return {
        "checks": checks,
        "total": len(checks),
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "failed_names": [c["name"] for c in failed],
    }
