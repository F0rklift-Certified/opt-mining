"""
Property-based test for the S2-08 ``compare_scenarios`` Service_Operation —
scenario reuse (Property 5).

# Feature: s2-08-decision-service-api, Property 5: scenario reuse

**Property 5 — Scenario reuse.** ``compare_scenarios`` produces each scenario's
ranks via the **S2-05 engine**, NOT a second scorer (CONTRACT.md §4.5, §7 P5,
Requirement 4.3). For ANY pair of named Scenarios, the ranks the operation
surfaces — ``(rank_a, rank_b)`` for every cell — are EXACTLY the ranks
``get_ranked_results`` returns for each Scenario's OWN materialised Run. The
operation runs no scoring or ranking of its own; the only arithmetic it performs
is the display convenience ``rank_delta = rank_a - rank_b``, a difference of two
engine ranks.

**Validates: Requirements 4.3**

Where the sibling deterministic test in ``test_scenarios.py``
(``test_drives_the_engine_once_per_scenario``, tagged P5) pins the engine-reuse
path on one hand-built stub, this test exercises the guarantee across MANY
generated inputs, in two complementary strategies:

* **Stubbed-engine (always runs, hermetic, deterministic).** Hypothesis draws a
  pair of distinct Scenario names and an independent per-scenario rank map for
  each, stubs the engine-reuse path (``run_analysis`` / ``get_ranked_results``
  in ``scenarios.py``) with those ranks, and asserts every ``(rank_a, rank_b)``
  ``compare_scenarios`` surfaces is EXACTLY the stubbed engine rank for that
  cell under that Scenario — with ``rank_delta`` the difference of the two
  engine ranks (or ``None`` when a cell is ranked under only one Scenario). This
  proves the operation goes THROUGH the reused engine rather than a second
  scorer, over hundreds of generated rank maps, without touching disk.

* **Engine-backed (skipped when the frozen table is absent).** Hypothesis
  samples a pair of scenario keys from the packaged ``scenarios.yaml`` and runs
  the REAL operation against real materialised Runs, asserting the surfaced
  ranks equal ``get_ranked_results`` for each Scenario's own Run. This is the
  end-to-end proof that the comparison reuses the S2-05 engine on the frozen
  dataset; it is skipped gracefully (like the other engine-backed service tests)
  when the integrated feature table has not been built.

Hermeticity discipline (matching ``test_results_properties.py`` and
``test_filters_properties.py``): the per-Run store (``service_config.RUNS_DIR``)
is redirected to a per-example temp directory with an explicit save/restore — a
function-scoped fixture cannot be shared across the many examples a single
``@given`` body drives — so the real ``DATA/service/`` tree is never written and
each example is isolated. The stubbed strategy touches no disk at all; the
engine-backed strategy still redirects the store so its materialisations land in
a temp directory.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pipeline.scoring import config as scoring_config
from pipeline.scoring.scenarios import load_scenarios
from pipeline.service import compare_scenarios, get_ranked_results, run_analysis
from pipeline.service import config as service_config
from pipeline.service import scenarios as scenarios_module
from pipeline.service.models import RankedRow, RunHandle, ScenarioComparison


# --------------------------------------------------------------------------- #
# Strategy: a per-scenario rank map (cell_id -> distinct dense rank).          #
# --------------------------------------------------------------------------- #

_cell_ids = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_",
    min_size=1,
    max_size=8,
)


@st.composite
def _rank_map(draw):
    """
    Draw one Scenario's ranking as a ``{cell_id: rank}`` map.

    A ranking assigns DISTINCT dense ranks (1..k) to a set of unique cells — the
    shape the S2-05 engine produces and ``get_ranked_results`` returns. The set
    of cells (and which cell holds which rank) is drawn freely so the two
    scenarios in a pair can rank overlapping, disjoint or identical cell sets in
    any order; that variety is what exercises the join, the null-handling and
    the reuse guarantee. An empty ranking (no eligible cells) is permitted.
    """
    ids = draw(st.lists(_cell_ids, min_size=0, max_size=10, unique=True))
    # A permutation of 1..k assigns each drawn cell a distinct rank.
    order = draw(st.permutations(list(range(1, len(ids) + 1))))
    return {cid: rank for cid, rank in zip(ids, order)}


def _stub_engine(monkeypatch, ranks_by_scenario: dict[str, dict[str, int]]) -> list[str]:
    """
    Stub the engine-reuse path in ``scenarios.py`` with the given per-scenario
    ranks.

    ``run_analysis(scenario=...)`` is replaced with a stub returning a
    ``RunHandle`` for the scenario (and recording which scenarios were
    requested); ``get_ranked_results(handle)`` is replaced with a stub returning
    the ``RankedRow``s carrying the ranks specified for that handle's scenario.
    Returns the capture list so a caller can assert the operation drove the
    engine once per scenario. Mirrors ``_stub_engine`` in ``test_scenarios.py``.
    """
    requested: list[str] = []

    def fake_run_analysis(weights=None, scenario=None, *, verbose=False):
        requested.append(scenario)
        return RunHandle(run_id=f"run_{scenario}", weights_id=scenario, scenario=scenario)

    def fake_get_ranked_results(run, top_n=None, min_score=None):
        ranks = ranks_by_scenario[run.scenario]
        return [
            RankedRow(
                cell_id=cell_id,
                # A monotone-in-rank placeholder score; the property is about
                # ranks, and rank is carried through independently of score.
                suitability_score=1.0 / rank,
                rank=rank,
                key_components={},
            )
            for cell_id, rank in ranks.items()
        ]

    monkeypatch.setattr(scenarios_module, "run_analysis", fake_run_analysis)
    monkeypatch.setattr(scenarios_module, "get_ranked_results", fake_get_ranked_results)
    return requested


# --------------------------------------------------------------------------- #
# Stubbed-engine strategy — reuse proven across many generated rank maps.      #
# --------------------------------------------------------------------------- #


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(ranks_a=_rank_map(), ranks_b=_rank_map())
def test_property_5_scenario_reuse_surfaces_engine_ranks(monkeypatch, ranks_a, ranks_b):
    """
    For any pair of Scenarios and any per-scenario engine ranking:
    ``compare_scenarios`` surfaces EXACTLY the engine ranks for each Scenario's
    own materialised Run — ``rank_a``/``rank_b`` equal the ranks
    ``get_ranked_results`` returns, and ``rank_delta`` is their difference (or
    ``None`` when a cell is ranked under only one Scenario). This proves the
    operation reuses the S2-05 engine per Scenario, never a second scorer
    (Requirement 4.3).
    """
    # Feature: s2-08-decision-service-api, Property 5: scenario reuse
    scenario_a, scenario_b = "scenario_a", "scenario_b"
    requested = _stub_engine(
        monkeypatch,
        {scenario_a: ranks_a, scenario_b: ranks_b},
    )

    result = compare_scenarios(scenario_a, scenario_b)

    assert isinstance(result, ScenarioComparison)
    assert result.labels == {"a": scenario_a, "b": scenario_b}

    # (a) The operation drove the ENGINE once per scenario (the reuse path) —
    #     never a second scorer.
    assert requested == [scenario_a, scenario_b]

    by_cell = {row.cell_id: row for row in result.rows}

    # (b) No cell is invented and none is duplicated: the compared cells are
    #     exactly the union of the two engine rankings.
    assert set(by_cell) == set(ranks_a) | set(ranks_b)
    assert len(result.rows) == len(by_cell)

    # (c) The core P5 guarantee: every surfaced (rank_a, rank_b) is EXACTLY the
    #     engine rank get_ranked_results returned for that cell under that
    #     Scenario — carried through unchanged, never re-derived. A cell absent
    #     from a Scenario's ranking surfaces None on that side.
    for cell_id, row in by_cell.items():
        assert row.rank_a == ranks_a.get(cell_id)
        assert row.rank_b == ranks_b.get(cell_id)

        # rank_delta is the difference of the two engine ranks when both are
        # present, else None — the only arithmetic in the operation.
        if row.rank_a is not None and row.rank_b is not None:
            assert row.rank_delta == row.rank_a - row.rank_b
        else:
            assert row.rank_delta is None


# --------------------------------------------------------------------------- #
# Engine-backed strategy — reuse against the real frozen dataset.             #
# --------------------------------------------------------------------------- #

INTEGRATED_PATH = Path(scoring_config.INTEGRATED_PATH)
ENGINE_INPUT_AVAILABLE = INTEGRATED_PATH.exists()
requires_engine_input = pytest.mark.skipif(
    not ENGINE_INPUT_AVAILABLE,
    reason=f"integrated feature table not built: {INTEGRATED_PATH}",
)

# The packaged Scenario keys the engine-backed strategy samples pairs from.
_PACKAGED_SCENARIOS = sorted(load_scenarios(scoring_config.DEFAULT_SCENARIOS_PATH))


@requires_engine_input
@settings(
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(pair=st.lists(st.sampled_from(_PACKAGED_SCENARIOS), min_size=2, max_size=2))
def test_property_5_scenario_reuse_from_real_runs(pair):
    """
    For a pair of packaged Scenarios run against the REAL frozen dataset, the
    ranks ``compare_scenarios`` surfaces are exactly those ``get_ranked_results``
    returns for each Scenario's own materialised Run — the comparison reuses the
    S2-05 engine, not a second scorer (Requirement 4.3, 8.4). Each example
    redirects the per-Run store to a temp directory (hermetic); Runs are reused
    idempotently by content, so re-materialising the same scenario is free.
    """
    # Feature: s2-08-decision-service-api, Property 5: scenario reuse
    scenario_a, scenario_b = pair

    original_runs_dir = service_config.RUNS_DIR
    with tempfile.TemporaryDirectory() as tmp_name:
        service_config.RUNS_DIR = Path(tmp_name) / "runs"
        try:
            result = compare_scenarios(scenario_a, scenario_b)

            assert isinstance(result, ScenarioComparison)
            assert result.labels == {"a": scenario_a, "b": scenario_b}

            # The engine ranks for each Scenario's own materialised Run — the
            # SAME reuse path compare_scenarios drives internally.
            ranks_a = {
                r.cell_id: r.rank
                for r in get_ranked_results(run_analysis(scenario=scenario_a))
            }
            ranks_b = {
                r.cell_id: r.rank
                for r in get_ranked_results(run_analysis(scenario=scenario_b))
            }

            # Every surfaced (rank_a, rank_b) equals the engine rank for that
            # cell under that Scenario — reuse, not a second scorer.
            for row in result.rows:
                assert row.rank_a == ranks_a.get(row.cell_id)
                assert row.rank_b == ranks_b.get(row.cell_id)
                if row.rank_a is not None and row.rank_b is not None:
                    assert row.rank_delta == row.rank_a - row.rank_b
                else:
                    assert row.rank_delta is None

            # The compared cells are exactly the union of the two engine
            # rankings — no cell invented, none dropped.
            assert {row.cell_id for row in result.rows} == set(ranks_a) | set(ranks_b)
        finally:
            service_config.RUNS_DIR = original_runs_dir
