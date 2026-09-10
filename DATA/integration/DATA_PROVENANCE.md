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
- **Method:** left joins on `cell_id` from the S1-02 grid; row count asserted after every join; excluded cells retained with `eligible = False`; no reprojection, no back-filling; composite confidence appended by the S1-09 layer (`confidence.assess()`).
- **Confidence config:** `pipeline/integration/confidence_weights.yaml` (version `1.0`, SHA-256 `3b34c47b8da6260b53245397491b0f60ed3df68d47434458ed93495295922f93`)
- **Regenerable:** yes — `python -m pipeline --only integration` (after the five feature stages and `exclusions`).
- **SHA-256 (GeoPackage):** `b7cd3d261abfdedd613301e0e2fdd07e3381178deb8ce8aff506a066117a1e61`
- **SHA-256 (CSV):** `263d3d13efa9b221bf079358de5f20601b77cd90b0c3a6ffca4552437c6dd355`
- **Rows:** 47,311
- **Generated (UTC):** 2026-09-03T05:09:16+00:00
- **Git commit:** `2e2c6375949d926579916cd12d140d6bda2f23d8`
<!-- END integration.merge derived layer (generated) -->

## Derived metadata — Input-contract gate (S2-02)

These two JSON artefacts are written by the `validate` stage (`pipeline/validate.py`),
not by `integration.merge`, and are therefore recorded outside the generated block
above. They live alongside `metadata/integration_manifest.json` under
`DATA/integration/metadata/` and follow the same file-naming and metadata convention.
Both are written atomically (`pipeline/common/geo.atomic_write_json`) and are
regenerable — the frozen dataset itself is treated as strictly read-only.

- **File:** `DATA/integration/metadata/integrated_baseline_manifest.json` (Baseline_Manifest, JSON)
- **Derived from:** the frozen S1-08 integrated table `DATA/integration/optmining_integrated-features_2026_nsw.gpkg` (layer `integrated_features`)
- **Method:** `pipeline.validate.freeze_baseline` — records the frozen reference (path relative to project root, layer, vintage `2026`, SHA-256, byte count, human-readable size, storage CRS `EPSG:4326`, computation CRS `EPSG:3577`, UTC freeze timestamp); read-only on the dataset.
- **Regenerable:** yes — `python -m pipeline --only validate` (write mode records/overwrites the baseline reference).

- **File:** `DATA/integration/metadata/integrated_input_validation.json` (Validation_Result, JSON)
- **Sibling report:** `DATA/integration/metadata/integrated_input_validation.md` (Validation_Report, `banner()`-stamped)
- **Derived from:** the frozen S1-08 integrated table `DATA/integration/optmining_integrated-features_2026_nsw.gpkg` (layer `integrated_features`) and the input-contract check battery
- **Method:** `pipeline.validate.run` → `pipeline.validate._run_integrated_input_checks` — emits the Baseline_Manifest record, the list of `{name, expected, observed, passed}` Check_Records, and the `all_passed` verdict; a pure reporter that never mutates the dataset.
- **Regenerable:** yes — `python -m pipeline --only validate`.
