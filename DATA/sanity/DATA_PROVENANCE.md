# Data Provenance — Validation / Sanity Check (S1-12)

Everything the `sanity` stage writes is a DERIVED product: the Validation_Report and the optional Results_Sidecar. Nothing here is custodial source data; the generated block below is rewritten on every run.

<!-- BEGIN sanity.run derived product (generated) -->
## Derived product — Sprint 1 Validation Report (S1-12)

- **DERIVED PRODUCT — not custodial source data.** A preliminary-screening plausibility sanity check, fully regenerable from the five inputs below; it contains no data of its own.
- **Validation_Report:** `outputs/sprint1_validation_report.md` (Markdown; a FIXED, non-timestamped path so downstream readers and the README always know where to find it — 10.4)
- **Results_Sidecar:** `DATA/sanity/optmining_validation-results_2026_nsw.json` (machine-readable JSON; named per the `{source}_{dataset}_{year/vintage}_{region}.{ext}` convention, region slug `nsw`, SHA-256 `bdec3530802b9a1f28ce1be70b6479002ef47f1ea710dbd7ee7ad35311859f06`)
- **Derived from (five READ-ONLY inputs, never modified):**
  - shortlist: `DATA/shortlist/sprint1_shortlist_20261022T041848.geojson` (, SHA-256 `e29fadd8dd046d83baffe9d8d3c666ea7743f2244a36eb78c3744ee02f221e62`)
  - scored_table: `DATA/scoring/optmining_suitability-score_2026_nsw.gpkg` (layer `suitability_score`, SHA-256 `7f79db687d7c11a73683a7245496458ef7468ba98e1760ad2a6198ea0382f2b6`)
  - integrated_feature_table: `DATA/integration/optmining_integrated-features_2026_nsw.gpkg` (layer `integrated_features`, SHA-256 `df7073bd6c0ac9c57baf1273f2dcf2da04d3baf0c697aeeaaab3cea2e60e4da5`)
  - wind_generators: `DATA/infrastructure/generators/ga_wind_generators_2026_nsw.geojson` (, SHA-256 `ee63e1b966d9aabbc944152f3a5dff373926ed515302b9c1ff46aa67b3c9fdb0`)
  - analysis_grid: `DATA/grid/nsw_analysis_grid.gpkg` (layer `nsw_grid`, SHA-256 `7c7e6433d061f0029331b4e19460abb664535bf21c7ca50fb8fa4511fa90052b`)
- **Method:** four plausibility checks (Known Wind Farm Comparison, Exclusion Validation, Feature-Value Spot-Checks, Score-Distribution Plausibility) over the inputs read-only; the model is NEVER re-scored, re-ranked, re-weighted, or re-tuned.
- **SHA-256 (report):** `9e7c9958aed5cfa38e215e1b76d5c4abe9c3319b64b8587773e6957e8626d28b`
- **SHA-256 (sidecar):** `bdec3530802b9a1f28ce1be70b6479002ef47f1ea710dbd7ee7ad35311859f06`
- **Regenerable:** yes — `python -m pipeline --only sanity` (the terminal stage, after `shortlist`).
- **Run timestamp (UTC):** 2026-10-22T04:19:38+00:00
- **Pipeline version:** `9d7280098afbc5f63ad67ca3c4d9497eeae6f66a`
<!-- END sanity.run derived product (generated) -->
