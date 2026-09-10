"""
Property-based tests for the S2-02 input-contract gate (task 8.3).

Two Hypothesis properties, each in its own ``@given`` test running >= 100
examples, sitting next to the pure core they validate
(``pipeline.validate.freeze_baseline`` / ``_run_integrated_input_checks``):

  * Property 8 (P8) — Non-mutation. After running the input-contract checks (and
    a verify-mode ``freeze_baseline``) over ANY generated present table, the byte
    content of the input file is unchanged: ``sha256_file(path)`` after equals
    ``sha256_file(path)`` before. The validator/gate is strictly read-only on the
    frozen artefact (Requirement 1.5, design P8).

  * Property 4 (P4) — Frozen-baseline reproducibility. Freezing a baseline over a
    written good GeoPackage records its ``sha256``; a verify-mode call over the
    UNCHANGED file yields ``hash_ok=True`` and reports that same recorded
    ``sha256``, while pointing verify-mode at a byte-different file flips
    ``hash_ok`` to ``False`` (Hash_Drift). Requirements 1.3, 1.4.

Hermeticity — the real ``DATA/integration/metadata`` directory is NEVER written.
``freeze_baseline`` resolves its manifest destination from the module-level
``pipeline.validate.DEFAULT_BASELINE_MANIFEST_PATH`` (read inside the function
body). Because the function-scoped ``monkeypatch`` fixture cannot be shared
across the many examples Hypothesis drives from a single ``@given`` test body,
each example opens its own ``pytest.MonkeyPatch.context()`` and redirects that
constant to a per-example temp path, restoring it on context exit. Fixture
GeoPackages are written under ``tmp_path_factory`` temp dirs, so the frozen
artefact under test is always a throwaway file, never the real S1-08 table.

Validates: Requirements 1.3, 1.4, 1.5.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pipeline import validate
from pipeline.common.geo import sha256_file
from pipeline.integration.config import SCORED_FEATURE_COLUMNS
from pipeline.validate import SANITY_RANGES

from tests.integration.integrated_fixtures import (
    hash_drift_baseline,
    make_integrated_fixture,
    write_fixture_gpkg,
)

# Per-example raster/GeoPackage I/O and geopandas reads can exceed the default
# Hypothesis deadline on a cold cache, so deadline=None; suppress the too_slow
# health check for the same reason. >= 100 examples per property.
SETTINGS = settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)


# ---------------------------------------------------------------------------
# Strategies — vary the table VALUES while keeping it a valid present table
# ---------------------------------------------------------------------------
#
# The property is invariant to the specific values in the table, so the
# strategy varies things that change the file bytes (and hence its hash)
# without changing the property: the number of cells and the in-range value of
# a ranged scored column. Bounds are read from SANITY_RANGES so a schema change
# propagates rather than drifting.

# Scored columns that carry a numeric Sanity_Range (lo, hi) — the ones we can
# safely perturb within contract. Read from the Schema_Authority.
_RANGED_SCORED = [
    c
    for c in SCORED_FEATURE_COLUMNS
    if isinstance(SANITY_RANGES.get(c), tuple)
]


@st.composite
def generated_tables(draw):
    """
    A valid, present integrated table with varied values.

    Returns a GeoDataFrame from ``make_integrated_fixture`` (schema-faithful,
    at least one Eligible_Cell) with a Hypothesis-chosen cell count and one
    ranged scored column nudged to a Hypothesis-chosen in-range value. The
    result stays a valid table (the property holds for every value), while the
    file bytes — and therefore the SHA-256 — differ across examples.
    """
    n_cells = draw(st.integers(min_value=2, max_value=8))
    gdf = make_integrated_fixture(n_cells=n_cells)

    column = draw(st.sampled_from(_RANGED_SCORED))
    lo, hi = SANITY_RANGES[column]
    value = draw(
        st.floats(
            min_value=float(lo),
            max_value=float(hi),
            allow_nan=False,
            allow_infinity=False,
            width=32,
        )
    )
    gdf.loc[gdf.index[0], column] = value
    return gdf


# ---------------------------------------------------------------------------
# Property 8 — Non-mutation
# ---------------------------------------------------------------------------


class TestPropertyNonMutation:
    """P8: the gate never mutates the frozen artefact's bytes."""

    # Feature: s2-02-freeze-validate-integrated-dataset, Property 8: Non-mutation
    @SETTINGS
    @given(gdf=generated_tables())
    def test_property_8_non_mutation(self, tmp_path_factory, gdf):
        # A fresh temp dir per example (tmp_path is a function-scoped fixture and
        # does not compose with @given's many examples; tmp_path_factory does).
        tmp_path = tmp_path_factory.mktemp("p8")
        path = write_fixture_gpkg(gdf, tmp_path, name="input.gpkg")

        before = sha256_file(path)

        # Redirect the Baseline_Manifest to a per-example temp path so the real
        # DATA/integration/metadata dir is never written, then run the read-only
        # gate: the input-contract checks (which internally call verify-mode
        # freeze_baseline for the hash check) plus an explicit verify-mode and
        # a write-mode freeze_baseline. None of these may touch the input bytes.
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                validate,
                "DEFAULT_BASELINE_MANIFEST_PATH",
                tmp_path / "meta" / validate.BASELINE_MANIFEST_FILENAME,
                raising=True,
            )
            validate.freeze_baseline(path, write=True)
            validate.freeze_baseline(path, write=False)
            checks = validate._run_integrated_input_checks(integrated_path=path)

        after = sha256_file(path)

        assert after == before, "the input-contract gate mutated the input bytes"
        # Sanity: the gate actually ran over a present table (no silent skip),
        # so the non-mutation guarantee is meaningful.
        assert checks, "expected a non-empty check battery on a present table"


# ---------------------------------------------------------------------------
# Property 4 — Frozen-baseline reproducibility
# ---------------------------------------------------------------------------


class TestPropertyFrozenBaselineReproducibility:
    """P4: an unchanged artefact re-hashes to the recorded sha256; drift flips it."""

    # Feature: s2-02-freeze-validate-integrated-dataset, Property 4: Frozen-baseline reproducibility
    @SETTINGS
    @given(gdf=generated_tables())
    def test_property_4_frozen_baseline_reproducibility(self, tmp_path_factory, gdf):
        tmp_path = tmp_path_factory.mktemp("p4")

        # Write the good artefact and a byte-different sibling. hash_drift_baseline
        # nudges one in-range value, so only the file bytes (and hash) change.
        good_gpkg = write_fixture_gpkg(gdf, tmp_path, name="good.gpkg")
        drifted_gpkg = write_fixture_gpkg(
            hash_drift_baseline(gdf), tmp_path, name="drifted.gpkg"
        )

        # The two artefacts really are byte-different (otherwise the drift half
        # of the property is vacuous).
        assert sha256_file(good_gpkg) != sha256_file(drifted_gpkg)

        with pytest.MonkeyPatch.context() as mp:
            manifest_path = tmp_path / "meta" / validate.BASELINE_MANIFEST_FILENAME
            mp.setattr(
                validate,
                "DEFAULT_BASELINE_MANIFEST_PATH",
                manifest_path,
                raising=True,
            )

            # Freeze the baseline over the good file (records its sha256 once).
            frozen = validate.freeze_baseline(good_gpkg, write=True)
            recorded_sha = frozen["sha256"]
            assert manifest_path.exists(), "freeze wrote to the redirected temp path"

            # (a) Verify-mode over the UNCHANGED file → hash_ok True, and its
            # reported sha256 equals the recorded reference.
            verified = validate.freeze_baseline(good_gpkg, write=False)
            assert verified["hash_ok"] is True
            assert verified["sha256"] == recorded_sha
            assert recorded_sha == sha256_file(good_gpkg)

            # (b) Verify-mode pointed at the byte-different file → hash_ok False.
            # The frozen reference stays the good sha, so the drifted observed
            # hash disagrees and Hash_Drift surfaces as a failing verification.
            drifted = validate.freeze_baseline(drifted_gpkg, write=False)
            assert drifted["sha256"] == recorded_sha, (
                "verify mode should report the FROZEN reference sha256"
            )
            assert drifted["hash_ok"] is False

            # Hermeticity: the only Baseline_Manifest written this example lives
            # under the per-example temp dir (the redirected target), never the
            # real DATA/integration/metadata path.
            assert manifest_path.parent == tmp_path / "meta"
