# S3-07: Shortlist Export (CSV)

**Type:** Story
**Priority:** Medium *(Should — per guidance §5/§8)*
**Story Points:** 2
**Labels:** web-app, export, frontend
**Blocked by:** S3-04
**Blocks:** —
**Status:** ✅ Done — branch `s3-07-shortlist-export`, commit `9cab93e`

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

- [x] The user can download the ranked shortlist/results as CSV
- [x] The exported rows match the displayed shortlist exactly (same cells, same order, same scores)
- [x] Exported columns include at least: rank, Site ID, total suitability score, key component values, eligibility
- [x] The export carries the preliminary-screening disclaimer in a header/metadata line (consistent with AC12)
- [x] Export does not trigger any recomputation — it serialises the current engine output

---

## Technical Notes

- Reuse the S1-11 Shortlist_CSV schema and the Preliminary_Disclaimer already carried by that output.
- Being a "Should", keep it thin; do not let export formatting pull effort from the Must-priority tickets.

---

## Implementation Notes (completed)

Delivered on branch `s3-07-shortlist-export`, commit `9cab93e`.

**Files changed:**
- `app/web/app/shell/shortlistExport.ts` — pure `serializeShortlistCsv(rows, disclaimer)` helper. No recomputation, no network/engine call; serialises the `RankedRow[]` already in UI state.
- `app/web/app/shell/shortlistExport.test.ts` — unit tests (columns, served order, RFC-4180 escaping, disclaimer line, empty-shortlist case).
- `app/web/app/shell/RankedShortlist.tsx` — "use client" export control that triggers a browser download via a Blob + object URL (revoked after use).
- `app/web/app/shell/RankedShortlist.test.tsx` — extended component tests covering the export control and serializer invocation.
- `app/web/app/globals.css` — export control styling.

**Format details:**
- Columns reuse the S1-11 lowercase engine keys: `rank, cell_id, suitability_score, <one column per key_component in first-served order>, eligible`. (S1-11 sidecar confidence/centroid columns are not in `RankedRow`, so they are not emitted.)
- Numeric values use `toFixed(3)`, matching `RankedShortlist`'s on-screen formatting; a component the engine omitted for a row is an empty field.
- The preliminary-screening disclaimer is emitted verbatim as a leading `#` metadata line above the header row, mirroring the S1-11 sidecar wording.
- Records are RFC-4180 escaped and joined with CRLF.

**Known simplifications (non-blocking):**
- `eligible` is a constant `true`: `GET /runs/{id}/results` returns only eligible ranked cells (exclusions come from a separate endpoint), and `RankedRow` carries no per-row eligibility field. If a future ticket serves per-row eligibility, emit the served value.
- The disclaimer is a frontend constant mirroring the S1-11 sidecar, because the S2-08 HTTP contract does not surface it. Swap for the served value if the API later carries it.

**Verification:** `npm run typecheck`, the full Jest suite, and `npm run build` (with its integrated lint+type phase) all pass. Standalone `npm run lint` is not runnable in this checkout — no ESLint config/package is installed (pre-existing, not introduced by this work).
