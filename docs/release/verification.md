# Verification evidence — S3-10 release candidate

> **Historical record (Sprint 3).** This log verifies the S3-10 release candidate
> as built on another worktree. Since then the baseline changed: the
> `outside_nsw_land` exclusion (QA F-01, 2026-10-22) is now **current**, so the
> "stale token" sweep below no longer applies, and the current counts are
> 23,266 eligible / 24,045 excluded (input SHA `df7073bd`). The Sprint 4
> rehearsal evidence is [`rehearsal.json`](rehearsal.json) and
> [`demo-script.md`](demo-script.md); the Sprint 4 verification and clean-environment
> reproduction are recorded in the final handover package.

Branch / worktree: `s3-10-final-demo` at
`/Users/nb/Desktop/Opt Mining/.worktrees/s3-10-final-demo`.

All Python commands run from the worktree root with the parent-root 3.13 venv
(`/Users/nb/Desktop/Opt Mining/.venv/bin/python`, Python 3.13.13, pytest 9.1.1 as
CI pins). The repo `python3` is 3.14 (unsupported — the grid builder emits
degenerate cells), so the venv is used throughout.

This document records the literal commands run to bring the stack up, verify it,
rehearse the demo, and gate the release docs, with their PASS/FAIL results and
the observed environment, so a reviewer can read the evidence without re-running.

A stale-token sweep over `docs/release/**` and the ticket confirms **none** of
the four old divergent-lineage markers (the dropped `outside_nsw…` exclusion
reason, the old `23,2xx` eligible count, and the two old run-hash prefixes
`604d05…` / `e43fd8…`) appear as literal values in any S3-10 artifact. The exact
grep pattern is in §2 below.

---

## 1. Rehearsal against the real running MVP (FEAT-002)

Docker **was available**, so the full Docker stack path was used (no dev-server
fallback) and the integration gate ran for real (it did NOT skip).

### Observed environment / versions

| Component | Version |
| --- | --- |
| Docker Engine (server) | 29.5.2 |
| Docker Compose | v5.1.4 (`docker compose version --short`) |
| API image | `opt-mining-s3-10-api:latest` (`310e6dd883e1`) |
| Web image | `opt-mining-s3-10-web:latest` (`02d9da747a30`) |
| API container Python | 3.13.16 (`python:3.13-slim`) |
| Web container Node | v20.20.2 |
| Host venv Python | 3.13.13 |
| pytest | 9.1.1 |

### Stack up on non-default ports (run from `app/`)

```
API_HOST_PORT=18010 WEB_HOST_PORT=13010 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:18010 \
CORS_ALLOW_ORIGINS=http://localhost:13010 \
docker compose -p opt-mining-s3-10 -f docker-compose.yml up --build -d
```

### Smoke test (from the worktree root, same env)

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:18010 \
CORS_ALLOW_ORIGINS=http://localhost:13010 \
python app/smoke_test.py
```

Smoke PASS line (captured verbatim):

```
PASS: web, CORS and all seven operations; run=a743f7dc0bcabffa; quality_checks=28; returned_ranks=5
```

### Rehearsal harness (from the worktree root, same env)

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:18010 \
CORS_ALLOW_ORIGINS=http://localhost:13010 \
python app/rehearse_demo.py --require-final --output docs/release/rehearsal.json
```

Harness output / exit:

```
PASS (technical) but NOT FINAL; evidence -> docs/release/rehearsal.json
REHEARSE_EXIT=3
```

Exit code `3` is the intended `--require-final` signal (`EXIT_NOT_FINAL`): the
automated run is technically green but is NOT Checkpoint-D acceptance; review /
merge / client sign-off gates remain open. `result` in the JSON is `PASS`.

### Integration gate (from the worktree root)

```
python -m pytest -v -m integration tests/backend/test_demo_rehearsal.py
# => 1 passed, 17 deselected  (ran against the live stack; NOT skipped)
```

### Teardown

```
docker compose -p opt-mining-s3-10 -f docker-compose.yml down
```

### Captured live values (all regenerated on this branch — never copied)

- Both URLs reachable: API `http://localhost:18010`, web origin
  `http://localhost:13010`.
- Frozen input SHA the API loaded: `4062224a`.
- Cells: total **47,311**, eligible **32,525**, excluded **14,786**;
  `data-quality` passed with **28** checks.
- Run ids: baseline `9a4c70db9cd5f912`, wind_led `a743f7dc0bcabffa`,
  grid_led `2b0d1e4f332babe9`.
- Rank-1 (wind_led) cell `S31.186_E151.686`, score `0.9139051757537562`; its six
  per-criterion contributions sum to the score with diff `0.00e+00` (within
  `RECONCILE_TOLERANCE` = 1e-9).
- Excluded example cell `S28.186_E152.386`, reason code **`excessive_slope`**
  ("Slope exceeds 15°"), `suitability_score` = null and `rank` = null.
- `/scenario-comparison` wind_led vs grid_led: **32,525** rows; observed
  moved-cell count (|rank_a − rank_b| ≥ 1) = **32,519**; example moved cell
  `S31.186_E151.686` (rank_a 1 → rank_b 21, delta −20).
- Sanity: known-wind-farm quartile check present; most references in the upper
  quartile, `Bodangora Wind Farm` in the top band (rank 2, pct 99.997);
  `top_band_n` = 20; 2 contradictions disclosed; the always-on
  model-not-trained caveat present. Honest anomalies surfaced: `Boco Rock`
  outside the upper quartile (rank 11,225, pct 65.49), and two references with
  null rank/percentile (`Taralga Wind Farm`, `Rye Park Wind Farm`).
- `engine_recompute`: `not requested`.

### Fixes made during rehearsal (recorded for the reviewer)

Two defects blocked the first rehearsal against the real stack; both were
corrected with the minimal change required:

1. **Harness baseline run used a non-existent scenario.** `app/rehearse_demo.py`
   requested the baseline run as `POST /runs {"scenario":"baseline"}`, but the
   API has NO `baseline` named scenario (only `wind_led`/`grid_led`) and
   returned HTTP 422. The web client's Baseline run sends explicit default
   weights, so the harness was fixed to request the baseline run as
   `POST /runs {"weights":{"criteria": BASELINE_CRITERIA}}`, mirroring the web
   client verbatim. No scoring/weights/baseline value was changed.
2. **API image omitted the sanity sidecar.** `GET /sanity-check` returned HTTP
   503 because `app/api/Dockerfile` did not copy `DATA/sanity`. Fixed by adding
   `COPY DATA/sanity ./DATA/sanity` and rebuilding; the endpoint then returned
   200. No frozen data was modified — only an already-committed frozen input was
   packaged.

---

## 2. Release-doc gates and CI-parity checks (FEAT-003)

### Readiness matrix loads clean and covers AC1–AC12

```
python -c "import json; d=json.load(open('docs/release/readiness.json')); print(sorted(k for k in d if k.startswith('AC')))"
# => ['AC1','AC10','AC11','AC12','AC2','AC3','AC4','AC5','AC6','AC7','AC8','AC9']
```

All twelve `AC1`..`AC12` keys present; FEAT-001's `readiness_keys_cover_acs`
unit test (in `tests/backend/test_demo_rehearsal.py`) passes.

### Docs-consistency guard now asserts for real on the new release docs

```
python -m pytest -v -m "not integration" tests/backend/test_s309_docs_consistency.py
# => 15 passed, 3 skipped
```

The release-doc assertions on `docs/release/README.md` and
`docs/release/limitations.md` now run for real (screening language present,
every "best site"/"best place" negated, demand framed as a proxy with a
negation around measured/actual). The 3 skips are the non-prose release files
(`verification.md`, `readiness.json`, `rehearsal.json`), which are not
prose-guarded by design.

### Rehearsal pure-predicate unit tests (CI fast tier)

```
python -m pytest -v -m "not integration" tests/backend/test_demo_rehearsal.py
# => 18 passed  (ranks-ordered, contribution reconcile, scenario-row keys,
#     moved-cell count, readiness keys cover AC1..AC12, stale-token grep)
```

### Full backend fast gate (CI parity — no regressions)

```
python -m pytest -q -m "not integration" tests/backend
# => 101 passed, 1 skipped, 2 deselected
```

### README link check

```
grep -REn 'docs/release' README.md app/README.md
# => README.md and app/README.md both link docs/release/README.md
```

### Stale-token sweep (fatal in review)

Run the `grep -REn` alternation of the four old-lineage markers (defined
verbatim as `STALE_TOKENS` in `app/rehearse_demo.py` and in the FEAT-003 task
`verification` command) over `docs/release/` and
`Sprint-3-Tasks/S3-10-Final-Demo-Release-Candidate.md`:

```
# pattern = the four STALE_TOKENS from app/rehearse_demo.py
grep -REn "$STALE_TOKEN_PATTERN" docs/release/ Sprint-3-Tasks/S3-10-Final-Demo-Release-Candidate.md
# => no matches (no old-lineage values leaked)
```

The literal tokens are intentionally **not** written out in this file so the
sweep over `docs/release/**` stays clean; the canonical pattern lives in
`app/rehearse_demo.py::STALE_TOKENS`.

### Pre-tag check (recorded; the tag itself is cut only on explicit authorisation)

```
git tag -l 'v0.1.0-rc.*'
# => v0.1.0-rc.1   (only the stale-lineage tag exists)
```

`v0.1.0-rc.2` is free on this branch. Per design Decision 1-A the annotated tag
is cut on the final S3-10 commit only after the full rehearsal passes and only
when authorised; this verification does not cut it.

---

## 3. Remaining CI-parity commands (for the reviewer to run with the stack up)

These are the documented CI-parity commands; the backend fast gate and the
docs/rehearsal gates above are run here. The remaining non-Docker, frontend and
Compose-smoke steps mirror `.github/workflows/ci.yml`:

```
# remaining non-Docker backend/e2e
python -m pytest -v -m "not integration" --ignore=tests/backend

# frontend (from app/web)
npm ci && npm test -- --runInBand && npm run typecheck && npm run build

# Compose build + smoke (from app/)
docker compose up --build -d && python app/smoke_test.py && docker compose down

# optional raw-source rebuild (slow, needs raw inputs)
python -m pipeline
```
