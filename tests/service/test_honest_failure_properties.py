"""
Property-based test for the S2-08 error handling — honest failure (Property 6).

# Feature: s2-08-decision-service-api, Property 6: honest failure

**Property 6 — Honest failure.** A missing Run, an unknown ``cell_id``, or a
missing materialised engine output each yield an ERROR that NAMES the fault —
never a misleading empty success (CONTRACT.md §6, §7 P6, Requirement 7.1, 7.2,
7.3). The whole point of the requirement is that the service DISTINGUISHES "no
such thing" from "nothing to show": it raises, and the raised error carries the
concrete run_id / cell_id / input that was absent, so the Web_Application can
present a real, specific error rather than an empty list that looks like a valid
result.

**Validates: Requirements 7.1, 7.2, 7.3**

Where the sibling deterministic test ``test_honest_failure.py`` (task 7.1) pins
this contract on a handful of hand-picked ids, this test exercises it across
MANY generated faults:

  ARM A (Requirement 7.1). For ANY generated ``run_id`` that is NOT present in
  the store, EVERY run-keyed read operation (``get_ranked_results``,
  ``get_site_detail``, ``get_exclusions``) raises ``RunNotFoundError`` whose
  message NAMES that ``run_id`` — and never returns an empty list. Asserting all
  three per generated id proves the honest-failure behaviour is uniform, not
  incidental to one operation.

  ARM B (Requirement 7.2). For ANY generated ``cell_id`` NOT present in a real,
  materialised Run, ``get_site_detail`` raises ``CellNotFoundError`` whose
  message NAMES that ``cell_id`` — distinct from a missing Run (which names the
  run), and never a fabricated empty success.

  ARM C (Requirement 7.3). For a real Run whose required Scored_Table is then
  REMOVED, every run-keyed read operation that needs it raises
  ``EngineOutputError`` NAMING the missing input — never a fabricated result.

Hermeticity discipline (matching ``test_results_properties.py`` and
``test_empty_but_valid_properties.py``): the per-Run store
(``service_config.RUNS_DIR``), the shared explanation output
(``service_config.EXPLANATION_PATH``) and the shared Eligibility_Table
(``service_config.ELIGIBILITY_TABLE_PATH``) are redirected to a per-example temp
directory with an explicit save/restore — a function-scoped fixture cannot be
shared across the many examples a single ``@given`` body drives — so the real
``DATA/service/`` tree is never touched and each example is fully isolated. No
engine run is required: the property is about the service's failure path over a
fixed (or deliberately broken) materialised output, so hand-materialised Runs
exercise it directly and deterministically. Runs at least 100 examples per arm.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import geopandas as gpd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Point

from pipeline.scoring import config as scoring_config
from pipeline.service import (
    config as service_config,
    get_exclusions,
    get_ranked_results,
    get_site_detail,
)
from pipeline.service.runs import (
    CellNotFoundError,
    EngineOutputError,
    RunNotFoundError,
)


# --- Strategies: identifiers that are guaranteed to be *absent* ---------------
#
# A run_id / cell_id is drawn from the same alphabet the real ones use so the
# generator explores realistic-looking ids; the test then materialises a Run
# whose id (and only cell) is a FIXED sentinel that the strategy cannot draw, so
# every generated id is guaranteed absent from the store / the Run without any
# per-example filtering.

_id_alphabet = "abcdefghijklmnopqrstuvwxyz0123456789_"

# The one Run id and cell id that DO exist in the materialised fixture. They are
# uppercase, so they can never collide with a lowercase-only generated id.
PRESENT_RUN_ID = "REALRUN000000001"
PRESENT_CELL_ID = "REALCELL0001"

_missing_ids = st.text(alphabet=_id_alphabet, min_size=1, max_size=16)


# The run-keyed read operations, as (name, callable-taking-a-run_id) pairs — the
# same three the deterministic cross-operation test parametrises, so the two
# tests pin the SAME uniform contract (holistic-project-awareness: one error
# contract across every operation).
RUN_KEYED_OPERATIONS = [
    ("get_ranked_results", lambda run_id: get_ranked_results(run_id)),
    ("get_site_detail", lambda run_id: get_site_detail(run_id, PRESENT_CELL_ID)),
    ("get_exclusions", lambda run_id: get_exclusions(run_id)),
]


def _materialise_one_eligible_cell(store: Path, tmp: Path, run_id: str) -> Path:
    """
    Materialise a complete, readable single-eligible-cell Run: a Scored_Table,
    the integrated table it "scored", the S2-06 explanation output, and a
    manifest. Returns the explanation path (redirected by the caller).

    Enough for every read operation to SUCCEED for ``PRESENT_CELL_ID`` — so the
    unknown-cell arm can be exercised against a real, readable Run rather than a
    broken one, and the missing-output arm can break exactly one input.
    """
    target = store / run_id
    target.mkdir(parents=True, exist_ok=True)
    geometry = [Point(150.0, -30.0)]

    gpd.GeoDataFrame(
        [{
            "cell_id": PRESENT_CELL_ID,
            "suitability_score": 0.9,
            "rank": 1,
            "contrib_wind_speed": 0.9,
        }],
        geometry=geometry,
        crs=scoring_config.STORAGE_CRS,
    ).to_file(
        target / service_config.SCORED_GPKG_FILENAME,
        driver="GPKG",
        layer=service_config.SCORED_LAYER,
    )

    integrated_path = tmp / f"integrated_{run_id}.gpkg"
    gpd.GeoDataFrame(
        [{"cell_id": PRESENT_CELL_ID, "eligible": True, "wind_speed": 9.0}],
        geometry=geometry,
        crs=scoring_config.STORAGE_CRS,
    ).to_file(integrated_path, driver="GPKG", layer=service_config.INTEGRATED_LAYER)

    explanation_path = tmp / f"explanations_{run_id}.json"
    explanation_path.write_text(
        json.dumps([{
            "cell_id": PRESENT_CELL_ID, "eligible": True, "headline": "H",
            "positive_factors": [], "weaknesses": [], "proxy_caveats": [],
            "data_quality_notes": [],
        }]) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "run_id": run_id,
        "weights_id": run_id,
        "scenario": None,
        "criteria": [
            {"feature": "wind_speed", "weight": 1.0, "direction": "higher_is_better"}
        ],
        "integrated_path": str(integrated_path),
        "integrated_layer": service_config.INTEGRATED_LAYER,
    }
    (target / service_config.RUN_MANIFEST_FILENAME).write_text(
        json.dumps(manifest) + "\n", encoding="utf-8"
    )
    return explanation_path


# --------------------------------------------------------------------------- #
# ARM A (7.1) — a missing Run: EVERY run-keyed read op raises                  #
# RunNotFoundError NAMING the run, never an empty list, for ANY generated id.  #
# --------------------------------------------------------------------------- #


@settings(max_examples=100, deadline=None)
@given(missing_run_id=_missing_ids)
def test_property_6a_missing_run_raises_naming_the_run(missing_run_id):
    """
    For ANY generated ``run_id`` absent from the store, every run-keyed read
    operation raises ``RunNotFoundError`` whose message NAMES that ``run_id`` —
    never returns an empty list (Requirement 7.1).
    """
    # Feature: s2-08-decision-service-api, Property 6: honest failure

    original_runs_dir = service_config.RUNS_DIR
    original_explanation_path = service_config.EXPLANATION_PATH
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        store = tmp / "runs"
        service_config.RUNS_DIR = store
        try:
            # A real Run exists under a DIFFERENT (uppercase) id, so the store is
            # not empty — a missing-run failure is proven to be about THIS id, not
            # an empty store. The generated id is lowercase-only, so it can never
            # equal PRESENT_RUN_ID.
            explanation_path = _materialise_one_eligible_cell(
                store, tmp, PRESENT_RUN_ID
            )
            service_config.EXPLANATION_PATH = explanation_path

            for op_name, op in RUN_KEYED_OPERATIONS:
                with pytest.raises(RunNotFoundError) as exc_info:
                    op(missing_run_id)
                # The error NAMES the missing run (not a bare "not found"), so
                # the UI can present a real, specific error — the honest-failure
                # contract, uniform across every run-keyed operation.
                assert missing_run_id in str(exc_info.value), (
                    f"{op_name} did not name the missing run {missing_run_id!r}"
                )
        finally:
            service_config.RUNS_DIR = original_runs_dir
            service_config.EXPLANATION_PATH = original_explanation_path


# --------------------------------------------------------------------------- #
# ARM B (7.2) — an unknown cell_id in a REAL Run: get_site_detail raises       #
# CellNotFoundError NAMING the cell, never an empty success, for ANY id.       #
# --------------------------------------------------------------------------- #


@settings(max_examples=100, deadline=None)
@given(unknown_cell_id=_missing_ids)
def test_property_6b_unknown_cell_raises_naming_the_cell(unknown_cell_id):
    """
    For ANY generated ``cell_id`` not present in a real, materialised Run,
    ``get_site_detail`` raises ``CellNotFoundError`` whose message NAMES that
    ``cell_id`` — distinct from a missing Run, never an empty success
    (Requirement 7.2).
    """
    # Feature: s2-08-decision-service-api, Property 6: honest failure

    original_runs_dir = service_config.RUNS_DIR
    original_explanation_path = service_config.EXPLANATION_PATH
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        store = tmp / "runs"
        service_config.RUNS_DIR = store
        try:
            explanation_path = _materialise_one_eligible_cell(
                store, tmp, PRESENT_RUN_ID
            )
            service_config.EXPLANATION_PATH = explanation_path

            # The Run EXISTS and is readable; only the cell is absent (the
            # generated id is lowercase-only, so it can never equal the
            # uppercase PRESENT_CELL_ID). The failure is therefore proven to be
            # about the cell, not the Run.
            with pytest.raises(CellNotFoundError) as exc_info:
                get_site_detail(PRESENT_RUN_ID, unknown_cell_id)
            assert unknown_cell_id in str(exc_info.value), (
                f"get_site_detail did not name the missing cell {unknown_cell_id!r}"
            )
        finally:
            service_config.RUNS_DIR = original_runs_dir
            service_config.EXPLANATION_PATH = original_explanation_path


# --------------------------------------------------------------------------- #
# ARM C (7.3) — a real Run whose required Scored_Table is REMOVED: every       #
# run-keyed read op that needs it raises EngineOutputError NAMING the input.   #
# --------------------------------------------------------------------------- #

# The operations whose read path requires the Run's Scored_Table. get_exclusions
# reads the shared Eligibility_Table instead, so it is exercised separately in
# arm C2 with ITS required input removed.
SCORED_TABLE_OPERATIONS = [
    ("get_ranked_results", lambda run_id: get_ranked_results(run_id)),
    ("get_site_detail", lambda run_id: get_site_detail(run_id, PRESENT_CELL_ID)),
]


@settings(max_examples=100, deadline=None)
@given(run_id=_missing_ids)
def test_property_6c_missing_scored_table_names_the_input(run_id):
    """
    For a real Run (ANY generated id) whose required Scored_Table has been
    REMOVED, every operation that reads it raises ``EngineOutputError`` NAMING
    the missing input — never a fabricated result (Requirement 7.3).
    """
    # Feature: s2-08-decision-service-api, Property 6: honest failure

    original_runs_dir = service_config.RUNS_DIR
    original_explanation_path = service_config.EXPLANATION_PATH
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        store = tmp / "runs"
        service_config.RUNS_DIR = store
        try:
            explanation_path = _materialise_one_eligible_cell(store, tmp, run_id)
            service_config.EXPLANATION_PATH = explanation_path

            # The Run EXISTS (its manifest is present), but its engine output is
            # gone: remove the Scored_Table so the failure is 7.3 (missing
            # output naming the input), NOT 7.1 (missing Run).
            scored_path = store / run_id / service_config.SCORED_GPKG_FILENAME
            scored_path.unlink()

            for op_name, op in SCORED_TABLE_OPERATIONS:
                with pytest.raises(EngineOutputError) as exc_info:
                    op(run_id)
                # The error NAMES the missing input — the run_id AND the fault —
                # so the failure is diagnosable, never a fabricated empty result.
                message = str(exc_info.value)
                assert run_id in message, (
                    f"{op_name} did not name the Run {run_id!r} whose output is missing"
                )
                assert "Scored_Table is missing" in message, (
                    f"{op_name} did not name the missing Scored_Table input"
                )
        finally:
            service_config.RUNS_DIR = original_runs_dir
            service_config.EXPLANATION_PATH = original_explanation_path


@settings(max_examples=100, deadline=None)
@given(run_id=_missing_ids)
def test_property_6c_missing_eligibility_table_names_the_input(run_id):
    """
    For a real Run (ANY generated id) whose shared Eligibility_Table is absent,
    ``get_exclusions`` raises ``EngineOutputError`` NAMING the missing input —
    never a fabricated empty exclusion set (Requirement 7.3).

    This completes arm C: ``get_exclusions`` reads the Eligibility_Table rather
    than the Scored_Table, so its honest-failure input is that shared artefact.
    """
    # Feature: s2-08-decision-service-api, Property 6: honest failure

    original_runs_dir = service_config.RUNS_DIR
    original_explanation_path = service_config.EXPLANATION_PATH
    original_eligibility_path = service_config.ELIGIBILITY_TABLE_PATH
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        store = tmp / "runs"
        service_config.RUNS_DIR = store
        try:
            explanation_path = _materialise_one_eligible_cell(store, tmp, run_id)
            service_config.EXPLANATION_PATH = explanation_path

            # The Run exists and is readable, but the shared Eligibility_Table
            # get_exclusions needs points at an absent path — so the failure is
            # 7.3 (missing output naming the input), never an empty success.
            service_config.ELIGIBILITY_TABLE_PATH = tmp / "absent_eligibility.gpkg"

            with pytest.raises(EngineOutputError) as exc_info:
                get_exclusions(run_id)
            assert "Eligibility_Table is missing" in str(exc_info.value), (
                "get_exclusions did not name the missing Eligibility_Table input"
            )
        finally:
            service_config.RUNS_DIR = original_runs_dir
            service_config.EXPLANATION_PATH = original_explanation_path
            service_config.ELIGIBILITY_TABLE_PATH = original_eligibility_path
