# S4-01: Complete Outstanding Sprint 3 Integration

**Type:** Task
**Priority:** P0
**Status:** Partially complete — integration verified; 2 baseline-sealing items outstanding (see Completion Evidence)
**Source:** [Client Sprint 4 brief](OPT_MINING_Sprint4_Final_Guidance.md), §4 S4-01

## Objective

Create one stable application baseline before adding any final-sprint enhancements.

## Required Work

- [x] Merge approved Sprint 2 and Sprint 3 work in the correct dependency order.
- [x] Complete any remaining web-to-decision-service integration.
- [x] Complete outstanding analysis controls, map rendering, click-to-inspect and ranked-results integration.
- [ ] Resolve merge conflicts, failed checks and integration defects. *(No conflicts; one backend check fails locally only due to pydantic env drift — needs CI-green confirmation under the pinned stack.)*
- [x] Confirm that the frontend uses the approved backend decision engine; do not duplicate scoring logic in the UI.
- [x] Record the final integrated dataset/configuration version used for the Sprint 4 baseline.

## Acceptance Criteria

- [x] A clean checkout can start the integrated application and execute the core analysis flow without manually running intermediate scripts.
- [ ] Approved Sprint 2 and Sprint 3 work is merged in dependency order with no outstanding merge conflicts and all CI checks green. *(Merge state clean, no conflicts; "all CI checks green" not yet confirmed under the pinned dependency stack — see gap 1.)*
- [x] The remaining web↔decision-service integration (analysis controls, map rendering, click-to-inspect, ranked results) is wired to the backend engine.
- [x] The frontend uses the approved backend decision engine; there is no duplicated scoring/normalisation logic in the UI.
- [x] The integrated dataset and configuration version used for the baseline is recorded in the repository.
- [ ] A release branch or tag marks the stable Sprint 4 baseline. *(Only S3-10 release candidates v0.1.0-rc.1/rc.2 exist; no dedicated Sprint 4 baseline cut — see gap 2.)*

## Deliverable

Stable Sprint 4 baseline/release branch or tag, with all required Sprint 2-3 components integrated.

## Completion Evidence

**Verification date:** 2026-10-14 · **Branch verified:** `docs/sprint-4-final-backlog` @ `6f40c00` (working tree clean) · **Method:** read-only verification, report at `.agents/tasks/s4-01-verification/findings.md`.

**Overall: PARTIALLY COMPLETE.** The integration work itself is done and verified; two baseline-sealing criteria remain.

Per-criterion verdict: AC1 PASS · AC2 PARTIAL · AC3 PASS · AC4 PASS · AC5 PASS · AC6 PARTIAL.

What passed, with evidence:

- **Single-command startup (AC1):** `docker compose up --build` from `app/` brings up both services (`app/docker-compose.yml`, `app/README.md`, `README.md` §2); a clean checkout ships frozen artefacts, so no manual intermediate scripts are needed. Self-contained smoke test at `app/smoke_test.py` run by CI's `docker-build` job.
- **Merge state (AC2, merge part):** `docs/sprint-4-final-backlog` folds s2-03..s2-09 → origin/main → s3-03B..s3-10 in dependency order; `git branch --merged` confirms; no conflict markers in any tracked file.
- **Web↔service wiring (AC3):** all four features route through the single typed client `app/web/app/api/decision-service.ts` → FastAPI → `pipeline.service`. Analysis controls (`POST /runs`), map (`GET /runs/{id}/cells`), click-to-inspect (`GET /runs/{id}/sites/{cell_id}`), ranked results (`GET /runs/{id}/results`). Backend `app/api/app.py` is delegation-only. Nothing stubbed in production.
- **No duplicated scoring in UI (AC4):** no scoring/normalisation/ranking math in any shell component; enforced by passing `app/web/__tests__/scope-guard.test.ts`.
- **Dataset/config version recorded (AC5):** `DATA/integration/metadata/integrated_baseline_manifest.json` — version `"2026"`, sha256 `4062224a…d2a1c80`, frozen 2026-09-15. Config in `pipeline/scoring/scoring_weights.yaml` + `scenarios.yaml`.
- **Test runs:** frontend jest 208 passed; `npm run typecheck` + `npm run build` exit 0; non-backend pytest 1210 passed / 9 skipped; in-process e2e `tests/integration/test_e2e_dataset_engine_app.py` 1 passed.

Gaps blocking closure:

1. **CI not confirmed green under pinned stack (AC2).** Backend gate fails one test locally — `tests/backend/test_frontend_openapi_snapshot.py::test_frontend_openapi_snapshot_matches_live_fastapi_app` — because local `.venv` has pydantic 2.13.5 vs the repo-pinned `pydantic==2.10.3` (`app/api/requirements.txt`); newer pydantic emits `additionalProperties: true` on three open-dict fields. Environment drift, not a code defect. Resolve by citing a green CI run (CI installs the pins), reinstalling the pinned deps and re-running the backend gate, or regenerating the snapshot under the agreed pydantic version.
2. **No stable Sprint 4 baseline branch/tag (AC6).** Only tags `v0.1.0-rc.1`/`v0.1.0-rc.2` exist; both are S3-10 release candidates and rc.2 is explicitly "not yet accepted." Cut/designate a Sprint 4 baseline marker on the integrated commit once CI is confirmed green.

Minor (non-blocking): the "Definition of Done" anchor linked below does not exist in `README.md` (dead link); the Docker boot was judged statically (compose + smoke test + passing in-process e2e), not executed live.

Refer to the Sprint 4 Definition of Done in [README.md](README.md) for final acceptance.
