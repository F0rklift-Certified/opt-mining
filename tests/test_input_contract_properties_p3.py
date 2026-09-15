"""
Property-based test for the S2-02 input-contract gate — Property 3 (P3):
Gate soundness (monotonic gate).

Feature: s2-02-freeze-validate-integrated-dataset, Property 3: Gate soundness
(monotonic gate).

Validates: Requirements 9.2, 10.3.

The property, stated over the pure gate (``_run_integrated_input_checks`` +
``_verdict`` / ``build_validation_result``):

  * a known-good generated table yields ``all_passed=True``; and
  * injecting *exactly one* defect flips ``all_passed`` to ``False`` **and**
    fails at least one Check_Record.

Because any single injected defect must flip the verdict, the gate is
*monotonic*: it cannot silently pass a table that carries a real defect. This
is the counterpart to P1 (no silent passes): P1 says every check is always
emitted; P3 says the conjunction of those checks actually reacts to defects.

Strategy
--------
* The value dimension is varied with Hypothesis by drawing ``n_cells`` (the
  good fixture marches ``n_cells`` cells east along a fixed latitude inside
  ``NSW_BBOX`` and makes the last one ineligible, so every draw is a distinct
  but still-valid good table — mirroring the value-variation approach used by
  the sibling P1 test / task 8.1).
* The defect dimension is varied by drawing a mutator *key* from
  ``KNOWN_BAD_MUTATORS`` via ``st.sampled_from``.

Hash-drift handling (documented choice)
---------------------------------------
The ``hash_drift_baseline`` mutator is **excluded** from this property. Every
other mutator injects a *content* defect that the battery detects on its own
merits with **no** Baseline_Manifest present: in verify mode with no recorded
reference, ``freeze_baseline`` treats the observed hash as its own reference,
so Check 1 (baseline hash) passes trivially and the verdict flip comes purely
from the injected defect's own check. That keeps the good-table baseline clean
(``all_passed=True``) and the bad-table flip attributable to the single defect,
with no manifest fixture to set up. ``hash_drift_baseline`` is the one mutator
that needs a *frozen manifest written first* to be detectable, so it is covered
separately by the frozen-baseline reproducibility property (P4, task 8.3)
rather than here.

Hermeticity
-----------
Each example writes its fixture GeoPackage to a fresh
``tempfile.TemporaryDirectory`` (Hypothesis ``@given`` does not compose with
pytest's ``tmp_path`` fixture — the repo's existing ``@given`` tests create
their temp artefacts in the test body for the same reason). The module-level
``DEFAULT_BASELINE_MANIFEST_PATH`` constant is redirected to a non-existent
path under that temp dir for the duration of each example, so no real
``DATA/integration/metadata`` manifest is read or written and the "no manifest"
precondition above holds regardless of local state. No baseline is ever frozen
into the real metadata dir.
"""

from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pipeline import validate

from tests.integration.integrated_fixtures import (
    KNOWN_BAD_MUTATORS,
    make_integrated_fixture,
    write_fixture_gpkg,
)

# Mutator keys eligible for the monotonic-gate property: every known-bad
# mutator EXCEPT hash_drift_baseline (see module docstring — it needs a frozen
# manifest and is covered by P4/task 8.3).
_CONTENT_DEFECT_KEYS = sorted(set(KNOWN_BAD_MUTATORS) - {"hash_drift_baseline"})

SETTINGS = settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


@contextmanager
def _hermetic_manifest(tmpdir: Path):
    """
    Point ``DEFAULT_BASELINE_MANIFEST_PATH`` at a non-existent temp location for
    the duration of the block so freezing/verifying never touches the real
    project metadata dir. ``freeze_baseline`` reads the module constant inside
    its body, so rebinding the attribute is sufficient.

    Not using ``monkeypatch`` because Hypothesis ``@given`` does not compose
    with function-scoped pytest fixtures; save/restore by hand instead.
    """
    original = validate.DEFAULT_BASELINE_MANIFEST_PATH
    validate.DEFAULT_BASELINE_MANIFEST_PATH = tmpdir / "meta" / validate.BASELINE_MANIFEST_FILENAME
    try:
        yield
    finally:
        validate.DEFAULT_BASELINE_MANIFEST_PATH = original


def _all_passed(checks: list[dict]) -> bool:
    """The gate verdict, via the same helpers run() uses (Requirement 10.3)."""
    # build_validation_result enforces all_passed == _verdict(checks); assert
    # the two agree so the property pins the documented invariant, then return
    # the verdict.
    baseline = {"hash_ok": True}  # placeholder baseline block; verdict is over checks
    result = validate.build_validation_result(baseline, checks)
    assert result["all_passed"] == validate._verdict(checks)
    assert result["n_checks"] == len(checks)
    assert result["n_passed"] == sum(1 for c in checks if c["passed"])
    return result["all_passed"]


@SETTINGS
@given(
    n_cells=st.integers(min_value=2, max_value=20),
    mutator_key=st.sampled_from(_CONTENT_DEFECT_KEYS),
)
def test_property_3_monotonic_gate(n_cells, mutator_key):
    # Feature: s2-02-freeze-validate-integrated-dataset, Property 3: Gate
    # soundness (monotonic gate).
    # Validates: Requirements 9.2, 10.3.
    good = make_integrated_fixture(n_cells)
    mutate = KNOWN_BAD_MUTATORS[mutator_key]
    bad = mutate(good)

    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        with _hermetic_manifest(tmpdir):
            # (a) The good table passes the gate. With no manifest written,
            # Check 1 (hash) passes trivially, so all_passed reflects the
            # content checks alone — every one of which passes for a valid
            # table.
            good_gpkg = write_fixture_gpkg(good, tmpdir, name="good.gpkg")
            good_checks = validate._run_integrated_input_checks(
                integrated_path=good_gpkg
            )
            assert good_checks, "a present table must yield a non-empty battery"
            assert _all_passed(good_checks) is True, (
                f"good table (n_cells={n_cells}) unexpectedly failed the gate: "
                f"{[c for c in good_checks if not c['passed']]}"
            )

            # (b) Injecting exactly one defect flips the verdict to False AND
            # fails at least one Check_Record.
            bad_gpkg = write_fixture_gpkg(bad, tmpdir, name="bad.gpkg")
            bad_checks = validate._run_integrated_input_checks(
                integrated_path=bad_gpkg
            )
            assert bad_checks, "a present (defective) table must still yield checks"

            failed = [c for c in bad_checks if not c["passed"]]
            assert failed, (
                f"defect {mutator_key!r} (n_cells={n_cells}) failed no check — "
                "the gate silently passed a defective table"
            )
            assert _all_passed(bad_checks) is False, (
                f"defect {mutator_key!r} (n_cells={n_cells}) did not flip the "
                "monotonic gate to all_passed=False"
            )
