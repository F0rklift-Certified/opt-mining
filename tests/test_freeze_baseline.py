"""
Unit tests for ``pipeline.validate.freeze_baseline`` (S2-02 task 2.2).

These tests pin the Frozen_Baseline half of the input-contract gate against its
requirements without ever touching the real ``DATA/integration/metadata``
directory:

  * a first ``write=True`` call over a fixture table writes the Baseline_Manifest
    exactly once, with a 64-hex ``sha256``, ``bytes == path.stat().st_size``, a
    relative ``path``, and ``storage_crs`` / ``computation_crs`` copied from the
    integration config; a second ``write=True`` overwrites it (1.2, 1.6, 1.7);
  * a verify-mode (``write=False``) call over the unchanged file returns
    ``hash_ok=True``, and a one-byte-different file flips ``hash_ok=False``
    (Hash_Drift) (1.3, 1.4);
  * no code path mutates the fixture file — the input SHA-256 is unchanged
    across every call (1.5, read-only guarantee / design P8).

Hermeticity: ``freeze_baseline`` resolves the manifest destination from the
module-level ``pipeline.validate.DEFAULT_BASELINE_MANIFEST_PATH`` constant (read
inside the function body, not bound as a default argument). Each test
``monkeypatch``-redirects that constant to a path under ``tmp_path`` so the real
project metadata directory is never written. The fixture GeoPackage is written
to ``tmp_path`` and passed via the ``integrated_path=`` override, so the frozen
artefact under test is a throwaway temp file, never the real S1-08 table.

Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pipeline import validate
from pipeline.common.geo import sha256_file
from pipeline.integration.config import (
    COMPUTATION_CRS,
    INTEGRATION_VINTAGE,
    OUTPUT_LAYER,
    STORAGE_CRS,
)

from tests.integration.integrated_fixtures import (
    hash_drift_baseline,
    make_integrated_fixture,
    write_fixture_gpkg,
)

_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")


@pytest.fixture
def redirected_manifest(monkeypatch, tmp_path) -> Path:
    """
    Redirect ``DEFAULT_BASELINE_MANIFEST_PATH`` to a throwaway location under
    ``tmp_path`` so ``write=True`` never touches the real project metadata dir.

    ``freeze_baseline`` reads the module constant inside its body, so patching
    the attribute on the ``pipeline.validate`` module is sufficient. The path is
    returned so tests can assert on the written manifest.
    """
    manifest_path = tmp_path / "meta" / validate.BASELINE_MANIFEST_FILENAME
    monkeypatch.setattr(
        validate, "DEFAULT_BASELINE_MANIFEST_PATH", manifest_path, raising=True
    )
    return manifest_path


@pytest.fixture
def good_gpkg(tmp_path) -> Path:
    """A valid integrated-table GeoPackage written to a temp file."""
    gdf = make_integrated_fixture()
    return write_fixture_gpkg(gdf, tmp_path, name="good.gpkg")


class TestFreezeWritesBaselineManifest:
    """First ``write=True`` records the manifest once; a second overwrites it."""

    def test_first_write_records_manifest_with_expected_fields(
        self, redirected_manifest, good_gpkg
    ):
        assert not redirected_manifest.exists()

        record = validate.freeze_baseline(good_gpkg, write=True)

        # The manifest was written exactly once, to the redirected temp path,
        # and NOT to the real project metadata dir.
        assert redirected_manifest.exists(), "Baseline_Manifest was not written"
        persisted = json.loads(redirected_manifest.read_text())

        # 64-hex lowercase sha256, matching the observed file hash.
        assert _HEX64.match(persisted["sha256"]), persisted["sha256"]
        assert persisted["sha256"] == sha256_file(good_gpkg)

        # bytes matches the on-disk size.
        assert persisted["bytes"] == good_gpkg.stat().st_size

        # path is relative (a fixture outside PROJECT_ROOT is recorded as its
        # own path string, but it must not be absolute for an in-tree file);
        # here the temp file lives outside the project root, so freeze_baseline
        # records the given path. Assert it is a string and carries the file
        # name, and that the layer/version/CRS fields are copied from config.
        assert isinstance(persisted["path"], str)
        assert persisted["path"].endswith("good.gpkg")
        assert persisted["layer"] == OUTPUT_LAYER
        assert persisted["version"] == INTEGRATION_VINTAGE
        assert persisted["storage_crs"] == STORAGE_CRS
        assert persisted["computation_crs"] == COMPUTATION_CRS

        # The returned record carries the per-run verify fields on top of the
        # persisted manifest, and a freshly frozen file matches itself.
        assert record["hash_ok"] is True
        assert record["sha256"] == persisted["sha256"]
        assert "verified_at_utc" in record

    def test_relative_path_for_in_tree_file(
        self, redirected_manifest, monkeypatch, tmp_path
    ):
        # When the fixture lives *inside* the project root, the recorded path is
        # relative to PROJECT_ROOT (Requirement 1.2). Point PROJECT_ROOT at the
        # temp dir so the fixture is "in tree" for this assertion.
        from pipeline.integration import config as integration_config

        monkeypatch.setattr(
            integration_config, "PROJECT_ROOT", tmp_path, raising=True
        )
        gpkg = write_fixture_gpkg(make_integrated_fixture(), tmp_path, name="in_tree.gpkg")

        record = validate.freeze_baseline(gpkg, write=True)

        assert not Path(record["path"]).is_absolute()
        assert record["path"] == "in_tree.gpkg"

    def test_second_write_overwrites_manifest(
        self, redirected_manifest, good_gpkg, tmp_path
    ):
        first = validate.freeze_baseline(good_gpkg, write=True)
        first_persisted = json.loads(redirected_manifest.read_text())

        # A byte-different second artefact re-frozen with write=True should
        # OVERWRITE the recorded reference with the new observed hash.
        drifted_gpkg = write_fixture_gpkg(
            hash_drift_baseline(make_integrated_fixture()), tmp_path, name="drifted.gpkg"
        )
        second = validate.freeze_baseline(drifted_gpkg, write=True)
        second_persisted = json.loads(redirected_manifest.read_text())

        assert second_persisted["sha256"] == sha256_file(drifted_gpkg)
        assert second_persisted["sha256"] != first_persisted["sha256"]
        # Re-freezing adopts the new hash as the reference, so hash_ok stays True.
        assert second["hash_ok"] is True
        assert first["hash_ok"] is True


class TestVerifyModeHashDrift:
    """Verify mode surfaces Hash_Drift via ``hash_ok``."""

    def test_unchanged_file_is_hash_ok(self, redirected_manifest, good_gpkg):
        validate.freeze_baseline(good_gpkg, write=True)

        verified = validate.freeze_baseline(good_gpkg, write=False)

        assert verified["hash_ok"] is True
        assert verified["sha256"] == sha256_file(good_gpkg)

    def test_one_byte_change_flips_hash_ok_false(
        self, redirected_manifest, good_gpkg, tmp_path
    ):
        # Freeze over the good file, recording its SHA-256 as the reference.
        validate.freeze_baseline(good_gpkg, write=True)
        recorded = json.loads(redirected_manifest.read_text())["sha256"]

        # Point a verify-mode call at a byte-different GeoPackage. The recorded
        # frozen_sha comes from the manifest, so the observed hash of the
        # drifted file differs and hash_ok flips to False (Hash_Drift).
        drifted_gpkg = write_fixture_gpkg(
            hash_drift_baseline(make_integrated_fixture()), tmp_path, name="drifted.gpkg"
        )
        drifted = validate.freeze_baseline(drifted_gpkg, write=False)

        assert drifted["sha256"] == recorded, (
            "verify mode should report the FROZEN reference sha256"
        )
        assert drifted["sha256"] != sha256_file(drifted_gpkg)
        assert drifted["hash_ok"] is False


class TestReadOnlyNonMutation:
    """No code path mutates the frozen artefact (Requirement 1.5, design P8)."""

    def test_freeze_and_verify_do_not_mutate_the_file(
        self, redirected_manifest, good_gpkg
    ):
        before = sha256_file(good_gpkg)

        validate.freeze_baseline(good_gpkg, write=True)
        validate.freeze_baseline(good_gpkg, write=True)  # overwrite
        validate.freeze_baseline(good_gpkg, write=False)  # verify

        after = sha256_file(good_gpkg)
        assert after == before, "freeze_baseline mutated the input artefact"
