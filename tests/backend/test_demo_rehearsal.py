"""Release verification must reject plausible-looking but inconsistent output."""

import copy
import importlib.util
from pathlib import Path

import pytest


_spec = importlib.util.spec_from_file_location(
    "demo_rehearsal", Path(__file__).resolve().parents[2] / "app/rehearse_demo.py"
)
demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(demo)


def ranked(cell, rank, score):
    return {"cell_id": cell, "rank": rank, "suitability_score": score,
            "key_components": {"wind_speed": score}}


def test_rehearsal_checks_both_scenarios_and_retains_an_unscored_exclusion():
    a, b = [ranked("A", 1, 0.8), ranked("B", 2, 0.6)], [ranked("B", 1, 0.9), ranked("A", 2, 0.5)]
    calls = []

    def request(path, payload=None):
        calls.append(path)
        if path == "/data-quality":
            return {"passed": True, "checks": [{"passed": True}]}
        if path == "/runs":
            scenario = payload["scenario"]
            return {"run_id": scenario, "scenario": scenario, "weights_id": scenario}
        if path == "/scenario-comparison":
            return {"labels": {"a": "Wind-led", "b": "Grid-led"}, "rows": [
                {"cell_id": "A", "rank_a": 1, "rank_b": 2, "rank_delta": -1},
                {"cell_id": "B", "rank_a": 2, "rank_b": 1, "rank_delta": 1}]}
        if path.endswith("/exclusions"):
            return [{"cell_id": "X", "reason_codes": ["protected"], "reason_text": "Protected area"}]
        if "/results" in path:
            return a if "/wind_led/" in path else b
        if path.endswith("/sites/X"):
            return {"eligible": False, "rank": None, "suitability_score": None}
        row = (a if "/wind_led/" in path else b)[0]
        return {**row, "eligible": True, "features": {"wind_speed": 7.5},
                "contributions": row["key_components"], "explanation": {
                    "cell_id": row["cell_id"], "proxy_caveats": ["Demand is a proxy"],
                    "data_quality_notes": ["Screening-level input"]}}

    report = {}
    demo.live_rehearsal(request, report)
    assert report["service_checks_passed"]
    assert report["scenario_comparison"]["changed_rank_count"] == 2
    assert report["exclusions"]["sample_detail"]["rank"] is None
    assert "/runs/grid_led/results" in calls


@pytest.mark.parametrize("fault", ["duplicate", "wrong_rank", "wrong_sum", "nan"])
def test_ranked_values_cannot_silently_pass_release_checks(fault):
    rows = [ranked("A", 1, 0.8), ranked("B", 2, 0.6)]
    if fault == "duplicate":
        rows[1]["cell_id"] = "A"
    elif fault == "wrong_rank":
        rows[1]["rank"] = 7
    elif fault == "wrong_sum":
        rows[1]["key_components"]["wind_speed"] = 0.5
    else:
        rows[1]["suitability_score"] = float("nan")
    with pytest.raises(ValueError):
        demo.validate_rows(rows)


def test_stale_site_detail_does_not_pass_with_another_run_score():
    row = ranked("A", 1, 0.8)
    detail = {**copy.deepcopy(row), "eligible": True, "suitability_score": 0.5}
    with pytest.raises(ValueError, match="score mismatch"):
        demo.validate_detail(row, detail)


def test_comparison_must_match_two_actual_runs_not_just_contain_a_delta():
    a, b = [ranked("A", 1, 0.8)], [ranked("A", 1, 0.6)]
    comparison = {"rows": [{"cell_id": "A", "rank_a": 1, "rank_b": 2, "rank_delta": -1}]}
    with pytest.raises(ValueError, match="disagrees with actual runs"):
        demo.validate_comparison(a, b, comparison)


def test_service_success_cannot_clear_missing_web_or_dependency_evidence():
    readiness = {"criteria": [{"id": "AC8", "required_for_rc": True, "status": "blocked"}],
                 "gaps": [{"id": "S3-09", "blocking": True, "reason": "No browser E2E"},
                          {"id": "export", "blocking": False, "reason": "Optional"}]}
    assert demo.final_blockers(readiness) == ["S3-09: No browser E2E", "AC8: blocked"]
