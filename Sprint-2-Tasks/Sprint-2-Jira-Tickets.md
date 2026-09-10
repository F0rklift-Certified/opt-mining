# Sprint 2 — Jira Tickets

**Epic:** Sprint 2 — Transparent NSW Wind-Site Decision Engine

**Sprint Objective:** Turn the frozen Sprint 1 integrated NSW dataset into a reusable, tested, explainable decision engine (exclusions → normalisation → scoring → ranking → explanation → scenarios) exposed through a service layer the web app can call.

**Outcome:** Running the engine on the real NSW data produces eligibility, deterministic scores/ranks, per-site explanations and scenario comparisons — all outside the UI and covered by tests.

**Checkpoints:** A (Decision design), B (Backend working).

**Grounding note:** Much of this backend already exists from Sprint 1 (`pipeline/exclusions/`, `pipeline/scoring/`, `pipeline/sanity/`). Sprint 2 formalises the spec, closes gaps against the combined-sprint acceptance criteria (deterministic explanations, scenario comparison, service layer) and raises test coverage — it is not a green-field rebuild.

**Formal specs:** S2-01, S2-05 and S2-08 have full Kiro spec folders under `.kiro/specs/` (`s2-01-decision-engine-specification`, `s2-05-suitability-scoring-ranking`, `s2-08-decision-service-api`), each with requirements.md (EARS), design.md and tasks.md. S2-06 is broken into S2-06a/S2-06b.

---

## S2-01: Decision-Engine Specification & Frozen Configuration

**Type:** Task
**Priority:** Highest
**Story Points:** 3
**Labels:** decision-engine, documentation, data-governance
**Blocked by:** —
**Blocks:** S2-02, S2-04, S2-05, S2-06a
**Sizing recommendation:** FULL SPEC (this task is the Checkpoint-A design artefact) — spec folder created at `.kiro/specs/s2-01-decision-engine-specification/`

### Description

Produce a single authoritative decision-engine specification fixing the exact per-cell features, directions, normalisation method, scoring formula and default weighting configuration. Reconcile it with the existing `pipeline/scoring/scoring_weights.yaml`. This is the document reviewed at Client Checkpoint A.

### Acceptance Criteria

- [ ] Each of the four criteria has named per-cell feature(s), with source, units and beneficial/adverse direction (AC3)
- [ ] Wind uses a named GWA variable with a justified height/variable choice
- [ ] Demand is explicitly a spatial demand proxy allocated below the AEMO region
- [ ] Infrastructure uses measurable indicators (distance to transmission/substation, REZ membership) — no undefined "infrastructure score"
- [ ] Scoring formula written out: `S_i = w_W·W_i + w_D·D_i + w_I·I_i + w_G·G_i` with the weight-normalisation rule
- [ ] Default weights listed with a written rationale each, labelled as documented assumptions (AC5)
- [ ] Normalisation method/direction per feature and outlier/missing-value policy specified
- [ ] Differences from the current `scoring_weights.yaml` explicitly reconciled
- [ ] Screening-level language throughout

---

## S2-02: Freeze & Validate the Sprint 1 Integrated Dataset

**Type:** Story
**Priority:** Highest
**Story Points:** 3
**Labels:** validation, data-quality, decision-engine
**Blocked by:** S2-01
**Blocks:** S2-03, S2-04
**Sizing recommendation:** Keep as-is

### Description

Adopt the Sprint 1 integrated NSW dataset as the frozen baseline input and add automated data-quality validation so the engine fails clearly or flags a problem rather than ranking from invalid input.

### Acceptance Criteria

- [ ] Sprint 1 integrated dataset consumed reproducibly — path, version, hash recorded (AC1)
- [ ] Automated checks: required columns; unique non-null `cell_id`; valid coordinates/geometries; expected units/ranges; missing-value counts; eligibility field present
- [ ] Each check reports expected vs observed vs pass/fail (no silent passes)
- [ ] On failure the engine halts or flags the problem — never ranks invalid input
- [ ] Reuses/extends `pipeline/validate.py` rather than duplicating
- [ ] Machine-readable validation result available to the service layer
- [ ] Unit tests with known-good and known-bad fixtures

---

## S2-03: Harden the Hard-Exclusion Component

**Type:** Story
**Priority:** High
**Story Points:** 3
**Labels:** exclusions, decision-engine
**Blocked by:** S2-02
**Blocks:** S2-06b
**Sizing recommendation:** Keep as-is

### Description

Harden `pipeline/exclusions/` (S1-07) to the combined-sprint bar: exclusions applied before scoring, each excluded cell retaining machine- and human-readable reasons, no compensation by a high wind score, thresholds configurable, per-rule tests.

### Acceptance Criteria

- [ ] Hard exclusions applied before scoring; excluded cells never scored (AC2)
- [ ] Each excluded cell retains a machine-readable reason code AND a human-readable string
- [ ] A cell can carry multiple exclusion reasons
- [ ] A high wind score cannot override an exclusion — verified by a controlled test
- [ ] Rules/thresholds remain configurable (YAML); every rule documented
- [ ] Exclusion summary statistics produced (total, eligible %, excluded by reason)
- [ ] Rule handling consistent across all exclusion layers (no fix-one-leave-others)
- [ ] Unit tests per rule + the compensation-guard case

---

## S2-04: Feature Normalisation Module

**Type:** Story
**Priority:** High
**Story Points:** 3
**Labels:** normalisation, decision-engine
**Blocked by:** S2-01, S2-02
**Blocks:** S2-05
**Sizing recommendation:** Keep as-is

### Description

Surface `pipeline/scoring/normalise.py` as a documented, tested, standalone component (DataFrame in, normalised DataFrame out) with explicit direction, outlier and missing-value policies, and bounds fixed per run (not per UI filter).

### Acceptance Criteria

- [ ] Each feature normalised to [0,1] with a documented direction (AC3)
- [ ] Normalisation implemented outside the UI and covered by tests (AC4)
- [ ] Bounds computed from the eligible population, documented and reproducible — not changed by UI filtering
- [ ] Outliers handled explicitly with a documented method
- [ ] Missing values handled explicitly (no biasing silent imputation)
- [ ] Constant feature handled without divide-by-zero and flagged
- [ ] Boolean features use {False→0, True→1}
- [ ] Unit tests: directions, boundaries, missing values, outliers, constant feature

---

## S2-05: Suitability Scoring & Ranking Module

**Type:** Story
**Priority:** High
**Story Points:** 5
**Labels:** scoring, ranking, decision-engine
**Blocked by:** S2-04
**Blocks:** S2-06a, S2-07
**Sizing recommendation:** FULL SPEC (correctness-critical; client signs off methodology) — spec folder created at `.kiro/specs/s2-05-suitability-scoring-ranking/`

### Description

Confirm/harden the transparent weighted-MCDA engine (`pipeline/scoring/`): configurable weights, deterministic scores and ranks for eligible cells only, per-criterion contributions retained for explanation.

### Acceptance Criteria

- [ ] Implements the documented S2-01 weighted-MCDA formula (AC6)
- [ ] Weights are configurable inputs, not hard-coded; defaults documented (AC5)
- [ ] Weights enforced/auto-normalised so interpretation is unambiguous
- [ ] Only eligible cells scored; excluded cells get null score/rank/contributions and take no part in bounds or ranking
- [ ] Every eligible cell has component scores, total score and a deterministic rank (documented tie-break)
- [ ] Per-criterion contributions retained and verified to sum to the total each run (AC7 data)
- [ ] Scoring computation is pure (no file I/O) and swappable
- [ ] No circular modelling (wind is an input, not a target)
- [ ] Implemented outside the UI and covered by tests (AC4)
- [ ] Unit tests: formula, weight re-normalisation, tie-break, eligible-only rule

---

## S2-06a: Explanation Rule/Template Engine & Eligible-Cell Explanations

**Type:** Story
**Priority:** High
**Story Points:** 3
**Labels:** explanation, decision-engine
**Blocked by:** S2-05
**Blocks:** S2-06b, S2-08
**Sizing recommendation:** First half of the split former S2-06

### Description

Build the deterministic rule/template explanation engine and use it to explain every eligible site — strongest positive factors and important weaknesses — from the S2-05 contributions, with no LLM dependency. Genuinely new (no narrative generator exists today).

### Acceptance Criteria

- [ ] A deterministic rule/template engine maps a scored cell to a structured explanation, no LLM
- [ ] For any eligible cell, explanation identifies strongest positive factors and important weaknesses from S2-05 contributions (AC7, eligible path)
- [ ] Explanations deterministic (same input → identical text)
- [ ] Produced by the backend, returned in a structured form the UI renders; schema documented
- [ ] Screening-level language, never "best site"
- [ ] Unit tests for a high-scoring and a marginal cell

---

## S2-06b: Excluded-Cell Explanations & Proxy/Data-Quality Caveats

**Type:** Story
**Priority:** High
**Story Points:** 2
**Labels:** explanation, decision-engine
**Blocked by:** S2-03, S2-06a
**Blocks:** S2-08
**Sizing recommendation:** Second half of the split former S2-06

### Description

Extend the S2-06a engine to explain excluded sites (their exclusion reasons) and to surface proxy and data-quality caveats for every site, completing AC7.

### Acceptance Criteria

- [ ] For excluded cells, machine- and human-readable exclusion reason(s) from S2-03 shown
- [ ] Any proxy variable called out as a proxy; demand proxy never shown as measured local demand (AC7, proxy caveat)
- [ ] Relevant data-quality limitations (S1-09/S2-02) surfaced
- [ ] Reuses/extends the S2-06a structured schema (not a fork); deterministic, no LLM
- [ ] Unit tests for an excluded cell and a proxy/low-confidence caveat cell

---

## S2-07: Scenario / Weight-Comparison Engine

**Type:** Story
**Priority:** High
**Story Points:** 3
**Labels:** scenarios, decision-engine
**Blocked by:** S2-05
**Blocks:** S2-08
**Sizing recommendation:** Keep as-is

### Description

Add a scenario abstraction (named preset → weight set) that reuses the S2-05 scoring function and returns comparable ranked outputs across at least two scenarios. Not probabilistic uncertainty scenarios.

### Acceptance Criteria

- [ ] At least two weighting scenarios can be defined and run (AC9)
- [ ] Presets documented (e.g. wind-led, grid-led)
- [ ] Each scenario reuses the S2-05 function — no duplicate scoring logic
- [ ] Two scenarios produce two ranked outputs plus a comparison (e.g. rank delta)
- [ ] Users can change weights or select a preset, rerun, observe changes
- [ ] Labelled as weighting/preference scenarios, not uncertainty scenarios
- [ ] Normalisation bounds consistent across scenarios for a given population
- [ ] Unit tests verify different weights → different, correctly re-ranked outputs

---

## S2-08: Decision Service / API Layer

**Type:** Story
**Priority:** High
**Story Points:** 5
**Labels:** api, service-layer, decision-engine
**Blocked by:** S2-06b, S2-07
**Blocks:** S3-01a
**Sizing recommendation:** FULL SPEC (contract blocks all of Sprint 3; freeze early) — spec folder created at `.kiro/specs/s2-08-decision-service-api/`

### Description

Expose the engine through a thin service/API layer so the web app consumes engine output and never re-implements decision logic. Define and freeze the request/response contract at the sprint boundary.

### Acceptance Criteria

- [ ] Exposes: run analysis (weights/scenario), get ranked results, get site detail + explanation, get exclusions, compare two scenarios
- [ ] All decision logic behind the service; UI never re-implements scoring/normalisation/exclusions (supports AC4)
- [ ] Results include component scores, total score, deterministic ranks (AC6)
- [ ] Site detail returns the S2-06a/S2-06b explanation structure (AC7)
- [ ] Weights/scenario accepted as inputs; interpretation documented (AC5)
- [ ] Surfaces the S2-02 data-quality status for a UI banner
- [ ] Request/response schema documented (OpenAPI or typed schema doc)
- [ ] Contract/integration tests per operation against the real engine on the frozen dataset

---

## S2-09: Backend Unit & Integration Test Suite

**Type:** Story
**Priority:** High
**Story Points:** 2
**Labels:** testing, decision-engine
**Blocked by:** S2-05, S2-06a, S2-06b, S2-07
**Blocks:** —
**Sizing recommendation:** Keep as-is

### Description

Consolidate cross-module tests: unit tests for decision functions, an end-to-end backend integration test on the frozen dataset, and a controlled fixture with a hand-computed expected ranking.

### Acceptance Criteria

- [ ] Unit tests cover normalisation, scoring formula, tie-break, explanation content, scenario re-ranking (AC4, AC6)
- [ ] A controlled test case with a hand-computed expected ranking verifies scoring end-to-end
- [ ] Integration test runs the full backend flow on the frozen dataset with a deterministic result
- [ ] Tests confirm excluded cells never scored / never in bounds
- [ ] Tests confirm contributions sum to the total score
- [ ] Tests run in CI and pass from a clean environment
- [ ] Determinism asserted across runs

---

## Summary — Sprint 2 Dependency Graph

```
S2-01 (Decision spec + frozen config)
  ├── S2-02 (Freeze/validate dataset)
  │     ├── S2-03 (Hard exclusions) ──────────────────────────────┐
  │     └── S2-04 (Normalisation) ──┐                             │
  │                                 └── S2-05 (Scoring + ranking) ─┬── S2-06a (Explanation engine + eligible) ── S2-06b (excluded + caveats) ┐
  │                                                                └── S2-07 (Scenarios) ─────────────────────────────────────────────────────┤
  │                                                                        S2-09 (Backend tests)                                               │
  └──────────────────────────────────────────────────────────── S2-08 (Service/API layer) ◄────────────────────────────────────────────────┘  → blocks S3-01a
```

---

## Import Notes

- **Total Story Points:** ~32 across 10 tickets (S2-06 split into S2-06a=3 + S2-06b=2).
- **Critical Path:** S2-01 → S2-02 → S2-04 → S2-05 → S2-06a → S2-06b / S2-07 → S2-08.
- **Parallelisable:** S2-03 runs alongside S2-04/S2-05 once S2-02 is done; S2-09 runs alongside S2-05 onward.
- **Full-spec tickets** (spec folders created under `.kiro/specs/`): S2-01 (`s2-01-decision-engine-specification`), S2-05 (`s2-05-suitability-scoring-ranking`), S2-08 (`s2-08-decision-service-api`). Each carries requirements.md (EARS), design.md and tasks.md.
- **Broken down:** S2-06 → S2-06a (engine + eligible explanations) / S2-06b (excluded + proxy/quality caveats).
- **Checkpoint gates:** A after S2-01; B after S2-05/S2-06a/S2-06b/S2-07/S2-09 with S2-08 ready for Sprint 3.
- Merge tested backend components first (reviewable PRs), per client guidance §6.
