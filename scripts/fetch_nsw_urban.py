"""Fetch only the missing NSW ABS UCL input; never overwrite unrelated sources."""
from pipeline.common.geo import atomic_write_json, sha256_file, utc_now
from pipeline.geographic import config
from pipeline.geographic.download import _fetch_with_size_guardrail, _write_geojson


def main():
    url = f"{config.ABS_ASGS_BASE}/UCL/FeatureServer/0"
    query = "state_code_2021 = '1'"
    collection, offset = _fetch_with_size_guardrail(url, where=query)
    features = collection.get("features", [])
    if not features or any(str(f["properties"].get("state_code_2021")) != "1" for f in features):
        raise ValueError("ABS query did not return a complete NSW-only state extract")
    path = config.GEO_DIR / "urban" / "abs_ucl_2021_nsw.geojson"
    _write_geojson(path, collection)
    atomic_write_json(config.GEO_META_DIR / "abs_ucl_2021_nsw_source.json", {
        "dataset": "ABS ASGS 2021 Urban Centres and Localities, complete NSW",
        "source": url, "where": query, "out_crs": "EPSG:4326",
        "licence": "Creative Commons Attribution 4.0 International (ABS)",
        "retrieved_utc": utc_now(), "feature_count": len(features),
        "max_allowable_offset_deg": offset, "sha256": sha256_file(path),
        "output": str(path.relative_to(config.PROJECT_ROOT)),
        "purpose": "S3-10 approved source-coverage correction; unchanged exclusion rules",
    })
    print(f"NSW ABS UCL: {len(features)} features, {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
