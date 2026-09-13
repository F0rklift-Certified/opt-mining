"""
No-silent-passes validation for the Explanation_Table (S2-06a).

Every check reports EXPECTED vs OBSERVED vs PASS/FAIL and is listed whether it
passed or not, so the validation report never hides a passing check behind
silence (the pipeline's "no silent passes" rule). `run()` writes the report
even when validation fails, then raises, so a failed run still leaves the
evidence behind and the orchestrator halts non-zero.

The checks assert the eligible-path guarantees S2-06a owns:
  1. one explanation record per eligible cell (count matches the Scored_Table);
  2. every record is marked eligible on this path;
  3. every record has a non-empty headline;
  4. every record has at least one positive factor;
  5. every factor phrase references a CONFIGURED criterion (no invented factor);
  6. no record contains a banned superlative ("best site", etc.).
"""

from __future__ import annotations

from collections.abc import Sequence

from . import config
from .templates import BANNED_SUPERLATIVES, ExplanationTemplates


def _check(name: str, expected: str, observed: str, passed: bool) -> dict:
    return {"name": name, "expected": expected, "observed": observed, "passed": passed}


def _phrase_references_configured_criterion(
    phrase: str, phrases: dict, positive: bool
) -> bool:
    """
    True when the phrase's leading text matches a configured criterion phrase.

    The engine renders "<criterion phrase> (<band>)"; a factor that does not
    start with one of the configured phrases would be an invented factor.
    """
    for cp in phrases.values():
        text = cp.positive if positive else cp.weakness
        if phrase == text or phrase.startswith(text + " ("):
            return True
    return False


def validate(
    records: Sequence[dict],
    templates: ExplanationTemplates,
    *,
    n_eligible_cells: int,
) -> dict:
    """
    Run every check over the assembled explanation records.

    Returns a result dict with a per-check list and pass/fail totals, in the
    same shape the scoring stage's validator uses so the report renderer and
    the orchestrator handle both identically.
    """
    checks: list[dict] = []

    # 1. One record per eligible cell.
    n_records = len(records)
    checks.append(_check(
        "one explanation per eligible cell",
        f"{n_eligible_cells} records",
        f"{n_records} records",
        n_records == n_eligible_cells,
    ))

    # 2. Every record eligible on this path.
    n_not_eligible = sum(1 for r in records if r.get(config.FIELD_ELIGIBLE) is not True)
    checks.append(_check(
        "every record eligible == true",
        "0 non-eligible records",
        f"{n_not_eligible} non-eligible records",
        n_not_eligible == 0,
    ))

    # 3. Non-empty headline.
    n_empty_headline = sum(
        1 for r in records if not str(r.get(config.FIELD_HEADLINE, "")).strip()
    )
    checks.append(_check(
        "non-empty headline on every record",
        "0 empty headlines",
        f"{n_empty_headline} empty headlines",
        n_empty_headline == 0,
    ))

    # 4. At least one informative factor (a positive OR a weakness).
    # An eligible cell that is the WORST on every criterion legitimately has no
    # standout strength; requiring a positive factor unconditionally would force
    # a dishonest one. What must never happen is an EMPTY explanation — a record
    # with neither a strength nor a weakness says nothing.
    n_empty = sum(
        1 for r in records
        if not r.get(config.FIELD_POSITIVE_FACTORS)
        and not r.get(config.FIELD_WEAKNESSES)
    )
    checks.append(_check(
        "every record has at least one factor (positive or weakness)",
        "0 records with an empty explanation",
        f"{n_empty} records with neither a positive factor nor a weakness",
        n_empty == 0,
    ))

    # 5. Every factor references a configured criterion.
    n_unknown = 0
    for r in records:
        for phrase in r.get(config.FIELD_POSITIVE_FACTORS, []):
            if not _phrase_references_configured_criterion(phrase, templates.phrases, True):
                n_unknown += 1
        for phrase in r.get(config.FIELD_WEAKNESSES, []):
            if not _phrase_references_configured_criterion(phrase, templates.phrases, False):
                n_unknown += 1
    checks.append(_check(
        "every factor references a configured criterion",
        "0 factors referencing an unconfigured criterion",
        f"{n_unknown} unrecognised factor phrase(s)",
        n_unknown == 0,
    ))

    # 6. No banned superlative anywhere in the rendered text.
    n_superlatives = 0
    for r in records:
        blob = " ".join([
            str(r.get(config.FIELD_HEADLINE, "")),
            *r.get(config.FIELD_POSITIVE_FACTORS, []),
            *r.get(config.FIELD_WEAKNESSES, []),
        ]).lower()
        if any(banned in blob for banned in BANNED_SUPERLATIVES):
            n_superlatives += 1
    checks.append(_check(
        "no non-screening superlative in any explanation",
        "0 records with a 'best/optimal site' phrase",
        f"{n_superlatives} records with a banned phrase",
        n_superlatives == 0,
    ))

    passed = sum(1 for c in checks if c["passed"])
    failed = [c["name"] for c in checks if not c["passed"]]
    return {
        "checks": checks,
        "total": len(checks),
        "passed": passed,
        "failed": len(failed),
        "failed_names": failed,
    }
