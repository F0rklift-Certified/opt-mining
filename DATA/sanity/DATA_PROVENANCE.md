# Data Provenance — Validation / Sanity Check (S1-12)

Everything the `sanity` stage writes is a DERIVED product: the Validation_Report and the optional Results_Sidecar. Nothing here is custodial source data; the generated block below is rewritten on every run.

<!-- BEGIN sanity.run derived product (generated) -->
## Derived product — Sprint 1 Validation Report (S1-12)

- **DERIVED PRODUCT — not custodial source data.** A preliminary-screening plausibility sanity check, fully regenerable from the five inputs below; it contains no data of its own.
- **Validation_Report:** `outputs/sprint1_validation_report.md` (Markdown; a FIXED, non-timestamped path so downstream readers and the README always know where to find it — 10.4)
- **Results_Sidecar:** `DATA/sanity/optmining_validation-results_2026_nsw.json` (machine-readable JSON; named per the `{source}_{dataset}_{year/vintage}_{region}.{ext}` convention, region slug `nsw`, SHA-256 `dd4b33ccabc05060b422ab343e47fec12d49c1d336e650aef79d41d86247dae0`)
- **Derived from (five READ-ONLY inputs, never modified):**
  - shortlist: `DATA/shortlist/sprint1_shortlist_20261007.geojson` (, SHA-256 `0572e0aafa5a003563f6c9d0482eef2ca5836c82d3f402f8ee1a98c9955dd26f`)
  - scored_table: `DATA/scoring/optmining_suitability-score_2026_nsw.gpkg` (layer `suitability_score`, SHA-256 `182d0a9a158ff65e223ccaec1355c27fd7cddb67cf3d6b02e1367c5d6d44277d`)
  - integrated_feature_table: `DATA/integration/optmining_integrated-features_2026_nsw.gpkg` (layer `integrated_features`, SHA-256 `4062224a2b96adace37f5166feb0fb7b7dbd9251e9433ed5028659347d2a1c80`)
  - wind_generators: `DATA/infrastructure/generators/ga_wind_generators_2026_nsw.geojson` (, SHA-256 `ee63e1b966d9aabbc944152f3a5dff373926ed515302b9c1ff46aa67b3c9fdb0`)
  - analysis_grid: `DATA/grid/nsw_analysis_grid.gpkg` (layer `nsw_grid`, SHA-256 `7c7e6433d061f0029331b4e19460abb664535bf21c7ca50fb8fa4511fa90052b`)
- **Method:** four plausibility checks (Known Wind Farm Comparison, Exclusion Validation, Feature-Value Spot-Checks, Score-Distribution Plausibility) over the inputs read-only; the model is NEVER re-scored, re-ranked, re-weighted, or re-tuned.
- **SHA-256 (report):** `dfabbadfd9409806b8f562326376af4544c8ac91d7279b1cecd6be92099a434a`
- **SHA-256 (sidecar):** `dd4b33ccabc05060b422ab343e47fec12d49c1d336e650aef79d41d86247dae0`
- **Regenerable:** yes — `python -m pipeline --only sanity` (the terminal stage, after `shortlist`).
- **Run timestamp (UTC):** 2026-10-12T11:05:16+00:00
- **Pipeline version:** `ba456c7b48d12fa8c94f25316408293a69af7daa-dirty`
<!-- END sanity.run derived product (generated) -->
