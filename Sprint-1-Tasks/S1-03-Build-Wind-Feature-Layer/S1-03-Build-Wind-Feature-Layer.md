# S1-03: Build the Wind Feature Layer

**Type:** Story  
**Priority:** High  
**Story Points:** 5  
**Labels:** feature-engineering, wind  
**Blocked by:** S1-01, S1-02  
**Blocks:** S1-08

---

## Objective

Take the selected Global Wind Atlas data and map it to every valid NSW analysis cell. The pipeline should generate this automatically — no manual CSV preparation.

---

## Context

The Global Wind Atlas provides modelled wind resource data (wind speed, power density, capacity factor) at multiple heights. During Sprint 0 this data was investigated and its characteristics documented. This task converts that investigation into an automated pipeline step that produces a per-cell wind feature.

The team should determine the most defensible MVP wind-resource variable (e.g. mean wind speed at 100m, or power density at hub height). The key requirement is automation and reproducibility.

---

## Deliverables

1. Pipeline module at `pipeline/wind/` that ingests GWA data and produces per-cell wind features
2. Documentation of variable selection rationale
3. Output table/GeoDataFrame with wind values per cell

---

## Acceptance Criteria

- [ ] Pipeline module (`pipeline/wind/`) ingests GWA data and resamples/aggregates to analysis cells
- [ ] The MVP wind-resource variable is selected and documented (e.g. mean wind speed or power density at a specific height)
- [ ] Justification for height and variable choice is recorded (why this height? why this variable?)
- [ ] Output is a table/GeoDataFrame: `cell_id | wind_variable | units | data_source | confidence_flag`
- [ ] Cells with no valid wind data are flagged (not filled with defaults or fabricated values)
- [ ] Resampling/aggregation method is documented (mean, median, area-weighted, etc.)
- [ ] Automated — runs as part of the pipeline without manual intervention
- [ ] Unit tests cover the resampling/aggregation logic
- [ ] Output statistics are logged: min, max, mean, count of valid/invalid cells

---

## Technical Notes

- If Option A (GWA-aligned grid) was chosen in S1-02, this may be a direct extraction rather than resampling
- If Option B (projected grid) was chosen, document the resampling method carefully
- Per the Constitution: "Never invent, extrapolate or hard-code data values to make a pipeline run"
- Per the Constitution: "Never build a circular model" — wind data is an input feature, not a prediction target

---

## Example Output

| cell_id | wind_speed_100m_ms | power_density_100m_wm2 | data_source | confidence |
|---------|-------------------|----------------------|-------------|------------|
| NSW001  | 7.8               | 285                  | GWA 3.0     | high       |
| NSW002  | 8.4               | 340                  | GWA 3.0     | high       |
| NSW003  | NULL              | NULL                 | —           | no_data    |

---

## How to Complete This Task

This ticket is now backed by a full spec. Three companion documents sit in this
same folder and should be read in this order before writing any code:

1. **`requirements.md`** — the authoritative, testable definition of "done".
   Every acceptance criterion above is expanded into EARS-format requirements
   (R1–R12) with precise, verifiable clauses. When this ticket and
   `requirements.md` appear to disagree, `requirements.md` wins.
2. **`design.md`** — how the stage is built: the new `pipeline/wind/features.py`
   module, its `run(verbose=False) -> dict` entry point, the zonal block-extraction
   method, the CRS boundaries, the output schema, provenance, and the eight
   Correctness Properties the tests must uphold. Read this to understand *how* the
   requirements are satisfied.
3. **`tasks.md`** — the actual build order. This is the checklist you execute:
   a 15-task, dependency-ordered plan (with a Task Dependency Graph) that goes
   config → module scaffold → pure logic functions → writers → `run()` →
   validation → stage registration → property/unit tests → documentation.

### Working the plan

- Open `tasks.md` and execute tasks top-to-bottom. Each task lists the specific
  requirement clauses it satisfies (`_Requirements: ...`) and, where useful, a
  `_Design ref:_` pointer — use those to jump back into `requirements.md` /
  `design.md` for detail.
- Tasks marked with `*` are optional test sub-tasks; core implementation tasks are
  never optional. Do not skip the no-silent-passes validation (task 9) or the stage
  registration (task 10).
- Stop at the checkpoints (tasks 6, 11, 15), run the test suite, and confirm green
  before moving on.

### Key decisions already locked in the spec (don't re-litigate silently)

- **S1-02 chose Option A** (0.05° GWA-aligned cells, EPSG:4326), so this is a clean
  20×20 native-pixel **block extraction** — no reprojection/resampling of the GWA
  rasters. If S1-02 is ever revisited, this stage changes.
- **Variable = mean wind speed at 100 m**, honouring frozen decisions **Q1** (mean)
  and **Q2** (100 m hub). Changing either must go through the data-specification §8
  change-control process (recorded in both spec §2 and the README) — not an ad-hoc
  edit here.
- Cells with no valid GWA coverage are **flagged `no_data` with a null value**,
  never back-filled (Constitution: "never invent data"; "never build a circular
  model").

### Cross-component impact (must ship together — see `tasks.md` tasks 10 & 14)

Finishing this task is not just writing `features.py`. To keep the pipeline
consistent you must also: register `wind.features` in `pipeline/config.py`
`STAGES` **after `grid`**; add the `_get_runner` dispatch in `pipeline/__main__.py`;
update the `pipeline/wind/__init__.py` docstring; record provenance
(`DATA_PROVENANCE.md` + `download_manifest.json` via read-merge-write so the
download records aren't clobbered); and update `pipeline/README.md` (stage order +
expected outputs) and the data specification §4/§7.

> Note: this file is a documentation snapshot. The `requirements.md` / `design.md` /
> `tasks.md` that Kiro's task runner uses live in the workspace spec store; the
> copies in this folder are for reading alongside the ticket and may drift if the
> spec is later edited.
