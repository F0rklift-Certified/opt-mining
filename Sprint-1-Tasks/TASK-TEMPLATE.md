# Task Template — Sprint 1 Build Tasks

*This template defines the scaffold every Sprint 1 task sheet follows. Sprint 0's template was investigation-shaped (sources, samples, data dictionaries); Sprint 1 tasks are build tasks, so the scaffold changes: each sheet specifies what to build, what to reuse, and how to prove it works. Copy the sections below into your document and fill them in.*

---

## How to Use This Template

Every task sheet keeps the same header block as Sprint 0 so status is scannable across sprints:

```
**Sprint:** 1 (Week N)
**Assignee:** <name>
**Status:** Not Started | In Progress | Blocked | Complete
**Estimated Effort:** <days>
```

Fill in every section. If a section is not applicable, write "N/A" with a brief explanation why. Flag surprises early — if reality contradicts the sheet (an endpoint is gone, a number doesn't reconcile), record it in the Decision Log and raise it with the team rather than silently working around it.

Two rules inherited from the AI Development Constitution bind every task:

- **Units, CRS and resolutions are explicit at every boundary** — in docstrings, in column tables, in reports.
- **Nothing user-facing is hard-coded that should be a parameter** — thresholds, weights, statistics choices all surface as configuration with documented defaults.

---

## Document Scaffold

### 1. Objective

*One or two sentences describing what this task builds and why.*

### 2. Context & Frozen Decisions

*Which entries of `DATA/DATA_SPECIFICATION.md` and the frozen Task 5 §9 decisions bind this task. Quote the decided values (e.g. "wind: mean is the default scoring statistic; p90 carried; 100 m primary height").*

### 3. Scope

*Explicit **In** and **Out** lists. "Out" prevents scope creep mid-sprint — if something feels missing, it goes to the Decision Log, not silently into scope.*

### 4. Inputs

*Exact files (repo-relative paths), endpoints (full URLs), and upstream task outputs this task consumes. Note anything that must be regenerated first (e.g. gitignored raw data).*

### 5. Implementation Plan

*Ordered checklist. Name the modules to create and the existing functions to reuse, with paths (e.g. "reuse `query_layer_geojson` in `pipeline/common/geo.py`"). Follow house conventions: domain subpackage with `config.py` + stage modules, each exposing `run(...) -> dict`, NumPy docstrings stating units and CRS, `banner()` headers on generated reports, atomic writes via `pipeline/common/geo.py`.*

- [ ] Step 1 …
- [ ] Step 2 …

### 6. Outputs

*Exact paths and formats, following the data filename convention `<custodian>_<variable>[_<resolution>]_<area-slug>.<ext>`. For tabular outputs, a column table:*

| Column | dtype | Units | Description |
|---|---|---|---|

### 7. Configuration Parameters

*Everything tunable this task introduces:*

| Parameter | Default | CLI flag | Meaning |
|---|---|---|---|

### 8. Acceptance Criteria

*Measurable checkboxes. Prefer reconciliations against known numbers (Sprint 0 figures, ground truth sites) over "looks right".*

- [ ] …

### 9. Tests

*Offline pytest additions (no network, no fixture downloads — house style): file name, and the invariants each test asserts (e.g. "mean ≤ p90 ≤ max on synthetic rasters").*

### 10. Risks & Mitigations

*What could sink this task, and the fallback for each.*

### 11. Dependencies

**Blocked by:** *task numbers that must land first (or "None").*
**Blocks:** *task numbers waiting on this.*

### 12. Decision Log

*Filled during execution: dated entries for every deviation from this sheet, surprise, or decision taken. Empty at kickoff is fine; empty at completion of a non-trivial task is suspicious.*

| Date | Decision / Surprise | Rationale |
|---|---|---|
