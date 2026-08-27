# S1-07: Implement the Exclusion Layer

**Type:** Story  
**Priority:** High  
**Story Points:** 3  
**Labels:** exclusions, pipeline  
**Blocked by:** S1-06  
**Blocks:** S1-08

---

## Objective

Build an explicit exclusion component in the pipeline. Exclusions must not be hidden inside scoring code — they are a separate, auditable, transparent step that determines which cells are eligible for scoring.

---

## Context

Not every analysis cell is a valid candidate for wind energy development. Cells that overlap protected areas, have missing critical data, or meet other disqualifying criteria should be explicitly excluded before scoring begins.

Making exclusions an explicit pipeline component (rather than embedding them in scoring logic) ensures:
- Transparency — users can see exactly why a cell was excluded
- Auditability — exclusion rules are inspectable and configurable
- Separation of concerns — scoring only operates on eligible cells

---

## Deliverables

1. Dedicated pipeline module at `pipeline/exclusions/`
2. Configurable exclusion rules (not hard-coded)
3. Output table with eligibility status and exclusion reasons per cell

---

## Acceptance Criteria

- [ ] Dedicated module (`pipeline/exclusions/`) applies exclusion rules to the cell grid
- [ ] Exclusion rules are **configurable** — defined in a rules file or config (e.g. YAML/JSON), not hard-coded in logic
- [ ] Each cell receives:
  - `eligible` (boolean)
  - `exclusion_reason` (text, nullable — reason or list of reasons)
- [ ] Minimum exclusion criteria for MVP:
  - Protected areas (CAPAD overlap) → reason: "Protected area: {name}"
  - Missing critical wind data → reason: "Missing wind data"
  - Excessive slope (configurable threshold) → reason: "Slope exceeds {threshold}°"
  - Urban areas → reason: "Urban area"
  - Other rules justified by Sprint 0
- [ ] A cell can have **multiple** exclusion reasons (comma-separated or list)
- [ ] Exclusion summary statistics are logged:
  - Total cells
  - Eligible cells (count and %)
  - Excluded cells by reason (count and %)
- [ ] Automated — runs as part of the pipeline
- [ ] Unit tests cover each exclusion rule independently

---

## Exclusion Rules Config Example

```yaml
# exclusion_rules.yaml
exclusions:
  - name: protected_area
    description: "Cell overlaps a protected area (CAPAD)"
    field: protected_area
    condition: "== True"
    
  - name: missing_wind_data
    description: "No valid wind resource data available"
    field: wind_speed_100m_ms
    condition: "is_null"
    
  - name: excessive_slope
    description: "Mean slope exceeds construction threshold"
    field: slope_deg
    condition: "> 15"
    threshold: 15
    
  - name: urban_area
    description: "Cell is within an urban centre"
    field: urban_area
    condition: "== True"
```

---

## Output Format

| cell_id | eligible | exclusion_reason |
|---------|----------|------------------|
| NSW001  | Yes      | —                |
| NSW002  | No       | Protected area: Oxley Wild Rivers NP |
| NSW003  | No       | Missing wind data |
| NSW004  | No       | Slope exceeds 15°, Protected area: Barrington Tops NP |
| NSW005  | Yes      | —                |

---

## Technical Notes

- Exclusion rules should be applied AFTER all feature layers are computed (depends on S1-03 through S1-06 outputs)
- Rules are evaluated independently — a cell can fail multiple rules
- Per the Constitution: "Where critical data is missing, exclude the cell"
- Per the Constitution: "Where non-critical data is missing or low confidence, retain and flag it"
- Distinguish between critical exclusions (hard no) and flagged concerns (soft warning)
- The exclusion layer does NOT assign scores — it only determines eligibility

---

## Summary Statistics Example

```
Exclusion Summary:
  Total cells:        12,847
  Eligible:           9,231 (71.9%)
  Excluded:           3,616 (28.1%)
  
  By reason:
    Protected area:     1,842 (14.3%)
    Missing wind data:    456 (3.5%)
    Excessive slope:    1,105 (8.6%)
    Urban area:           213 (1.7%)
```
