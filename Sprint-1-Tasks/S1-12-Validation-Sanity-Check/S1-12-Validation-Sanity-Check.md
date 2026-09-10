# S1-12: Validation and Sanity Check

**Type:** Story  
**Priority:** High  
**Story Points:** 3  
**Labels:** validation, qa  
**Blocked by:** S1-11  
**Blocks:** —

---

## Objective

Verify that the pipeline outputs are plausible by checking against known reality. This is not a formal accuracy assessment — it is a sanity check that the pipeline is producing defensible results.

---

## Context

Per the Constitution: "Validate against reality. Check that known successful wind development areas score highly, using public operational and existing wind farm data."

If a pipeline produces a shortlist where all top sites are in implausible locations, or where known successful wind farms score poorly, something is wrong. This task catches those issues before the Sprint 1 output is trusted.

---

## Deliverables

1. Validation report at `outputs/sprint1_validation_report.md`
2. Documented comparison against known wind farm locations
3. Spot-check results for individual cells
4. Issues log for Sprint 2

---

## Acceptance Criteria

- [ ] Compare top-ranked cells against locations of existing operational wind farms in NSW
- [ ] Known wind farm sites should appear in or near high-scoring cells — document results:
  - Which known wind farms fall within high-scoring cells?
  - Which known wind farms score poorly? Why? (Is it a data issue or a legitimate model result?)
- [ ] Check that cells in obviously unsuitable areas are correctly excluded:
  - Urban centres (Sydney, Newcastle, Wollongong) → should be excluded
  - National parks (Blue Mountains, Kosciuszko) → should be excluded
  - Offshore cells → should not exist in grid
- [ ] Spot-check 5–10 cells manually:
  - Select cells across the score range (top, middle, bottom)
  - Verify feature values against source data (open GWA, check elevation, confirm distances)
  - Document any discrepancies
- [ ] Document any anomalies or unexpected results with investigation notes
- [ ] If validation reveals systematic issues, log them as bugs/improvements for Sprint 2
- [ ] Validation report saved as `outputs/sprint1_validation_report.md`

---

## Validation Checks

### Check 1: Known Wind Farms

Use the Geoscience Australia wind generators dataset (`DATA/infrastructure/generators/ga_wind_generators_2026_nsw.geojson`) to identify existing NSW wind farms.

For each major wind farm:
- Find the cell it falls within
- Record that cell's suitability score and rank
- Expected: most operational wind farms should score in the upper quartile

| Wind Farm | Cell ID | Score | Rank | Percentile | Notes |
|-----------|---------|-------|------|------------|-------|
| Sapphire Wind Farm | NSWxxxx | ? | ? | ? | |
| Bango Wind Farm | NSWxxxx | ? | ? | ? | |
| Collector Wind Farm | NSWxxxx | ? | ? | ? | |
| ... | ... | ... | ... | ... | |

### Check 2: Exclusion Validation

- Verify Sydney CBD cells are excluded (urban)
- Verify Blue Mountains NP cells are excluded (protected)
- Verify Kosciuszko NP cells are excluded (protected + slope)
- Verify no offshore/ocean cells exist in grid

### Check 3: Feature Value Spot-Check

For 5–10 selected cells, independently verify:
- Wind speed: compare to GWA web viewer or raw data
- Elevation: compare to topographic map
- Distance to transmission: measure manually in GIS
- Protected area flag: verify against CAPAD map

### Check 4: Score Distribution Plausibility

- Is the score distribution reasonable? (Not all clustered at 0 or 1)
- Is there geographic diversity in top scores? (Not all in one tiny area)
- Do scores correlate sensibly with wind resource? (Higher wind → higher score, generally)

---

## Validation Report Template

```markdown
# Sprint 1 Validation Report

**Date:** YYYY-MM-DD
**Pipeline version:** X.Y.Z
**Total cells:** N
**Eligible cells:** N

## 1. Known Wind Farm Comparison

[Table of wind farms vs scores]

**Result:** X of Y known wind farms score in the upper quartile.
**Issues:** [Any farms that scored unexpectedly low, with explanation]

## 2. Exclusion Validation

[Results of exclusion checks]

**Result:** All expected exclusions confirmed / Issues found: [list]

## 3. Feature Value Spot-Checks

[Table of spot-checked cells with verified vs pipeline values]

**Result:** All values within acceptable tolerance / Discrepancies found: [list]

## 4. Score Distribution

[Summary statistics and observations]

**Result:** Distribution is plausible / Concerns: [list]

## 5. Issues for Sprint 2

[Numbered list of issues discovered during validation]

## 6. Conclusion

[Overall assessment: pipeline output is / is not trustworthy for preliminary screening]
```

---

## Technical Notes

- This is a manual + automated hybrid task — some checks can be scripted, others require human judgement
- Do NOT adjust the model to "pass" validation — document discrepancies honestly
- Per the Constitution: "When a result looks surprising, investigate the data before adjusting the model"
- If systematic issues are found, they should be logged for Sprint 2, not fixed ad-hoc in this task
- Consider creating a reusable validation script that can be run after future pipeline changes
