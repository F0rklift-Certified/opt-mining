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

- [x] Clicking a site returns its ID, score, key criteria and eligibility information
- [x] Where practical, filters are provided (top-N sites and/or minimum suitability threshold)
- [x] Filters affect only the **display**, not the scoring/normalisation population (applied via the S2-08 service over fixed output)
- [x] The click event exposes a selection contract that the S3-05 site-detail view consumes
- [x] Interaction renders the same engine output as the ranked table — no recomputation in the UI (supports **AC4**)

---

## Technical Notes

- Top-N / threshold filtering is a display query over fixed engine output (S2-08 `get_ranked_results` filters); it must not re-trigger normalisation.
- Cross-cutting impact: agree the selection event/contract with S3-04 (shortlist) and S3-05 (site detail) so map and table selection are interchangeable.

---

## Status: Done

Delivered on branch `s3-03B`. All five acceptance criteria met, additively on
the approved S3-03a rendering; the S3-03a lifecycle/staleness guards (`mapRef`,
`mapReady`, `pendingDataRef`, `requestIdRef`, `fetchedRunRef`) are untouched and
all browser HTTP stays in the single integration point.

### Completion Notes

**Click-to-inspect (AC1).** A MapLibre `click` handler scoped to the three cell
layers reads the clicked feature's engine-produced properties and surfaces the
cell's ID, suitability score, rank and eligibility. No HTTP and no decision math
on click — it reads only values already in memory.

**Selection contract (AC4-shape).** A shared, typed `CellSelection`
(`cell_id`, `eligible`, `suitability_score`, `rank`) is exported from the single
service module (`app/web/app/api/decision-service.ts`). Both a map click and a
ranked-table row produce the same shape, so map and table selection are
interchangeable and ready for the S3-05 site-detail view (which fetches the
richer explanation on demand via `getSiteDetail` keyed on `cell_id`).

**Display filters (AC2 / AC3).** Filter state (top-N and minimum-suitability
threshold) lives in `AppShell` and re-queries only
`service.getRankedResults(runId, { top_n, min_score })` — the S2-08 operation's
pure display-selection over fixed engine output — behind its own staleness
guard. It never calls `runAnalysis`/`getRunCells`, so filtering never re-runs
scoring or normalisation.

**No recomputation (AC5).** No scoring/ranking/normalisation math, no new HTTP
dependency, and no banned tokens in the added frontend lines; the scope-guard,
single-integration-point, and no-URL-literal rules all still hold.
`generated.ts` and `package.json` are unchanged.

**Selection highlight (added after the spec, by request).** A visual square
outlines the chosen cell on top of the cell layers:

- A **persistent selected box** (solid black) is pinned on `click` and stays on
  that cell until another cell is clicked or the run changes.
- A **transient hover box** (dashed) follows the pointer. It is driven by the
  cell's **square footprint**, not the small circle: a map-wide `mousemove`
  snaps the cursor to the cell whose ±~2.5 km square contains it and draws the
  box there (nearest centre wins on overlap), clearing when the cursor is inside
  no cell's square or leaves the canvas. The pinned selected box is untouched by
  hover. Both are presentation-only (no HTTP, no decision math).

### Verification

From `app/web`: `npm run typecheck` clean; `npm test -- --runInBand` green
(7 suites, 93 tests, incl. `scope-guard`, `CellMap`, and
`AppShell`/`AppShell.integration`); `NEXT_PUBLIC_API_BASE_URL=… npm run build`
succeeds. GPU click/hover rendering and visual readability are not unit-testable
under jsdom (same caveat as S3-03a) and remain a manual check against the
running stack; the typed selection contract, the filter service-call path, the
no-recomputation guard, and the highlight (click-pin, square-footprint hover,
clear-on-leave) are covered by tests.

### Commits

- `9897733` — click-to-inspect + display filters + shared `CellSelection` (S3-03b core)
- `7dc93b9` — square outline around the clicked cell
- `ddffb63` — split into persistent selected box + transient hover box
- `2d65430` — hover box driven by the square footprint, not the circle
