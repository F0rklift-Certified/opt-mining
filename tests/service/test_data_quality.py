"""
Tests for the S2-08 ``get_data_quality`` read operation
(``pipeline.service.data_quality``).

`get_data_quality` holds NO validation logic. It reads the machine-readable
S2-02 Validation_Result JSON the `validate` stage wrote
(`config.VALIDATION_RESULT_PATH`) and PROJECTS it onto the typed
``DataQualityStatus`` model, carrying the overall `all_passed` verdict and every
`{name, expected, observed, passed}` Check_Record through VERBATIM (CONTRACT.md
§1, §5, Requirement 2.4, 8.2). A missing/unreadable Validation_Result raises
``EngineOutputError`` naming the missing input rather than fabricating a passing
status — no silent passes (CONTRACT.md §6, the HTTP layer maps this to a 503).

These pin the pass-through and the honest-failure behaviour over a hand-written
Validation_Result JSON redirected into a temp file, so no built dataset is
required.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.service import config as service_config
from pipeline.service import get_data_quality
from pipeline.service.models import DataQualityCheck, DataQualityStatus
from pipeline.service.runs import EngineOutputError


@pytest.fixture
def validation_result(tmp_path, monkeypatch):
    """Redirect the service's Validation_Result path to a per-test temp file and
    return a writer that materialises a given JSON payload there."""
    path = tmp_path / "integrated_input_validation.json"
    monkeypatch.setattr(service_config, "VALIDATION_RESULT_PATH", path)

    def _write(payload) -> Path:
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    _write.path = path
    return _write


def test_passes_the_validation_json_through_unchanged(validation_result):
    """The overall verdict and every check record are carried through verbatim
    from the S2-02 record onto the DataQualityStatus (no recompute)."""
    validation_result(
        {
            "all_passed": True,
            "checks": [
                {
                    "name": "baseline_hash_match",
                    "expected": "sha256=abc123",
                    "observed": "sha256=abc123",
                    "passed": True,
                },
                {
                    "name": "row_count",
                    "expected": "== 12345",
                    "observed": "12345",
                    "passed": True,
                },
            ],
        }
    )

    status = get_data_quality()

    assert isinstance(status, DataQualityStatus)
    assert status.passed is True
    assert all(isinstance(c, DataQualityCheck) for c in status.checks)
    assert [c.name for c in status.checks] == ["baseline_hash_match", "row_count"]

    first = status.checks[0]
    assert first.expected == "sha256=abc123"
    assert first.observed == "sha256=abc123"
    assert first.passed is True

    # The projected status round-trips to exactly the S2-02 record shape (§5).
    assert status.to_dict() == {
        "passed": True,
        "checks": [
            {
                "name": "baseline_hash_match",
                "expected": "sha256=abc123",
                "observed": "sha256=abc123",
                "passed": True,
            },
            {
                "name": "row_count",
                "expected": "== 12345",
                "observed": "12345",
                "passed": True,
            },
        ],
    }


def test_failing_check_is_surfaced_not_hidden(validation_result):
    """No silent passes: a failing check and a False overall verdict are carried
    through, not dropped or coerced to a green banner."""
    validation_result(
        {
            "all_passed": False,
            "checks": [
                {
                    "name": "baseline_hash_match",
                    "expected": "sha256=abc123",
                    "observed": "sha256=def456",
                    "passed": False,
                },
            ],
        }
    )

    status = get_data_quality()

    assert status.passed is False
    assert len(status.checks) == 1
    assert status.checks[0].passed is False
    assert status.checks[0].observed == "sha256=def456"


def test_non_passed_fields_are_stringified_verbatim(validation_result):
    """The S2-02 non-`passed` fields are carried through as strings (faithful
    pass-through of the validator's own expected/observed forms)."""
    validation_result(
        {
            "all_passed": True,
            "checks": [
                {"name": "cell_count", "expected": 12345, "observed": 12345, "passed": True},
            ],
        }
    )

    status = get_data_quality()

    assert status.checks[0].expected == "12345"
    assert status.checks[0].observed == "12345"
    assert status.checks[0].passed is True


def test_missing_validation_result_raises_naming_the_input(tmp_path, monkeypatch):
    """An absent Validation_Result is an honest fault (EngineOutputError naming
    the missing input), never a fabricated passing status."""
    absent = tmp_path / "absent_validation.json"
    monkeypatch.setattr(service_config, "VALIDATION_RESULT_PATH", absent)

    with pytest.raises(EngineOutputError, match="Validation_Result is missing"):
        get_data_quality()


def test_unreadable_validation_result_raises_naming_the_input(validation_result):
    """A present-but-corrupt Validation_Result raises rather than passing."""
    validation_result.path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(EngineOutputError, match="unreadable"):
        get_data_quality()


def test_non_object_validation_result_raises(validation_result):
    """A Validation_Result that is not the expected object shape is a fault."""
    validation_result([1, 2, 3])

    with pytest.raises(EngineOutputError, match="not the expected object"):
        get_data_quality()
