<!-- BEGIN integration.merge derived layer (generated) -->
## Derived layer — Integrated NSW Feature Table (S1-08)

- **File:** `DATA/integration/optmining_integrated-features_2026_nsw.gpkg` (GeoPackage, layer `integrated_features`)
- **CSV:** `DATA/integration/optmining_integrated-features_2026_nsw.csv` (no geometry; the deterministic artefact)
- **Derived from:**
  - grid: `DATA/grid/nsw_analysis_grid.gpkg` (layer `nsw_grid`, 47,311 rows, SHA-256 `7c7e6433d061f0029331b4e19460abb664535bf21c7ca50fb8fa4511fa90052b`)
  - wind: `DATA/wind-resource/features/gwa_v4_wind-feature_2025_nsw.gpkg` (layer `wind_features`, 47,311 rows, SHA-256 `ff735ce010f90ff99d308ea32e6c375d3003133225f4168417c36b7bb42e88d6`)
  - geographic: `DATA/geographic/features/optmining_geographic-features_2024_nsw.gpkg` (layer `geographic_features`, 47,311 rows, SHA-256 `9501883e2cf871d87fb68aa6f483de1a80711ed603b8f0a3a8a828a7e7fcf175`)
  - infrastructure: `DATA/infrastructure/optmining_infra-features_2026_nsw.gpkg` (layer `infra_features`, 47,311 rows, SHA-256 `12bca14fccc7d89f687d5026dc762b8a1d32f5f4365e8d893e0163881bbe1d8e`)
  - demand: `DATA/electricity-demand/aemo_demand-proxy_2026_nsw.gpkg` (layer `demand_proxy`, 47,311 rows, SHA-256 `8e9890bf9371de015fe3da7635515ea3e50f5713eab247c683045f0e0e92a646`)
  - exclusions: `DATA/exclusions/optmining_exclusions_2024_nsw.gpkg` (layer `optmining_exclusions_2024_nsw.gpkg`, 47,311 rows, SHA-256 `c5caa822647024c4b0bb62ad78735b41b0e72aa314e7e288a162233928a771ca`)
- **Method:** left joins on `cell_id` from the S1-02 grid; row count asserted after every join; excluded cells retained with `eligible = False`; no reprojection, no back-filling; `data_confidence` deferred to S1-09.
- **Regenerable:** yes — `python -m pipeline --only integration` (after the five feature stages and `exclusions`).
- **SHA-256 (GeoPackage):** `eac0e1bfa9a31b805dd29f66d06d236b628f99744727670e424c2f954caca509`
- **SHA-256 (CSV):** `313486ed54abc461966a0ac499c9f2fa79eb59e44b0b42b36112ada57a22a4bb`
- **Rows:** 47,311
- **Generated (UTC):** 2026-09-03T01:37:03+00:00
- **Git commit:** `055357f8b20109a916c535b01115a46fa200f4c6`
<!-- END integration.merge derived layer (generated) -->
