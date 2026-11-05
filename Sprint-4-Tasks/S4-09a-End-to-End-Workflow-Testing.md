# S4-09a: Complete End-to-End Workflow Testing (Happy Path)

**Type:** Task
**Priority:** P0
**Status:** Partly done — automated browser E2E added; clean-checkout run pending
**Source:** [Client Sprint 4 brief](OPT_MINING_Sprint4_Final_Guidance.md), §4 S4-09
**Blocked by:** S4-02, S4-03, S4-04, S4-05, S4-06, S4-10
**Blocks:** S4-09b

---

> **Split note:** First half of the former **S4-09** (End-to-End and Failure-Case Testing). S4-09a proves the happy-path workflow passes end-to-end; S4-09b exercises the failure and edge cases. Splitting lets the core workflow be verified and signed off before the (larger) failure-case effort, and keeps a green end-to-end baseline that the failure tests can build on.

## Objective

Verify the whole product on the intended end-to-end workflow, not only individual backend functions.

## Required Work

- [ ] Test the full workflow from application launch through scenario selection, analysis, map, shortlist, site inspection and rerun.
- [x] Confirm the frontend exercises the approved backend decision engine throughout (no UI-side scoring).
- [ ] Capture the test as a repeatable script/checklist, run against a clean checkout of the Sprint 4 baseline.
- [ ] Record the environment, dataset/config version and commands used so the run is reproducible.

## Acceptance Criteria

- [ ] A documented end-to-end test exercises launch → scenario/weights → run analysis → NSW map → eligible/excluded cells → ranked shortlist → site inspection → change scenario → rerun → compare, and passes on a clean checkout.
- [ ] Map, shortlist and site-detail views show consistent cell IDs, scores and ranks sourced from the same backend analysis output.
- [ ] A rerun with changed weights produces an observably different ranking (confirming the UI calls the engine rather than caching/recomputing).
- [ ] The test is reproducible from documented commands and names the dataset/config version used.
- [x] Automated coverage exists where practical; any step verified manually is explicitly recorded as a manual check with its rationale.

## Deliverable

End-to-end (happy-path) test script/checklist plus evidence of a passing run, and automated tests where appropriate.

## Completion Evidence

**Branch:** `s4-integration`. **Owner:** Pouya Mousavi. **Verified:** 2026-10-22.

- **Automated browser test:** `app/web/e2e/happy-path.spec.ts` (Playwright 1.63.0, `npm run e2e`), run in CI by the `docker-build` job after `smoke_test.py`. It drives the real UI: baseline run on load → map canvas → shortlist row 1 → site detail shows the same `cell_id` → edit the wind weight and re-run (new `run_id`) → CSV export with the screening disclaimer. A second test checks a 1e308 weight is refused before any run (QA F-07).
- **Run:** 2 passed against the production Compose stack (`docker compose -f docker-compose.yml up --build`), 2026-10-22, integrated table SHA-256 `df7073bd…`.
- **Rehearsal:** `PYTHONPATH=. python app/rehearse_demo.py --output docs/release/rehearsal.json --external-sanity` PASS (23,266 eligible, data quality 28/28).
- **Not yet covered automatically:** the scenario-comparison step and an explicit map-vs-shortlist cell-id check; both are in the demo script as manual checks. The clean-checkout run is recorded in the handover pack (`04_Test_and_E2E_Evidence`).

**Review outcome:** _pending PR review._

Refer to the [Sprint 4 Definition of Done](README.md#definition-of-done) for final acceptance.
