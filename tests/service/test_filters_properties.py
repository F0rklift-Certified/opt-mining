"""
Property-based test for the S2-08 Display_Filters — filters do not re-score
(Property 2).

# Feature: s2-08-decision-service-api, Property 2: filters do not re-score

**Property 2 — Filters do not re-score.** For ANY Display_Filter (a ``top_n``
and/or a ``min_score``) over a materialised Run, the ``suitability_score`` and
``rank`` of every cell the filtered ``get_ranked_results`` returns are IDENTICAL
to that same ``cell_id``'s values in the UNFILTERED ``get_ranked_results`` for
the Run (CONTRACT.md §4.2, §7 P2). A Display_Filter is a pure selection over the
fixed Run output: it changes WHICH cells are shown, never their score or rank,
so the service holds no path by which a filter could re-run normalisation or
scoring on the filtered subset (Requirement 3.1, 3.2).

**Validates: Requirements 3.1, 3.2**

Where the sibling unit tests in ``test_filters.py`` pin the selection rules on
hand-built ``RankedRow`` lists, this test exercises the guarantee end-to-end
over MANY generated Runs AND many generated filter parameters: Hypothesis draws
varied Scored_Tables (mixed eligible and excluded cells, varied scores in
``[0, 1]`` with ties, distinct dense ranks, varied ``contrib_{feature}`` shares)
and varied ``(top_n, min_score)`` filters (each independently present or absent,
with ``min_score`` drawn to span below/within/above the score range so the
filter sometimes keeps all, some, or no cells), materialises each Run, and
asserts every filtered row's score and rank match the unfiltered baseline for
its ``cell_id``. Runs at least 100 examples.

Hermeticity discipline (matching ``test_results_properties.py`` and
``test_run_analysis_properties.py``): the per-Run store
(``service_config.RUNS_DIR``) and the shared explanation output
(``service_config.EXPLANATION_PATH``) are redirected to a per-example temp
directory with an explicit save/restore — a function-scoped fixture cannot be
shared across the many examples a single ``@given`` body drives — so the real
``DATA/service/`` tree is never written and each example is fully isolated. No
engine run is required: the property is about the service's read-and-select
path over a fixed materialised output, so hand-materialised Scored_Tables
exercise it directly and deterministically.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import geopandas as gpd
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Point

from pipeline.scoring import config as scoring_config
from pipeline.service import config as service_config
from pipeline.service import get_ranked_results


# --- Strategy: one cell of a Scored_Table -------------------------------------
#
# A cell is either ELIGIBLE (a score in [0, 1] and, later, a dense rank) or
# EXCLUDED (null score / null rank). Scores are drawn on a coarse grid so ties
# are possible (exercising the engine's own rank ordering, which the service
# must preserve verbatim under any filter rather than re-derive).

_cell_ids = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_",
    min_size=1,
    max_size=8,
)
_scores = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_contribs = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


@st.composite
def _scored_tables(draw):
    """
    Draw a Scored_Table as a list of row dicts with unique ``cell_id``s.

    Each cell is independently eligible or excluded. Eligible cells carry a
    score and a ``contrib_wind_speed`` share; excluded cells carry ``None`` for
    score, rank and contribution. Eligible cells are then assigned DISTINCT
    dense ranks (1..k) ordered by descending score (the engine's own
    rank-by-score convention), with ties broken by cell_id so the rank
    assignment is deterministic per drawn table. The service must serve these
    ranks unchanged under any filter; the property never depends on HOW they
    were assigned.
    """
    n = draw(st.integers(min_value=1, max_value=12))
    ids = draw(st.lists(_cell_ids, min_size=n, max_size=n, unique=True))

    rows: list[dict] = []
    for cid in ids:
        eligible = draw(st.booleans())
        if eligible:
            rows.append(
                {
                    "cell_id": cid,
                    "suitability_score": draw(_scores),
                    "contrib_wind_speed": draw(_contribs),
                    "_eligible": True,
                }
            )
        else:
            rows.append(
                {
                    "cell_id": cid,
                    "suitability_score": None,
                    "contrib_wind_speed": None,
                    "_eligible": False,
                }
            )

    # Assign dense ranks (1..k) to the eligible cells, descending by score
    # (ties broken by cell_id for determinism). Excluded cells get no rank.
    eligible_rows = [r for r in rows if r["_eligible"]]
    eligible_rows.sort(key=lambda r: (-r["suitability_score"], r["cell_id"]))
    for rank, r in enumerate(eligible_rows, start=1):
        r["rank"] = rank
    for r in rows:
        if not r["_eligible"]:
            r["rank"] = None
        r.pop("_eligible")

    return rows


# --- Strategy: a Display_Filter -----------------------------------------------
#
# Each of top_n / min_score is independently present or absent. top_n is a
# positive integer that can exceed the eligible count (exercising the no-padding
# clamp); min_score spans a little below 0 to a little above 1 so the threshold
# sometimes keeps all, some, or no cells — every branch of the filter is a pure
# selection that must preserve score and rank.

_top_n = st.one_of(st.none(), st.integers(min_value=1, max_value=20))
_min_score = st.one_of(
    st.none(),
    st.floats(min_value=-0.1, max_value=1.1, allow_nan=False, allow_infinity=False),
)


def _materialise(store: Path, tmp: Path, run_id: str, rows: list[dict]) -> Path:
    """
    Write a fake Run's Scored_Table plus a minimal manifest — everything
    ``get_ranked_results`` touches. Mirrors the fixtures in ``test_results.py``
    and ``test_results_properties.py`` but is fed by the Hypothesis strategy.

    ``get_ranked_results`` reads only the Scored_Table (and the manifest to
    confirm the Run exists), so the integrated table and explanation output the
    single-site path needs are not required here; the shared explanation path is
    still redirected for hermeticity.
    """
    target = store / run_id
    target.mkdir(parents=True, exist_ok=True)

    geometry = [Point(150.0 + i * 0.1, -30.0) for i in range(len(rows))]

    scored = gpd.GeoDataFrame(rows, geometry=geometry, crs=scoring_config.STORAGE_CRS)
    scored.to_file(
        target / service_config.SCORED_GPKG_FILENAME,
        driver="GPKG",
        layer=service_config.SCORED_LAYER,
    )

    integrated_path = tmp / f"integrated_{run_id}.gpkg"
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

    explanation_path = tmp / f"explanations_{run_id}.json"
    explanation_path.write_text(json.dumps([]) + "\n", encoding="utf-8")
    return explanation_path


@settings(max_examples=100, deadline=None)
@given(rows=_scored_tables(), top_n=_top_n, min_score=_min_score)
def test_property_2_filters_do_not_re_score(rows, top_n, min_score):
    """
    For every drawn Run and every drawn Display_Filter: the score and rank of
    each cell the filtered ``get_ranked_results`` returns are identical to the
    unfiltered baseline for that ``cell_id`` (Requirement 3.1, 3.2).
    """
    # Feature: s2-08-decision-service-api, Property 2: filters do not re-score

    # Redirect the store + explanation output per example with explicit
    # save/restore (not a function-scoped fixture, which Hypothesis reuses
    # across examples) so the real DATA/service/ tree is never written.
    original_runs_dir = service_config.RUNS_DIR
    original_explanation_path = service_config.EXPLANATION_PATH
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        store = tmp / "runs"
        service_config.RUNS_DIR = store
        run_id = "runpropp2000000"
        try:
            explanation_path = _materialise(store, tmp, run_id, rows)
            service_config.EXPLANATION_PATH = explanation_path

            # The UNFILTERED baseline: the fixed Run output, before any filter.
            baseline = get_ranked_results(run_id)
            baseline_by_cell = {
                row.cell_id: (row.suitability_score, row.rank) for row in baseline
            }
            baseline_ids = set(baseline_by_cell)

            # The FILTERED call over the SAME Run.
            filtered = get_ranked_results(run_id, top_n=top_n, min_score=min_score)

            filtered_ids = [row.cell_id for row in filtered]

            # (a) No cell is invented and none is duplicated: the filtered set is
            #     a strict subset of the unfiltered baseline.
            assert set(filtered_ids) <= baseline_ids
            assert len(filtered_ids) == len(set(filtered_ids))

            # (b) The core P2 guarantee: every returned cell's score AND rank are
            #     IDENTICAL to its unfiltered Run values — the filter never
            #     re-scored or re-ranked (Requirement 3.1, 3.2).
            for row in filtered:
                base_score, base_rank = baseline_by_cell[row.cell_id]
                assert row.suitability_score == base_score
                assert row.rank == base_rank

            # (c) A filter only narrows: the survivors stay in the baseline's
            #     ascending-rank order — filtering changes which cells show, not
            #     their ordering.
            filtered_ranks = [row.rank for row in filtered]
            assert filtered_ranks == sorted(filtered_ranks)
        finally:
            service_config.RUNS_DIR = original_runs_dir
            service_config.EXPLANATION_PATH = original_explanation_path
