"""S3-10 authorised coverage repair and two explicit F16 rule additions.

Run fetch_nsw_urban first. This script rebuilds exclusions, integration,
baseline/validation, scoring and explanation in dependency order. It halts
on source disagreement instead of publishing inconsistent eligibility.
"""
from collections import Counter
from pathlib import Path
import geopandas as gpd
import io
import subprocess
from pipeline.common.geo import atomic_write_json, sha256_file, utc_now
from pipeline.exclusions.apply import run as exclusions
from pipeline.integration.merge import run as integrate
from pipeline.scoring.run import run as score
from pipeline.explanation.run import run as explain
from pipeline import validate


def reasons(frame):
    return dict(Counter(code for value in frame.triggered_rules.dropna()
                        for code in value.split(", ")))


def main():
    path = Path(validate.DEFAULT_INTEGRATED_PATH)
    # Immutable pre-repair commit, so a failed/restarted build retains the
    # original comparison rather than comparing the new baseline with itself.
    original = "a2ad4a7a5f9be683b70f4d6aeef6468ba29d61d5"
    old_bytes = subprocess.check_output(["git", "show", f"{original}:DATA/integration/optmining_integrated-features_2026_nsw.gpkg"])
    before = gpd.read_file(io.BytesIO(old_bytes)).set_index("cell_id")
    import hashlib
    before_hash = hashlib.sha256(old_bytes).hexdigest()
    old_score_path = Path("DATA/scoring/optmining_suitability-score_2026_nsw.gpkg")
    old_scores = gpd.read_file(io.BytesIO(subprocess.check_output([
        "git", "show", f"{original}:{old_score_path}"]))).set_index("cell_id")
    exclusions(verbose=True)
    integrate(verbose=True)
    after = gpd.read_file(path).set_index("cell_id")
    eligibility = gpd.read_file("DATA/exclusions/optmining_exclusions_2024_nsw.gpkg").set_index("cell_id")
    assert before.index.equals(after.index), "Coverage repair changed analysis grid identity/order"
    assert eligibility.index.is_unique and set(eligibility.index) == set(after.index)
    assert (eligibility.wind_speed_100m_ms.reindex(after.index) == after.wind_speed).all()
    assert (eligibility.slope_deg.reindex(after.index) == after.slope_deg).all()
    assert eligibility.loc[after.eligible, "inside_nsw_land"].all()
    outside = ~eligibility.inside_nsw_land.astype(bool)
    assert not after.loc[outside, "eligible"].any()
    score(verbose=True)
    explain(verbose=True)
    baseline = validate.freeze_baseline(path, write=True)
    checks = validate._run_integrated_input_checks(verbose=True, integrated_path=path)
    result, _, _ = validate.write_validation_outputs(baseline, checks)
    if not result["all_passed"]:
        raise RuntimeError("Rebuilt baseline failed the existing input contract")
    new_scores = gpd.read_file(old_score_path).set_index("cell_id")
    common = old_scores.suitability_score.notna() & new_scores.suitability_score.notna()
    audit = {
        "generated_utc": utc_now(), "authorised_by": "XINHAO WANG, explicit chat approval",
        "reason": "Legacy exclusion source window disagreed with full NSW integrated input",
        "original_commit": original,
        "approved_rule_additions": ["missing_demand_data: exclude null scored demand proxy",
                                    "outside_nsw_land: centroid outside ABS NSW boundary"],
        "nsw_boundary": {"path": "DATA/geographic/boundaries/abs_ste_2021_national.geojson",
                         "sha256": sha256_file(Path("DATA/geographic/boundaries/abs_ste_2021_national.geojson")),
                         "predicate": "centroid covered_by NSW geometry, EPSG:3577; edge included",
                         "invalid_geometry_policy": "repair in source CRS with buffer(0) before projection, same as other exclusion vectors",
                         "outside_centroid_count": int(outside.sum()),
                         "eligible_outside_count": 0},
        "unchanged": ["analysis grid", "four original exclusion rules and thresholds",
                      "scoring formula", "default and scenario weights"],
        "before": {"sha256": before_hash, "eligible": int(before.eligible.sum()),
                   "reasons": reasons(before)},
        "after": {"sha256": sha256_file(path), "eligible": int(after.eligible.sum()),
                  "reasons": reasons(after)},
        "newly_eligible": int((~before.eligible & after.eligible).sum()),
        "newly_excluded": int((before.eligible & ~after.eligible).sum()),
        "previously_ranked_common": int(common.sum()),
        "rank_changed_in_common_population": int((old_scores.loc[common, "rank"] != new_scores.loc[common, "rank"]).sum()),
        "top_five_before": old_scores.sort_values("rank").head(5).index.tolist(),
        "top_five_after": new_scores.sort_values("rank").head(5).index.tolist(),
        "limitations": ["Centroid membership is not parcel-level land availability; border cells can straddle NSW",
                        "Missing context-only land-use/elevation remains flagged, not imputed",
                        "Connection-point geometry remains unavailable; no capacity claim is made"],
    }
    atomic_write_json(Path("docs/release/baseline-change.json"), audit)
    print(audit)


if __name__ == "__main__":
    main()
