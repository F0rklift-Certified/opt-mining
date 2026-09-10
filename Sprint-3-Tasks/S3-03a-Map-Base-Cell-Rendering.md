# S3-03a: Base Map & Cell Rendering (Eligible/Excluded Styling)

**Type:** Story
**Priority:** High
**Story Points:** 3
**Labels:** web-app, map, visualisation, frontend
**Blocked by:** S3-01b
**Blocks:** S3-03b

---

> **Split note:** First half of the former **S3-03** (Interactive NSW Map), the highest-risk UI ticket. S3-03a renders the analysis cells readably; S3-03b adds click-to-inspect and filters.

## Objective

Render an interactive NSW base map with the analysis cells drawn from engine output, readable at the ~5 km analysis resolution, with eligible and excluded/candidate cells visually distinguished.

---

## Context

Guidance Step 9. Readability across the full NSW grid at ~5 km resolution is the main risk, which is why rendering is isolated from interaction. The map must render the **same** engine output as the ranking table — no separate calculations in the UI.

---

## Deliverables

1. An interactive NSW base map.
2. A cell layer drawn from S2-08 engine output.
3. Eligible vs excluded/candidate visual styling.

---

## Acceptance Criteria

- [ ] The map displays candidate sites/cells across NSW and remains **readable** (not visually overwhelmed) (satisfies **AC8**, render half)
- [ ] Eligible and excluded/candidate cells are visually distinguished
- [ ] Cell data comes from the S2-08 service (score/rank/eligibility per cell) — no recomputation in the UI
- [ ] Coordinates come from the engine output (grid centroids/geometry in EPSG:4326) — no reprojection in the UI
- [ ] The rendered layer represents the same engine output as the ranked table (supports **AC4**)

---

## Technical Notes

- Consider aggregation/level-of-detail so the full grid stays readable; keep the styling driven by engine `eligible`/`suitability_score` values.
- Cross-cutting impact: the rendered layer is the surface S3-03b adds interaction to and that S3-05 selection highlights.
