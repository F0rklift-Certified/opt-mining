"""Real-data regression guards for the S3-10 coverage/contract repairs."""
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import geopandas as gpd
import pytest
from pipeline.service import config, run_analysis, get_ranked_results, get_site_detail, get_exclusions
from pipeline.service.runs import _run_id_for, resolve_weights


@pytest.fixture(scope="module")
def live_runs(tmp_path_factory):
    original = config.RUNS_DIR
    config.RUNS_DIR = tmp_path_factory.mktemp("release-runs")
    try:
        yield {name: run_analysis(scenario=name) for name in ("wind_led", "grid_led")}
    finally:
        config.RUNS_DIR = original


def test_run_identity_includes_frozen_input():
    weights, _, _ = resolve_weights(scenario="wind_led")
    assert _run_id_for(weights, "wind_led", "a" * 64) != _run_id_for(weights, "wind_led", "b" * 64)


def test_concurrent_first_materialisation_is_serialised(tmp_path, monkeypatch):
    from pipeline.service import runs
    from pipeline.service.models import RunHandle
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    calls = []
    def fake_materialise(run_id, weights, scenario, weights_id, verbose):
        calls.append(run_id)
        target = runs.run_dir(run_id)
        target.mkdir()
        (target / config.SCORED_GPKG_FILENAME).touch()
        (target / "explanations.json").write_text("[]")
        runs._atomic_write_json(target / config.RUN_MANIFEST_FILENAME,
            {"run_id": run_id, "weights_id": weights_id, "scenario": scenario})
        return RunHandle(run_id, weights_id, scenario)
    monkeypatch.setattr(runs, "_materialise", fake_materialise)
    with ThreadPoolExecutor(max_workers=4) as pool:
        handles = list(pool.map(lambda _: runs.materialise_run(scenario="wind_led"), range(4)))
    assert len(calls) == 1
    assert len({h.run_id for h in handles}) == 1


def test_exclusion_features_agree_with_full_nsw_input():
    integrated = gpd.read_file(config.INTEGRATED_PATH).set_index("cell_id")
    excluded = gpd.read_file(config.ELIGIBILITY_TABLE_PATH).set_index("cell_id").reindex(integrated.index)
    assert (excluded.wind_speed_100m_ms == integrated.wind_speed).all()
    assert (excluded.slope_deg == integrated.slope_deg).all()
    missing = integrated.demand_proxy.isna()
    assert int(missing.sum()) == 6637
    assert not integrated.loc[missing, "eligible"].any()
    assert integrated.loc[missing, "triggered_rules"].str.contains("missing_demand_data").all()


def test_eligible_centroids_are_inside_committed_nsw_boundary():
    from pipeline.exclusions import config as exclusions_config
    integrated = gpd.read_file(config.INTEGRATED_PATH)
    states = gpd.read_file(exclusions_config.NSW_BOUNDARY_PATH)
    invalid = ~states.geometry.is_valid
    states.loc[invalid, "geometry"] = states.loc[invalid].geometry.buffer(0)
    states = states.to_crs("EPSG:3577")
    nsw = states.loc[states.state_code_2021.astype(str) == "1"].geometry.iloc[0]
    points = gpd.GeoSeries(gpd.points_from_xy(integrated.centroid_lon, integrated.centroid_lat),
                          crs="EPSG:4326").to_crs("EPSG:3577")
    outside = ~points.covered_by(nsw)
    assert outside.any()
    assert not integrated.loc[outside, "eligible"].any()
    assert integrated.loc[outside, "triggered_rules"].str.contains("outside_nsw_land").all()


@pytest.mark.parametrize("scenario", ["wind_led", "grid_led"])
def test_actual_scenario_explanation_and_coords(live_runs, scenario, monkeypatch):
    handle = live_runs[scenario]
    rows = get_ranked_results(handle, top_n=1)
    assert handle.criteria and handle.input_sha256
    assert rows[0].centroid_lat is not None and rows[0].centroid_lon is not None
    # If the old global explanation is accessed, this must fail. Production
    # reads the Run's actual S2-06 output, not a default-weight explanation.
    monkeypatch.setattr(config, "EXPLANATION_PATH", Path("/definitely-missing-global-explanations.json"))
    site = get_site_detail(handle, rows[0].cell_id)
    assert site.features["centroid_lat"] == rows[0].centroid_lat
    assert site.features["data_confidence"]
    assert site.suitability_score == rows[0].suitability_score
    recorded = json.loads((config.RUNS_DIR / handle.run_id / "explanations.json").read_text())
    assert site.explanation == next(r for r in recorded if r["cell_id"] == site.cell_id)
    excluded = get_exclusions(handle)[0]
    assert excluded.centroid_lon is not None and excluded.centroid_lat is not None
    excluded_detail = get_site_detail(handle, excluded.cell_id)
    assert excluded_detail.rank is None and excluded_detail.suitability_score is None
    assert [r["code"] for r in excluded_detail.explanation["exclusion_reasons"]] == excluded.reason_codes
