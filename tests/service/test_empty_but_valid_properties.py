"""
Property-based test for the S2-08 Display_Filters — empty-but-valid results
(Property 4).

# Feature: s2-08-decision-service-api, Property 4: empty-but-valid

**Property 4 — Empty-but-valid.** Two boundary behaviours of a Display_Filter
over a materialised Run must be empty-but-VALID, never padded and never an
error (CONTRACT.md §4.2, §6, §7 P4):

  ARM A (Requirement 3.3). For ANY ``top_n`` that meets or exceeds the eligible
  count, ``get_ranked_results`` returns EVERY eligible cell with NO padding —
  exactly the unfiltered eligible set, same size, in the same order, with no
  invented or duplicated row. A ``top_n`` past the count clamps to the count;
  it never fabricates a cell to reach ``top_n``.

  ARM B (Requirement 3.4). For ANY ``min_score`` STRICTLY GREATER than the
  maximum eligible score, ``get_ranked_results`` returns an EMPTY list — a
  legitimate empty-but-valid result, NOT an error and NOT an exception. An
  all-excluding threshold narrows the set to nothing; it does not fail.

**Validates: Requirements 3.3, 3.4**

Where the sibling ``test_filters_properties.py`` (Property 2) asserts that a
filter never alters a returned cell's score or rank, this test pins the two
BOUNDARY outcomes the contract calls out by name: the no-padding clamp (Arm A)
and the all-excluding empty set (Arm B). Hypothesis draws varied Scored_Tables
(mixed eligible and excluded cells, varied scores in ``[0, 1]`` with ties,
distinct dense ranks) and, per arm, a filter parameter drawn to guarantee the
boundary: for Arm A a ``top_n`` at or above the eligible count; for Arm B a
``min_score`` strictly above the maximum eligible score. Runs at least 100
examples per arm.

Hermeticity discipline (matching ``test_results_properties.py`` and
``test_filters_properties.py``): the per-Run store (``service_config.RUNS_DIR``)
and the shared explanation output (``service_config.EXPLANATION_PATH``) are
redirected to a per-example temp directory with an explicit save/restore — a
function-scoped fixture cannot be shared across the many examples a single
``@given`` body drives — so the real ``DATA/service/`` tree is never written and
each example is fully isolated. No engine run is required: the property is about
the service's read-and-select path over a fixed materialised output, so
hand-materialised Scored_Tables exercise it directly and deterministically.
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
# EXCLUDED (null score / null rank). Scores are drawn allowing ties so the
# clamp and the threshold are exercised against a realistic engine output whose
# rank ordering the service must preserve verbatim rather than re-derive.

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
    rank-by-score convention), ties broken by cell_id for determinism. Excluded
    cells get no rank. The service must serve these ranks unchanged under any
    filter; the property never depends on HOW they were assigned.
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

    eligible_rows = [r for r in rows if r["_eligible"]]
    eligible_rows.sort(key=lambda r: (-r["suitability_score"], r["cell_id"]))
    for rank, r in enumerate(eligible_rows, start=1):
        r["rank"] = rank
    for r in rows:
        if not r["_eligible"]:
            r["rank"] = None
        r.pop("_eligible")

    return rows


def _materialise(store: Path, tmp: Path, run_id: str, rows: list[dict]) -> Path:
    """
    Write a fake Run's Scored_Table plus a minimal manifest — everything
    ``get_ranked_results`` touches. Mirrors the fixtures in
    ``test_filters_properties.py`` but is fed by the Hypothesis strategy.

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


def _eligible_count(rows: list[dict]) -> int:
    """The number of eligible (ranked) cells in a drawn Scored_Table."""
    return sum(1 for r in rows if r["rank"] is not None)


def _max_eligible_score(rows: list[dict]) -> float | None:
    """The maximum score over the eligible cells, or ``None`` if there are none."""
    scores = [r["suitability_score"] for r in rows if r["rank"] is not None]
    return max(scores) if scores else None


# --- Arm A: top-N at/over the eligible count returns all eligible, no padding -


@settings(max_examples=100, deadline=None)
@given(rows=_scored_tables(), over=st.integers(min_value=0, max_value=20))
def test_property_4a_top_n_over_count_returns_all_eligible_no_padding(rows, over):
    """
    For any ``top_n`` >= the eligible count, ``get_ranked_results`` returns
    EXACTLY the unfiltered eligible set — same cells, same size, no padding and
    no invented rows (Requirement 3.3).
    """
    # Feature: s2-08-decision-service-api, Property 4: empty-but-valid

    original_runs_dir = service_config.RUNS_DIR
    original_explanation_path = service_config.EXPLANATION_PATH
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        store = tmp / "runs"
        service_config.RUNS_DIR = store
        run_id = "runpropp4a00000"
        try:
            explanation_path = _materialise(store, tmp, run_id, rows)
            service_config.EXPLANATION_PATH = explanation_path

            # The UNFILTERED baseline: the fixed eligible Run output.
            baseline = get_ranked_results(run_id)
            eligible_count = _eligible_count(rows)
            assert len(baseline) == eligible_count  # sanity: strategy vs service

            # Draw a top_n AT or ABOVE the eligible count (over >= 0). A top_n
            # of zero is not a valid count, so clamp the floor to 1.
            top_n = max(1, eligible_count) + over

            filtered = get_ranked_results(run_id, top_n=top_n)

            # (a) NO PADDING: the result is exactly the eligible set, same size —
            #     never grown toward top_n with fabricated rows (Requirement 3.3).
            assert len(filtered) == eligible_count

            # (b) SAME CELLS, SAME ORDER: the survivors are the unfiltered
            #     baseline verbatim — no cell invented, none dropped, none
            #     duplicated, order (ascending rank) preserved.
            baseline_ids = [row.cell_id for row in baseline]
            filtered_ids = [row.cell_id for row in filtered]
            assert filtered_ids == baseline_ids
            assert len(filtered_ids) == len(set(filtered_ids))

            # (c) Every returned cell carries its unfiltered score and rank —
            #     the clamp is a pure selection, not a re-score.
            baseline_by_cell = {
                row.cell_id: (row.suitability_score, row.rank) for row in baseline
            }
            for row in filtered:
                base_score, base_rank = baseline_by_cell[row.cell_id]
                assert row.suitability_score == base_score
                assert row.rank == base_rank
        finally:
            service_config.RUNS_DIR = original_runs_dir
            service_config.EXPLANATION_PATH = original_explanation_path


# --- Arm B: an all-excluding threshold returns an empty set, not an error -----


@settings(max_examples=100, deadline=None)
@given(rows=_scored_tables(), above=st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
))
def test_property_4b_all_excluding_threshold_returns_empty_not_error(rows, above):
    """
    For any ``min_score`` STRICTLY GREATER than the maximum eligible score,
    ``get_ranked_results`` returns an EMPTY list — an empty-but-valid result,
    never an error or exception (Requirement 3.4).
    """
    # Feature: s2-08-decision-service-api, Property 4: empty-but-valid

    original_runs_dir = service_config.RUNS_DIR
    original_explanation_path = service_config.EXPLANATION_PATH
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        store = tmp / "runs"
        service_config.RUNS_DIR = store
        run_id = "runpropp4b00000"
        try:
            explanation_path = _materialise(store, tmp, run_id, rows)
            service_config.EXPLANATION_PATH = explanation_path

            max_score = _max_eligible_score(rows)

            # A threshold STRICTLY above the maximum eligible score excludes
            # every cell. When there are no eligible cells at all, any threshold
            # trivially excludes every (zero) cell; use 1.0 + a positive margin
            # so the intent — "above the max" — holds in both cases.
            base = max_score if max_score is not None else 1.0
            min_score = base + (above + 1e-9)

            # The call must NOT raise — an all-excluding threshold is valid.
            filtered = get_ranked_results(run_id, min_score=min_score)

            # EMPTY-BUT-VALID: an empty list, not an error, not a fabricated row
            # (Requirement 3.4).
            assert filtered == []

            # Cross-check the boundary is strict: the unfiltered baseline held
            # only cells at or below `max_score`, so none can survive a threshold
            # strictly above it.
            baseline = get_ranked_results(run_id)
            assert all(row.suitability_score < min_score for row in baseline)
        finally:
            service_config.RUNS_DIR = original_runs_dir
            service_config.EXPLANATION_PATH = original_explanation_path
