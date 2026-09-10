# S3-07: Shortlist Export (CSV)

**Type:** Story
**Priority:** Medium *(Should — per guidance §5/§8)*
**Story Points:** 2
**Labels:** web-app, export, frontend
**Blocked by:** S3-04
**Blocks:** —

---

## Objective

Allow the user to download the ranked shortlist/results as CSV (or similar), without distracting from the core MVP.

---

## Context

Guidance Step 10 and §5 (Export — **Should** priority). This is explicitly a "Should", not a "Must": implement only once the Must-priority results panel is stable. Sprint 1's S1-11 already writes a Shortlist_CSV, so the engine output format exists.

---

## Deliverables

1. An export action on the results panel.
2. A CSV (and optionally GeoJSON) download matching the on-screen shortlist.

---

## Acceptance Criteria

- [ ] The user can download the ranked shortlist/results as CSV
- [ ] The exported rows match the displayed shortlist exactly (same cells, same order, same scores)
- [ ] Exported columns include at least: rank, Site ID, total suitability score, key component values, eligibility
- [ ] The export carries the preliminary-screening disclaimer in a header/metadata line (consistent with AC12)
- [ ] Export does not trigger any recomputation — it serialises the current engine output

---

## Technical Notes

- Reuse the S1-11 Shortlist_CSV schema and the Preliminary_Disclaimer already carried by that output.
- Being a "Should", keep it thin; do not let export formatting pull effort from the Must-priority tickets.
