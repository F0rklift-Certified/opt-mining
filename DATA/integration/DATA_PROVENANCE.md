<!-- BEGIN integration.merge derived layer (generated) -->
## Derived layer — Integrated NSW Feature Table (S1-08)

- **File:** `DATA/integration/optmining_integrated-features_2026_nsw.gpkg` (GeoPackage, layer `integrated_features`)
- **CSV:** `DATA/integration/optmining_integrated-features_2026_nsw.csv` (no geometry; the deterministic artefact)
- **Derived from:**
  - grid: `DATA/grid/nsw_analysis_grid.gpkg` (layer `nsw_grid`, 47,311 rows, SHA-256 `7c7e6433d061f0029331b4e19460abb664535bf21c7ca50fb8fa4511fa90052b`)
  - wind: `DATA/wind-resource/features/gwa_v4_wind-feature_2025_nsw.gpkg` (layer `wind_features`, 47,311 rows, SHA-256 `b350dc3d4847ae9df2c6e0f3f1ecdecb74e2bcd960ca05f462203bf2eea72be8`)
  - geographic: `DATA/geographic/features/optmining_geographic-features_2024_nsw.gpkg` (layer `geographic_features`, 47,311 rows, SHA-256 `af9db24669bdaf6d45154987d133d7c03a7b01833c920d601b93fa3057c04031`)
  - infrastructure: `DATA/infrastructure/optmining_infra-features_2026_nsw.gpkg` (layer `infra_features`, 47,311 rows, SHA-256 `12bca14fccc7d89f687d5026dc762b8a1d32f5f4365e8d893e0163881bbe1d8e`)
  - demand: `DATA/electricity-demand/aemo_demand-proxy_2026_nsw.gpkg` (layer `demand_proxy`, 47,311 rows, SHA-256 `f04be6b449e1f3410b3aa4733786fc4c3cb681042c6f2e678cdcb52031a29c1e`)
  - exclusions: `DATA/exclusions/optmining_exclusions_2024_nsw.gpkg` (layer `optmining_exclusions_2024_nsw.gpkg`, 47,311 rows, SHA-256 `e1bebde00500c3969239ad8b33e64e6a5e7f5660bdb32c04362de60f7ef3e172`)
  - demand_coord_confidence: `DATA/electricity-demand/aemo_demand-coord-confidence_2026_nsw.csv` (layer `(CSV sidecar)`, 47,311 rows, SHA-256 `a4e2bbeede59597e5725d487bda5ed82d3be2eb3b0d1904236b455c303e34c11`)
- **Method:** left joins on `cell_id` from the S1-02 grid; row count asserted after every join; excluded cells retained with `eligible = False`; no reprojection, no back-filling; composite confidence appended by the S1-09 layer (`confidence.assess()`).
- **Confidence config:** `pipeline/integration/confidence_weights.yaml` (version `1.0`, SHA-256 `2cd31b17ae28cff604aa6416079275678b137f4b866ee4e1e806088895e1eab8`)
- **Regenerable:** yes — `python -m pipeline --only integration` (after the five feature stages and `exclusions`).
- **SHA-256 (GeoPackage):** `011ebbc3020fe136b48bec967bf58b64393a5bf001f9276a2e3d8ae551d6fc11`
- **SHA-256 (CSV):** `247d8d9f61378292ca1f9a8aba20512f0582491e1b9039a007abb5442ac872f6`
- **Rows:** 47,311
- **Generated (UTC):** 2026-10-21T12:41:42+00:00
- **Git commit:** `7fb987eaa587d684c94a1e260e167f04f9dfcd8a-dirty`
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

### Re-freeze — statewide-coverage fix (data-spec §8 v1.12, 2026-10-05)

The S2-02 baseline above was **deliberately re-frozen** as part of the statewide-coverage
fix (a documented re-freeze of a *derived* baseline, not a bypass of the gate — see
`DATA/data-specification/sprint1_data_specification.md` §8 "Applied — S2-02 … re-freeze, v1.12").

- **Trigger:** the exclusions stage was migrated to join the statewide wind + geographic +
  demand feature tables and the `missing_demand_data` reason code was added, so the regenerated
  integrated table's bytes changed and its SHA-256 no longer matched the previous pinned
  reference.
- **Old SHA-256:** `8b300ca520ff42028fbb7b09024916580c105967c92fa8ade575c4e006c196fd`
  (New-England-window baseline, 1,233 eligible cells).
- **New SHA-256:** `4062224a2b96adace37f5166feb0fb7b7dbd9251e9433ed5028659347d2a1c80`
  (statewide baseline, 32,525 eligible cells, re-frozen after the `missing_demand_data` rule and
  the full chain regeneration), recorded by `freeze_baseline(write=True)` with the
  original `frozen_at_utc` preserved. Re-validation then reports `all_passed = true` and the
  "Baseline hash matches the frozen reference" check reads "match".
- **Not a frozen-parameter change:** no §2 decision (Q1–Q7) is touched and geographic extent is
  not frozen, so the data-spec "Modifying a Frozen Parameter" dual-edit process is not triggered.
  The re-freeze is reversible (the old hash is in git history and the data-spec §8 record).
