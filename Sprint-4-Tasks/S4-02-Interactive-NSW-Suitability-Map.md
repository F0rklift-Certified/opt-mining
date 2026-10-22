# S4-02: Complete the Interactive NSW Suitability Map

**Type:** Task
**Priority:** P0
**Status:** In review — implemented on `s4-02-map-completion`; evidence below
**Source:** [Client Sprint 4 brief](OPT_MINING_Sprint4_Final_Guidance.md), §4 S4-02

## Objective

Make the spatial screening results usable and understandable through the web interface.

## Required Work

- [x] Render NSW analysis cells/sites on the map.
- [x] Clearly distinguish eligible and excluded cells.
- [x] Visualise relative suitability for eligible cells without presenting excluded cells as merely low scoring.
- [x] Provide a clear map legend and meaningful labels.
- [x] Support zoom and pan.
- [x] Maintain acceptable rendering performance with the intended NSW dataset.

## Acceptance Criteria

- [x] A user can visually distinguish eligible, excluded and relatively higher/lower suitability areas on the NSW map.
- [x] Eligible and excluded cells are visually distinct, and relative suitability for eligible cells is shown on a continuous scale (excluded cells are not presented as merely low-scoring).
- [x] A clear legend and meaningful labels explain the styling.
- [x] Zoom and pan work, and the full NSW grid renders readably (not visually overwhelmed) at the intended resolution.
- [x] Cell data, coordinates and eligibility/score values come from the decision-service engine output — no recomputation or reprojection in the UI.
- [x] The rendered layer represents the same engine output as the ranked shortlist (consistent IDs/scores/eligibility).

## Deliverable

Working map component integrated with the real decision-engine results.

## Completion Evidence

**Branch:** `s4-02-map-completion` (from `docs/sprint-4-final-backlog`, PR #30). **Owner:** Pouya Mousavi. **Verified:** 2026-10-19.

What was already in place from S3-03a/b (MapLibre `CellMap`, three engine-driven cell layers, click-to-inspect) was audited against each criterion; the gaps below were closed.

| Acceptance criterion | Evidence |
| --- | --- |
| Distinguish eligible / excluded / higher-lower suitability | Eligible ramp now spans the real score distribution: the service serves `score_quantiles` (contract v1.2.2) and the map places its 7 colour stops there, so the 0.66–0.75 bulk no longer collapses into one band. Environmental exclusions drawn full-size in slate at higher opacity. Screenshots `evidence/S4-02/s4-02-map-statewide.png`, `s4-02-map-zoom8.png`. |
| Eligible vs excluded distinct; continuous scale; excluded not "low-scoring" | Continuous `interpolate` over `suitability_score` (ColorBrewer Reds, one hue, monotone lightness — test `keeps the ramp one hue…`); excluded classes are separate layers filtered on `eligible == false` and never touch the ramp. |
| Clear legend + labels | Gradient bar built from the layer's own stops, labelled with the run's lowest / median / highest score, plus keys for both excluded classes, the selected and hover outlines and the outside-NSW mask (`CellMap.test.tsx` "names every map style in the legend"). |
| Zoom/pan; full grid readable at intended resolution | Cell radius scales with zoom to ~one 0.05° cell (MapLibre 512-px world), so the grid reads as a surface at every zoom; `maxBounds` around NSW, zoom 4.5–12. NSW clip rewritten with per-row boundary crossings: full 47,311-cell baseline grid **37 ms (was ~2,000 ms)**, identical output to the original ray cast (`cell-layers.test.ts`). Hover lookup is a constant-time grid index instead of a 47k-cell scan per `mousemove`. |
| Data from the decision service only | Unchanged: `GET /runs/{id}/cells` passthrough; the UI only places colour stops and builds outline squares. `score_quantiles` is computed in the service (`results.py::_score_quantiles`, allow-listed in the no-recompute guard as display metadata). |
| Same engine output as the shortlist | The shared selection is now mirrored on the map (`selectedCellId` prop): shortlist picks and the automatic rank-1 pick draw the selected box, panning to it when off-screen (`s4-02-map-shortlist-select.png`). A cells payload for a different `run_id` is refused. Backend set-equality test (eligible cells == ranked results) unchanged and passing; new real-grid test proves no top-100 cell is clipped. |

**Tests (2026-10-19):** web `tsc --noEmit` clean, Jest 226/226, `next build` OK; backend `pytest tests/backend tests/service tests/integration` all passing (new: `test_score_quantiles_*`).

**Live check:** API + `next dev` against the real integrated dataset (47,311 cells, 32,525 eligible); statewide view, zoom 8–10, map click → detail, shortlist click → map pan + box; no console errors.

**Findings raised outside S4-02 (not fixed here):**
1. *Engine scores cells outside NSW.* The scored grid is the full 253 × 187 bounding box; 9,184 eligible cells lie outside the NSW boundary (QLD/SA/VIC) and are hidden only by the map's clip. None ranks in the top 1,000 (best #1,755), so the shortlist is unaffected, but every NSW rank number counts them. Needs an "outside NSW" exclusion in the engine — for S4-07 / the baseline owner.
2. *Stale runs are reused across data changes.* `run_id` hashes only the weights, so a run materialised from an older integrated table (found locally: 2026-09-17, 1,233 eligible) is served silently. Fixed in S4-03 by porting the input-hash binding from 6fe88a3.
3. *Concurrent identical `POST /runs` race* (React dev double-mount) on shared temp paths → 500 without CORS headers. Also fixed in S4-03 via the materialisation lock from 6fe88a3.

**Update 2026-10-22:** finding 1 is resolved by the `outside_nsw_land` exclusion (QA F-01, commit `f48ff13`; 23,266 eligible cells), and findings 2 and 3 by S4-03, merged together on `s4-integration`.

**Review outcome:** _pending PR review._

Refer to the [Sprint 4 Definition of Done](README.md#definition-of-done) for final acceptance.
