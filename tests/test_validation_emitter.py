"""
Unit tests for the S2-02 Validation_Result / Validation_Report emitter
(``pipeline.validate`` task 6.1; test task 6.2).

These pin the pure result/report writers — ``build_validation_result``,
``write_validation_result``, ``render_validation_report``,
``write_validation_report`` and the ``write_validation_outputs`` convenience
seam — against their requirements, without ever touching the real
``DATA/integration/metadata`` directory:

  * ``all_passed`` is the conjunction of every Check_Record's ``passed``
    (``True`` for an all-pass battery, ``False`` if any fails, ``False`` for an
    empty battery), and ``n_passed`` / ``n_checks`` are correct (10.2, 10.3);
  * the JSON sidecar round-trips — ``json.loads`` of the written file equals the
    in-memory Validation_Result object (13.5);
  * the Validation_Report carries ``banner("validate")`` as its first content
    (10.6) and contains the expected/observed/result markdown table, and is
    phrased in Screening_Language — "preliminary screening", never "best site"
    (8A.1, 10.6, 13.6);
  * both output files are written even when the checks list is empty (10.4A).

Hermeticity: every writer accepts a ``meta_dir`` override, resolved at call
time. Each test passes ``tmp_path`` (or a subdirectory of it) so the real
project metadata directory is never written; no monkeypatching of module
constants is needed for the writes.

Requirements: 8A.1, 10.2, 10.3, 10.4A, 10.6, 13.5, 13.6.
"""

from __future__ import annotations

import json
import re

from pipeline import validate
from pipeline.common.geo import banner


def _asserts_no_best_site_claim(report_text: str) -> None:
    """
    Screening_Language guard (8A.1, 13.6): the report must never *present* model
    output as a "best site". The Screening_Language purpose sentence disclaims
    the term explicitly (``… never a "best site"``), so a bare substring ban is
    wrong — a legitimate negation contains the words. Instead assert that every
    occurrence of the phrase is a negation (preceded by "never"/"not"), i.e.
    there is no positive best-site claim anywhere in the report.
    """
    lowered = report_text.lower()
    for match in re.finditer(r'"?best site"?', lowered):
        preceding = lowered[max(0, match.start() - 20):match.start()]
        assert re.search(r"\b(never|not|no)\b", preceding), (
            f"report presents a 'best site' claim without a negation: "
            f"...{lowered[max(0, match.start() - 20):match.end() + 5]}..."
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check(name: str, expected: str, observed: str, passed: bool) -> dict:
    """A Check_Record in the exact {name, expected, observed, passed} shape."""
    return {"name": name, "expected": expected, "observed": observed,
            "passed": passed}


def _baseline() -> dict:
    """
    A minimal but shape-faithful baseline record (design Model 1 + the per-run
    verify fields), built as a plain dict so these tests are independent of the
    real S1-08 table and of ``freeze_baseline``.
    """
    return {
        "artefact": "s1-08 integrated feature table",
        "path": "DATA/integration/optmining_integrated-features_2026_nsw.gpkg",
        "layer": "integrated_features",
        "version": "2026",
        "sha256": "a" * 64,
        "bytes": 12345,
        "bytes_human": "12.3 KB",
        "storage_crs": "EPSG:4326",
        "computation_crs": "EPSG:3577",
        "frozen_at_utc": "2026-01-01T00:00:00+00:00",
        "frozen_by": "pipeline.validate.freeze_baseline",
        "verified_at_utc": "2026-01-02T00:00:00+00:00",
        "hash_ok": True,
    }


# ---------------------------------------------------------------------------
# all_passed conjunction, n_passed / n_checks (10.2, 10.3)
# ---------------------------------------------------------------------------


class TestVerdictConjunction:
    def test_all_pass_yields_all_passed_true(self):
        checks = [
            _check("a", "0", "0", True),
            _check("b", "0", "0", True),
            _check("c", "0", "0", True),
        ]
        result = validate.build_validation_result(_baseline(), checks)

        assert result["all_passed"] is True
        assert result["n_checks"] == 3
        assert result["n_passed"] == 3

    def test_one_failing_flips_all_passed_false(self):
        checks = [
            _check("a", "0", "0", True),
            _check("b", "0", "1", False),
            _check("c", "0", "0", True),
        ]
        result = validate.build_validation_result(_baseline(), checks)

        assert result["all_passed"] is False
        assert result["n_checks"] == 3
        assert result["n_passed"] == 2

    def test_mixed_battery_counts_are_correct(self):
        checks = [
            _check("a", "0", "0", True),
            _check("b", "0", "1", False),
            _check("c", "0", "0", True),
            _check("d", "0", "2", False),
            _check("e", "0", "0", True),
        ]
        result = validate.build_validation_result(_baseline(), checks)

        # Conjunction over the battery: any failure → False.
        assert result["all_passed"] is False
        assert result["all_passed"] == all(c["passed"] for c in checks)
        assert result["n_checks"] == 5
        assert result["n_passed"] == 3

    def test_empty_battery_is_all_passed_false(self):
        # An empty battery means nothing was verified — the gate forbids the
        # vacuous all([]) == True silent pass (4A.1 → 10.4A, 8.3).
        result = validate.build_validation_result(_baseline(), [])

        assert result["all_passed"] is False
        assert result["n_checks"] == 0
        assert result["n_passed"] == 0

    def test_passed_is_coerced_to_plain_bool(self):
        # A truthy/falsey non-bool passed value is normalised to a JSON-clean
        # bool so the emitted result cannot carry incidental types.
        checks = [_check("a", "0", "0", 1), _check("b", "0", "0", 0)]
        result = validate.build_validation_result(_baseline(), checks)

        assert result["checks"][0]["passed"] is True
        assert result["checks"][1]["passed"] is False
        assert result["all_passed"] is False
        assert result["n_passed"] == 1


# ---------------------------------------------------------------------------
# JSON sidecar round-trip (13.5)
# ---------------------------------------------------------------------------


class TestJsonRoundTrip:
    def test_written_json_loads_back_equal(self, tmp_path):
        checks = [
            _check("a", "0", "0", True),
            _check("b", "0", "1", False),
        ]
        result = validate.build_validation_result(_baseline(), checks)

        out_path = validate.write_validation_result(result, meta_dir=tmp_path)

        assert out_path == tmp_path / validate.VALIDATION_RESULT_FILENAME
        assert out_path.exists()

        loaded = json.loads(out_path.read_text())
        assert loaded == result

    def test_round_trip_via_write_validation_outputs(self, tmp_path):
        checks = [_check("a", "0", "0", True)]

        result, json_path, report_path = validate.write_validation_outputs(
            _baseline(), checks, meta_dir=tmp_path
        )

        assert json.loads(json_path.read_text()) == result
        assert report_path.exists()


# ---------------------------------------------------------------------------
# Report: banner-first, table present, Screening_Language (8A.1, 10.6, 13.6)
# ---------------------------------------------------------------------------


class TestReportRendering:
    def test_banner_is_first_content(self):
        result = validate.build_validation_result(
            _baseline(), [_check("a", "0", "0", True)]
        )
        report = validate.render_validation_report(result)

        # banner("validate") is the FIRST content of the report (10.6). The
        # banner itself ends in a newline, so the rendered report starts with
        # the banner's stripped first line.
        first_line = report.splitlines()[0]
        assert first_line == banner("validate").splitlines()[0]
        # Sanity: the do-not-edit marker and the generator are present up front.
        assert first_line.startswith("*Generated by `pipeline.validate`")
        assert "Do not edit by hand." in first_line

    def test_table_header_present_when_checks_nonempty(self):
        checks = [
            _check("Required columns present", "all present", "0 missing", True),
            _check("cell_id unique", "0 duplicates", "0 duplicates", True),
        ]
        result = validate.build_validation_result(_baseline(), checks)
        report = validate.render_validation_report(result)

        assert "| Check | Expected | Observed | Result |" in report
        assert "| --- | --- | --- | --- |" in report
        # Each Check_Record renders a row with a PASS/FAIL result cell.
        assert "Required columns present" in report
        assert "PASS" in report

    def test_failing_check_renders_fail_cell(self):
        checks = [_check("cell_id unique", "0 duplicates", "3 duplicates", False)]
        result = validate.build_validation_result(_baseline(), checks)
        report = validate.render_validation_report(result)

        assert "| FAIL |" in report
        assert "**Result:** FAIL" in report

    def test_screening_language_no_best_site_claim(self):
        result = validate.build_validation_result(
            _baseline(), [_check("a", "0", "0", True)]
        )
        report = validate.render_validation_report(result)

        # Screening_Language: a preliminary-screening phrase IS present, and no
        # positive "best site" claim appears anywhere (8A.1, 13.6).
        assert "preliminary screening" in report.lower()
        _asserts_no_best_site_claim(report)


# ---------------------------------------------------------------------------
# Both files written even for an empty battery (10.4A)
# ---------------------------------------------------------------------------


class TestEmptyBatteryWritesBothFiles:
    def test_empty_checks_writes_json_and_report(self, tmp_path):
        result, json_path, report_path = validate.write_validation_outputs(
            _baseline(), [], meta_dir=tmp_path
        )

        # BOTH output files exist even though zero checks executed.
        assert json_path.exists(), "JSON sidecar was not written for empty battery"
        assert report_path.exists(), "Report was not written for empty battery"
        assert json_path == tmp_path / validate.VALIDATION_RESULT_FILENAME
        assert report_path == tmp_path / validate.VALIDATION_REPORT_FILENAME

        # The written JSON reports a failing, zero-check verdict (not a silent
        # vacuous pass).
        loaded = json.loads(json_path.read_text())
        assert loaded["all_passed"] is False
        assert loaded["n_checks"] == 0
        assert loaded["n_passed"] == 0

        # The empty-battery report still leads with the banner and phrases its
        # purpose in Screening_Language.
        report_text = report_path.read_text()
        assert report_text.splitlines()[0] == banner("validate").splitlines()[0]
        assert "preliminary screening" in report_text.lower()
        _asserts_no_best_site_claim(report_text)
