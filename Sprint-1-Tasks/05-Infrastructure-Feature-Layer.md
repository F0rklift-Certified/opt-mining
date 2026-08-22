# Task 5 — Build Infrastructure Features

**Sprint:** 1 (Week 1)
**Assignee:** TBD
**Status:** Not Started
**Estimated Effort:** 2.5 days

---

## 1. Objective

Convert the Sprint 0 infrastructure investigation into measurable site-level features: straight-line distance to the nearest high-voltage transmission line, distance to the nearest substation, and REZ membership — computed in a projected CRS and labelled for exactly what they are.

## 2. Context & Frozen Decisions

- **Q7**: no hard distance threshold — distances are continuous penalties; remote cells rank low naturally.
- Distances are **Euclidean in EPSG:3577** and are never called "network distance" or "available capacity" (Task 3 Sprint 0 conclusion). Substation voltage ≠ spare capacity.
- Line filter: `capacity_kv ≥ 132` for the transmission-distance feature (66 kV distribution noise excluded) — parameter, not constant.
- REZ source of truth for NSW: **NSW EnergyCo shapefiles** (EPSG:4283 GDA94); the AEMO ISP KMZ is an indicative national overlay used for cross-checking only.
- **`distance_to_nearest_connection_point` is DROPPED for Sprint 1**: the AEMO Key Connection Information workbook has no coordinates (Sprint 0 Task 3 finding), so the feature cannot be built honestly. Publishing a substation-distance proxy under a "connection point" name would be misleading; `dist_substation_km` already carries that information under its true name. Revisit triggers, recorded in `DATA_SPECIFICATION.md`: AEMO publishing coordinates, or a name-matched KCI↔GA-substation join implemented as an explicitly low-confidence stretch feature.

## 3. Scope

**In:**
- `dist_transmission_km`, `dist_substation_km`, `inside_rez`, `rez_name`
- EnergyCo REZ format resolution (Day-1 spike — see plan)
- scipy added to `requirements.txt` (pinned; the first and only new dependency this sprint)
- Bundled: write the missing `DATA/infrastructure/DATA_PROVENANCE.md`

**Out:**
- Connection-point feature (dropped, per above)
- Network distance, hosting capacity, congestion — out of scope for the entire MVP
- Generator proximity features (GA power stations remain validation reference only)

## 4. Inputs

- `DATA/infrastructure/transmission-lines/ga_power_lines_2026_nsw.geojson` (957 NSW features; regenerate subsets via `pipeline.infrastructure.inspect` if needed)
- `DATA/infrastructure/substations/ga_substations_2026_nsw.geojson` (586 NSW features)
- `DATA/infrastructure/renewable-energy-zones/energyco-nsw/*.zip` — three Shapefile ZIPs (New England, Central-West Orana, Hunter-Central Coast), EPSG:4283
- `DATA/infrastructure/renewable-energy-zones/aemo_indicative_rez_boundaries_2026.kmz` (cross-check)
- `pipeline/infrastructure/helpers.py` — `iter_coordinates`, `filter_by_state`, `compute_bounds`
- Task 2 cell index (`centroid_x_3577`, `centroid_y_3577`) + fine land mask grid geometry

## 5. Implementation Plan

- [ ] **Day-1 spike — REZ format resolution** (the sprint's riskiest technical item; timeboxed to half a day, escalate if all routes fail). The frozen dependency set has no shapefile reader (rasterio reads rasters; no fiona/geopandas). Route ladder, in order:
  - (a) **ArcGIS endpoint**: probe NSW SEED / EnergyCo portals for a REZ FeatureServer; if found, reuse `query_layer_geojson` with explicit `outSR=4326` — cleanest, no new code.
  - (b) **Minimal stdlib reader**: `pipeline/infrastructure/shp.py` — `struct`-based parser for shapefile record types 5/15 (Polygon/PolygonZ) only, ~60 lines, converting to GeoJSON dicts; offline-testable against the three committed ZIPs. (.prj confirms 4283; treat as 4326-equivalent at dataset accuracy, note the ~1.8 m datum offset.)
  - (c) **AEMO KMZ** (stdlib zipfile + XML): national indicative polygons as cross-check only — never the NSW source of truth.
- [ ] Add `scipy` (pinned current stable) to `requirements.txt` with a comment noting it also unblocks `pipeline/integration/analyse.py`'s existing cKDTree usage.
- [ ] Create `pipeline/features/infrastructure.py` with `run(area_name="nsw", min_voltage_kv=132, densify_m=100.0, verbose=False) -> dict`:
  1. Load NSW lines; filter `capacity_kv ≥ min_voltage_kv` via `helpers.py` patterns.
  2. Transform vertices 4326→3577 (`rasterio.warp.transform`, batch); **densify** segments to ≤ `densify_m` vertex spacing (pure numpy linear interpolation). Densification bounds the vertex-vs-true-segment error to ≤ densify_m/2 = 50 m — negligible against 5 km cells; state this in the report.
  3. Build one `scipy.spatial.cKDTree` over densified line vertices; query all ~30.5k cell centroids at once; `/1000` → km. Same pattern for substation points (no densification needed).
  4. `inside_rez`: rasterize REZ polygons (from the spike's chosen route) onto the 0.0025° subgrid; a cell is inside if any of its subpixels is (binary); `rez_name` from the polygon; cells in no REZ → `inside_rez=False`, `rez_name` empty.
  5. Join onto the cell index; write CSV + report (report includes voltage-filter counts and the densification-error statement).
- [ ] Convert the EnergyCo boundaries to committed GeoJSON beside the ZIPs (`energyco_<rez-slug>_rez_boundary.geojson`) with derivation notes ("converted from EnergyCo shapefile <file>, EPSG:4283→4326"), keeping originals untouched (house rule: derived files distinguishable by name, sources never overwritten).
- [ ] Write `DATA/infrastructure/DATA_PROVENANCE.md` (closes the domain's missing-provenance gap): GA layers, EnergyCo REZ, AEMO KMZ, KCI — with the connection-point drop decision and its revisit triggers.

## 6. Outputs

| Output | Path |
|---|---|
| Infrastructure feature table | `DATA/features/optmining_infrastructure-features_0.05deg_nsw.csv` |
| Report | `DATA/features/metadata/infrastructure_features_report.md` |
| Converted REZ GeoJSONs | `DATA/infrastructure/renewable-energy-zones/energyco-nsw/energyco_*_rez_boundary.geojson` |
| Domain provenance (new) | `DATA/infrastructure/DATA_PROVENANCE.md` |
| scipy dependency | `requirements.txt` |

Feature-table columns:

| Column | dtype | Units | Description |
|---|---|---|---|
| cell_id | str | — | join key |
| dist_transmission_km | float | km (EPSG:3577 Euclidean) | to nearest ≥132 kV line; straight-line, not network distance |
| dist_substation_km | float | km (EPSG:3577 Euclidean) | to nearest GA substation (any voltage) |
| inside_rez | bool | — | cell intersects an NSW EnergyCo REZ |
| rez_name | str, nullable | — | e.g. "New England"; empty when inside_rez=False |

## 7. Configuration Parameters

| Parameter | Default | CLI flag | Meaning |
|---|---|---|---|
| `min_voltage_kv` | `132` | `--min-voltage` | line filter for the transmission-distance feature |
| `densify_m` | `100.0` | — | max vertex spacing before KD-tree build |

## 8. Acceptance Criteria

- [ ] Brute-force point-to-segment distance on 100 random cells matches the KD-tree result within the densification tolerance (≤ 50 m + float noise).
- [ ] A cell on the Armidale 330 kV corridor has `dist_transmission_km < 5`; a far-western NSW cell has `dist_transmission_km > 100` (continuous, not clipped).
- [ ] New England REZ interior cell → `inside_rez=True` with `rez_name="New England"`; Sydney CBD cell → `False`.
- [ ] EnergyCo-derived REZ area agrees with the AEMO KMZ overlay to the expected indicative-vs-official tolerance (report, not gate).
- [ ] No column or doc text names a "connection point" feature; the drop decision + triggers are in `DATA_SPECIFICATION.md` and the domain provenance.
- [ ] `pip install -r requirements.txt` on a clean venv succeeds with scipy pinned.

## 9. Tests

`tests/test_features_infrastructure_unit.py`: KD-tree vs brute force on synthetic line sets; densification produces spacing ≤ parameter; voltage filter counts on synthetic features; if route (b) was taken — `shp.py` parses a tiny committed fixture shapefile (few-vertex polygon) to the expected GeoJSON.

## 10. Risks & Mitigations

- **REZ format gap** (main risk): three-route ladder above, timeboxed Day-1 spike, escalation path = raise in Decision Log + team call before Day 3.
- **GA service drift**: all needed GA files are already committed; no live GA dependency in the stage itself.

## 11. Dependencies

**Blocked by:** Task 1 (spec); Task 2 (cell index) — *except* the Day-1 REZ spike + scipy pin, which start immediately.
**Blocks:** Tasks 7, 8, 10, 12.

## 12. Decision Log

| Date | Decision / Surprise | Rationale |
|---|---|---|
