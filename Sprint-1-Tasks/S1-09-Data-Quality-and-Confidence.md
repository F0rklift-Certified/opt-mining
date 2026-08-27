# S1-09: Data Quality and Confidence Layer

**Type:** Story  
**Priority:** Medium  
**Story Points:** 3  
**Labels:** quality, confidence  
**Blocked by:** S1-08  
**Blocks:** S1-10

---

## Objective

Add a data-quality and confidence assessment to the integrated dataset so that downstream scoring can account for certainty. Cells with low confidence should not be excluded, but their limitations must be transparent.

---

## Context

Not all cells have equal data quality. Some may have:
- Missing features (e.g. no demand proxy for remote areas)
- Low-resolution source data (e.g. wind data interpolated over a large area)
- Known data limitations documented in S1-01

The Constitution requires: "Report confidence alongside every score" and "Where non-critical data is missing or low confidence, retain and flag it. Never silently assign a normal ranking to a poorly evidenced cell."

---

## Deliverables

1. Confidence scoring methodology document
2. Per-cell confidence score/flag added to the integrated table
3. Summary report on data quality distribution

---

## Acceptance Criteria

- [ ] Each cell in the integrated table has a composite `data_confidence` score or categorical flag (e.g. high / medium / low)
- [ ] Confidence reflects:
  - Number of missing or null features
  - Spatial resolution mismatch between source data and cell size
  - Known data limitations (from S1-01 specification)
  - Distance from nearest measured/modelled data point (if applicable)
- [ ] Confidence methodology is documented:
  - How is the composite score calculated?
  - What thresholds define high/medium/low?
  - Which features are weighted more heavily?
- [ ] Cells with low confidence are **not excluded** but clearly flagged
- [ ] Per-feature confidence flags (from S1-03 through S1-06) are preserved in the integrated table
- [ ] Summary report includes:
  - Distribution of confidence scores (histogram or table)
  - Count of cells at each confidence level
  - Geographic pattern of low-confidence areas (are they clustered?)
  - Most common reason for reduced confidence

---

## Confidence Scoring Approach (Suggested)

```
For each cell:
  completeness = count(non_null_features) / total_features
  resolution_match = average(feature_resolution_scores)  # 1.0 = native match, 0.5 = interpolated
  
  confidence = weighted_average(completeness, resolution_match)
  
  If confidence >= 0.8 → "high"
  If confidence >= 0.5 → "medium"
  If confidence < 0.5  → "low"
```

---

## Example Output (added to integrated table)

| cell_id | ... features ... | data_confidence | confidence_score | confidence_notes |
|---------|-----------------|-----------------|------------------|------------------|
| NSW001  | ...             | high            | 0.92             | —                |
| NSW002  | ...             | medium          | 0.67             | Missing demand proxy |
| NSW003  | ...             | low             | 0.41             | Missing wind data, low-res elevation |

---

## Summary Report Example

```
Data Quality Summary — Sprint 1 Integrated Table
=================================================
Total cells:    12,847

Confidence Distribution:
  High (≥0.8):    8,924 (69.5%)
  Medium (0.5–0.8): 2,891 (22.5%)
  Low (<0.5):     1,032 (8.0%)

Most Common Quality Issues:
  1. Missing demand proxy data:     1,456 cells
  2. Low-resolution wind data:        892 cells
  3. Incomplete land-use coverage:    634 cells

Geographic Patterns:
  Low-confidence cells concentrated in western NSW 
  (sparse population data, limited infrastructure mapping)
```

---

## Technical Notes

- This is a metadata/quality layer, not a filter — it does not remove cells
- The confidence score will be used by the scoring model (S1-10) to weight or caveat results
- Per the Constitution: "Report confidence alongside every score"
- Consider whether confidence should influence the suitability score directly or be reported alongside it
