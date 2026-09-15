"""
Property-based test for the Backend_App's pass-through purity — the API layer
adds no decision arithmetic (Property 2).

# Feature: s3-01a-application-shell-scaffold, Property 2: The API layer adds no
# decision arithmetic (pure pass-through)

**Property 2.** For ANY value a `pipeline.service` operation could return, the
matching HTTP endpoint's response body equals EXACTLY that operation's
`to_dict()` serialisation — the same fields, the same values, nothing added,
nothing dropped, nothing modified. The API is a pure mapping layer: it parses
the request, calls the operation with the request's arguments passed through
UNCHANGED, and serialises the returned dataclass. It holds no weight literal, no
criteria list, and no normalisation/ranking/threshold arithmetic — every value
in the response traces to the operation, never to the transport layer
(CONTRACT.md §1, §7-P3; Requirement 2.4, 8.2).

**Validates: Requirements 2.4, 8.2**

Method
------
Each `pipeline.service` operation is monkeypatched to return a
Hypothesis-generated service dataclass value (a `RunHandle`, `RankedRow` list,
`SiteDetail`, `ExcludedRow` list, `ScenarioComparison`, or `DataQualityStatus`).
The endpoint is called via FastAPI's `TestClient`, and its JSON body is asserted
equal to `operation(mapped_args).to_dict()` — the operation's own serialisation
of the SAME value the stub returned. If the API added, dropped, renamed, or
recomputed any field, the two would differ.

The import-namespace detail
----------------------------
`app/api/app.py` imports the operations INTO its own module namespace:

    from pipeline.service import (run_analysis, get_ranked_results, ...)

so each handler calls the name bound on the `app` module, NOT the attribute on
`pipeline.service`. Monkeypatching `pipeline.service.run_analysis` would rebind
the package attribute but leave `app.run_analysis` pointing at the original
function — the patch would not take effect. This test therefore patches the
names ON THE `app` MODULE (`monkeypatch.setattr(app_module, "run_analysis", …)`),
which is exactly what the handlers resolve at call time.

`app.py` is launched with its own directory as the working directory
(`uvicorn app:app`, per the design run command and the api Dockerfile), so it
does sibling imports (`import settings`, `from models import …`). We reproduce
that launch layout by putting `app/api/` on `sys.path` before importing `app`,
mirroring `tests/backend/test_env_config_properties.py`'s by-path approach.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pipeline.service.models import (
    DataQualityCheck,
    DataQualityStatus,
    ExcludedRow,
    RankedRow,
    RunHandle,
    ScenarioComparison,
    ScenarioComparisonRow,
    SiteDetail,
)

# ---------------------------------------------------------------------------
# Import app/api/app.py the way it is launched: working dir = app/api/, so
# `settings` and `models` resolve as sibling top-level modules and the six
# operations get bound onto the `app` module namespace.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "app" / "api"


def _load_app_module():
    """Import app/api/app.py as the top-level module `app` (matches launch)."""
    api_dir = str(API_DIR)
    if api_dir not in sys.path:
        sys.path.insert(0, api_dir)
    # A fresh import so the module's imported operation names are the real ones
    # before any monkeypatching in this test session.
    if "app" in sys.modules:
        return importlib.reload(sys.modules["app"])
    return importlib.import_module("app")


app_module = _load_app_module()
client = TestClient(app_module.app)


# ---------------------------------------------------------------------------
# Strategies: generate each service dataclass the operations return. These build
# the SAME dataclasses `pipeline.service` returns, so `to_dict()` is the exact
# serialisation the real operation would emit — the property pins the endpoint
# body to that serialisation.
# ---------------------------------------------------------------------------

# JSON-round-trippable scalars for free-form maps (features / explanation).
_json_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-1_000_000, max_value=1_000_000),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.text(max_size=20),
)

_cell_ids = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-",
    min_size=1,
    max_size=16,
)
_scores = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_ranks = st.integers(min_value=1, max_value=100_000)
_component_maps = st.dictionaries(
    keys=st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=12),
    values=st.floats(allow_nan=False, allow_infinity=False, width=32),
    max_size=6,
)


def _run_handles():
    return st.builds(
        RunHandle,
        run_id=st.text(min_size=1, max_size=24),
        weights_id=st.text(min_size=1, max_size=64),
        scenario=st.one_of(st.none(), st.text(min_size=1, max_size=24)),
    )


def _ranked_rows():
    return st.builds(
        RankedRow,
        cell_id=_cell_ids,
        suitability_score=_scores,
        rank=_ranks,
        key_components=_component_maps,
    )


def _site_details():
    return st.builds(
        SiteDetail,
        cell_id=_cell_ids,
        features=st.dictionaries(
            keys=st.text(min_size=1, max_size=16), values=_json_scalars, max_size=6
        ),
        contributions=_component_maps,
        suitability_score=st.one_of(st.none(), _scores),
        rank=st.one_of(st.none(), _ranks),
        eligible=st.booleans(),
        explanation=st.dictionaries(
            keys=st.text(min_size=1, max_size=16), values=_json_scalars, max_size=6
        ),
    )


def _excluded_rows():
    return st.builds(
        ExcludedRow,
        cell_id=_cell_ids,
        reason_codes=st.lists(st.text(min_size=1, max_size=16), max_size=5),
        reason_text=st.text(max_size=64),
    )


def _scenario_comparisons():
    _nullable_rank = st.one_of(st.none(), _ranks)
    rows = st.lists(
        st.builds(
            ScenarioComparisonRow,
            cell_id=_cell_ids,
            rank_a=_nullable_rank,
            rank_b=_nullable_rank,
            rank_delta=st.one_of(st.none(), st.integers(min_value=-1000, max_value=1000)),
        ),
        max_size=6,
    )
    labels = st.fixed_dictionaries(
        {"a": st.text(min_size=1, max_size=16), "b": st.text(min_size=1, max_size=16)}
    )
    return st.builds(ScenarioComparison, labels=labels, rows=rows)


def _data_quality_statuses():
    checks = st.lists(
        st.builds(
            DataQualityCheck,
            name=st.text(min_size=1, max_size=24),
            expected=st.text(max_size=24),
            observed=st.text(max_size=24),
            passed=st.booleans(),
        ),
        max_size=6,
    )
    return st.builds(DataQualityStatus, passed=st.booleans(), checks=checks)


# Common Hypothesis settings: >= 100 iterations (the task floor). function_scoped
# fixtures aren't used inside @given here (we patch by hand), so no health check
# is suppressed for that; we set a generous deadline because each example issues
# a real (in-process) HTTP request through the TestClient.
_PBT = settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])


# ---------------------------------------------------------------------------
# Patch helper: rebind the operation NAME on the `app` module (where the handler
# resolves it), returning a callable that both records the call args and returns
# the generated value. Restored by the caller in a finally block so examples
# never leak into each other.
# ---------------------------------------------------------------------------


class _RecordingStub:
    """A stub that records the (args, kwargs) it was called with and returns `value`."""

    def __init__(self, value):
        self.value = value
        self.calls: list[tuple[tuple, dict]] = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.value


def _seg(value: str) -> str:
    """Percent-encode a value for use as a single URL path segment.

    Generated `run_id` / `cell_id` values can contain `.` (real cell ids look
    like ``S30.186_E151.636``) or, adversarially, a bare ``.``/``..`` or a
    reserved character. URL path-resolution would normalise those away before
    the request reached the route, so we encode each segment (``safe=""``) so
    the value arrives at the FastAPI path parameter byte-for-byte — the property
    is about pass-through, not about URL-normalisation quirks.
    """
    return quote(value, safe="")


def _patched(name: str, value):
    """Context-manager-free patch of `app_module.<name>`; returns (stub, restore)."""
    original = getattr(app_module, name)
    stub = _RecordingStub(value)
    setattr(app_module, name, stub)

    def restore():
        setattr(app_module, name, original)

    return stub, restore


# ---------------------------------------------------------------------------
# POST /runs  ->  run_analysis(weights, scenario)
# ---------------------------------------------------------------------------


@_PBT
@given(handle=_run_handles(), scenario=st.one_of(st.none(), st.text(min_size=1, max_size=16)))
def test_post_runs_is_pure_passthrough(handle: RunHandle, scenario):
    # Feature: s3-01a-application-shell-scaffold, Property 2: pure pass-through
    stub, restore = _patched("run_analysis", handle)
    try:
        body = {"scenario": scenario} if scenario is not None else {"weights": {"criteria": []}}
        response = client.post("/runs", json=body)

        assert response.status_code == 200
        # The body is EXACTLY the operation's own serialisation of its return.
        assert response.json() == handle.to_dict()
        # The request args are passed through UNCHANGED (scenario straight through;
        # weights either the mapped dict or None) — the layer maps, never decides.
        assert len(stub.calls) == 1
        _args, kwargs = stub.calls[0]
        assert kwargs["scenario"] == scenario
        if scenario is None:
            assert kwargs["weights"] == {"criteria": []}
        else:
            assert kwargs["weights"] is None
    finally:
        restore()


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/results  ->  get_ranked_results(run_id, top_n, min_score)
# ---------------------------------------------------------------------------


@_PBT
@given(
    rows=st.lists(_ranked_rows(), max_size=8),
    run_id=st.text(alphabet="abcdef0123456789", min_size=1, max_size=16),
    top_n=st.one_of(st.none(), st.integers(min_value=0, max_value=1000)),
    min_score=st.one_of(st.none(), _scores),
)
def test_get_results_is_pure_passthrough(rows, run_id, top_n, min_score):
    # Feature: s3-01a-application-shell-scaffold, Property 2: pure pass-through
    stub, restore = _patched("get_ranked_results", rows)
    try:
        params = {}
        if top_n is not None:
            params["top_n"] = top_n
        if min_score is not None:
            params["min_score"] = min_score
        response = client.get(f"/runs/{_seg(run_id)}/results", params=params)

        assert response.status_code == 200
        assert response.json() == [row.to_dict() for row in rows]
        # run_id and the display filters go straight through to the operation.
        assert len(stub.calls) == 1
        args, kwargs = stub.calls[0]
        assert args[0] == run_id
        assert kwargs["top_n"] == top_n
        assert kwargs["min_score"] == min_score
    finally:
        restore()


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/sites/{cell_id}  ->  get_site_detail(run_id, cell_id)
# ---------------------------------------------------------------------------


@_PBT
@given(
    detail=_site_details(),
    run_id=st.text(alphabet="abcdef0123456789", min_size=1, max_size=16),
    cell_id=_cell_ids,
)
def test_get_site_detail_is_pure_passthrough(detail: SiteDetail, run_id, cell_id):
    # Feature: s3-01a-application-shell-scaffold, Property 2: pure pass-through
    stub, restore = _patched("get_site_detail", detail)
    try:
        response = client.get(f"/runs/{_seg(run_id)}/sites/{_seg(cell_id)}")

        assert response.status_code == 200
        assert response.json() == detail.to_dict()
        assert len(stub.calls) == 1
        args, _kwargs = stub.calls[0]
        assert args[0] == run_id
        assert args[1] == cell_id
    finally:
        restore()


# ---------------------------------------------------------------------------
# GET /runs/{run_id}/exclusions  ->  get_exclusions(run_id)
# ---------------------------------------------------------------------------


@_PBT
@given(
    rows=st.lists(_excluded_rows(), max_size=8),
    run_id=st.text(alphabet="abcdef0123456789", min_size=1, max_size=16),
)
def test_get_exclusions_is_pure_passthrough(rows, run_id):
    # Feature: s3-01a-application-shell-scaffold, Property 2: pure pass-through
    stub, restore = _patched("get_exclusions", rows)
    try:
        response = client.get(f"/runs/{_seg(run_id)}/exclusions")

        assert response.status_code == 200
        assert response.json() == [row.to_dict() for row in rows]
        assert len(stub.calls) == 1
        args, _kwargs = stub.calls[0]
        assert args[0] == run_id
    finally:
        restore()


# ---------------------------------------------------------------------------
# POST /scenario-comparison  ->  compare_scenarios(scenario_a, scenario_b)
# ---------------------------------------------------------------------------


@_PBT
@given(
    comparison=_scenario_comparisons(),
    scenario_a=st.text(min_size=1, max_size=16),
    scenario_b=st.text(min_size=1, max_size=16),
)
def test_post_scenario_comparison_is_pure_passthrough(comparison, scenario_a, scenario_b):
    # Feature: s3-01a-application-shell-scaffold, Property 2: pure pass-through
    stub, restore = _patched("compare_scenarios", comparison)
    try:
        response = client.post(
            "/scenario-comparison",
            json={"scenario_a": scenario_a, "scenario_b": scenario_b},
        )

        assert response.status_code == 200
        assert response.json() == comparison.to_dict()
        assert len(stub.calls) == 1
        args, _kwargs = stub.calls[0]
        assert args[0] == scenario_a
        assert args[1] == scenario_b
    finally:
        restore()


# ---------------------------------------------------------------------------
# GET /data-quality  ->  get_data_quality()
# ---------------------------------------------------------------------------


@_PBT
@given(status=_data_quality_statuses())
def test_get_data_quality_is_pure_passthrough(status: DataQualityStatus):
    # Feature: s3-01a-application-shell-scaffold, Property 2: pure pass-through
    stub, restore = _patched("get_data_quality", status)
    try:
        response = client.get("/data-quality")

        assert response.status_code == 200
        assert response.json() == status.to_dict()
        assert len(stub.calls) == 1
    finally:
        restore()
