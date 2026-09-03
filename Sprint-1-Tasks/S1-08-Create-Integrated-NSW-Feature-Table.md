# S1-08: Create the Integrated NSW Feature Table

**Type:** Story  
**Priority:** High  
**Story Points:** 5  
**Labels:** integration, pipeline  
**Blocked by:** S1-03, S1-04, S1-05, S1-06, S1-07  
**Blocks:** S1-09, S1-10  
**Status:** Complete  
**Completed:** 2026-09-03

---

## Objective

Join all feature layers and the exclusion layer into a single integrated site dataset for NSW. This is the core Sprint 1 deliverable — the table that answers "what does Opt-Mining know about this location?"

---

## Context

By this point, the pipeline has produced:
- Wind features (S1-03)
- Demand proxy features (S1-04)
- Infrastructure features (S1-05)
- Geographic/environmental features (S1-06)
- Exclusion flags (S1-07)

This task merges them all by `cell_id` into a single, comprehensive feature table that serves as the input to scoring and the queryable output of the pipeline.

---

## Deliverables

1. Pipeline step at `pipeline/integration/` that performs the merge
2. Integrated feature table saved as GeoPackage (with geometry) and CSV (without geometry)
3. Merge validation report

---

## Acceptance Criteria

- [x] Pipeline step (`pipeline/integration/`) merges all feature layers by `cell_id`
- [x] Output table includes at minimum:

| Column | Source | Units |
|--------|--------|-------|
| cell_id | Grid (S1-02) | — |
| geometry | Grid (S1-02) | — |
| centroid_lat | Grid (S1-02) | degrees |
| centroid_lon | Grid (S1-02) | degrees |
| wind_speed | Wind (S1-03) | m/s |
| demand_proxy | Demand (S1-04) | normalised 0–1 |
| dist_transmission_km | Infrastructure (S1-05) | km |
| dist_substation_km | Infrastructure (S1-05) | km |
| dist_connection_km | Infrastructure (S1-05) | km |
| inside_rez | Infrastructure (S1-05) | boolean |
| elevation_m | Geographic (S1-06) | m |
| slope_deg | Geographic (S1-06) | degrees |
| land_use | Geographic (S1-06) | category |
| protected_area | Geographic (S1-06) | boolean |
| eligible | Exclusion (S1-07) | boolean |
| exclusion_reason | Exclusion (S1-07) | text |
| data_confidence | All layers | flag/score |

- [x] All columns retain their units, documented in metadata or column naming convention
- [x] Rows for excluded cells are **retained** but marked as ineligible (do not drop them)
- [x] Output saved as:
  - GeoPackage (with geometry) for GIS use
  - CSV (without geometry) for tabular analysis
- [x] Row count matches the total analysis grid cell count (no rows lost or duplicated in join)
- [x] Merge validation checks:
  - No unexpected NaN inflation from bad joins
  - Row count before and after join is identical
  - No duplicate `cell_id` values
- [x] Automated — single command runs the full pipeline from raw data to integrated table
- [x] Output file path and format documented in pipeline README

---

## Example Output

| cell_id | wind_speed | demand_proxy | dist_transmission_km | dist_substation_km | slope_deg | protected | eligible |
|---------|-----------|--------------|---------------------|-------------------|-----------|-----------|----------|
| NSW001  | 7.8       | 0.72         | 4.2                 | 11.3              | 3.1       | No        | Yes      |
| NSW002  | 8.4       | 0.51         | 19.7                | 26.4              | 7.8       | No        | Yes      |
| NSW003  | 9.1       | 0.43         | 5.6                 | 8.9               | 2.4       | Yes       | No       |

---

## Technical Notes

- Use left joins from the grid to each feature layer to ensure no cells are dropped
- Validate: `assert len(integrated) == len(grid)` after each join
- Per the Constitution: keep "data integration, criteria derivation, scoring and presentation in separate layers"
- The integrated table is the boundary between the integration layer and the scoring layer
- Consider adding a `pipeline_version` or `run_timestamp` column for reproducibility

---

## Pipeline Command

The full pipeline should be runnable with a single command, e.g.:

```bash
python -m pipeline run --output outputs/sprint1_integrated_nsw.gpkg
```

This command should execute all steps from raw data through to the integrated table.

---

## Completion Notes

- Implemented as the `integration` stage in `pipeline/integration/merge.py` (paths and constants in `pipeline/integration/config.py`, every input path composed from the producing domain's config), registered in `config.STAGES` after `exclusions` and before `validate`, with an `integration` domain. `python -m pipeline` runs every stage from raw data to the integrated table; `python -m pipeline --only integration` re-joins already-generated layers. The ticket's example `python -m pipeline run --output …` sub-command was **not** added: the flat `--only/--skip` CLI convention was kept and, like every other stage, the output path is fixed under `DATA/`.
- Outputs (all committed): `DATA/integration/optmining_integrated-features_2026_nsw.gpkg` (layer `integrated_features`, EPSG:4326, 24.5 MB), `…_nsw.csv` (no geometry, 15.6 MB, byte-identical across reruns), `metadata/integration_method.md`, `metadata/merge_validation.md`, `metadata/integration_manifest.json`, and a generated block in `DATA/integration/DATA_PROVENANCE.md`. Vintage token `2026` = the newest upstream vintage merged.
- Column names follow the table above (`wind_speed` ← `wind.wind_speed_100m`, `dist_*_km`, `inside_rez`, …); the full source → target map with units is in the method report. Extra columns carried: `area_km2`, `source_region`, `rez_name`, `tri`, `protected_area_name`, `triggered_rules`, `data_flags`. Dropped: the constant `units`/`data_source`/`allocation_method` columns and S1-07's own recomputed `protected_area`/`protected_area_name`/`slope_deg`/`urban_area`/`wind_speed_100m_ms` (the geographic and wind layers are canonical; S1-07's copies are only compared in the WARN checks).
- **`data_confidence` is not emitted.** Deriving a composite confidence is S1-09's job; the table carries the four upstream flags under per-layer names (`wind_confidence`, `demand_confidence`, `infra_confidence`, `geo_confidence`) plus an objective `n_missing_features` count (nulls among the ten scored feature columns).
- Real run, 2026-09-03: 47,311 rows; 40/41 checks passed (0 fatal failures, 1 WARN); eligible **1,233**, excluded **46,078** (rows retained). `n_missing_features` histogram: 1 → 1,600 cells; 3 → 471; 4 → 38,603; 5 → 6,637 — the minimum is 1 because `dist_connection_km` is null for every cell (the AEMO KCI source has no coordinates). Runtime ≈ 1.8 s.
- **Finding for S1-07 (raise with Divyaansh):** the exclusion layer samples the New-England-REZ wind clip while `wind.features` covers all of NSW, so 45,711 cells are excluded as "Missing wind data" although the wind table has a value for every cell; in the 1,600 overlapping cells, 73 differ from `wind.features` by more than 0.01 m/s (likely partial-window cells at the clip boundary). Slope and protected-area agree exactly. S1-07's own migration note says it should now read the S1-03/S1-06 feature tables instead of recomputing.
- Data specification updated at §4.5 / §7 / §8 (v1.2). `DATA/exclusions/` was generated and committed here for the first time (the S1-07 branch never committed its output).
- Gaps deliberately not fixed in this ticket: the data specification has no §4 entries for the S1-04 demand-proxy table or the S1-07 Eligibility_Table; the README's exclusions scope note (S1-03/S1-06 "not implemented in code yet") is stale on this branch.
