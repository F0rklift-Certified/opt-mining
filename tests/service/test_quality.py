"""
Tests for the S2-08 ``get_data_quality`` Service_Operation
(``pipeline.service.quality``).

`get_data_quality` reads the S2-02 Validation_Result JSON sidecar the S2-02
validator (`pipeline/validate.py`) materialised and projects it VERBATIM into a
``DataQualityStatus``: the overall ``all_passed`` verdict and each
``{name, expected, observed, passed}`` Check_Record, carried through unchanged
(Requirement 1.6, 5.1). It performs no validation of its own — the
no-recompute guarantee (CONTRACT.md §1). A failed blocking check surfaces here
so the Web_Application can show a banner (Requirement 5.2), and a missing or
unreadable status fails HONESTLY rather than reporting a passing verdict
(Requirement 5.3, 7.3).

Two layers of coverage:

* Unit tests over a hand-written Validation_Result sidecar written to a temp
  path (the producing module's path constant monkeypatched), so the projection,
  the verdict pass-through, the failed-check surfacing and the honest-failure
  behaviour are pinned deterministically without running the validator.
* An engine-backed test that reconciles ``get_data_quality`` against the S2-02
  validator's own output on the frozen dataset, skipped when that output is
  absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import validate as validate_module
from pipeline.service import config as service_config
from pipeline.service import get_data_quality
from pipeline.service.models import DataQualityCheck, DataQualityStatus
from pipeline.service.runs import EngineOutputError


@pytest.fixture
def quality_sidecar(tmp_path, monkeypatch):
    """
    Redirect the S2-02 Validation_Result sidecar to a temp path.

    The service composes the sidecar path from the producing module's own
    constant (`pipeline.validate.DEFAULT_VALIDATION_RESULT_PATH`), so patching
    that constant exercises the real composition rather than a re-typed literal.
    Returns a writer that materialises a given Validation_Result object at that
    path (and a writer for raw bytes, for the unreadable-input case).
    """
    path = tmp_path / "integrated_input_validation.json"
    monkeypatch.setattr(
        validate_module, "DEFAULT_VALIDATION_RESULT_PATH", path, raising=True
    )

    def write(result: dict) -> Path:
        path.write_text(json.dumps(result), encoding="utf-8")
        return path

    write.path = path  # type: ignore[attr-defined]
    return write


def _result(all_passed: bool, checks: list[dict]) -> dict:
    """A minimal S2-02 Validation_Result object in the shape validate.py emits."""
    return {
        "generated_at_utc": "2026-01-01T00:00:00Z",
        "generator": "pipeline.validate",
        "baseline": {"artefact": "s1-08 integrated feature table"},
        "all_passed": all_passed,
        "n_checks": len(checks),
        "n_passed": sum(1 for c in checks if c["passed"]),
        "checks": checks,
    }


# --------------------------------------------------------------------------- #
# The projection — verdict + check records carried through verbatim.           #
# --------------------------------------------------------------------------- #


def test_surfaces_passing_status_verbatim(quality_sidecar):
    checks = [
        {"name": "Baseline hash matches the frozen reference",
         "expected": "sha256 == frozen reference", "observed": "match",
         "passed": True},
        {"name": "At least one Eligible_Cell", "expected": "≥ 1 eligible cell",
         "observed": "1,234 eligible cells", "passed": True},
    ]
    quality_sidecar(_result(True, checks))

    status = get_data_quality()

    assert isinstance(status, DataQualityStatus)
    assert status.passed is True
    assert all(isinstance(c, DataQualityCheck) for c in status.checks)
    # Each Check_Record is carried through unchanged, in the validator's order.
    assert [c.name for c in status.checks] == [c["name"] for c in checks]
    assert status.checks[0].expected == "sha256 == frozen reference"
    assert status.checks[0].observed == "match"
    assert status.checks[1].observed == "1,234 eligible cells"
    assert all(c.passed for c in status.checks)


def test_failed_check_is_surfaced_for_a_banner(quality_sidecar):
    """Requirement 5.2 — a failed blocking check surfaces so the UI can banner."""
    checks = [
        {"name": "Baseline hash matches the frozen reference",
         "expected": "sha256 == frozen reference", "observed": "DRIFTED",
         "passed": False},
        {"name": "Required columns present",
         "expected": "all present", "observed": "0 missing", "passed": True},
    ]
    quality_sidecar(_result(False, checks))

    status = get_data_quality()

    # The overall verdict reports the dataset failed a blocking check.
    assert status.passed is False
    # The specific failing check is retrievable (not hidden) — the banner can
    # name what failed.
    by_name = {c.name: c for c in status.checks}
    assert by_name["Baseline hash matches the frozen reference"].passed is False
    assert by_name["Baseline hash matches the frozen reference"].observed == "DRIFTED"
    # Passing checks are still surfaced too — no silent passes.
    assert by_name["Required columns present"].passed is True


def test_verdict_is_carried_through_not_rederived(quality_sidecar):
    """
    The `passed` verdict is the validator's own `all_passed`, not re-derived
    from the check records here (no-recompute, CONTRACT.md §1).

    A (contrived) sidecar whose `all_passed` disagrees with its checks proves
    the service reads the verdict verbatim rather than recomputing it.
    """
    checks = [
        {"name": "check A", "expected": "x", "observed": "x", "passed": True},
    ]
    # all_passed=False even though the only check passed — the service must
    # surface the recorded verdict, not recompute all(checks).
    quality_sidecar(_result(False, checks))

    status = get_data_quality()

    assert status.passed is False
    assert status.checks[0].passed is True


def test_empty_check_battery_is_surfaced(quality_sidecar):
    """
    An empty battery (absent table → validator's all_passed=False) is surfaced
    verbatim: a False verdict with no checks, never a fabricated pass.
    """
    quality_sidecar(_result(False, []))

    status = get_data_quality()

    assert status.passed is False
    assert status.checks == []


def test_to_dict_matches_contract_shape(quality_sidecar):
    """The serialised shape is CONTRACT.md §5 `DataQualityStatus`."""
    checks = [
        {"name": "check A", "expected": "e", "observed": "o", "passed": True},
    ]
    quality_sidecar(_result(True, checks))

    payload = get_data_quality().to_dict()

    assert payload == {
        "passed": True,
        "checks": [
            {"name": "check A", "expected": "e", "observed": "o", "passed": True},
        ],
    }


# --------------------------------------------------------------------------- #
# Honest failure — missing / unreadable status names the input (5.3, 7.3).     #
# --------------------------------------------------------------------------- #


def test_missing_status_raises_naming_the_input(tmp_path, monkeypatch):
    absent = tmp_path / "integrated_input_validation.json"
    monkeypatch.setattr(
        validate_module, "DEFAULT_VALIDATION_RESULT_PATH", absent, raising=True
    )

    with pytest.raises(EngineOutputError, match="Data_Quality_Status is missing"):
        get_data_quality()


def test_unreadable_status_raises_naming_the_input(quality_sidecar):
    quality_sidecar.path.write_text("{ not valid json", encoding="utf-8")

    with pytest.raises(EngineOutputError, match="unreadable"):
        get_data_quality()


def test_non_object_status_raises(quality_sidecar):
    quality_sidecar.path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(EngineOutputError, match="not the expected object"):
        get_data_quality()


# --------------------------------------------------------------------------- #
# The path is composed from the producing module (no re-typed literal).        #
# --------------------------------------------------------------------------- #


def test_path_is_composed_from_the_producing_config():
    """
    The served status path is `pipeline.validate.DEFAULT_VALIDATION_RESULT_PATH`
    — the producing module's own constant — so it can never drift from where the
    S2-02 validator writes it (holistic-project-awareness).
    """
    assert (
        service_config.data_quality_result_path()
        == validate_module.DEFAULT_VALIDATION_RESULT_PATH
    )


# --------------------------------------------------------------------------- #
# Against the real S2-02 validator output (Requirement 1.6, 5.1, 8.1).         #
# --------------------------------------------------------------------------- #


REAL_STATUS_PATH = validate_module.DEFAULT_VALIDATION_RESULT_PATH
REAL_STATUS_AVAILABLE = REAL_STATUS_PATH.exists()
requires_real_status = pytest.mark.skipif(
    not REAL_STATUS_AVAILABLE,
    reason=f"S2-02 validation result not materialised: {REAL_STATUS_PATH}",
)


@requires_real_status
def test_get_data_quality_reconciles_with_the_validator_output():
    """
    `get_data_quality` surfaces exactly the S2-02 validator's own verdict and
    check records for the frozen dataset (no recompute, Requirement 5.1).
    """
    raw = json.loads(REAL_STATUS_PATH.read_text(encoding="utf-8"))

    status = get_data_quality()

    assert status.passed == bool(raw["all_passed"])
    assert len(status.checks) == len(raw["checks"])
    for served, source in zip(status.checks, raw["checks"]):
        assert served.name == str(source["name"])
        assert served.expected == str(source["expected"])
        assert served.observed == str(source["observed"])
        assert served.passed == bool(source["passed"])
