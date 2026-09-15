"""
The data-quality read operation over the S2-02 Validation_Result (S2-08).

This module serves the frozen integrated dataset's Data_Quality_Status for the
Web_Application's data-quality banner. It holds NO validation logic: it does not
re-hash the baseline, re-check the input contract, or re-derive any verdict. It
reads the machine-readable S2-02 Validation_Result JSON the `validate` stage
already wrote (`pipeline/validate.py`,
`DATA/integration/metadata/integrated_input_validation.json`) and PROJECTS it
into the typed `DataQualityStatus` model the contract defines, carrying every
value through verbatim. This is the no-recompute structural guarantee
(CONTRACT.md §1, Requirement 2.4, 8.2): the `passed` verdict and each check
record served here are the validator's own, read from the fixed sidecar — there
is no arithmetic path by which they could differ from what S2-02 recorded.

`get_data_quality` is this operation. It mirrors the read-and-project discipline
of `results.py` and the fixed-artefact readers in `runs.py`
(`load_explanations`, `load_eligibility_table`): a required materialised engine
output that is missing or unreadable raises `EngineOutputError` NAMING the
missing input rather than fabricating a passing result (the HTTP layer maps this
to a 503, CONTRACT.md §6). "No silent passes": an absent Validation_Result is an
honest fault, never a green banner.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import config
from .models import DataQualityCheck, DataQualityStatus
from .runs import EngineOutputError


def _check_from_record(record: dict[str, Any]) -> DataQualityCheck:
    """
    Project one S2-02 Check_Record onto a ``DataQualityCheck`` VERBATIM.

    Reads the record's ``{name, expected, observed, passed}`` fields (keyed via
    the service config, never re-typed as literals) and carries each through
    unchanged. The non-``passed`` fields are stringified to match the frozen
    ``DataQualityCheck`` shape (CONTRACT.md §5) — the S2-02 validator writes
    them as human-readable expected/observed strings, so this is a faithful
    pass-through, not a coercion of a numeric verdict. ``passed`` is carried as
    a plain ``bool``. No check is dropped, so a failing check is surfaced rather
    than silently hidden (no silent passes).
    """
    return DataQualityCheck(
        name=str(record.get(config.VALIDATION_CHECK_NAME_KEY, "")),
        expected=str(record.get(config.VALIDATION_CHECK_EXPECTED_KEY, "")),
        observed=str(record.get(config.VALIDATION_CHECK_OBSERVED_KEY, "")),
        passed=bool(record.get(config.VALIDATION_CHECK_PASSED_KEY, False)),
    )


def get_data_quality() -> DataQualityStatus:
    """
    Return the frozen integrated dataset's Data_Quality_Status (CONTRACT.md §5,
    §6, Requirement 2.3, 2.4, 8.2).

    Reads the materialised S2-02 Validation_Result JSON sidecar
    (`config.VALIDATION_RESULT_PATH`, written by `pipeline/validate.py`) and
    PROJECTS it onto the ``DataQualityStatus`` model: the overall ``all_passed``
    verdict becomes ``passed`` and each ``{name, expected, observed, passed}``
    Check_Record becomes a ``DataQualityCheck``, carried through VERBATIM.

    NO VALIDATION. This function computes no data-quality check of its own — it
    neither re-hashes the baseline nor re-evaluates the input contract nor
    re-derives the verdict. The `passed` flag and every check record are the
    S2-02 validator's own, read from the fixed sidecar; there is no path by
    which the served status could differ from what `validate` recorded
    (Requirement 2.4, 8.2). Every check the record reports is surfaced, whether
    it passed or failed (no silent passes).

    The Validation_Result is a screening-level artefact shared across Runs (the
    input contract does not depend on the scoring weights), so — like the S2-06
    explanation output and the S2-03 Eligibility_Table — it is resolved once
    from its fixed location rather than per-Run.

    Returns
    -------
    DataQualityStatus
        The overall verdict plus the per-check records, carried through
        unchanged from the S2-02 Validation_Result.

    Raises
    ------
    EngineOutputError
        The Validation_Result sidecar is missing, unreadable, or not the
        expected object shape — the error NAMES the missing/unreadable input
        rather than fabricating a passing status (Requirement 7.3, CONTRACT.md
        §6; the HTTP layer maps this to a 503).
    """
    path = Path(config.VALIDATION_RESULT_PATH)
    if not path.exists():
        raise EngineOutputError(
            f"S2-02 Validation_Result is missing: {path}. Run "
            f"`python -m pipeline --only validate` to generate it before the "
            f"data-quality status can be served."
        )
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EngineOutputError(
            f"S2-02 Validation_Result {path} is unreadable: {exc}"
        ) from exc
    if not isinstance(result, dict):
        raise EngineOutputError(
            f"S2-02 Validation_Result {path} is not the expected object "
            f"(got {type(result).__name__}); it cannot be resolved into a "
            f"data-quality status."
        )

    raw_checks = result.get(config.VALIDATION_CHECKS_KEY, [])
    checks = [
        _check_from_record(record)
        for record in raw_checks
        if isinstance(record, dict)
    ]

    return DataQualityStatus(
        passed=bool(result.get(config.VALIDATION_ALL_PASSED_KEY, False)),
        checks=checks,
    )
