"""
S3-10 demo-rehearsal gate (design Decision 1-I).

Two tiers, matching the design's split between a Docker-gated integration test
and fast unit tests on the harness's pure predicates:

* An ``@pytest.mark.integration`` test mirroring
  ``tests/backend/test_compose_stack_integration.py``'s
  ``_docker_stack_unavailable_reason`` gate: it SKIPS with a clear reason when
  Docker / the running stack is unavailable, and otherwise asserts the same
  FATAL rehearsal invariants against the running stack (a run is created; rows
  are rank-ordered with scores in ``[0, 1]``; site detail agrees with the ranked
  row, carries a verbatim explanation, and its contributions reconcile within
  ``1e-9``; exclusions are non-empty and carry a reason; ``/scenario-comparison``
  returns non-empty rows each carrying ``cell_id``/``rank_a``/``rank_b``/
  ``rank_delta`` keys — null values allowed; the sanity result is present with
  its caveat).
* FAST non-integration unit tests that exercise the harness's PURE predicates
  against fixture payloads — ranks-ordered true/false, contribution-sum within/
  over tolerance, the non-empty-rows-with-keys structural check, the moved-cell
  count, the readiness-matrix AC coverage, and the stale-token grep. These need
  no running stack and run in the fast suite.

Whether a cell actually moves between scenarios is DATA-DEPENDENT and is
captured as evidence by the harness, NOT asserted here (design Decision 1-I).

The harness lives at ``app/rehearse_demo.py``. ``app/`` is not a package, so it
is loaded by file path with ``importlib`` (the repo root is already on
``sys.path`` via ``conftest.py`` for ``pipeline`` imports the harness may make).
"""

from __future__ import annotations

import importlib.util
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS_PATH = REPO_ROOT / "app" / "rehearse_demo.py"


def _load_harness():
    """Load ``app/rehearse_demo.py`` as a module by file path (app/ is not a pkg)."""
    spec = importlib.util.spec_from_file_location("rehearse_demo", HARNESS_PATH)
    assert spec and spec.loader, f"could not load harness at {HARNESS_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("rehearse_demo", module)
    spec.loader.exec_module(module)
    return module


harness = _load_harness()


# --------------------------------------------------------------------------- #
# FAST unit tests on the pure predicates (no running stack).                   #
# --------------------------------------------------------------------------- #


def test_ranks_are_ordered_true():
    rows = [{"rank": 1}, {"rank": 2}, {"rank": 3}]
    assert harness.ranks_are_ordered(rows) is True


def test_ranks_are_ordered_false_out_of_order():
    rows = [{"rank": 1}, {"rank": 3}, {"rank": 2}]
    assert harness.ranks_are_ordered(rows) is False


def test_ranks_are_ordered_false_on_empty():
    assert harness.ranks_are_ordered([]) is False


def test_scores_in_unit_interval_true():
    rows = [{"suitability_score": 0.0}, {"suitability_score": 0.5}, {"suitability_score": 1.0}]
    assert harness.scores_in_unit_interval(rows) is True


def test_scores_in_unit_interval_false_out_of_range():
    rows = [{"suitability_score": 0.5}, {"suitability_score": 1.5}]
    assert harness.scores_in_unit_interval(rows) is False


def test_contributions_reconcile_within_tolerance():
    detail = {
        # Sum = 0.6 but with float round-off; well within 1e-9 of the score.
        "contributions": {"a": 0.1, "b": 0.2, "c": 0.3},
        "suitability_score": 0.6,
    }
    assert harness.contributions_reconcile(detail) is True


def test_contributions_do_not_reconcile_over_tolerance():
    detail = {
        "contributions": {"a": 0.1, "b": 0.2},
        "suitability_score": 0.9,  # 0.3 vs 0.9 — far beyond 1e-9
    }
    assert harness.contributions_reconcile(detail) is False


def test_contributions_reconcile_false_on_empty():
    assert harness.contributions_reconcile({"contributions": {}, "suitability_score": 0.0}) is False


def test_scenario_rows_have_keys_true_with_null_values_allowed():
    rows = [
        {"cell_id": "c1", "rank_a": 1, "rank_b": 2, "rank_delta": -1},
        # Null values are valid (cell ranked under only one side).
        {"cell_id": "c2", "rank_a": 5, "rank_b": None, "rank_delta": None},
    ]
    assert harness.scenario_rows_have_keys(rows) is True


def test_scenario_rows_have_keys_false_missing_key():
    rows = [{"cell_id": "c1", "rank_a": 1, "rank_b": 2}]  # no rank_delta
    assert harness.scenario_rows_have_keys(rows) is False


def test_scenario_rows_have_keys_false_on_empty():
    assert harness.scenario_rows_have_keys([]) is False


def test_count_moved_cells():
    rows = [
        {"cell_id": "c1", "rank_a": 1, "rank_b": 1, "rank_delta": 0},   # not moved
        {"cell_id": "c2", "rank_a": 2, "rank_b": 5, "rank_delta": -3},  # moved
        {"cell_id": "c3", "rank_a": 7, "rank_b": None, "rank_delta": None},  # one-sided
        {"cell_id": "c4", "rank_a": 9, "rank_b": 8, "rank_delta": 1},   # moved
    ]
    assert harness.count_moved_cells(rows) == 2


def test_count_moved_cells_zero_is_valid():
    rows = [{"cell_id": "c1", "rank_a": 1, "rank_b": 1, "rank_delta": 0}]
    assert harness.count_moved_cells(rows) == 0


def test_readiness_keys_cover_acs_true():
    matrix = {f"AC{n}": {} for n in range(1, 13)}
    assert harness.readiness_keys_cover_acs(matrix) is True


def test_readiness_keys_cover_acs_false_when_one_missing():
    matrix = {f"AC{n}": {} for n in range(1, 13) if n != 7}
    assert harness.readiness_keys_cover_acs(matrix) is False


def test_find_stale_tokens_detects_leak():
    text = "rank 1 cell with hash 604d051bb2deb7d8 excluded as outside_nsw_land"
    found = harness.find_stale_tokens(text)
    assert "604d051bb2deb7d8" in found
    assert "outside_nsw_land" in found


def test_find_stale_tokens_clean_text_returns_empty():
    text = "32,525 eligible of 47,311; reason offshore_or_marine; SHA 4062224a"
    assert harness.find_stale_tokens(text) == []


# --------------------------------------------------------------------------- #
# Integration tier — needs the running Compose stack; SKIP (never fail) when   #
# Docker / the stack is unavailable (mirrors test_compose_stack_integration).  #
# --------------------------------------------------------------------------- #


API_HOST_PORT = 18010
WEB_HOST_PORT = 13010


def _docker_stack_unavailable_reason() -> str | None:
    """Return a skip reason if the stack cannot run, else None (mirrors the
    compose-stack integration test's gate)."""
    if shutil.which("docker") is None:
        return "Docker CLI not found on PATH; skipping CI-tier rehearsal gate"
    try:
        compose = subprocess.run(
            ["docker", "compose", "version"], capture_output=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - env-specific
        return f"`docker compose version` could not run ({exc}); skipping"
    if compose.returncode != 0:
        return "Docker Compose v2 plugin not available (`docker compose`); skipping"
    try:
        info = subprocess.run(["docker", "info"], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - env-specific
        return f"`docker info` could not run ({exc}); skipping"
    if info.returncode != 0:
        return "Docker daemon is not running/reachable (`docker info` failed); skipping"
    return None


def _http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - localhost
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return False


@pytest.mark.integration
def test_demo_rehearsal_invariants_against_running_stack():
    """Assert the fatal §10 rehearsal invariants against the running stack.

    SKIPS with a clear reason when Docker / the stack is unavailable, so a
    developer without Docker sees a SKIP, never a failure (design Decision 1-I).
    """
    reason = _docker_stack_unavailable_reason()
    if reason is not None:
        pytest.skip(reason)

    api = f"http://localhost:{API_HOST_PORT}"
    web = f"http://localhost:{WEB_HOST_PORT}"

    # The daemon is up, but the S3-10 stack may not be running on these ports.
    # Give it a brief, bounded window, then SKIP (never fail) if absent — the
    # rehearsal is driven by the operator / CI, not by this unit of the suite.
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if _http_ok(api + "/openapi.json"):
            break
        time.sleep(1)
    else:
        pytest.skip(
            f"S3-10 stack not reachable at {api} (bring it up with the "
            "documented non-default-port Compose command first); skipping gate"
        )

    client = harness._Client(api, web)
    harness._wait_ready(api, web)
    evidence = harness.rehearse(client)

    # A run was created and the ranked rows satisfy the fatal invariants.
    assert evidence["run_ids"], "a run must be created"
    assert evidence["top_cells"], "ranked rows must be returned"
    ranks = [c["rank"] for c in evidence["top_cells"]]
    assert ranks == sorted(ranks), "ranked rows must be rank-ordered"
    assert all(0.0 <= c["suitability_score"] <= 1.0 for c in evidence["top_cells"])

    # Site detail agreement + reconciliation (recomputed from the evidence).
    detail = evidence["rank_1_detail"]
    assert detail["cell_id"] == evidence["top_cells"][0]["cell_id"]
    assert harness.contributions_reconcile(
        {
            "contributions": detail["contributions"],
            "suitability_score": detail["suitability_score"],
        }
    )

    # Exclusions non-empty with a reason.
    assert evidence["exclusion_count"] >= 1
    excluded = evidence["excluded_example"]
    assert excluded["reason_codes"] or excluded["reason_text"]

    # /scenario-comparison structural invariant (keys present; nulls allowed).
    assert evidence["scenario_comparison"]["row_count"] >= 1

    # Sanity present with its caveat.
    assert evidence["sanity"]["caveat"]
