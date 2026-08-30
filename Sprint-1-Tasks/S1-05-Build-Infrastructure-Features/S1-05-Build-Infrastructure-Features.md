# S1-05: Build Infrastructure Features

**Type:** Story  
**Priority:** High  
**Story Points:** 5  
**Labels:** feature-engineering, infrastructure  
**Blocked by:** S1-01, S1-02  
**Blocks:** S1-08

---

## Objective

Convert the Sprint 0 infrastructure investigation into measurable per-cell features. Derive distance-based and categorical infrastructure indicators for every analysis cell.

---

## Context

During Sprint 0, infrastructure datasets were investigated including transmission lines, substations, connection points, and Renewable Energy Zones (REZs). This task takes those investigated datasets and computes actual numeric features that describe each cell's relationship to grid infrastructure.

Proximity to infrastructure is a key factor in wind farm viability — sites far from transmission are more expensive to connect.

---

## Deliverables

1. Pipeline module at `pipeline/infrastructure/` that computes infrastructure features per cell
2. Output table/GeoDataFrame with distance and categorical features
3. Documentation of calculation methods and data sources

---

## Acceptance Criteria

- [ ] Pipeline module (`pipeline/infrastructure/`) derives the following for each analysis cell:
  - `distance_to_nearest_transmission_line` (km)
  - `distance_to_nearest_substation` (km)
  - `distance_to_nearest_connection_point` (km)
  - `inside_REZ` (boolean)
  - `rez_name` (string, nullable — name of REZ if inside one)
- [ ] Additional defensible indicators from Sprint 0 are included if justified (e.g. transmission line voltage, substation capacity)
- [ ] Distance calculations use a **projected CRS** (not geographic degrees) — document which projection
- [ ] Distances are measured from cell centroid to nearest feature (document this choice)
- [ ] Output table: `cell_id | dist_transmission_km | dist_substation_km | dist_connection_km | inside_rez | rez_name | confidence_flag`
- [ ] Missing or unavailable infrastructure data results in a flag, not a fabricated value
- [ ] Automated — runs as part of the pipeline
- [ ] Unit tests cover distance calculation logic
- [ ] Performance is acceptable for full NSW grid (document runtime)

---

## Data Sources (from Sprint 0)

- Transmission lines: `DATA/infrastructure/` (Geoscience Australia power lines)
- Substations: `DATA/infrastructure/` (Geoscience Australia substations)
- Connection points: `DATA/infrastructure/connection-points/aemo_kci_2026.xlsx`
- REZ boundaries: `DATA/infrastructure/rez/`
- Generators (for context): `DATA/infrastructure/generators/`

---

## Technical Notes

- Use `geopandas.sjoin_nearest` or equivalent for distance calculations in projected space
- Per the Constitution: "Make coordinate reference systems, spatial resolutions and units explicit at every boundary"
- Consider using EPSG:3577 (Australian Albers) for distance calculations regardless of the analysis cell CRS
- For transmission lines, distance should be to the nearest point on the line geometry, not to line endpoints

---

## Example Output

| cell_id | dist_transmission_km | dist_substation_km | dist_connection_km | inside_rez | rez_name | confidence |
|---------|---------------------|-------------------|-------------------|------------|----------|------------|
| NSW001  | 4.2                 | 11.3              | 15.7              | Yes        | New England | high    |
| NSW002  | 19.7                | 26.4              | 32.1              | No         | —        | high       |
| NSW003  | 5.6                 | 8.9               | 12.3              | Yes        | Central-West | high  |

---

## How to Complete This Task

This ticket is now backed by a full spec. Three companion documents sit in this
same folder and should be read in this order before writing any code:

1. **`requirements.md`** — the authoritative, testable definition of "done".
   Every acceptance criterion above is expanded into EARS-format requirements
   (R1–R15) with precise, verifiable clauses. When this ticket and
   `requirements.md` appear to disagree, `requirements.md` wins.
2. **`design.md`** — how the stage is built: the new
   `pipeline/infrastructure/features.py` module, its `run(verbose=False, state="NSW",
   ...) -> dict` entry point, distance computation via `sjoin_nearest` in EPSG:3577,
   the connection-point (xlsx) CRS-resolution step, REZ membership, the output
   schema, provenance, and the thirteen Correctness Properties the tests must
   uphold. Read this to understand *how* the requirements are satisfied.
3. **`tasks.md`** — the actual build order. This is the checklist you execute:
   a dependency-ordered plan (with a Task Dependency Graph) that goes config →
   loaders → the pure distance/REZ core → confidence → writers → provenance →
   `run()` → stage registration → no-silent-passes validation → integration/smoke
   tests → documentation.

### Working the plan

- Open `tasks.md` and execute tasks top-to-bottom. Each task lists the specific
  requirement clauses it satisfies (`_Requirements: ...`). Use those to jump back
  into `requirements.md` / `design.md` for detail.
- Tasks marked with `*` are optional test sub-tasks; core implementation tasks are
  never optional. Do not skip the no-silent-passes validation or the stage
  registration.
- Stop at the checkpoints, run the test suite, and confirm green before moving on.

### Things the spec pins down (don't diverge silently)

- **All distances in EPSG:3577** (Australian Albers), measured from the **cell
  centroid** to the **nearest point on the nearest geometry** (for lines, not the
  endpoint). Storage stays EPSG:4326. Make every CRS boundary explicit and logged.
- **Route all three GA layers (transmission lines, substations, generators) through
  `pipeline/infrastructure/helpers.py`** with the identical `filter_by_state` rule.
  Do not hand-roll per-layer loading — fixing one layer and leaving the others is a
  known anti-pattern for this codebase.
- **Missing / unreadable / empty source => null feature + `low` confidence**, never a
  fabricated or sentinel distance (Constitution: "never invent data"). Grid and CRS
  problems are fatal and must halt before any output is written.
- **Reconcile `EXPECTED_FILES`** in `pipeline/infrastructure/config.py`: the existing
  transmission-lines entries (e.g. `part_001`/`part_002`) must line up with the
  actual source path this stage loads, and the REZ boundaries + connection-points
  file must be listed. See `tasks.md` task 1 and `design.md` §Components.

### Cross-component impact (must ship together)

Finishing this task is not just writing `features.py`. To keep the pipeline
consistent you must also: register `infrastructure.features` in
`pipeline/config.py` `STAGES` **after `grid`**; add the `_get_runner` dispatch and
CLI flag(s) (`--infra-features-crs`, reuse `--state`) in `pipeline/__main__.py`;
update the `pipeline/infrastructure/__init__.py` docstring; keep GA-layer handling
in `helpers.py` consistent; record provenance (`DATA_PROVENANCE.md` +
`download_manifest.json` + `source_register`); document the full-NSW-grid runtime;
and update `pipeline/README.md` (stage order + expected outputs, stating the
EPSG:3577 distance projection and centroid-based definition) and the data
specification §4.3/§7.

> Note: this file is a documentation snapshot. The `requirements.md` / `design.md` /
> `tasks.md` that Kiro's task runner uses live in the workspace spec store; the
> copies in this folder are for reading alongside the ticket and may drift if the
> spec is later edited.
