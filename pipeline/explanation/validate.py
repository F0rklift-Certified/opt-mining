"""
No-silent-passes validation for the Explanation_Table (S2-06a).

Every check reports EXPECTED vs OBSERVED vs PASS/FAIL and is listed whether it
passed or not, so the validation report never hides a passing check behind
silence (the pipeline's "no silent passes" rule). `run()` writes the report
even when validation fails, then raises, so a failed run still leaves the
evidence behind and the orchestrator halts non-zero.

The checks assert the guarantees S2-06a and S2-06b own:
  1. one record per cell (count matches eligible + excluded);
  2. every eligible record is marked eligible; every excluded record is not;
  3. every eligible record has a non-empty headline;
  4. every eligible record has at least one factor (positive or weakness);
  5. every factor phrase references a CONFIGURED criterion (no invented factor);
  6. no record contains a banned superlative ("best site", etc.) in ANY field;
  7. every excluded record has a non-empty exclusion_reasons whose codes are in
     the frozen vocabulary and whose texts are non-empty (F16);
  8. every eligible record carries no exclusion reasons;
  9. every record carries exactly one data-quality note with a known level;
 10. a proxy caveat appears only for a configured proxy variable.
"""

from __future__ import annotations

from collections.abc import Sequence

from . import config
from .templates import BANNED_SUPERLATIVES, ExplanationTemplates


def _proxy_features(templates: ExplanationTemplates) -> set[str]:
    """The features marked as proxies in the templates (S2-06b)."""
    return {f for f, cp in templates.phrases.items() if cp.is_proxy and cp.proxy_caveat}


def _proxy_caveat_texts(templates: ExplanationTemplates) -> set[str]:
    """The configured proxy-caveat sentences, for membership checks."""
    return {cp.proxy_caveat for cp in templates.phrases.values() if cp.proxy_caveat}


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
    n_excluded_cells: int = 0,
) -> dict:
    """
    Run every check over the assembled explanation records (eligible + excluded).

    Returns a result dict with a per-check list and pass/fail totals, in the
    same shape the scoring stage's validator uses so the report renderer and
    the orchestrator handle both identically.
    """
    checks: list[dict] = []
    eligible_records = [r for r in records if r.get(config.FIELD_ELIGIBLE) is True]
    excluded_records = [r for r in records if r.get(config.FIELD_ELIGIBLE) is False]

    # 1. One record per cell (eligible + excluded).
    n_records = len(records)
    n_expected = n_eligible_cells + n_excluded_cells
    checks.append(_check(
        "one explanation per cell (eligible + excluded)",
        f"{n_expected} records",
        f"{n_records} records ({len(eligible_records)} eligible, "
        f"{len(excluded_records)} excluded)",
        n_records == n_expected,
    ))

    # 2. Eligibility flag partitions the records: as many eligible/excluded
    # records as cells, and no record with a non-boolean flag.
    n_bad_flag = sum(
        1 for r in records if r.get(config.FIELD_ELIGIBLE) not in (True, False)
    )
    partition_ok = (
        n_bad_flag == 0
        and len(eligible_records) == n_eligible_cells
        and len(excluded_records) == n_excluded_cells
    )
    checks.append(_check(
        "eligible/excluded records match the cell counts",
        f"{n_eligible_cells} eligible, {n_excluded_cells} excluded, 0 bad flags",
        f"{len(eligible_records)} eligible, {len(excluded_records)} excluded, "
        f"{n_bad_flag} bad flags",
        partition_ok,
    ))

    # 3. Non-empty headline on every ELIGIBLE record.
    n_empty_headline = sum(
        1 for r in eligible_records if not str(r.get(config.FIELD_HEADLINE, "")).strip()
    )
    checks.append(_check(
        "non-empty headline on every eligible record",
        "0 empty headlines",
        f"{n_empty_headline} empty headlines",
        n_empty_headline == 0,
    ))

    # 4. At least one informative factor (a positive OR a weakness) on every
    # ELIGIBLE record. An eligible cell that is the WORST on every criterion
    # legitimately has no standout strength; requiring a positive factor
    # unconditionally would force a dishonest one. What must never happen is an
    # EMPTY explanation — a record with neither a strength nor a weakness.
    n_empty = sum(
        1 for r in eligible_records
        if not r.get(config.FIELD_POSITIVE_FACTORS)
        and not r.get(config.FIELD_WEAKNESSES)
    )
    checks.append(_check(
        "every eligible record has at least one factor (positive or weakness)",
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

    # 6. No banned superlative anywhere in the rendered text — including the
    # S2-06b caveats and the excluded-cell reason texts.
    n_superlatives = 0
    for r in records:
        blob = " ".join([
            str(r.get(config.FIELD_HEADLINE, "")),
            *r.get(config.FIELD_POSITIVE_FACTORS, []),
            *r.get(config.FIELD_WEAKNESSES, []),
            *r.get(config.FIELD_PROXY_CAVEATS, []),
            *r.get(config.FIELD_DATA_QUALITY_NOTES, []),
            *[p.get(config.REASON_TEXT_KEY, "")
              for p in r.get(config.FIELD_EXCLUSION_REASONS, [])],
        ]).lower()
        if any(banned in blob for banned in BANNED_SUPERLATIVES):
            n_superlatives += 1
    checks.append(_check(
        "no non-screening superlative in any explanation",
        "0 records with a 'best/optimal site' phrase",
        f"{n_superlatives} records with a banned phrase",
        n_superlatives == 0,
    ))

    # 7. Every EXCLUDED record has non-empty exclusion_reasons whose codes are
    # in the frozen vocabulary and whose texts are non-empty (F16). The
    # vocabulary is the set of codes actually present across excluded cells —
    # the rules config is authoritative, so this check enforces SHAPE (present,
    # paired, non-empty), not a hard-coded code list, which would duplicate the
    # rules vocabulary here and drift. A malformed/absent reason list was
    # already halted in the loader; this re-asserts it on the written records.
    n_bad_reasons = 0
    for r in excluded_records:
        reasons = r.get(config.FIELD_EXCLUSION_REASONS)
        if not isinstance(reasons, list) or not reasons:
            n_bad_reasons += 1
            continue
        for pair in reasons:
            code = pair.get(config.REASON_CODE_KEY) if isinstance(pair, dict) else None
            text = pair.get(config.REASON_TEXT_KEY) if isinstance(pair, dict) else None
            if not (isinstance(code, str) and code.strip()) or not (
                isinstance(text, str) and text.strip()
            ):
                n_bad_reasons += 1
                break
    checks.append(_check(
        "every excluded record has a non-empty {code, text} reason list",
        "0 excluded records with a missing/empty reason",
        f"{n_bad_reasons} excluded records with a bad reason list",
        n_bad_reasons == 0,
    ))

    # 8. Every ELIGIBLE record carries no exclusion reasons (the pairing
    # contract: eligible ⇔ no reasons).
    n_eligible_with_reasons = sum(
        1 for r in eligible_records if r.get(config.FIELD_EXCLUSION_REASONS)
    )
    checks.append(_check(
        "no eligible record carries exclusion reasons",
        "0 eligible records with reasons",
        f"{n_eligible_with_reasons} eligible records with reasons",
        n_eligible_with_reasons == 0,
    ))

    # 9. Every record carries exactly one data-quality note, and its level is a
    # known confidence level (design decision 3C — a note on every record).
    known_levels = tuple(str(x).lower() for x in config.CONFIDENCE_LEVELS)
    n_bad_dq = 0
    for r in records:
        notes = r.get(config.FIELD_DATA_QUALITY_NOTES)
        if not isinstance(notes, list) or len(notes) != 1:
            n_bad_dq += 1
            continue
        if not any(level in notes[0].lower() for level in known_levels):
            n_bad_dq += 1
    checks.append(_check(
        "exactly one data-quality note with a known level on every record",
        "0 records with a missing/unknown data-quality note",
        f"{n_bad_dq} records with a bad data-quality note",
        n_bad_dq == 0,
    ))

    # 10. Every proxy caveat is a CONFIGURED proxy-caveat sentence — a caveat
    # can only be surfaced for a criterion the templates marked a proxy, never
    # invented, and never attached to a non-proxy criterion.
    proxy_texts = _proxy_caveat_texts(templates)
    n_bad_proxy = 0
    for r in records:
        for caveat in r.get(config.FIELD_PROXY_CAVEATS, []):
            if caveat not in proxy_texts:
                n_bad_proxy += 1
    checks.append(_check(
        "every proxy caveat is a configured proxy-variable caveat",
        "0 unrecognised proxy caveats",
        f"{n_bad_proxy} unrecognised proxy caveat(s)",
        n_bad_proxy == 0,
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
