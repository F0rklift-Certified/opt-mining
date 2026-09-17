<!-- BEGIN integration.merge derived layer (generated) -->
## Derived layer — Integrated NSW Feature Table (S1-08)

- **File:** `DATA/integration/optmining_integrated-features_2026_nsw.gpkg` (GeoPackage, layer `integrated_features`)
- **CSV:** `DATA/integration/optmining_integrated-features_2026_nsw.csv` (no geometry; the deterministic artefact)
- **Derived from:**
  - grid: `DATA/grid/nsw_analysis_grid.gpkg` (layer `nsw_grid`, 47,311 rows, SHA-256 `7c7e6433d061f0029331b4e19460abb664535bf21c7ca50fb8fa4511fa90052b`)
  - wind: `DATA/wind-resource/features/gwa_v4_wind-feature_2025_nsw.gpkg` (layer `wind_features`, 47,311 rows, SHA-256 `46256d3e6a764286c9ee3db9bac3fe8e4bcc25588dd49ef239fea0beaa4e4303`)
  - geographic: `DATA/geographic/features/optmining_geographic-features_2024_nsw.gpkg` (layer `geographic_features`, 47,311 rows, SHA-256 `b000ae2bf994f17f35a9199ee7a2ba5ca2c37efbb76dbc54c01dc9e342a067ae`)
  - infrastructure: `DATA/infrastructure/optmining_infra-features_2026_nsw.gpkg` (layer `infra_features`, 47,311 rows, SHA-256 `12bca14fccc7d89f687d5026dc762b8a1d32f5f4365e8d893e0163881bbe1d8e`)
  - demand: `DATA/electricity-demand/aemo_demand-proxy_2026_nsw.gpkg` (layer `demand_proxy`, 47,311 rows, SHA-256 `8e9890bf9371de015fe3da7635515ea3e50f5713eab247c683045f0e0e92a646`)
  - exclusions: `DATA/exclusions/optmining_exclusions_2024_nsw.gpkg` (layer `optmining_exclusions_2024_nsw.gpkg`, 47,311 rows, SHA-256 `08c44e99dc08fd63a8ae7644cf25ab9091aef302b398f8fc63d9fc7633347110`)
- **Method:** left joins on `cell_id` from the S1-02 grid; row count asserted after every join; excluded cells retained with `eligible = False`; no reprojection, no back-filling; composite confidence appended by the S1-09 layer (`confidence.assess()`).
- **Confidence config:** `pipeline/integration/confidence_weights.yaml` (version `1.0`, SHA-256 `3b34c47b8da6260b53245397491b0f60ed3df68d47434458ed93495295922f93`)
- **Regenerable:** yes — `python -m pipeline --only integration` (after the five feature stages and `exclusions`).
- **SHA-256 (GeoPackage):** `8b300ca520ff42028fbb7b09024916580c105967c92fa8ade575c4e006c196fd`
- **SHA-256 (CSV):** `f8e861bce48d86f9387983b8d12d0b2e3288099b804d9767ef49459ce50df2a2`
- **Rows:** 47,311
- **Generated (UTC):** 2026-09-17T01:59:28+00:00
- **Git commit:** `23b669a3878497c561489b558d25775909f25c80-dirty`
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
