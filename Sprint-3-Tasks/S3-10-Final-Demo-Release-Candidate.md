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
- [ ] A release candidate is tagged and the final PR is reviewable (not one giant PR — backend merged first, then web, then validation/docs) — *reviewable backend→web→docs PR sequence is defined in [`docs/release/README.md`](../docs/release/README.md); the annotated `v0.1.0-rc.2` tag is pre-checked free but cut only on explicit authorisation, so this box stays open until the tag is created.*
- [x] Any known gaps or Should/Could items not completed are listed honestly

---

## Technical Notes

- Follow the guidance's reviewable-PR guidance: tested backend components first, then web integration, then validation/documentation — avoid one very large final PR.
- Rehearse the full §10 sequence on the real MVP; the demo is the acceptance evidence for the combined sprint.

---

## Completion Notes

**Status:** Release package authored and verified on branch `s3-10-final-demo`
(worktree `/Users/nb/Desktop/Opt Mining/.worktrees/s3-10-final-demo`, based on
`s3-10` → S3-05…S3-09, HEAD at authoring `ca692f9`). The MVP feature set
(S3-01…S3-09) is unchanged; S3-10 adds only release packaging, the rehearsal
tooling and the widened docs guard. The human **Checkpoint-D gate is not
cleared by a green build** — review, merge and client sign-off remain open, and
the annotated `v0.1.0-rc.2` tag is cut only on explicit authorisation.

**Delivered artifacts:**

- `docs/release/README.md` — review-package index: pre-review/not-yet-accepted
  status, the single-command reproduce step (`docker compose up --build` from
  `app/`), and the backend→web→docs reviewable PR sequence.
- `docs/release/demo-script.md` — the guidance §10 nine-step live walkthrough
  (steps 1–8 screening flow; step 9 the required supporting-GitHub walkthrough),
  each step mapped to a concrete `AppShell.tsx` region and `app/api/app.py`
  operation. Every concrete value (run ids, cell ids, scores, contributions,
  counts, rank deltas, reason code) is sourced from `docs/release/rehearsal.json`
  — regenerated live on this branch, never transcribed from the old lineage.
  Includes the three-scenario weight table and a reference-caveats subsection.
- `docs/release/limitations.md` — review-facing restatement (links, not a fork)
  of `docs/technical-reference.md` §7: screening-level only, relative scores,
  demand proxy, linear normalisation, no cost/yield/engineering grade, ~5 km
  resolution, the seven frozen team decisions — plus an honest list of
  Should/Could items not delivered (optional Playwright E2E, UI polish, national
  expansion, extra datasets).
- `docs/release/readiness.json` — machine-readable AC1–AC12 → evidence map;
  Checkpoint-D acceptance marked `pending human sign-off`, not auto-passed.
- `docs/release/verification.md` — the literal commands run, their PASS/FAIL
  results, the observed Docker/Python/Node versions, the pre-tag
  `git tag -l 'v0.1.0-rc.*'` check and the stale-token sweep.
- `docs/release/rehearsal.json` — the captured FEAT-002 rehearsal evidence
  (authored by the preceding step).
- Project README link: `README.md` and `app/README.md` now link
  `docs/release/README.md`.

**Verification evidence** (parent-root 3.13 venv, `pytest 9.1.1` as CI pins;
full detail in `docs/release/verification.md`):

- `pytest -v -m "not integration" tests/backend/test_s309_docs_consistency.py`
  → **15 passed, 3 skipped** (the release-doc guard now asserts for real on
  `README.md`/`limitations.md`; the 3 skips are the non-prose files).
- `pytest -v -m "not integration" tests/backend/test_demo_rehearsal.py`
  → **18 passed** (pure predicates incl. `readiness_keys_cover_acs`).
- `pytest -q -m "not integration" tests/backend` → **101 passed, 1 skipped,
  2 deselected** (no regressions).
- `readiness.json` loads clean and contains `AC1`..`AC12`.
- Live rehearsal (FEAT-002, Docker available): smoke
  `PASS … run=a743f7dc0bcabffa; quality_checks=28; returned_ranks=5`; harness
  `REHEARSE_EXIT=3` (`EXIT_NOT_FINAL`, `result=PASS`); integration gate
  `1 passed, 17 deselected`. Rehearsal evidence location:
  `docs/release/rehearsal.json`.
- `grep -REn 'docs/release' README.md app/README.md` → both link the index.
- Stale-token sweep over `docs/release/` and this ticket → **no matches**.

**Honest Should/Could gaps:** the optional Playwright browser E2E
(`app/web/e2e/final-demo.spec.ts`) is **not delivered** (Should-level; the §10
flow is covered by the e2e test, smoke test and rehearsal gate); commercial-grade
UI polish, national expansion and additional datasets are deferred by §8.

**Checkpoint-D note:** an automated green rehearsal and a passing CI run are
**not** final acceptance. The `--require-final` harness exits non-zero by design
so a green build is never mistaken for client sign-off.
