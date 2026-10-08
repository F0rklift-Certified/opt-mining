"""
`get_data_quality` — the data-quality-surfacing Service_Operation (S2-08,
CONTRACT.md §4.6).

Surfaces the S2-02 Data_Quality_Status for the frozen integrated dataset so the
Web_Application can render a data-quality banner (Requirement 1.6, 5.1). The
operation reads the Validation_Result JSON sidecar the S2-02 validator
(`pipeline/validate.py`) materialised and PROJECTS it verbatim into the typed
``DataQualityStatus`` the contract defines — the overall ``all_passed`` verdict
and every ``{name, expected, observed, passed}`` Check_Record, carried through
UNCHANGED.

THE SERVICE PERFORMS NO VALIDATION. It re-runs no check and re-derives no
verdict; the status is the S2-02 validator's own (CONTRACT.md §1, Requirement 2).
This is what lets the Web_Application learn a blocking check failed so it can
show a banner (Requirement 5.2): a failing check is surfaced as
``check.passed == False`` and a failed dataset as ``status.passed == False``,
never hidden. Because the status is always retrievable here, a Run derived from
a failed dataset can never hide its failure — the failure is retrievable
independently of any Run (Requirement 5.3).

FAIL HONESTLY. When the Validation_Result sidecar is missing or unreadable, the
loader raises ``EngineOutputError`` naming the missing input rather than
fabricating a passing verdict (Requirement 5.3, 7.3): a missing data-quality
status is never silently reported as "passed".
"""

from __future__ import annotations

from .models import DataQualityCheck, DataQualityStatus
from .runs import load_validation_result


def get_data_quality() -> DataQualityStatus:
    """
    Return the S2-02 Data_Quality_Status for the frozen integrated dataset
    (CONTRACT.md §4.6, Requirement 1.6, 5.1, 5.2, 5.3).

    Reads the materialised S2-02 Validation_Result sidecar and projects it
    VERBATIM into a ``DataQualityStatus``: the overall ``all_passed`` verdict
    becomes ``passed``, and each ``{name, expected, observed, passed}``
    Check_Record becomes a ``DataQualityCheck``, in the validator's own order.
    Every check is surfaced — passing and failing alike — so there are no silent
    passes (CONTRACT.md §5).

    NO RECOMPUTE. This function performs no validation, re-runs no check and
    re-derives no verdict; the ``passed`` flag and the check records are the
    S2-02 validator's own, carried through unchanged (CONTRACT.md §1, Requirement
    2). A failed blocking check therefore surfaces here as a ``False`` verdict so
    the Web_Application can render a data-quality banner (Requirement 5.2), and
    the failure of a dataset a Run was derived from is always retrievable through
    this operation (Requirement 5.3).

    Returns
    -------
    DataQualityStatus
        ``passed`` — the S2-02 ``all_passed`` verdict — and ``checks`` — one
        ``DataQualityCheck`` per S2-02 Check_Record.

    Raises
    ------
    EngineOutputError
        The Validation_Result sidecar is missing or unreadable — the error names
        the missing input rather than fabricating a passing verdict (Requirement
        5.3, 7.3).
    """
    result = load_validation_result()

    # `all_passed` is the S2-02 overall verdict (the conjunction of every
    # input-contract Check_Record, with the baseline-hash match folded in as a
    # check). Read it verbatim; never re-derive it from the check records here.
    passed = bool(result.get("all_passed", False))

    checks = [
        DataQualityCheck(
            name=str(record.get("name", "")),
            expected=str(record.get("expected", "")),
            observed=str(record.get("observed", "")),
            passed=bool(record.get("passed", False)),
        )
        for record in result.get("checks", [])
        if isinstance(record, dict)
    ]

    return DataQualityStatus(passed=passed, checks=checks)
