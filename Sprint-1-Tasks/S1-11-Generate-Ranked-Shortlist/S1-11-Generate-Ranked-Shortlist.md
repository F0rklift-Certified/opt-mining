# S1-11: Generate a Preliminary Ranked Shortlist

**Type:** Story  
**Priority:** Medium  
**Story Points:** 2  
**Labels:** output, shortlist  
**Blocked by:** S1-10  
**Blocks:** S1-12

---

## Objective

Produce the Sprint 1 headline output: a ranked list of the top candidate sites/cells in NSW for wind energy development.

---

## Context

This is the user-facing output of Sprint 1. After all data has been integrated, quality-assessed, and scored, this task extracts the top-ranked cells and presents them in a clear, actionable format.

The shortlist is NOT a final recommendation — it is a starting point for further investigation. Per the Constitution: "Its output informs what to study next; it never constitutes a site approval."

---

## Deliverables

1. Pipeline step that generates the ranked shortlist
2. Output files (CSV + GeoJSON)
3. Summary statistics

---

## Acceptance Criteria

- [ ] Pipeline generates a ranked shortlist (top N configurable, default top 20)
- [ ] Output format:

| rank | cell_id | suitability_score | confidence | centroid_lat | centroid_lon |
|------|---------|-------------------|------------|--------------|--------------|
| 1    | NSWxxx  | 0.87              | high       | -30.12       | 151.45       |
| 2    | NSWxxx  | 0.84              | high       | -30.08       | 151.52       |
| 3    | NSWxxx  | 0.81              | high       | -29.95       | 151.38       |

- [ ] Shortlist includes geographic coordinates for easy verification on a map
- [ ] Export as:
  - CSV (tabular, easy to share)
  - GeoJSON (for map visualisation)
- [ ] Summary statistics included:
  - Score distribution (min, max, mean, std of eligible cells)
  - Geographic spread of top sites (are they clustered or distributed?)
  - Confidence distribution of top sites
- [ ] Output file is timestamped and versioned (e.g. `outputs/sprint1_shortlist_20260827.csv`)
- [ ] Top N parameter is configurable via command line or config

---

## Example Output

### Shortlist (Top 10)

| Rank | Cell ID | Score | Confidence | Lat    | Lon    | REZ           |
|------|---------|-------|------------|--------|--------|---------------|
| 1    | NSW4521 | 0.87  | high       | -30.12 | 151.45 | New England   |
| 2    | NSW4522 | 0.84  | high       | -30.08 | 151.52 | New England   |
| 3    | NSW4489 | 0.81  | high       | -29.95 | 151.38 | New England   |
| 4    | NSW3210 | 0.79  | high       | -33.45 | 149.12 | Central-West  |
| 5    | NSW3211 | 0.78  | high       | -33.41 | 149.18 | Central-West  |
| ...  | ...     | ...   | ...        | ...    | ...    | ...           |

### Summary Statistics

```
Sprint 1 Shortlist Summary
===========================
Pipeline run: 2026-08-27T14:30:00
Total cells: 12,847
Eligible cells: 9,231
Scored cells: 9,231

Score Distribution (eligible cells):
  Min:  0.12
  Max:  0.87
  Mean: 0.48
  Std:  0.15

Top 20 Geographic Spread:
  REZs represented: New England (8), Central-West (6), South-West (4), Other (2)
  Latitude range: -29.5 to -34.2
  Longitude range: 148.5 to 152.1

Top 20 Confidence:
  High: 18/20
  Medium: 2/20
  Low: 0/20
```

---

## Technical Notes

- This is primarily a filtering and formatting step — the scoring is done in S1-10
- Ensure the shortlist clearly states it is a preliminary screening output, not a site recommendation
- Include the pipeline version and run timestamp in output metadata
- Consider adding a "nearby existing wind farms" column for context (aids validation in S1-12)
- Per the Constitution: "Always state the analysis resolution and its limitations wherever results are presented"
