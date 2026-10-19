"""
S4-03 regression guards: each Run explains its cells with ITS OWN weights.

Before S4-03 every Run served one packaged explanation file built with the
default weights, so a Wind-led or Grid-led site could list positive factors in
an order contradicting the contribution table shown beside them. Each Run now
materialises `explanations.json` through the S2-06 stage's own assembler. The
run identity also binds the frozen input (a Run scored from an older integrated
table is never reused) and first materialisations are serialised (identical
concurrent POST /runs no longer race). The identity and lock tests are ported
from S3-10 6fe88a3 (Xinhao Wang).
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from pipeline.explanation.templates import load_templates
from pipeline.service import config, get_ranked_results, get_site_detail, run_analysis
from pipeline.service import runs
from pipeline.service.models import RunHandle
from pipeline.service.runs import _run_id_for, resolve_weights

ENGINE_INPUT_AVAILABLE = Path(config.INTEGRATED_PATH).exists()
requires_engine_input = pytest.mark.skipif(
    not ENGINE_INPUT_AVAILABLE,
    reason=f"integrated feature table not built: {config.INTEGRATED_PATH}",
)
SCENARIOS = ("wind_led", "grid_led")


def test_run_identity_includes_frozen_input():
    weights, _, _ = resolve_weights(scenario="wind_led")
    assert _run_id_for(weights, "wind_led", "a" * 64) != _run_id_for(
        weights, "wind_led", "b" * 64
    )


def test_concurrent_first_materialisation_is_serialised(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    calls: list[str] = []

    def fake_materialise(run_id, weights, scenario, weights_id, verbose):
        calls.append(run_id)
        target = runs.run_dir(run_id)
        target.mkdir()
        (target / config.SCORED_GPKG_FILENAME).touch()
        (target / config.RUN_EXPLANATIONS_FILENAME).write_text("[]")
        runs._atomic_write_json(
            target / config.RUN_MANIFEST_FILENAME,
            {"run_id": run_id, "weights_id": weights_id, "scenario": scenario},
        )
        return RunHandle(run_id, weights_id, scenario)

    monkeypatch.setattr(runs, "_materialise", fake_materialise)
    monkeypatch.setattr(runs, "_scored_table_readable", lambda run_id: True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        handles = list(
            pool.map(lambda _: runs.materialise_run(scenario="wind_led"), range(4))
        )
    assert len(calls) == 1
    assert len({h.run_id for h in handles}) == 1


@pytest.fixture(scope="module")
def live_runs(tmp_path_factory):
    if not ENGINE_INPUT_AVAILABLE:
        pytest.skip(f"integrated feature table not built: {config.INTEGRATED_PATH}")
    original = config.RUNS_DIR
    config.RUNS_DIR = tmp_path_factory.mktemp("s4-03-runs")
    try:
        yield {name: run_analysis(scenario=name) for name in SCENARIOS}
    finally:
        config.RUNS_DIR = original


def _feature_for_phrase(phrase: str, templates) -> str:
    """The criterion a rendered positive-factor phrase belongs to."""
    text = phrase.split(" (")[0]
    for feature, phrases in templates.phrases.items():
        if phrases.positive == text:
            return feature
    raise AssertionError(f"no template produces positive factor {phrase!r}")


@requires_engine_input
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_positive_factors_follow_the_runs_own_contributions(live_runs, scenario):
    """Positive factors are listed in THIS Run's contribution order."""
    handle = live_runs[scenario]
    templates = load_templates()
    for row in get_ranked_results(handle, top_n=25):
        site = get_site_detail(handle, row.cell_id)
        factors = site.explanation["positive_factors"]
        contributions = [
            site.contributions[_feature_for_phrase(phrase, templates)]
            for phrase in factors
        ]
        assert contributions == sorted(contributions, reverse=True), (
            f"{scenario} {row.cell_id}: {factors} vs {site.contributions}"
        )


@requires_engine_input
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_site_detail_serves_the_runs_own_explanation_file(
    live_runs, scenario, monkeypatch
):
    handle = live_runs[scenario]
    # The packaged default-weights file must not be consulted for a new Run.
    monkeypatch.setattr(config, "EXPLANATION_PATH", Path("/definitely/missing.json"))
    recorded = json.loads(
        (config.RUNS_DIR / handle.run_id / config.RUN_EXPLANATIONS_FILENAME).read_text()
    )
    by_cell = {record["cell_id"]: record for record in recorded}
    top = get_ranked_results(handle, top_n=1)[0]
    site = get_site_detail(handle, top.cell_id)
    assert site.explanation == by_cell[top.cell_id]
    # The full integrated context travels with the detail (S4-03 AC2).
    for column in ("centroid_lat", "centroid_lon", "land_use", "data_confidence"):
        assert column in site.features


@requires_engine_input
def test_excluded_site_has_reasons_and_no_rank(live_runs):
    handle = live_runs["wind_led"]
    recorded = json.loads(
        (config.RUNS_DIR / handle.run_id / config.RUN_EXPLANATIONS_FILENAME).read_text()
    )
    excluded = next(r for r in recorded if r.get("exclusion_reasons"))
    site = get_site_detail(handle, excluded["cell_id"])
    assert site.eligible is False
    assert site.rank is None and site.suitability_score is None
    assert [r["code"] for r in site.explanation["exclusion_reasons"]] == [
        r["code"] for r in excluded["exclusion_reasons"]
    ]
