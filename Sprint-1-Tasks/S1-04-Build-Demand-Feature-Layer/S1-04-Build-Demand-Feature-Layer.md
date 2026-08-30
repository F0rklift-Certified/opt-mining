# S1-04: Build the Demand Feature Layer

**Type:** Story  
**Priority:** High  
**Story Points:** 5  
**Labels:** feature-engineering, demand  
**Blocked by:** S1-01, S1-02  
**Blocks:** S1-08

---

## Objective

Use the AEMO operational-demand pipeline developed during Sprint 0 to produce a per-cell demand proxy feature. Maintain the agreed distinction: AEMO regional demand ≠ local cell demand.

---

## Context

AEMO publishes operational demand at the NEM region level (e.g. NSW1). This is aggregate demand for an entire state/region — it does not tell us about demand at a specific cell location. To produce a per-cell demand feature, we need a spatial-allocation method that distributes regional demand to cells.

This is explicitly a **proxy**, not a measurement. The allocation method and its assumptions must be documented transparently.

---

## Deliverables

1. Pipeline module at `pipeline/demand/` that produces a demand proxy per analysis cell
2. Documentation of the spatial-allocation formula and assumptions
3. Output table/GeoDataFrame with demand proxy values per cell

---

## Acceptance Criteria

- [ ] Pipeline module (`pipeline/demand/`) produces a demand proxy value for each analysis cell
- [ ] The spatial-allocation method is explicitly documented with:
  - Formula
  - Assumptions
  - Limitations
  - Data inputs (e.g. population grid, if used)
- [ ] Documentation clearly states this is a **proxy** and not measured local demand
- [ ] Output table: `cell_id | demand_proxy | allocation_method | source_region | confidence_flag`
- [ ] If population data or other weighting data is used, its source and vintage are recorded in the data specification (S1-01)
- [ ] Automated — runs as part of the pipeline
- [ ] Edge cases are documented:
  - Cells outside NEM regions
  - Cells on region boundaries
  - Cells in areas with no population data

---

## Allocation Options to Consider

| Method | Description | Pros | Cons |
|--------|-------------|------|------|
| Uniform | Divide regional demand equally across all cells | Simple | Unrealistic |
| Population-weighted | Allocate proportional to population density | More realistic | Requires population data |
| Load-centre proximity | Weight by distance to known load centres | Captures spatial pattern | Requires load centre data |
| Binary (high/low) | Classify cells as near/far from demand | Simple, avoids false precision | Loses nuance |

---

## Technical Notes

- The Sprint 0 demand pipeline already extracts and summarises AEMO operational demand data
- AEMO data lives in `DATA/electricity-demand/`
- Per the Constitution: "Never invent, extrapolate or hard-code data values to make a pipeline run"
- The demand proxy should be normalised (0–1) or expressed in interpretable units — document which

---

## Example Output

| cell_id | demand_proxy | allocation_method | source_region | confidence |
|---------|-------------|-------------------|---------------|------------|
| NSW001  | 0.72        | population_weight  | NSW1          | medium     |
| NSW002  | 0.51        | population_weight  | NSW1          | medium     |
| NSW003  | 0.03        | population_weight  | NSW1          | low        |

---

## How to Complete This Task

This ticket is now backed by a full spec. Three companion documents sit in this
same folder and should be read in this order before writing any code:

1. **`requirements.md`** — the authoritative, testable definition of "done".
   Every acceptance criterion above is expanded into EARS-format requirements
   (R1–R14) with precise, verifiable clauses. When this ticket and
   `requirements.md` appear to disagree, `requirements.md` wins.
2. **`design.md`** — how the stage is built: the new `pipeline/demand/feature.py`
   module, its `run(verbose=False, allocation_method="uniform", ...) -> dict`
   entry point, the spatial-disaggregation approach, source-region assignment via
   the NEM region geometry, CRS boundaries, the output schema, provenance, and the
   eleven Correctness Properties the tests must uphold. Read this to understand
   *how* the requirements are satisfied.
3. **`tasks.md`** — the actual build order. This is the checklist you execute:
   a dependency-ordered plan (with a Task Dependency Graph) that goes config →
   loaders → the pure allocation core → writers → provenance → `run()` → stage
   registration → no-silent-passes validation → documentation.

### Working the plan

- Open `tasks.md` and execute tasks top-to-bottom. Each task lists the specific
  requirement clauses it satisfies (`_Requirements: ...`). Use those to jump back
  into `requirements.md` / `design.md` for detail.
- Tasks marked with `*` are optional test sub-tasks; core implementation tasks are
  never optional. Do not skip the no-silent-passes validation (including the
  demand-conservation check) or the stage registration.
- Stop at the checkpoints, run the test suite, and confirm green before moving on.

### Decision you must confirm BEFORE building (see `design.md` "Review: Open Decision")

The allocation method is a genuine fork, and the plan defaults to one — confirm it
before you start:

- **Uniform (recommended MVP, the plan's default):** each cell in a NEM region gets
  `MEAN_DEMAND_MW / N_cells`. Needs no new dataset, conserves demand exactly, and is
  fully reproducible. The module is structured so a weighted method can be added
  later without changing the `run()` contract or output schema.
- **Population-weighted (frozen decision Q4: ABS Census 2021 ERP):** more realistic,
  but pulls in a new weighting dataset that then **requires** source-register
  registration (custodian, access, CRS, licence, vintage), a data-specification §4 +
  §8 change-control entry, and a no-coverage fallback path. Choosing this adds tasks.

Whichever you pick, the output stays a **proxy**, not a measurement (AEMO regional
demand ≠ local cell demand), and every value must trace to a real AEMO regional
figure — never fabricated (Constitution: "never invent data").

### Edge cases the spec already pins down

Cells outside all NEM regions, cells straddling a region boundary (deterministic
tie-break), and cells lacking weighting data are each handled explicitly with a
documented rule and a low `confidence_flag` — see `requirements.md` R4 and
`design.md`. Honor the **NSW1 = NSW+ACT** convention when assigning `source_region`.

### Cross-component impact (must ship together)

Finishing this task is not just writing `feature.py`. To keep the pipeline
consistent you must also: register `demand.feature` in `pipeline/config.py` `STAGES`
**after `grid`** (and after the demand aggregate stage); add the `_get_runner`
dispatch and `--allocation-method` CLI flag in `pipeline/__main__.py`; update the
`pipeline/demand/__init__.py` docstring; add the no-silent-passes checks in
`pipeline/demand/validate.py`; record provenance (`DATA_PROVENANCE.md` +
`download_manifest.json`, plus a source-register entry if a weighting dataset is
used); and update `pipeline/README.md` and the data specification §4/§7 (and §2 +
README together if a frozen decision like Q4/Q5 is touched).

> Note: this file is a documentation snapshot. The `requirements.md` / `design.md` /
> `tasks.md` that Kiro's task runner uses live in the workspace spec store; the
> copies in this folder are for reading alongside the ticket and may drift if the
> spec is later edited.
