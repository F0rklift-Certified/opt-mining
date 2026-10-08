"""
Property-based test for the S2-08 read operations — one engine output across
``get_ranked_results`` and ``get_site_detail`` (Property 1).

# Feature: s2-08-decision-service-api, Property 1: one engine output

**Property 1 — One engine output.** For a materialised Run, the
``suitability_score`` and ``rank`` served for any ``cell_id`` are IDENTICAL
across ``get_ranked_results`` and ``get_site_detail`` (CONTRACT.md §4.3
consistency guarantee, §7 P1). The ranking table and the single-site detail
view therefore always show the same engine output — the service reads both from
the SAME materialised Scored_Table and never recomputes a score or a rank.

**Validates: Requirements 2.3**

Where the sibling deterministic test in ``test_results.py``
(``test_site_detail_score_and_rank_match_ranked_results``) pins the guarantee on
one hand-picked fixture, this test exercises it across MANY generated Runs:
Hypothesis draws varied Scored_Tables — mixed eligible and excluded cells,
varied scores in ``[0, 1]``, distinct dense ranks, varied ``contrib_{feature}``
shares — materialises each into a fake Run, and asserts the two operations agree
for every ``cell_id``. Runs at least 100 examples.

Hermeticity discipline (matching ``test_run_analysis_properties.py``): the
per-Run store (``service_config.RUNS_DIR``) and the shared explanation output
(``service_config.EXPLANATION_PATH``) are redirected to a per-example temp
directory with an explicit save/restore — a function-scoped fixture cannot be
shared across the many examples a single ``@given`` body drives — so the real
``DATA/service/`` tree is never written and each example is fully isolated. No
engine run is required: the property is about the service's read-path
consistency over a fixed materialised output, so hand-materialised Scored_Tables
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
from pipeline.service import get_ranked_results, get_site_detail


# --- Strategy: one cell of a Scored_Table -------------------------------------
#
# A cell is either ELIGIBLE (a score in [0, 1] and, later, a dense rank) or
# EXCLUDED (null score / null rank). Scores are drawn on a coarse grid so ties
# are possible (exercising the engine's own rank ordering, which the service
# must preserve verbatim rather than re-derive).

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
    ranks unchanged; the property never depends on HOW they were assigned.
    """
    n = draw(st.integers(min_value=1, max_value=12))
    ids = draw(
        st.lists(_cell_ids, min_size=n, max_size=n, unique=True)
    )

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


def _materialise(store: Path, tmp: Path, run_id: str, rows: list[dict]) -> None:
    """
    Write a fake Run with everything both read operations touch: a Scored_Table,
    the integrated feature table the Run "scored", and the S2-06 explanation
    output — plus a manifest wiring the integrated path and one criterion.

    Mirrors the fixtures in ``test_results.py`` but is fed by the Hypothesis
    strategy rather than a hand-picked example.
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
    integrated_rows = [
        {
            "cell_id": r["cell_id"],
            "eligible": r["rank"] is not None,
            "wind_speed": 8.0,
        }
        for r in rows
    ]
    integrated = gpd.GeoDataFrame(
        integrated_rows, geometry=geometry, crs=scoring_config.STORAGE_CRS
    )
    integrated.to_file(
        integrated_path, driver="GPKG", layer=service_config.INTEGRATED_LAYER
    )

    explanation_path = tmp / f"explanations_{run_id}.json"
    explanations = [
        {
            "cell_id": r["cell_id"],
            "eligible": r["rank"] is not None,
            "headline": "H",
            "positive_factors": [],
            "weaknesses": [],
            "proxy_caveats": [],
            "data_quality_notes": [],
        }
        for r in rows
    ]
    explanation_path.write_text(json.dumps(explanations) + "\n", encoding="utf-8")

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


@settings(max_examples=100, deadline=None)
@given(rows=_scored_tables())
def test_property_1_one_engine_output(rows):
    """
    For every drawn Run: the score and rank of any ``cell_id`` are identical
    across ``get_ranked_results`` and ``get_site_detail`` (Requirement 2.3).
    """
    # Feature: s2-08-decision-service-api, Property 1: one engine output

    # Redirect the store + explanation output per example with explicit
    # save/restore (not a function-scoped fixture, which Hypothesis reuses
    # across examples) so the real DATA/service/ tree is never written.
    original_runs_dir = service_config.RUNS_DIR
    original_explanation_path = service_config.EXPLANATION_PATH
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        store = tmp / "runs"
        service_config.RUNS_DIR = store
        run_id = "runpropp1000000"
        try:
            explanation_path = _materialise(store, tmp, run_id, rows)
            service_config.EXPLANATION_PATH = explanation_path

            ranked = get_ranked_results(run_id)

            # (a) Every RANKED (eligible) cell agrees, score and rank, with its
            #     single-site detail — the core P1 consistency guarantee.
            for row in ranked:
                detail = get_site_detail(run_id, row.cell_id)
                assert detail.suitability_score == row.suitability_score
                assert detail.rank == row.rank
                # The detail's contributions are the ranked key_components too:
                # one engine output extends to the component shares.
                assert detail.contributions == row.key_components

            # (b) An EXCLUDED cell is consistent the other way: absent from the
            #     ranking, and its detail carries null score AND null rank — the
            #     service never invents a score or rank the engine did not give.
            ranked_ids = {row.cell_id for row in ranked}
            for r in rows:
                if r["cell_id"] not in ranked_ids:
                    detail = get_site_detail(run_id, r["cell_id"])
                    assert detail.suitability_score is None
                    assert detail.rank is None
        finally:
            service_config.RUNS_DIR = original_runs_dir
            service_config.EXPLANATION_PATH = original_explanation_path
