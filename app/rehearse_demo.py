"""Record live S3-10 service evidence without claiming browser/client acceptance.

Run after the documented stack startup: python app/rehearse_demo.py
Use --external-sanity with the engine dependencies installed to compare the
live Wind-led results against the committed GA reference wind generators.
--require-final returns 2 while the release readiness register contains gaps.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable
from urllib.parse import quote
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
READINESS = ROOT / "docs/release/readiness.json"
TOLERANCE = 1e-9


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_rows(rows: list[dict]) -> None:
    require(bool(rows), "No eligible rows were returned")
    seen: set[str] = set()
    previous: dict | None = None
    for expected_rank, row in enumerate(rows, 1):
        cell = row["cell_id"]
        score = row["suitability_score"]
        require(cell not in seen, f"Duplicate ranked cell: {cell}")
        seen.add(cell)
        require(math.isfinite(score) and 0 <= score <= 1,
                f"Invalid suitability score for {cell}")
        require(row["rank"] == expected_rank, f"Non-contiguous rank for {cell}")
        components = row["key_components"]
        require(bool(components), f"No contributions for {cell}")
        require(all(math.isfinite(v) and v >= 0 for v in components.values()),
                f"Invalid contribution for {cell}")
        require(math.isclose(sum(components.values()), score, abs_tol=TOLERANCE,
                             rel_tol=0), f"Contributions do not reconcile for {cell}")
        if previous:
            require(previous["suitability_score"] >= score,
                    f"Scores are out of engine rank order at {cell}")
            if previous["suitability_score"] == score:
                require(previous["cell_id"] < cell, f"Unstable tie order at {cell}")
        previous = row


def validate_detail(row: dict, detail: dict) -> None:
    require(detail["cell_id"] == row["cell_id"], "Site detail identifies another cell")
    require(detail["eligible"] is True, "Ranked site is not eligible")
    require(detail["rank"] == row["rank"], "Site/table rank mismatch")
    require(math.isclose(detail["suitability_score"], row["suitability_score"],
                         abs_tol=TOLERANCE, rel_tol=0), "Site/table score mismatch")
    require(detail["contributions"] == row["key_components"],
            "Site/table contribution mismatch")
    require(bool(detail["features"]) and bool(detail["explanation"]),
            "Raw features or explanation missing")
    require(detail["explanation"].get("cell_id") == row["cell_id"],
            "Explanation identifies another cell")
    require(bool(detail["explanation"].get("proxy_caveats")),
            "Demand proxy caveat is absent")
    require(bool(detail["explanation"].get("data_quality_notes")),
            "Data-quality caveat is absent")


def validate_comparison(a: list[dict], b: list[dict], comparison: dict) -> int:
    ranks_a = {row["cell_id"]: row["rank"] for row in a}
    ranks_b = {row["cell_id"]: row["rank"] for row in b}
    require(ranks_a.keys() == ranks_b.keys(), "Scenario eligibility populations differ")
    rows = comparison["rows"]
    require(len(rows) == len(a), "Scenario comparison population mismatch")
    require(len({row["cell_id"] for row in rows}) == len(rows),
            "Duplicate scenario comparison cell")
    changed = 0
    for row in rows:
        cell = row["cell_id"]
        require(row["rank_a"] == ranks_a[cell] and row["rank_b"] == ranks_b[cell],
                f"Scenario comparison disagrees with actual runs for {cell}")
        require(row["rank_delta"] == row["rank_a"] - row["rank_b"],
                f"Scenario delta disagrees with engine ranks for {cell}")
        changed += row["rank_a"] != row["rank_b"]
    require(changed > 0, "The two packaged presets produce no ranking change")
    return changed


def live_rehearsal(request: Callable, report: dict) -> list[dict]:
    """Call all six operations; retain small, inspectable observations."""
    quality = request("/data-quality")
    require(bool(quality["checks"]), "Input validation checks are unavailable")
    report["data_quality"] = quality
    require(quality["passed"] is True and all(c["passed"] for c in quality["checks"]),
            "Frozen input validation is flagged; final release needs investigation")

    runs: dict[str, list[dict]] = {}
    handles: dict[str, dict] = {}
    report["scenarios"] = {}
    for scenario in ("wind_led", "grid_led"):
        handle = request("/runs", {"scenario": scenario})
        require(handle["scenario"] == scenario, "Service returned a different scenario")
        prefix = "/runs/" + quote(handle["run_id"], safe="")
        rows = request(prefix + "/results")
        validate_rows(rows)
        top = request(prefix + "/results?top_n=5")
        require(top == rows[:5], "Top-N display filtering changes engine values")
        detail = request(prefix + "/sites/" + quote(rows[0]["cell_id"], safe=""))
        validate_detail(rows[0], detail)
        runs[scenario], handles[scenario] = rows, handle
        report["scenarios"][scenario] = {
            "run": handle, "eligible_count": len(rows), "top_five": top,
            "selected_site": detail,
        }

    prefix = "/runs/" + quote(handles["wind_led"]["run_id"], safe="")
    exclusions = request(prefix + "/exclusions")
    require(bool(exclusions), "No excluded-site demonstration is available")
    excluded_ids = {row["cell_id"] for row in exclusions}
    require(len(excluded_ids) == len(exclusions), "Duplicate exclusions")
    require(not excluded_ids.intersection(row["cell_id"] for row in runs["wind_led"]),
            "An excluded cell received an eligible rank")
    require(all(row["reason_codes"] and row["reason_text"].strip() for row in exclusions),
            "An excluded cell has no machine-readable/human-readable reason")
    sample = exclusions[0]
    excluded_detail = request(prefix + "/sites/" + quote(sample["cell_id"], safe=""))
    require(excluded_detail["eligible"] is False and
            excluded_detail["rank"] is None and
            excluded_detail["suitability_score"] is None,
            "Excluded-site detail carries a score or rank")
    report["exclusions"] = {
        "count": len(exclusions), "sample": sample, "sample_detail": excluded_detail,
    }
    wind = excluded_detail.get("features", {}).get("wind_speed")
    if "missing_wind_data" in sample["reason_codes"] and wind is not None and math.isfinite(wind):
        report.setdefault("release_blockers", []).append(
            f"Exclusion/input discrepancy at {sample['cell_id']}: stored reason is missing wind "
            f"but the integrated wind feature is {wind} m/s; reconcile source coverage before release"
        )
    comparison = request("/scenario-comparison", {
        "scenario_a": "wind_led", "scenario_b": "grid_led",
    })
    changed = validate_comparison(runs["wind_led"], runs["grid_led"], comparison)
    report["scenario_comparison"] = {
        "labels": comparison["labels"], "compared_count": len(comparison["rows"]),
        "changed_rank_count": changed,
        "examples": [row for row in comparison["rows"] if row["rank_delta"]][:5],
    }
    report["service_checks_passed"] = True
    return runs["wind_led"]


def external_sanity(rows: list[dict]) -> dict:
    """Reuse the existing reference check on live results, without changing the model."""
    sys.path.insert(0, str(ROOT))
    import geopandas as gpd
    import pandas as pd
    from dataclasses import asdict
    from pipeline.sanity import config
    from pipeline.sanity.checks import check_known_wind_farms

    grid = gpd.read_file(config.GRID_PATH, layer=config.GRID_LAYER)
    farms = gpd.read_file(config.WIND_GENERATORS_PATH)
    # GA's committed source uses feature_name, while the existing pure check
    # consumes name. Record this adapter and limit the reference to operating
    # wind farms; planned generators are not evidence of built-site reality.
    require("feature_name" in farms and "status" in farms,
            "GA wind-generator name/status fields are unavailable")
    farms = farms.loc[farms["status"] == "Operational"].rename(columns={"feature_name": "name"})
    # A left join retains excluded cells with null score/rank for the check.
    scored = grid[["cell_id"]].merge(
        pd.DataFrame(rows)[["cell_id", "suitability_score", "rank"]],
        on="cell_id", how="left", validate="one_to_one",
    )
    result = check_known_wind_farms(farms, grid, scored, config.CONTAINMENT_CRS, [])
    return {
        "scenario": "wind_led", "reference": str(config.WIND_GENERATORS_PATH.relative_to(ROOT)),
        "reference_sha256": file_hash(config.WIND_GENERATORS_PATH),
        "source_name_field": "feature_name", "status_filter": "Operational",
        "reference_scope_note": "Counts refer to GA records, not unique wind farms. "
        "Gullen Range occurs twice. White Rock Solar Farm is labelled primary_fuel_type=Wind "
        "and technology_type=Turbine - Wind in the source; retain this source ambiguity "
        "for investigation rather than silently removing it to improve the result.",
        "containment_crs": config.CONTAINMENT_CRS,
        "outcome": asdict(result.outcome),
        "rows": [asdict(row) for row in result.rows],
        "anomalies": [asdict(item) for item in result.anomalies],
        "interpretation": "A plausibility comparison, not an accuracy metric or site approval. "
        "All excluded/out-of-grid reference locations are retained for investigation.",
    }


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def final_blockers(readiness: dict) -> list[str]:
    blockers = [f"{item['id']}: {item['reason']}" for item in readiness["gaps"]
                if item["blocking"]]
    blockers += [f"{item['id']}: {item['status']}" for item in readiness["criteria"]
                 if item["required_for_rc"] and item["status"] != "passed"]
    return blockers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("outputs/s3-10-rehearsal.json"))
    parser.add_argument("--external-sanity", action="store_true")
    parser.add_argument("--require-final", action="store_true")
    args = parser.parse_args()
    api = os.environ.get("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000").rstrip("/")
    web = os.environ.get("CORS_ALLOW_ORIGINS", "http://localhost:3000").split(",")[0].strip()
    report = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                                 text=True).strip(),
        "working_tree_dirty": bool(subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()),
        "rehearsal_script_sha256": file_hash(Path(__file__)),
        "api_url": api, "web_url": web, "service_checks_passed": False,
        "browser_acceptance": "Recorded separately; HTTP evidence does not prove UI interaction.",
    }
    readiness = json.loads(READINESS.read_text(encoding="utf-8"))
    report["release_blockers"] = final_blockers(readiness)
    try:
        data = ROOT / "DATA/integration/optmining_integrated-features_2026_nsw.gpkg"
        frozen = json.loads((ROOT / "DATA/integration/metadata/integrated_baseline_manifest.json")
                            .read_text(encoding="utf-8"))
        report["input_sha256"] = file_hash(data)
        require(report["input_sha256"] == frozen["sha256"], "Local frozen input hash drift")
        report["scenario_source_sha256"] = file_hash(ROOT / "pipeline/scoring/scenarios.yaml")
        with urllib.request.urlopen(web, timeout=60) as response:
            require(response.status == 200, "Web page failed to load")

        def request(path: str, payload: dict | None = None):
            req = urllib.request.Request(api + path,
                data=None if payload is None else json.dumps(payload).encode(),
                headers={"Origin": web, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as response:
                require(response.status == 200, f"HTTP failure: {path}")
                require(response.headers.get("Access-Control-Allow-Origin") == web,
                        f"Browser CORS failed: {path}")
                return json.load(response)

        rows = live_rehearsal(request, report)
        if args.external_sanity:
            report["external_sanity"] = external_sanity(rows)
            if not report["external_sanity"]["outcome"]["passed"]:
                report["release_blockers"].append("External plausibility check needs investigation")
        else:
            report["external_sanity"] = {"status": "not_run"}
            report["release_blockers"].append("External plausibility check not rehearsed")
        require(file_hash(data) == report["input_sha256"], "Rehearsal mutated the frozen input")
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    report["release_ready"] = report["service_checks_passed"] and not report.get("error") and not report["release_blockers"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Service rehearsal: {'FAIL' if report.get('error') else 'PASS'}; "
          f"final release: {'READY' if report['release_ready'] else 'BLOCKED'}; "
          f"evidence: {args.output}")
    if report.get("error"):
        print(report["error"], file=sys.stderr)
        return 1
    return 2 if args.require_final and not report["release_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
