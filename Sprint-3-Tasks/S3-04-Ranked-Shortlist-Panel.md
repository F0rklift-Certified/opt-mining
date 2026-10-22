# S3-04: Ranked Shortlist / Results Panel

**Type:** Story
**Priority:** High
**Story Points:** 3
**Labels:** web-app, results, frontend
**Blocked by:** S3-01
**Blocks:** S3-05

---

## Objective

Provide a ranked table/list of eligible sites, linked to the map, showing at minimum Site ID, total suitability score/rank and important component values, with the ability to select a site for detail.

---

## Context

Guidance Step 10 and §5 (Ranked shortlist — Must). The shortlist must use the **same** decision-engine output as the map (AC8). Sprint 1's S1-11 shortlist stage already produces the ranked top-N; here it is rendered and made interactive.

---

## Deliverables

1. A ranked results table/list bound to engine output.
2. Two-way linkage with the map (selecting in one highlights the other).
3. A row-select action opening site detail.

---

## Acceptance Criteria

- [x] A ranked table/list of eligible sites is shown, using the same S2-08 engine output as the map (satisfies **AC8**)
- [x] Each row shows at minimum: Site ID, total suitability score, rank, and important component values
- [x] Selecting a row lets the user inspect that site in more detail (opens S3-05)
- [x] The table and map stay in sync — selecting in one reflects in the other
- [x] Ranking is the deterministic engine ranking — the UI does not re-sort by recomputed scores
- [x] Ordering matches the S2-05 rank exactly (ties handled by the engine's documented rule)

---

## Technical Notes

- Render the engine's rank/score/contribution columns directly; the UI must not compute its own ranking.
- Cross-cutting impact: shares the site-selection contract with S3-03 and feeds S3-05; the optional S3-07 export operates on this panel's data.

---

## Status: Done

Implemented as the `RankedShortlist` component (`app/web/app/shell/RankedShortlist.tsx`), rendered in the Ranked results region of `AppShell`. Rows are bound directly to the S2-08 engine output (`getRankedResults`) in engine rank order, with no UI re-sort. Selection is lifted to a single shared `SiteSelection` ({ runId, cellId }) contract (`app/web/app/shell/siteSelection.ts`), so a shortlist-row click and a map (`CellMap`) click drive the same selection and the same `getSiteDetail`-backed site-detail view — the table and map stay in sync both ways.

Merged into `s3-04-ranked-shortlist-panel` alongside the S3-03B interactive map: the map's `CellSelection` output is adapted onto the shared `SiteSelection` so both views select the same site. Verified by typecheck, the full Jest suite, and `next build`.
