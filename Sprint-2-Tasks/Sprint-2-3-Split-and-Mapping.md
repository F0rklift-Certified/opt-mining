# Combined Sprint 2 & 3 — Split, Mapping and Work Breakdown

**Source:** `Sprint-2-Tasks/OPT_MINING_Combined_Sprint_2_3_Guidance.md` (Client: Iman Rahimi, OPT-MINING)

**Purpose of this document:** The client combined Sprint 2 and Sprint 3 into a single guidance note. This document splits that guidance back into two ordered sprints, maps every guidance step (Steps 1–12), work-breakdown bullet and acceptance criterion (AC1–AC12) to a numbered task, and records the dependency chain. It is the index for the per-task worksheets in `Sprint-2-Tasks/` and `Sprint-3-Tasks/`.

---

## 1. The Split — Rationale

The client's architecture is explicit and non-negotiable:

```
Sprint 1 integrated data → validation/feature prep → hard exclusions →
normalisation → suitability/decision engine → ranking + explanation →
web API/service layer → interactive web application
```

Everything from *validation* down to *ranking + explanation* is **backend decision logic** that "must not be implemented only inside the user-interface code" (guidance §3). Everything from the *web API/service layer* down is **presentation**. That boundary is the natural sprint boundary, and it matches the client's own Review Checkpoints:

- **Checkpoint A (Decision design)** and **Checkpoint B (Backend working)** → **Sprint 2**
- **Checkpoint C (Web integration)** and **Checkpoint D (Final acceptance)** → **Sprint 3**

**Sprint 2 — Decision Engine (backend, reusable, tested).** Formalise the decision-engine specification, then harden and complete the decision logic so it fully satisfies AC1–AC7, AC9 and the testing parts of AC4. Deliver it as a reusable, independently testable module plus a thin service/API surface the web app can call.

**Sprint 3 — Web Application (presentation + acceptance).** Build the web MVP on top of the Sprint 2 service layer, satisfying AC8, AC10, AC11, AC12 and the UI parts of AC9. Includes the interactive NSW map, controls, ranked shortlist, site detail, explanation, scenario comparison, export, sanity-check visualisation, documentation and the final end-to-end demo.

### Important grounding note — Sprint 1 already built much of the "Sprint 2" backend

The Sprint 1 pipeline (`pipeline/`) already contains working modules for the exact decision steps the guidance lists under Steps 2, 5, 6, 11:

| Guidance step | Existing Sprint 1 module | Sprint 2 is therefore mostly… |
|---------------|--------------------------|-------------------------------|
| Step 2 — Hard exclusions | `pipeline/exclusions/` (S1-07, configurable rules + reasons) | **Harden + spec-formalise**, verify reason retention, add tests to the combined-sprint bar |
| Step 4 — Normalisation | `pipeline/scoring/normalise.py` (directional min-max) | **Extract/document** as a standalone tested component; add outlier/missing-value policy |
| Step 5 — Suitability engine | `pipeline/scoring/score.py` (pure weighted MCDA) | **Formalise + freeze** the spec, confirm configurable weights |
| Step 6 — Ranking + explanation | `pipeline/scoring/rank.py`, `contrib_*` columns | **Add deterministic template explanations** (the contributions exist; the human-readable narrative does not) |
| Step 11 — Validation/sanity | `pipeline/sanity/` (S1-12) | **Extend** to the combined-sprint bar; feed results into the web app |

So Sprint 2 is **not** "build the decision engine from scratch." It is: write the frozen decision-engine specification (Step 3 + Checkpoint A), close the gaps against the combined-sprint acceptance criteria (deterministic explanations, scenario comparison, service layer), and raise test coverage. This is called out per-task below and is the single most important framing decision for scoping the sprint.

---

## 2. Sprint 2 — Task List (Decision Engine Backend)

**Epic:** Sprint 2 — Transparent NSW Wind-Site Decision Engine
**Checkpoints covered:** A (Decision design), B (Backend working)

| ID | Task | Guidance step(s) | AC(s) | Blocked by | Blocks |
|----|------|------------------|-------|-----------|--------|
| S2-01 | Decision-Engine Specification & Frozen Configuration | Step 3, Step 5 (defaults), Checkpoint A | AC3, AC5 | — | S2-02, S2-04, S2-05, S2-06 |
| S2-02 | Freeze & Validate the Sprint 1 Integrated Dataset (input contract) | Step 1 | AC1 | S2-01 | S2-03, S2-04 |
| S2-03 | Harden the Hard-Exclusion Component (reasons + tests) | Step 2 | AC2 | S2-02 | S2-06 |
| S2-04 | Feature Normalisation Module (standalone, tested) | Step 4 | AC3, AC4 | S2-01, S2-02 | S2-05 |
| S2-05 | Suitability Scoring & Ranking Module (configurable weights, tested) | Step 5, Step 6 | AC4, AC5, AC6 | S2-04 | S2-06, S2-07 |
| S2-06a | Explanation Rule/Template Engine & Eligible-Cell Explanations | Step 6 | AC7 | S2-05 | S2-06b, S2-08 |
| S2-06b | Excluded-Cell Explanations & Proxy/Data-Quality Caveats | Step 6 | AC7 | S2-03, S2-06a | S2-08 |
| S2-07 | Scenario / Weight-Comparison Engine | Step 7 | AC9 | S2-05 | S2-08 |
| S2-08 | Decision Service / API Layer (contract for the web app) | Step 3 (service layer), Step 8 (backend half) | AC4, AC6, AC7 | S2-06b, S2-07 | S3-01a |
| S2-09 | Backend Unit & Integration Test Suite | Step 12 (backend half) | AC4, AC6 | S2-05, S2-06a, S2-06b, S2-07 | — |

**Sprint 2 critical path:** S2-01 → S2-02 → S2-04 → S2-05 → S2-06a → S2-06b/S2-07 → S2-08. S2-03 runs parallel after S2-02. S2-09 runs alongside S2-05 onward.

**Full specs created:** S2-01, S2-05 and S2-08 have full Kiro spec folders under `.kiro/specs/` (`s2-01-decision-engine-specification`, `s2-05-suitability-scoring-ranking`, `s2-08-decision-service-api`), each with requirements.md (EARS), design.md and tasks.md. S2-06 is broken into S2-06a/S2-06b per the recommendations.

---

## 3. Sprint 3 — Task List (Web Application)

**Epic:** Sprint 3 — Explainable NSW Wind-Site Screening Web MVP
**Checkpoints covered:** C (Web integration), D (Final acceptance)

| ID | Task | Guidance step(s) | AC(s) | Blocked by | Blocks |
|----|------|------------------|-------|-----------|--------|
| S3-01a | Application Shell Scaffold (Next.js/React + FastAPI) | Step 8 | AC8 (foundation) | S2-08 | S3-01b |
| S3-01b | Decision-Service Integration (typed HTTP client) & Data-Quality Banner | Step 8 | AC1, AC4 (UI must not recompute) | S3-01a | S3-02, S3-03a, S3-04, S3-06 |
| S3-02 | Analysis Controls (weights / presets / run) | Step 8, Step 5 | AC5 | S3-01b | S3-06 |
| S3-03a | Base Map & Cell Rendering (eligible/excluded styling) | Step 9 | AC8 | S3-01b | S3-03b |
| S3-03b | Map Click-to-Inspect & Display Filters | Step 9 | AC8 | S3-03a | S3-05 |
| S3-04 | Ranked Shortlist / Results Panel | Step 10 | AC8 | S3-01b | S3-05 |
| S3-05 | Site-Detail & Explanation View | Step 10, Step 6 | AC7 | S3-03b, S3-04 | S3-07 |
| S3-06 | Scenario-Comparison UI | Step 7 | AC9 | S3-02, S2-07 | S3-07 |
| S3-07 | Shortlist Export (CSV) *(Should)* | Step 10 | — (AC list; "Should" priority) | S3-04 | — |
| S3-08 | Sanity-Check / Validation Visualisation | Step 11 | AC10 | S2-09, S3-03a | S3-09 |
| S3-09 | Docs, Reproducible Run Path & End-to-End Tests | Step 12 | AC11, AC12 | S3-05, S3-06 | S3-10 |
| S3-10 | Final Demo Preparation & Release Candidate | Step 10 (demo), Checkpoint D | all | S3-09 | — |

**Sprint 3 critical path:** S3-01a → S3-01b → (S3-02, S3-03a, S3-04 parallel) → S3-03b → S3-05 → S3-09 → S3-10. S3-06, S3-07, S3-08 slot in as their upstreams complete.

---

## 4. Coverage Check — every guidance element is mapped

**Steps 1–12:** 1→S2-02 · 2→S2-03 · 3→S2-01 · 4→S2-04 · 5→S2-01/S2-05 · 6→S2-05/S2-06a/S2-06b · 7→S2-07/S3-06 · 8→S2-08/S3-01a/S3-01b/S3-02 · 9→S3-03a/S3-03b · 10→S3-04/S3-05/S3-07 · 11→S3-08 · 12→S2-09/S3-09/S3-10.

**Work-breakdown bullets (guidance §6):** decision-engine spec→S2-01 · hard-exclusion module→S2-03 · normalisation module→S2-04 · scoring/ranking module→S2-05 · explanation + scenario→S2-06a/S2-06b/S2-07 · web skeleton + integration→S3-01a/S3-01b · map + site detail→S3-03a/S3-03b/S3-05 · shortlist + export→S3-04/S3-07 · validation/sanity→S3-08 · e2e testing + docs + demo→S3-09/S3-10.

**Acceptance criteria:** AC1→S2-02/S3-01b · AC2→S2-03 · AC3→S2-01/S2-04 · AC4→S2-04/S2-05/S2-08/S2-09/S3-01b · AC5→S2-01/S2-05/S3-02 · AC6→S2-05/S2-09 · AC7→S2-06a/S2-06b/S2-08/S3-05 · AC8→S3-01a/S3-03a/S3-03b/S3-04 · AC9→S2-07/S3-06 · AC10→S3-08 · AC11→S3-09 · AC12→S3-09/S3-10.

Every step, bullet and AC maps to at least one task. No gaps.

---

## 5. Combined Dependency Graph

```
Sprint 2 (backend)
  S2-01 (Decision spec + frozen config)  [FULL SPEC]
    ├── S2-02 (Freeze/validate dataset)
    │     ├── S2-03 (Hard exclusions) ───────────────────────────────┐
    │     └── S2-04 (Normalisation) ──┐                              │
    │                                 └── S2-05 (Scoring + ranking) ─┬── S2-06a (Explanation engine + eligible) ── S2-06b (excluded + caveats) ┐
    │                                     [FULL SPEC]                └── S2-07 (Scenarios) ────────────────────────────────────────────────────┤
    │                                                                        S2-09 (Backend tests)                                             │
    │                                                                                                                                          │
    └──────────────────────────────────────────────────────── S2-08 (Service/API layer) [FULL SPEC] ◄────────────────────────────────────────┘
                                                                     │
Sprint 3 (web)                                                       ▼
  S3-01a (Next.js/React + FastAPI shell scaffold)
    └── S3-01b (Typed HTTP client integration + banner)
          ├── S3-02 (Controls) ──────────────────────────┐
          ├── S3-03a (Map render) ── S3-03b (Map interaction + filters) ┐
          ├── S3-04 (Shortlist) ────────────────────────────────────────┴── S3-05 (Site detail + explanation) ──┐
          └── S3-06 (Scenario UI, needs S2-07) ────────────────────────────────────────────────────────────────┤
              S3-07 (Export, Should)                                                                             │
              S3-08 (Sanity viz, needs S2-09 + S3-03a) ──┐                                                       │
                                                         └── S3-09 (Docs + e2e) ◄──────────────────────────────┘
                                                                └── S3-10 (Demo + RC)
```

---

## 6. Story-Point Totals (see per-sprint Jira files for per-ticket points)

- **Sprint 2:** ~32 points across 10 tickets (S2-06 split into S2-06a + S2-06b).
- **Sprint 3:** ~34 points across 12 tickets (S3-01 split into S3-01a + S3-01b; S3-03 split into S3-03a + S3-03b).

These are planning estimates; the student team owns final sizing. See `Sprint-2-Tasks/Sprint-2-Task-Recommendations.md` for the sizing rationale. The three full-spec tickets (S2-01, S2-05, S2-08) have Kiro spec folders under `.kiro/specs/`.
