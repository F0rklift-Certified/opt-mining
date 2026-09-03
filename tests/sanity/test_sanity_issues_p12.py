"""Property test for the S1-12 sanity-check Sprint-2 issues collector.

# Feature: s1-12-validation-sanity-check, Property 12: Surprising results are recorded honestly as Sprint-2 issues

Property 12: Surprising results are recorded honestly as Sprint-2 issues
    A surprising / failing result is recorded with a data-issue / model-result
    investigation note, not suppressed, and where systematic logged as a
    Sprint2_Issue rather than fixed ad hoc.

Validates: Requirements 6.1, 6.3, 6.4, 6.5

``issues.collect_issues`` gathers every anomaly the four checks surfaced into
one ordered list for the report's "Issues for Sprint 2" section. Each result is
any object exposing an ``anomalies`` list of ``checks.CheckAnomaly`` records;
``collect_issues`` maps each ``CheckAnomaly`` — field for field — onto a frozen
``issues.Anomaly`` and NEVER drops one.

The test builds synthetic result-like objects each holding an arbitrary number
of ``CheckAnomaly`` records of either kind (``data_issue`` / ``model_result``)
and asserts:
  * exactly one ``Anomaly`` per input ``CheckAnomaly`` (nothing suppressed);
  * every field (check / description / kind / investigation_note) preserved;
  * every emitted ``Anomaly.kind`` is a valid data-issue / model-result value;
  * ordering is preserved across results and within each result;
  * an invalid ``kind`` is rejected rather than silently written to the report.
"""

from dataclasses import dataclass

from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.sanity.checks import (
    ANOMALY_DATA_ISSUE,
    ANOMALY_MODEL_RESULT,
    CheckAnomaly,
)
from pipeline.sanity.issues import Anomaly, collect_issues

# The two permitted anomaly kinds.
_VALID_KINDS = (ANOMALY_DATA_ISSUE, ANOMALY_MODEL_RESULT)


@dataclass
class _FakeResult:
    """A minimal stand-in for a check result: any object with ``.anomalies``.

    ``collect_issues`` reads only the ``anomalies`` attribute, so this is a
    faithful synthetic substitute for the four real check-result dataclasses
    (``WindFarmCheckResult`` / ``ExclusionCheckResult`` / ``SpotCheckResult`` /
    ``DistributionCheckResult``) without depending on their construction.
    """

    anomalies: list


# A single CheckAnomaly with arbitrary text fields and a valid kind.
_check_anomaly = st.builds(
    CheckAnomaly,
    check=st.text(min_size=0, max_size=40),
    description=st.text(min_size=0, max_size=80),
    kind=st.sampled_from(_VALID_KINDS),
    investigation_note=st.text(min_size=0, max_size=80),
)

# A single result holding an arbitrary number of anomalies (including zero).
_fake_result = st.builds(
    _FakeResult,
    anomalies=st.lists(_check_anomaly, min_size=0, max_size=6),
)


@settings(max_examples=200, deadline=None)
@given(results=st.lists(_fake_result, min_size=0, max_size=5))
def test_property_12_surprising_results_recorded_honestly(results):
    collected = collect_issues(*results)

    # The flat, ordered expectation: every CheckAnomaly across every result, in
    # the order the results were passed and the order recorded within each.
    expected = [a for result in results for a in result.anomalies]

    # --- Nothing suppressed: exactly one Anomaly per input CheckAnomaly. ---
    assert len(collected) == len(expected)

    for produced, source in zip(collected, expected):
        # --- Every field mapped one-for-one, nothing lost or rewritten. ---
        assert isinstance(produced, Anomaly)
        assert produced.check == source.check
        assert produced.description == source.description
        assert produced.kind == source.kind
        assert produced.investigation_note == source.investigation_note

        # --- Each recorded kind is a valid data-issue / model-result value. ---
        assert produced.kind in _VALID_KINDS

    # --- Ordering is preserved across results (kinds line up in sequence). ---
    assert [a.kind for a in collected] == [a.kind for a in expected]


@settings(max_examples=100, deadline=None)
@given(
    bad_kind=st.text(min_size=1, max_size=20).filter(lambda k: k not in _VALID_KINDS),
    check=st.text(min_size=0, max_size=40),
    description=st.text(min_size=0, max_size=80),
    note=st.text(min_size=0, max_size=80),
)
def test_property_12_invalid_kind_is_rejected(bad_kind, check, description, note):
    # A CheckAnomaly can carry an out-of-range kind (it does not validate), but
    # collect_issues must refuse to write it into the report as an Anomaly
    # rather than silently emitting an invalid data-issue/model-result value.
    bad_anomaly = CheckAnomaly(
        check=check,
        description=description,
        kind=bad_kind,
        investigation_note=note,
    )
    result = _FakeResult(anomalies=[bad_anomaly])

    try:
        collect_issues(result)
    except ValueError:
        pass
    else:
        raise AssertionError(
            f"collect_issues accepted an invalid Anomaly.kind {bad_kind!r}"
        )
