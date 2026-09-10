# S3-03b: Map Click-to-Inspect & Display Filters

**Type:** Story
**Priority:** High
**Story Points:** 2
**Labels:** web-app, map, visualisation, frontend
**Blocked by:** S3-03a
**Blocks:** S3-05

---

> **Split note:** Second half of the former **S3-03**. S3-03a rendered the cells; S3-03b adds click-to-inspect and display filters. Splitting lets rendering land and be reviewed before interaction is layered on.

## Objective

Add click-to-inspect interaction (returning a site's ID, score, key criteria and eligibility) and display filters (top-N and/or minimum suitability threshold) to the rendered NSW map.

---

## Context

Guidance Step 9. Click-to-inspect drives the S3-05 site-detail view. Filters affect only the display and are applied via the S2-08 service over fixed engine output — never a re-run of normalisation.

---

## Deliverables

1. Click-to-inspect returning site attributes.
2. Top-N and/or minimum-threshold display filters.
3. The map selection event feeding S3-05.

---

## Acceptance Criteria

- [ ] Clicking a site returns its ID, score, key criteria and eligibility information
- [ ] Where practical, filters are provided (top-N sites and/or minimum suitability threshold)
- [ ] Filters affect only the **display**, not the scoring/normalisation population (applied via the S2-08 service over fixed output)
- [ ] The click event exposes a selection contract that the S3-05 site-detail view consumes
- [ ] Interaction renders the same engine output as the ranked table — no recomputation in the UI (supports **AC4**)

---

## Technical Notes

- Top-N / threshold filtering is a display query over fixed engine output (S2-08 `get_ranked_results` filters); it must not re-trigger normalisation.
- Cross-cutting impact: agree the selection event/contract with S3-04 (shortlist) and S3-05 (site detail) so map and table selection are interchangeable.
