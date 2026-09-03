"""
Anomaly & Sprint-2 issues collector for the S1-12 sanity-check stage (`sanity`).

This module owns the report's "Issues for Sprint 2" section. It defines the
frozen :class:`Anomaly` dataclass — the report-side record of a single
surprising or inconsistent result — and :func:`collect_issues`, which gathers
every anomaly the four plausibility checks surfaced into one ordered list for
the Validation_Report (Requirement 6).

The four checks in ``checks.py`` each expose their surfaced anomalies as a list
of dependency-free :class:`checks.CheckAnomaly` records (``check``,
``description``, ``kind``, ``investigation_note``). This module maps each
``CheckAnomaly`` — field for field — onto an :class:`Anomaly`. Keeping the
check-side record (``CheckAnomaly``) separate from the report-side record
(``Anomaly``) avoids a circular import between ``checks.py`` and this module
while keeping the two field sets identical, so the mapping is purely mechanical.

The stage is a REALITY CHECK, not a modelling step. An anomaly is either a
suspected DATA issue (an input looks wrong) or a legitimate MODEL result (the
model genuinely disagrees with the expectation); the check records which,
honestly, via ``kind`` (one of :data:`checks.ANOMALY_DATA_ISSUE` /
:data:`checks.ANOMALY_MODEL_RESULT`). Anomalies are recorded with their
investigation note, NEVER suppressed, and NEVER used to auto-adjust the model
(Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 8.2). This module reads only the
``anomalies`` field of each result and never touches the filesystem or mutates
its inputs.

Design reference: design.md §8 "Anomaly & Sprint-2 issues collector".
"""

from __future__ import annotations

from dataclasses import dataclass

from .checks import (
    ANOMALY_DATA_ISSUE,
    ANOMALY_MODEL_RESULT,
    CheckAnomaly,
)

# The two permitted anomaly kinds, re-exported from ``checks`` so this module is
# the single import site for the report layer (Requirements 6.4, 6.5).
__all__ = [
    "ANOMALY_DATA_ISSUE",
    "ANOMALY_MODEL_RESULT",
    "Anomaly",
    "collect_issues",
]

# The permitted values of ``Anomaly.kind`` (Requirements 6.4, 6.5).
_VALID_KINDS = frozenset({ANOMALY_DATA_ISSUE, ANOMALY_MODEL_RESULT})


@dataclass(frozen=True)
class Anomaly:
    """
    A single anomaly for the report's "Issues for Sprint 2" section.

    The report-side, immutable record of one surprising or inconsistent result
    surfaced by a check. It records the check that surfaced it, a description of
    what was observed, whether it is a suspected data issue or a legitimate
    model result (``kind``), and an investigation note on how to tell the two
    apart (Requirements 6.1, 6.3, 6.4, 6.5). Field names mirror
    :class:`checks.CheckAnomaly` one-for-one so :func:`collect_issues` maps a
    ``CheckAnomaly`` onto an ``Anomaly`` mechanically.

    ``kind`` MUST be one of :data:`checks.ANOMALY_DATA_ISSUE` /
    :data:`checks.ANOMALY_MODEL_RESULT`; any other value is a programming error
    and is rejected at construction rather than silently written into the
    report (6.4, 6.5).
    """

    check: str  # which check surfaced it, e.g. "Known Wind Farm Comparison"
    description: str  # what was observed that was surprising
    kind: str  # ANOMALY_DATA_ISSUE | ANOMALY_MODEL_RESULT (6.4, 6.5)
    investigation_note: str  # how to tell a data issue from a model result

    def __post_init__(self) -> None:
        if self.kind not in _VALID_KINDS:
            raise ValueError(
                f"Anomaly.kind must be one of {sorted(_VALID_KINDS)} "
                f"(data issue vs. legitimate model result); got {self.kind!r}."
            )


def collect_issues(*check_results) -> list[Anomaly]:
    """
    Gather every anomaly the four checks surfaced into one ordered list.

    Iterates the given check results in order, reads each result's
    ``anomalies`` list (a ``list[checks.CheckAnomaly]``), and maps every
    ``CheckAnomaly`` — field for field — onto an :class:`Anomaly` for the
    report's "Issues for Sprint 2" section. Each recorded Anomaly carries its
    description, the check that surfaced it, whether it is a suspected data
    issue or a legitimate model result, and its investigation note (Requirements
    6.1, 6.3, 6.4, 6.5).

    Every anomaly present on any input result is carried through: anomalies are
    NEVER suppressed and are NEVER used to auto-adjust the model — surprising
    results are documented honestly and, where systematic, carried forward as
    Sprint2_Issues rather than fixed ad hoc within this stage (6.2, 8.2). This
    function is PURE: it reads only the ``anomalies`` field of each result,
    mutates nothing, and touches no filesystem.

    Args:
        *check_results: the structured results of the four checks — any object
            exposing an ``anomalies`` attribute that is an iterable of
            :class:`checks.CheckAnomaly` (``WindFarmCheckResult``,
            ``ExclusionCheckResult``, ``SpotCheckResult``,
            ``DistributionCheckResult``). Results are processed in the order
            given, and each result's anomalies are appended in their own order,
            so the output order is deterministic.

    Returns:
        A list of :class:`Anomaly`, one per ``CheckAnomaly`` across all results,
        in the order the results were passed and the order they were recorded
        within each result. Empty when no check surfaced an anomaly.

    Raises:
        AttributeError: if a passed result has no ``anomalies`` attribute — a
            missing anomaly list is a programming error, never silently treated
            as "no issues".
        TypeError: if a passed result's ``anomalies`` is not iterable of
            ``CheckAnomaly`` records.
    """
    issues: list[Anomaly] = []

    for result in check_results:
        # A result with no anomalies attribute is a programming error, not
        # "no issues" — surface it rather than silently skipping (6.1).
        anomalies = result.anomalies
        for anomaly in anomalies:
            if not isinstance(anomaly, CheckAnomaly):
                raise TypeError(
                    "collect_issues expected a checks.CheckAnomaly in "
                    f"{type(result).__name__}.anomalies; got "
                    f"{type(anomaly).__name__}."
                )
            # Map the check-side record onto the report-side Anomaly, field for
            # field — nothing is suppressed, nothing is used to adjust the model
            # (6.2, 6.3, 6.4, 6.5, 8.2).
            issues.append(
                Anomaly(
                    check=anomaly.check,
                    description=anomaly.description,
                    kind=anomaly.kind,
                    investigation_note=anomaly.investigation_note,
                )
            )

    return issues
