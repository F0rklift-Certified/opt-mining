# S3-10 Release Package — review index

The release-candidate review package for the Opt-Mining MVP (Client Checkpoint
D). This front page links the package and restates its status; the detail lives
in the linked documents.

Opt-Mining is a **preliminary screening** tool. Everything here is
**screening-level**: it surfaces higher-ranked candidate cells for further
investigation. It is **not** a tool for picking the best site to build a wind
farm, and is **never** a tool for the best place to build — no final
recommendation, no site approval. The electricity-demand input is a **proxy**;
it is **not** measured or actual local demand.

## Status — pre-review, not yet accepted

This is a **pre-review release candidate** (`v0.1.0-rc.2`, to be cut on this
branch's final S3-10 commit). An automated green rehearsal and a passing CI run
are **not** Checkpoint-D acceptance: review, merge and client sign-off remain
open. `v0.1.0-rc.1` belongs to a divergent earlier lineage and is left untouched.

## Reproduce in one command

From **`app/`**:

```bash
docker compose up --build
```

Then verify from the repository root with `python app/smoke_test.py`. The exact
rehearsal commands, non-default ports and observed versions are in
[`verification.md`](verification.md).

## Package contents

| Document | What it is |
| --- | --- |
| [`demo-script.md`](demo-script.md) | The guidance §10 nine-step live walkthrough, with every concrete value captured during rehearsal |
| [`limitations.md`](limitations.md) | Review-facing limitations & assumptions, plus honest Should/Could gaps |
| [`readiness.json`](readiness.json) | Machine-readable AC1–AC12 → evidence map; Checkpoint D marked pending human sign-off |
| [`rehearsal.json`](rehearsal.json) | Captured evidence from the live rehearsal on this branch (run ids, scores, counts, deltas, sanity outcomes) |
| [`verification.md`](verification.md) | The literal commands run, their PASS/FAIL results, and the observed Docker/Python/Node versions |

## Reviewable PR sequence (backend → web → docs)

Per the guidance §5 "not one giant PR" rule, the combined sprint is presented as
three review-ordered PRs. Each PR lists the evidence a reviewer runs to confirm
it in isolation.

1. **PR-1 — Backend decision components & service.**
   Scope: `pipeline/**`, `app/api/**`, and the backend/service/integration/sanity
   tests (already-committed ancestry on this branch). Merge first.
   Evidence:
   ```bash
   pytest -v -m "not integration" tests/backend
   pytest -v -m "not integration" --ignore=tests/backend
   ```
2. **PR-2 — Web integration.**
   Scope: `app/web/**`, `app/docker-compose.yml`. Merge second, on PR-1.
   Evidence (from `app/web`, plus the Compose smoke from `app/`):
   ```bash
   npm ci && npm test -- --runInBand && npm run typecheck && npm run build
   # from app/: docker compose up --build -d && python app/smoke_test.py && docker compose down
   ```
3. **PR-3 — Validation, documentation & release candidate.**
   Scope: `docs/**` (incl. this `docs/release/**` set), `app/rehearse_demo.py`,
   `tests/backend/test_demo_rehearsal.py`, and the e2e + docs-consistency guards.
   The annotated tag is cut on **this** merge commit. Merge last.
   Evidence:
   ```bash
   pytest -v -m "not integration" --ignore=tests/backend  # collects the e2e test
   pytest -v -m "not integration" tests/backend/test_s309_docs_consistency.py
   pytest -v -m integration  tests/backend/test_demo_rehearsal.py  # against the live stack
   ```

The S3-10 authored work lands on `s3-10-final-demo` as three review-ordered
commits in this backend→web→docs (Decision 2) shape — there is no new web source
in S3-10, so PR-2's web gate re-runs the existing green suite:

| Commit | Tier | Files |
| --- | --- | --- |
| `test(release): S3-10 rehearsal harness, gate, and widened docs guard` | backend/test | `app/rehearse_demo.py`, `tests/backend/test_demo_rehearsal.py`, `tests/backend/test_s309_docs_consistency.py` |
| `test(release): capture FEAT-002 live rehearsal evidence` | backend/test | `app/api/Dockerfile`, `app/rehearse_demo.py`, `docs/release/rehearsal.json` |
| `docs(release): author S3-10 release package and mark ticket` | docs | `docs/release/{README,demo-script,limitations,readiness,verification}`, `README.md`, `app/README.md`, the S3-10 ticket |
