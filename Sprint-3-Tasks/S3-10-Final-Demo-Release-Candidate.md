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

- [ ] The app starts from the documented environment (per S3-09)
- [ ] The demo shows: NSW inputs and default criteria/weights → run screening → show exclusions and explain one excluded site → show ranked shortlist and map → open a high-ranked site and explain its score → change the weighting/scenario and show how/why ranking changes → show a validation/sanity-check result → show the supporting GitHub code/tests/docs
- [ ] The MVP uses screening-level claims and documents important limitations (satisfies **AC12**)
- [ ] All Must-priority acceptance criteria (AC1–AC9, AC11) are demonstrably met end-to-end
- [ ] A release candidate is tagged and the final PR is reviewable (not one giant PR — backend merged first, then web, then validation/docs)
- [ ] Any known gaps or Should/Could items not completed are listed honestly

---

## Technical Notes

- Follow the guidance's reviewable-PR guidance: tested backend components first, then web integration, then validation/documentation — avoid one very large final PR.
- Rehearse the full §10 sequence on the real MVP; the demo is the acceptance evidence for the combined sprint.
