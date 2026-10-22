# S4-03: Complete Site Inspection and Explainability

**Type:** Task
**Priority:** P0
**Status:** In review — implemented on `s4-03-site-inspection` (stacked on `s4-02-map-completion`); evidence below
**Source:** [Client Sprint 4 brief](OPT_MINING_Sprint4_Final_Guidance.md), §4 S4-03

## Objective

Allow a user to understand why a site is eligible, excluded, highly ranked or weakly ranked.

## Required Work

- [x] For eligible sites show Site/Cell ID, suitability score, rank, wind value/score, demand proxy, infrastructure indicator(s), geographic/environmental indicator(s), criterion contributions, positive factors, weaknesses and data-quality/confidence information.
- [x] For excluded sites show Site/Cell ID, ineligible status, exclusion reason(s) and relevant data-quality information.
- [x] Do not assign a normal suitability rank to an excluded site.
- [x] Use the existing deterministic explanation engine; an LLM is not required.
- [x] Ensure explanations are derived from the same backend analysis results displayed elsewhere in the application.

## Acceptance Criteria

- [x] Selecting a site from the map or shortlist opens a consistent, understandable site-detail view with traceable explanations.
- [x] For an eligible site the view shows Site/Cell ID, suitability score, rank, wind value/score, demand proxy, infrastructure indicator(s), geographic/environmental indicator(s), criterion contributions, positive factors, weaknesses and data-quality/confidence information.
- [x] For an excluded site the view shows Site/Cell ID, ineligible status, exclusion reason(s) and relevant data-quality information, and does **not** show a normal suitability rank.
- [x] Map selection and shortlist selection open the same site-detail view for the same cell (interchangeable selection contract).
- [x] Explanations are produced by the existing deterministic explanation engine (no LLM) and derived from the same backend analysis results shown elsewhere in the app.

## Deliverable

Integrated Site Detail / Why This Site? panel.

## Completion Evidence

**Branch:** `s4-03-site-inspection`, stacked on `s4-02-map-completion` (the map-side selection mirroring lives there). **Owner:** Pouya Mousavi. **Verified:** 2026-10-20.

The S3-05 panel (`SiteDetailPanel`) and the shared selection contract already existed. The audit found that explanations were not run-specific, several required fields were missing or unlabelled, and an excluded site still showed a "Rank" row.

| Acceptance criterion | Evidence |
| --- | --- |
| Map or shortlist opens a consistent, traceable detail view | Both call the same `handleSelectSite` → one `getSiteDetail(run, cell)` → one panel. A new shell test proves the panel HTML is identical for the same cell picked from the shortlist and from the map, and that both paths request the same run + cell. S4-02 mirrors the selection on the map. |
| Eligible: id, score, rank, wind, demand proxy, infrastructure, geography/environment, contributions, positive factors, weaknesses, data quality | Header: id, status, location, score, rank, data-confidence badge. "Criterion values and contributions": every criterion's served value with units, its theme (wind / demand · proxy / grid infrastructure / geography) and its contribution (they sum to the score). Context tables come from the cell's full integrated row, which the service now serves: AEMO region, connection distance, REZ name, elevation, TRI, land use, protected area, cell area. Data quality: per-domain and overall confidence, score, notes and flags, plus the S2-06 notes and proxy caveat. `evidence/S4-03/s4-03-detail-eligible-baseline.png`. |
| Excluded: id, ineligible status, reasons, data quality, **no** normal rank | Status "Not eligible — excluded", "Why excluded" from the explanation's `exclusion_reasons`, and data quality — with no score or rank rows ("None — excluded cells are not scored or ranked"). The panel test asserts there is no "Rank", "Suitability score" or `#n` text; a shell test drives a map click on an excluded cell. Live: Pilliga cell S30.836_E149.586 (`s4-03-detail-excluded.png`). |
| Same view from map and shortlist | As row 1 (`AppShell.integration.test.tsx`: "opens the SAME detail view…"). |
| Deterministic engine, same backend results as the rest of the app | Each Run now materialises `explanations.json` with **its own weights**, using the S2-06 stage's own assembler, templates and writer (ported from Xinhao's 6fe88a3, co-authored). Before: one shared default-weights file, which for **Grid-led listed positive factors out of contribution order for all 25 top sites**. After: 0 of 25 (`tests/backend/test_run_specific_explanations.py`). Live, Grid-led rank 1 lists transmission (0.348) → wind (0.210) → REZ (0.150), matching its own contributions (`s4-03-detail-grid-led.png`). No LLM is involved anywhere. |

**Also fixed (found while verifying S4-02/S4-03, in the same port):**
- `run_id` now hashes the integrated input and the explanation templates, so a run scored from an older frozen table is never reused. One from 2026-09-17, with 1,233 eligible cells, was being served locally.
- Identical concurrent `POST /runs` are serialised. The React dev double-mount produced a 500 with no CORS header.
- Site-detail reads refuse a run whose input has changed.

Contract 1.3.

**Headline wording (agreed with Pouya):** the S2-06 template headline "Higher-ranked candidate under the selected assumptions and criteria" was shown for every eligible cell, including rank 16,641 of 32,525. It is now "Eligible candidate under the selected assumptions and criteria" in `explanation_templates.yaml`. New runs pick it up automatically, because the templates are part of the run identity. The S2-09 reviewed snapshot `EXPECTED_EXPLANATION_SHA256` was refreshed: restoring the old headline reproduces the previous digest exactly, so the wording is the only change, and top-5 cells, scores and scenario results are unchanged. The packaged `DATA/explanation/` JSON still carries the old wording, but it is now only a fallback for runs materialised before this change; regenerate it with the S2-06 stage when the baseline is next re-frozen. The S2-06 owner should confirm.

**Tests (2026-10-20):** web `tsc --noEmit` clean, Jest 235/235 (`SiteDetailPanel.test.tsx` rewritten for every S4-03 field, plus two new shell tests); backend `pytest tests/backend tests/service tests/integration` all passing (new: `test_run_specific_explanations.py`).

**Review outcome:** _pending PR review._

Refer to the [Sprint 4 Definition of Done](README.md#definition-of-done) for final acceptance.
