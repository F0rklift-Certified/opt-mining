"""
Integration tests for the S2-02 ``pipeline.validate.run()`` input-contract
contract (task 7.2).

These exercise the *wired* gate end-to-end through the uniform stage entry
point ``run(verbose=False, skip_land_sea=False, max_slope=15.0,
integrated_path=None) -> dict``, asserting the new return keys and the
pure-reporter behaviour without ever touching the real
``DATA/integration/metadata`` directory:

  * a good fixture (with its baseline frozen first) yields a results dict
    carrying ``baseline``, ``integrated_input_checks`` (non-empty),
    ``integrated_input_result`` (a JSON sidecar path that exists on disk) and
    ``all_passed=True`` (10.1, 11.2);
  * a known-bad fixture yields ``all_passed=False`` and ``run()`` does not raise
    — it stays a pure reporter (9.1, 9.2), and the sidecar is still written;
  * the input-contract checks are ordered before the wind/scoring/shortlist
    cross-checks — asserted both structurally (the key is present) and via the
    printed progress lines: the "[0/2] Integrated-input contract checks" line
    precedes the "[1/2] Cross-domain" line (11.3);
  * a missing table yields ``integrated_input_checks == []`` + ``all_passed
    False`` with BOTH the JSON sidecar and the ``.md`` report still written
    (8.3, 11.3, 11.4).

Hermeticity — TWO redirections are required, both read inside ``run()``'s call
graph at call time (never bound as default arguments):

  1. ``pipeline.validate.INTEGRATION_META_DIR`` — ``run()`` calls
     ``write_validation_outputs(baseline, checks)`` with NO ``meta_dir``
     override, and the writers resolve their directory as
     ``INTEGRATION_META_DIR if meta_dir is None else meta_dir`` at call time.
     Patching this module constant redirects run()'s JSON + report writes into
     ``tmp_path`` so the real metadata directory is never polluted.
  2. ``pipeline.validate.DEFAULT_BASELINE_MANIFEST_PATH`` — check 1 (baseline
     hash) calls ``freeze_baseline(path)`` in verify mode, which reads (and, in
     the good-fixture freeze step, writes) this manifest path. Patching it to a
     ``tmp_path`` location keeps the freeze/verify hermetic and lets the good
     fixture pass its hash check after a ``write=True`` freeze over the same
     file.

``skip_land_sea=True`` avoids the land-mask assessment's network access. The
wind/scoring/shortlist cross-checks may or may not find real inputs on a dev
machine; those results do not affect ``all_passed`` (which is the
input-contract verdict alone), so these tests never assert on their content.

Requirements: 8.3, 9.1, 9.2, 10.1, 11.2, 11.3, 11.4.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline import validate

from tests.integration.integrated_fixtures import (
    duplicate_cell_id,
    make_integrated_fixture,
    write_fixture_gpkg,
)


@pytest.fixture
def redirected_meta(monkeypatch, tmp_path) -> Path:
    """
    Redirect BOTH the Validation_Result/Report metadata directory and the
    Baseline_Manifest path into ``tmp_path`` so ``run()`` never writes to the
    real ``DATA/integration/metadata``.

    ``run()`` -> ``write_validation_outputs`` -> ``write_validation_result`` /
    ``write_validation_report`` resolve ``INTEGRATION_META_DIR`` at call time
    (``meta_dir`` defaults to ``None``), so patching the module attribute is
    sufficient. ``freeze_baseline`` reads ``DEFAULT_BASELINE_MANIFEST_PATH``
    inside its body, so patching that attribute redirects the manifest too.

    Returns the redirected metadata directory so tests can assert on the
    written sidecar / report.
    """
    meta_dir = tmp_path / "integration_meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(validate, "INTEGRATION_META_DIR", meta_dir, raising=True)
    monkeypatch.setattr(
        validate,
        "DEFAULT_BASELINE_MANIFEST_PATH",
        meta_dir / validate.BASELINE_MANIFEST_FILENAME,
        raising=True,
    )
    return meta_dir


@pytest.fixture
def good_gpkg(tmp_path) -> Path:
    """A valid integrated-table GeoPackage written to a temp file."""
    return write_fixture_gpkg(make_integrated_fixture(), tmp_path, name="good.gpkg")


def _real_metadata_dir() -> Path:
    """The real DATA/integration/metadata dir, used only to assert non-pollution."""
    from pipeline.integration import config as integration_config

    return integration_config.INTEGRATION_META_DIR


def _snapshot_real_metadata() -> set[str]:
    real = _real_metadata_dir()
    if not real.exists():
        return set()
    return {p.name for p in real.iterdir()}


# ---------------------------------------------------------------------------
# 1. Good fixture — the full contract passes and the sidecar is written
# ---------------------------------------------------------------------------


class TestGoodFixtureContract:
    def test_run_over_good_fixture_all_passed_true(self, redirected_meta, good_gpkg):
        # Freeze the baseline over the SAME good file first, so check 1
        # (baseline hash matches) passes when run() verifies it.
        validate.freeze_baseline(good_gpkg, write=True)

        results = validate.run(integrated_path=good_gpkg, skip_land_sea=True)

        # The new S2-02 return keys are all present (10.1, 11.2).
        assert "baseline" in results
        assert "integrated_input_checks" in results
        assert "integrated_input_result" in results
        assert "all_passed" in results

        # A present table produces a non-empty battery (no silent pass).
        checks = results["integrated_input_checks"]
        assert isinstance(checks, list) and len(checks) > 0

        # The verdict is True: every input-contract check passed AND the
        # baseline hash matched.
        assert results["all_passed"] is True

        # integrated_input_result is a real written path on disk (the JSON
        # sidecar), inside the redirected metadata dir.
        sidecar = results["integrated_input_result"]
        assert isinstance(sidecar, Path)
        assert sidecar.exists()
        assert sidecar.parent == redirected_meta
        assert sidecar.name == validate.VALIDATION_RESULT_FILENAME

        # The sidecar JSON agrees with the returned verdict and round-trips.
        loaded = json.loads(sidecar.read_text())
        assert loaded["all_passed"] is True
        assert loaded["n_checks"] == len(checks)
        assert loaded["n_passed"] == sum(1 for c in checks if c["passed"])

        # The baseline record carries the hash-match verdict.
        assert results["baseline"]["hash_ok"] is True

    def test_good_fixture_does_not_pollute_real_metadata(
        self, redirected_meta, good_gpkg
    ):
        before = _snapshot_real_metadata()
        validate.freeze_baseline(good_gpkg, write=True)
        validate.run(integrated_path=good_gpkg, skip_land_sea=True)
        after = _snapshot_real_metadata()

        # run() must not have written the S2-02 artefacts into the real dir.
        assert after == before
        real = _real_metadata_dir()
        assert not (real / validate.VALIDATION_RESULT_FILENAME).exists() or (
            validate.VALIDATION_RESULT_FILENAME in before
        )


# ---------------------------------------------------------------------------
# 2. Known-bad fixture — all_passed False, run() does not raise
# ---------------------------------------------------------------------------


class TestBadFixtureContract:
    def test_run_over_bad_fixture_all_passed_false_and_no_raise(
        self, redirected_meta, tmp_path
    ):
        # A duplicate cell_id is an input-contract defect (fails check 5).
        bad = duplicate_cell_id(make_integrated_fixture())
        bad_gpkg = write_fixture_gpkg(bad, tmp_path, name="bad.gpkg")

        # Freeze the baseline over the bad file so check 1 (hash) passes and the
        # only failing check is the injected defect — proving all_passed=False
        # comes from the data-quality failure, not from Hash_Drift.
        validate.freeze_baseline(bad_gpkg, write=True)

        # run() must NOT raise on a data-quality failure — it is a pure
        # reporter. If it returns, it did not raise.
        results = validate.run(integrated_path=bad_gpkg, skip_land_sea=True)

        assert results["all_passed"] is False

        # The sidecar was still written (a failing verdict is reported, not
        # thrown).
        sidecar = results["integrated_input_result"]
        assert sidecar.exists()
        loaded = json.loads(sidecar.read_text())
        assert loaded["all_passed"] is False

        # At least the cell_id-uniqueness check flipped to False.
        checks = results["integrated_input_checks"]
        unique_check = next(
            c for c in checks if c["name"] == "cell_id unique"
        )
        assert unique_check["passed"] is False


# ---------------------------------------------------------------------------
# 3. Ordering — input-contract checks run before the other cross-checks
# ---------------------------------------------------------------------------


class TestOrdering:
    def test_input_checks_run_before_cross_checks(
        self, redirected_meta, good_gpkg, capsys
    ):
        validate.freeze_baseline(good_gpkg, write=True)

        results = validate.run(integrated_path=good_gpkg, skip_land_sea=True)

        # Structural: the input-contract key is present in the results dict.
        assert "integrated_input_checks" in results

        # Behavioural: the progress lines confirm the input-contract gate is
        # emitted before the cross-domain wind checks (requirement 11.3).
        out = capsys.readouterr().out
        idx_input = out.find("[0/2] Integrated-input contract checks")
        idx_cross = out.find("[1/2] Cross-domain")
        assert idx_input != -1, "input-contract progress line not printed"
        assert idx_cross != -1, "cross-domain progress line not printed"
        assert idx_input < idx_cross, (
            "input-contract checks must run before the cross-domain checks"
        )


# ---------------------------------------------------------------------------
# 4. Missing table — [] checks + all_passed False, both output files written
# ---------------------------------------------------------------------------


class TestMissingTable:
    def test_missing_table_empty_checks_and_outputs_written(
        self, redirected_meta, tmp_path
    ):
        missing = tmp_path / "nonexistent.gpkg"
        assert not missing.exists()

        results = validate.run(integrated_path=missing, skip_land_sea=True)

        # A missing table yields an empty battery and a failing verdict as a
        # single combined operation — never a silent vacuous pass (8.3).
        assert results["integrated_input_checks"] == []
        assert results["all_passed"] is False

        # BOTH output files are still written into the redirected metadata dir
        # (requirement 10.4A carried through run()).
        json_path = redirected_meta / validate.VALIDATION_RESULT_FILENAME
        report_path = redirected_meta / validate.VALIDATION_REPORT_FILENAME
        assert json_path.exists(), "JSON sidecar not written for a missing table"
        assert report_path.exists(), "report not written for a missing table"

        # The returned sidecar path is the JSON one, and it reports the failing
        # zero-check verdict.
        assert results["integrated_input_result"] == json_path
        loaded = json.loads(json_path.read_text())
        assert loaded["all_passed"] is False
        assert loaded["n_checks"] == 0
