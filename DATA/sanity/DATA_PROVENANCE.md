# Data Provenance — Validation / Sanity Check (S1-12)

Everything the `sanity` stage writes is a DERIVED product: the Validation_Report and the optional Results_Sidecar. Nothing here is custodial source data; the generated block below is rewritten on every run.

<!-- BEGIN sanity.run derived product (generated) -->
## Derived product — Sprint 1 Validation Report (S1-12)

- **DERIVED PRODUCT — not custodial source data.** A preliminary-screening plausibility sanity check, fully regenerable from the five inputs below; it contains no data of its own.
- **Validation_Report:** `outputs/sprint1_validation_report.md` (Markdown; a FIXED, non-timestamped path so downstream readers and the README always know where to find it — 10.4)
- **Results_Sidecar:** `DATA/sanity/optmining_validation-results_2026_nsw.json` (machine-readable JSON; named per the `{source}_{dataset}_{year/vintage}_{region}.{ext}` convention, region slug `nsw`, SHA-256 `53ad14f671c2f25c29eaa8ecb7e2bb925e34e24095a2a9abd0f9f0a404bd2258`)
- **Derived from (five READ-ONLY inputs, never modified):**
  - shortlist: `DATA/shortlist/sprint1_shortlist_20261005.geojson` (, SHA-256 `0572e0aafa5a003563f6c9d0482eef2ca5836c82d3f402f8ee1a98c9955dd26f`)
  - scored_table: `DATA/scoring/optmining_suitability-score_2026_nsw.gpkg` (layer `suitability_score`, SHA-256 `9ce76ee93694cfa4f8c5591542581206cdaec84da477c747dd298da8952829ba`)
  - integrated_feature_table: `DATA/integration/optmining_integrated-features_2026_nsw.gpkg` (layer `integrated_features`, SHA-256 `1e5f5a1c73ed14de356866105db128fffbcb780cae8c835fff804750fbed87cc`)
  - wind_generators: `DATA/infrastructure/generators/ga_wind_generators_2026_nsw.geojson` (, SHA-256 `ee63e1b966d9aabbc944152f3a5dff373926ed515302b9c1ff46aa67b3c9fdb0`)
  - analysis_grid: `DATA/grid/nsw_analysis_grid.gpkg` (layer `nsw_grid`, SHA-256 `7c7e6433d061f0029331b4e19460abb664535bf21c7ca50fb8fa4511fa90052b`)
- **Method:** four plausibility checks (Known Wind Farm Comparison, Exclusion Validation, Feature-Value Spot-Checks, Score-Distribution Plausibility) over the inputs read-only; the model is NEVER re-scored, re-ranked, re-weighted, or re-tuned.
- **SHA-256 (report):** `5c035f36d6ae504090cb27bbd49f726eec2c6403b0d0aa951b07cd7bf44afc03`
- **SHA-256 (sidecar):** `53ad14f671c2f25c29eaa8ecb7e2bb925e34e24095a2a9abd0f9f0a404bd2258`
- **Regenerable:** yes — `python -m pipeline --only sanity` (the terminal stage, after `shortlist`).
- **Run timestamp (UTC):** 2026-10-05T15:17:06+00:00
- **Pipeline version:** `51508a48f87e609332a5148a92641695bb040fb2-dirty`
<!-- END sanity.run derived product (generated) -->
