# Task 4 — Build the Demand Feature Layer

**Sprint:** 1 (Week 1)
**Assignee:** TBD
**Status:** Not Started
**Estimated Effort:** 2.5 days

---

## 1. Objective

Produce a per-cell demand indicator by allocating AEMO NSW1 regional operational demand across cells with population weighting — while preserving, at every surface, the agreed distinction: **AEMO regional demand ≠ local cell demand**. The per-cell value is an *estimated demand indicator*, never "demand" or "consumption".

## 2. Context & Frozen Decisions

- **Q5**: Operational Demand (Actual, Half-Hourly) from NEMWeb Archive — not PRICE_AND_DEMAND.
- **Q4**: population source is **ABS Census 2021 ERP at SA2 level**.
- Allocation formula (Task 5 §6, recorded verbatim in provenance):
  `demand_local_proxy_mw = NSW1_annual_mean_MW × (cell_pop / Σ pop over NSW+ACT SA2s)`
  with `cell_pop` estimated by area-weighting SA2 populations over cells.
- NSW1 = NSW + ACT (constant); Sprint 0 measured NSW1 annual mean ≈ 7,565.6 MW on the 1-year sample.
- The caveat must appear in **three places**: the provenance file, the column description in `DATA_SPECIFICATION.md`, and the Task 11 query CLI output.

## 3. Scope

**In:**
- ABS SA2 ERP acquisition (the sprint's one missing dataset — pre-approved by Task 5 §8, not a new addition)
- AEMO demand re-download (raw data is gitignored and absent locally), extended to 3 financial years
- SA2 boundary download (NSW + ACT)
- `pipeline/features/demand.py` — allocation stage
- Bundled cleanup: `pipelines.demand` → `pipeline.demand` docstrings; write the missing `DATA/electricity-demand/DATA_PROVENANCE.md`

**Out:**
- Any claim about local grid connection capacity or demand growth (explicitly listed non-meanings)
- Mesh-block or gridded-population refinement (recorded as future work per Q4)

## 4. Inputs

- **ERP (Day 1, does not wait for Task 2):** primary route — ABS Data API (`https://data.api.abs.gov.au`): probe `.../rest/dataflow/ABS?detail=allstubs` to confirm the ERP-by-SA2 dataflow id (regional-population family), then query SA2-level ERP for NSW + ACT, 2021 vintage, `?format=csv`. Fallback route — ABS Census 2021 GCP DataPack (SA2, NSW+ACT), table G01 usual-resident population, with the documented caveat that G01 usual residents ≠ ERP.
- **SA2 polygons:** `https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/SA2/FeatureServer/0` via `query_layer_geojson` (`pipeline/common/geo.py:145-204`) — explicit `outSR=4326` (the service silently returns Web Mercator otherwise), paged, ~700 NSW+ACT features of 2,473 national.
- **AEMO demand:** existing chain `pipeline/demand/` (download → validate → inspect → aggregate); `https://nemweb.com.au/Reports/Archive/Operational_Demand/ACTUAL_DAILY/`.
- Task 2 cell index + fine land mask.

## 5. Implementation Plan

- [ ] **Day 1 (parallel with Task 2):** run the ERP probe; download SA2 ERP CSV; download SA2 polygons; extend `pipeline/demand/config.py` defaults to `2023-07-01 → 2026-06-30` (3 financial years — Task 2 §9 recommendation; avoids COVID-suppressed 2020–21) and re-run `python -m pipeline.demand` to regenerate `demand_annual_summary.csv`.
- [ ] Create `pipeline/features/demand.py` with `run(area_name="nsw", erp_year=2021, verbose=False) -> dict`:
  1. Rasterize SA2 polygons onto the 0.0025° subgrid with each polygon's array index as burn value (`rasterio.features.rasterize` over GeoJSON dicts — the established no-shapely pattern, cf. `pipeline/validate.py:158-165`).
  2. Count subpixels per SA2 → each subpixel carries `SA2_pop / SA2_subpixel_count`.
  3. `cell_pop` = sum of subpixel population over the cell's 20×20 block, **counting only subpixels inside the NSW land mask** (ACT and out-of-state parts of border SA2s contribute to the regional denominator but not to NSW cells — documented ACT treatment).
  4. `demand_local_proxy_mw` per the frozen formula; denominator = Σ ERP over all NSW+ACT SA2s.
  5. Join onto the cell index; write CSV + report.
- [ ] Write `DATA/electricity-demand/DATA_PROVENANCE.md` (closes the domain's missing-provenance gap): source, formula verbatim, assumptions (population as demand proxy; area-uniform population within SA2), and the three-part caveat block including what the value does **not** mean (local consumption, connection capacity, demand growth).
- [ ] Cleanup: fix `pipelines.demand` (plural) references in `pipeline/demand/__init__.py`, `demand/README.md`, `demand/aggregate.py`, `demand/inspect.py`.

## 6. Outputs

| Output | Path |
|---|---|
| Demand feature table | `DATA/features/optmining_demand-features_0.05deg_nsw.csv` |
| Report | `DATA/features/metadata/demand_features_report.md` |
| SA2 boundaries | `DATA/geographic/boundaries/abs_sa2_2021_nsw-act.geojson` |
| SA2 ERP table | `DATA/electricity-demand/abs_erp-sa2_2021_nsw-act.csv` |
| Regenerated 3-yr summary | `DATA/electricity-demand/demand_annual_summary.csv` + `.meta.json` |
| Domain provenance (new) | `DATA/electricity-demand/DATA_PROVENANCE.md` |

Feature-table columns:

| Column | dtype | Units | Description |
|---|---|---|---|
| cell_id | str | — | join key |
| population | float | persons | area-weighted SA2 ERP within the cell |
| demand_local_proxy_mw | float | MW | **estimated demand indicator** — population-weighted share of NSW1 regional operational demand; not measured local demand |
| demand_alloc_method | str | — | constant `"sa2-area-weighted-population"` (provenance travels with data) |

## 7. Configuration Parameters

| Parameter | Default | CLI flag | Meaning |
|---|---|---|---|
| `erp_year` | `2021` | `--erp-year` | ERP vintage (Q4) |
| `start_date` / `end_date` | `2023-07-01` / `2026-06-30` | `--start-date` / `--end-date` | demand averaging window |

## 8. Acceptance Criteria

- [ ] **Population conservation:** Σ `population` over NSW cells + documented ACT/out-of-mask remainder = Σ SA2 ERP within 1%.
- [ ] **Demand conservation:** Σ `demand_local_proxy_mw` × (regional pop / NSW-cell pop) reconciles to NSW1 annual mean MW within 1% (i.e. the allocation distributes exactly the regional total across the full NSW+ACT population).
- [ ] The words "regional demand allocated by population; not measured local demand" (or equivalent) appear in the provenance file and the `DATA_SPECIFICATION.md` column entry; Task 11 acceptance re-checks the CLI surface.
- [ ] `demand_annual_summary.meta.json` shows the 3-year window and passes the existing 6-check quality gate.
- [ ] No remaining `pipelines.demand` references: `grep -rn "pipelines\." pipeline/` is empty.

## 9. Tests

`tests/test_features_demand_unit.py`: allocation arithmetic on synthetic SA2 rasters (two SA2s, known pops → exact expected cell values); conservation property (Σ allocated = regional total on a fully-covered synthetic region); border-SA2 case (SA2 half outside the mask → cell values halve, denominator unchanged).

## 10. Risks & Mitigations

- **ABS Data API dataflow naming churn** (highest external risk): the probe step runs Day 1; the G01 DataPack fallback is fully specified and only changes one input file + one provenance caveat.
- **NEMWeb archive layout drift** since Sprint 0: the existing `download.py` scrapes listings — if the archive moved, fall back to the 1-year window already proven and log the deviation.
- **Border/ACT accounting confusion**: the conservation checks are designed to catch exactly this; the ACT treatment is written down before coding.

## 11. Dependencies

**Blocked by:** Task 1 (spec); Task 2 (cell index) — *except* the Day-1 acquisition substep, which starts immediately.
**Blocks:** Tasks 7, 8, 10, 12.

## 12. Decision Log

| Date | Decision / Surprise | Rationale |
|---|---|---|
