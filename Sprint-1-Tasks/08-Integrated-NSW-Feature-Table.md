# Task 8 — Create the Integrated NSW Feature Table

**Sprint:** 1 (Week 2)
**Assignee:** TBD
**Status:** Not Started
**Estimated Effort:** 1 day

---

## 1. Objective

Assemble the single integrated dataset — one row per NSW land cell carrying every feature, the eligibility verdict, and provenance metadata. This file is what "Opt-Mining knows about a location". Reference shape from the sprint brief (site ids are our `cell_id`s):

| Site | Wind | Demand Proxy | Transmission Dist. | Substation Dist. | Slope | Protected | Eligible |
|---|---|---|---|---|---|---|---|
| NSW001 | 7.8 | 0.72 | 4.2 | 11.3 | 3.1 | No | Yes |
| NSW002 | 8.4 | 0.51 | 19.7 | 26.4 | 7.8 | No | Yes |
| NSW003 | 9.1 | 0.43 | 5.6 | 8.9 | 2.4 | Yes | No |

## 2. Context & Frozen Decisions

- File format decision (sprint-level): **CSV primary** (~30.5k rows × ~40 cols ≤ 20 MB, diffable, pandas-native; Parquet would require pyarrow, outside the frozen scipy-only dependency decision) + **GeoJSON** for the spatial surface + **`.meta.json`** sidecar (existing demand-domain pattern) carrying schema version, parameter values, and input manifest references.
- Every column's dtype and units must appear in `DATA/DATA_SPECIFICATION.md` — the schema below is the contract shared by Tasks 3–11.

## 3. Scope

**In:**
- `pipeline/features/assemble.py` (join stage) + GeoJSON emission
- The full-schema contract table (below) recorded in `DATA_SPECIFICATION.md`

**Out:**
- Quality flags (Task 9 adds `q_*` columns via the annotation module assemble calls)
- Score/rank columns (Task 10/11 append)

## 4. Inputs

- Task 2 cell index; Tasks 3–6 feature CSVs; Task 7 eligibility CSV — all keyed by `cell_id`

## 5. Implementation Plan

- [ ] Create `pipeline/features/assemble.py` with `run(area_name="nsw", verbose=False) -> dict`:
  1. Left-join the cell index against each feature CSV and the eligibility CSV on `cell_id` (pandas); assert zero row loss and zero duplication after each join (anti-join check = 0).
  2. Call the Task 9 quality annotator when present (`pipeline/features/quality.py`; assemble runs before Task 9 lands by skipping annotation with a WARN line — forwards-compatible).
  3. Write the integrated CSV (column order = schema order below).
  4. Write the GeoJSON: one Polygon per cell from its 0.05° bounds (5-decimal coords ≈ 1 m precision), properties limited to the compact set (cell_id, eligible, exclusion_primary, wind_speed_100m_mean, demand_local_proxy_mw, dist_transmission_km, slope_mean_deg, protected) to keep the file ≈ 10–20 MB.
  5. Write `.meta.json`: `schema_version: "1.0"`, generation timestamp, parameter values in force, and the paths+hashes of every input file (provenance travels with data).
- [ ] Add the full schema table to `DATA/DATA_SPECIFICATION.md` §Integrated Table.
- [ ] Register stage `features.assemble`.

## 6. Outputs

| Output | Path |
|---|---|
| Integrated table | `DATA/integrated/optmining_site-screening_0.05deg_nsw.csv` |
| Spatial surface | `DATA/integrated/optmining_site-screening_0.05deg_nsw.geojson` |
| Sidecar | `DATA/integrated/optmining_site-screening_0.05deg_nsw.meta.json` |

**Full schema (the contract):**

| Column | dtype | Units | From |
|---|---|---|---|
| cell_id | str | — | T2 |
| grid_row, grid_col | int | — | T2 |
| centroid_lon, centroid_lat | float | deg EPSG:4326 | T2 |
| centroid_x_3577, centroid_y_3577 | float | m EPSG:3577 | T2 |
| lon_min, lat_min, lon_max, lat_max | float | deg EPSG:4326 | T2 |
| area_km2 | float | km² | T2 |
| land_fraction | float | 0–1 | T2 |
| wind_speed_100m_mean / _p90 / _max | float | m/s | T3 |
| wind_speed_150m_mean | float | m/s | T3 |
| capacity_factor_iec2_mean | float | ratio | T3 |
| wind_valid_fraction | float | 0–1 | T3 |
| population | float | persons | T4 |
| demand_local_proxy_mw | float | MW | T4 |
| demand_alloc_method | str | — | T4 |
| dist_transmission_km | float | km 3577 | T5 |
| dist_substation_km | float | km 3577 | T5 |
| inside_rez | bool | — | T5 |
| rez_name | str, nullable | — | T5 |
| elevation_mean_m | float | m ASL | T6 |
| slope_mean_deg, slope_p90_deg | float | deg | T6 |
| landuse_dominant_class / _label | int / str | ALUM v8 | T6 |
| water_fraction, urban_fraction, protected_fraction | float | 0–1 | T6 |
| protected | bool | — | T6 |
| eligible | bool | — | T7 |
| exclusion_reasons | str | — | T7 |
| exclusion_primary | str, nullable | — | T7 |
| q_wind, q_demand, q_infra, q_geo | str {ok,partial,missing} | — | T9 |
| score | float, nullable | 0–1 | T10 |
| rank | int, nullable | — | T11 |

## 7. Configuration Parameters

| Parameter | Default | CLI flag | Meaning |
|---|---|---|---|
| `area_name` | `nsw` | `--area-name` | input/output slug |

## 8. Acceptance Criteria

- [ ] Row count = Task 2 land-cell count; zero duplicate `cell_id`s; anti-join row loss = 0 at every join.
- [ ] Column order and names match the schema table exactly (a schema-diff check in the stage).
- [ ] Every column appears in `DATA_SPECIFICATION.md` with dtype + units.
- [ ] `.meta.json` names every input file with hash; regenerating from unchanged inputs is byte-identical (atomic write, deterministic ordering).
- [ ] GeoJSON loads in QGIS/geojson.io and renders NSW's shape (visual smoke check, noted in report).

## 9. Tests

`tests/test_assemble_unit.py`: join integrity on synthetic frames (missing cell in one feature CSV → NO_DATA-consistent null, not row loss); schema-order enforcement; GeoJSON polygon bounds round-trip cell_id.

## 10. Risks & Mitigations

- **Schema drift between sheets**: this table is the single contract; Tasks 3–7 sheets reference it; Task 12 re-validates.
- **GeoJSON size**: compact properties + 5 dp; if >25 MB, drop to centroid Points (Decision Log entry).

## 11. Dependencies

**Blocked by:** Tasks 2–7.
**Blocks:** Tasks 9, 10, 11, 12.

## 12. Decision Log

| Date | Decision / Surprise | Rationale |
|---|---|---|
