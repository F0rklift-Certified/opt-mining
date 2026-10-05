# S3-10: Final Demo Preparation & Release Candidate

**Type:** Story
**Priority:** High
**Story Points:** 2
**Labels:** demo, release, documentation
**Blocked by:** S3-09
**Blocks:** —

---

## Objective

Prepare the release candidate and the end-to-end demonstration that walks the client through the full screening flow, satisfying **Client Checkpoint D (Final acceptance)**.

---

## Context

Guidance §10 (Required Final Demonstration) and §11 (Checkpoint D). The client wants a live end-to-end demo, not slides. This ticket assembles the release candidate and rehearses the demo script against the running MVP.

---

## Deliverables

1. A tagged release candidate / final PR.
2. A rehearsed demo script following the guidance §10 sequence.
3. A short limitations & assumptions summary for the review.

---

## Acceptance Criteria

- [x] The app starts from the documented environment (per S3-09)
- [x] The demo shows: NSW inputs and default criteria/weights → run screening → show exclusions and explain one excluded site → show ranked shortlist and map → open a high-ranked site and explain its score → change the weighting/scenario and show how/why ranking changes → show a validation/sanity-check result → show the supporting GitHub code/tests/docs
- [x] The MVP uses screening-level claims and documents important limitations (satisfies **AC12**)
- [x] All Must-priority acceptance criteria (AC1–AC9, AC11) are demonstrably met end-to-end
- [ ] A release candidate is tagged and the final PR is reviewable (not one giant PR — backend merged first, then web, then validation/docs)
- [x] Any known gaps or Should/Could items not completed are listed honestly

---

## Technical Notes

- Follow the guidance's reviewable-PR guidance: tested backend components first, then web integration, then validation/documentation — avoid one very large final PR.
- Rehearse the full §10 sequence on the real MVP; the demo is the acceptance evidence for the combined sprint.

## Implementation evidence — 5 October 2026

Preparation is available in [`docs/release/`](../docs/release/README.md): the
§10 demo script, concise limitations, AC1–AC12 readiness register and actual
HTTP/browser rehearsal observations. `app/rehearse_demo.py` records both
scenarios, engine-ordered results, contribution reconciliation, site/table
consistency, exclusions and reference validation; CI preserves its report.
Two stale S2-09 fixed snapshots were updated with a recorded input comparison.

The full technical demonstration now passes on the authorised repaired NSW
baseline: 23,266 eligible of 47,311 retained cells. Map/table selection, full
scenario-specific explanation, unscored exclusion inspection, numeric weights,
comparison and real Compose browser E2E are implemented and verified.
The four original rules, formula and weights are unchanged; separately approved
missing-demand and NSW-centroid rules are recorded in frozen change control.
Python: 1,187 passed, 5 skipped, 1 deselected; frontend: 75 passed; real E2E:
1 passed. The GA reference majority check passes with disclosed anomalies.

**Final acceptance still requires prerequisite merges and actual Checkpoint D.**
Scoped baseline, backend, web, security and validation/docs PRs keep review
separate. The candidate tag is pre-review, not a claim that main or the client
has accepted it. CSV export and a dedicated web sanity view remain Should items.
