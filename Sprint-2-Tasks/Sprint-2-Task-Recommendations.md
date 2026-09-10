# Sprint 2 & 3 — Task Sizing Recommendations

**Purpose:** For each task, a recommendation on whether to (a) **fully spec it out** as a formal Kiro spec (requirements → design → tasks folder, like the Sprint 1 `.kiro/specs/` and folder-tasks), (b) **break it into smaller sub-tasks/tickets** before committing it to a sprint, or (c) **keep it as a single ticket** as written. Reasoning is given per task, driven by three factors: **complexity**, **novelty** (green-field vs hardening existing Sprint 1 code), and **cross-cutting impact** (how many other components it touches).

> **Status: carried out.** The three FULL SPEC tickets now have Kiro spec folders under `.kiro/specs/` (`s2-01-decision-engine-specification`, `s2-05-suitability-scoring-ranking`, `s2-08-decision-service-api`), each with requirements.md (EARS), design.md and tasks.md. The three BREAK DOWN tickets have been split into a/b worksheets (S2-06→S2-06a/b, S3-01→S3-01a/b, S3-03→S3-03a/b), and both Jira export sheets and the split-and-mapping doc have been updated to the new IDs.

**How to read the recommendation column:**
- **FULL SPEC** — create a `.kiro/specs/<id>/` folder (requirements.md + design.md + tasks.md) and a task folder, as Sprint 1 did for S1-03/04/05/06/10/11/12. Warranted where the design is non-trivial and needs client sign-off or drives many downstream contracts.
- **BREAK DOWN** — split into 2+ smaller tickets/sub-tasks before the sprint starts, because the single ticket is too large or bundles independent concerns.
- **KEEP AS-IS** — a single well-scoped ticket; the worksheet is sufficient.

---

## Sprint 2 — Decision Engine

| Task | Points | Novelty | Recommendation | Reasoning |
|------|--------|---------|----------------|-----------|
| S2-01 Decision-Engine Specification | 3 | Documentation of existing design | **FULL SPEC** *(it IS the spec)* | This task's deliverable is the frozen design note reviewed at Checkpoint A. It fixes feature names, directions, formula and default weights that every other Sprint 2 task and the whole web app build against. Treat it as the authoritative spec document; do not break it up. Get client sign-off before S2-04/05 start. |
| S2-02 Freeze & Validate Dataset | 3 | Extends existing `validate.py` | **KEEP AS-IS** | Well-bounded: adopt frozen input + add gated checks. Single concern, single owner. |
| S2-03 Harden Hard Exclusions | 3 | Hardening S1-07 | **KEEP AS-IS** | The module exists (`pipeline/exclusions/`). This is verification + reason-schema + tests, not new design. One ticket is right. |
| S2-04 Feature Normalisation | 3 | Surfacing S1 `normalise.py` | **KEEP AS-IS** | Refactor-to-standalone + document policy + tests. Contained. |
| **S2-05 Scoring & Ranking** | 5 | Hardening S1 `scoring/` | **FULL SPEC** | Highest-value correctness component and the single source of scores. Even though the code exists, its formula, tie-breaking, weight-normalisation and eligible-only guarantees deserve a formal design so the client can sign off the methodology (Checkpoint A) and so it is provably correct. Mirror S1-10's spec-folder treatment. |
| **S2-06 Explanation Generator** | 5 | **Green-field** | **BREAK DOWN** | This is genuinely new (no narrative generator exists today) and bundles two separable concerns: (1) the explanation *data model* + rule/template engine, and (2) covering all three cases (high-scoring, marginal, excluded). Suggest splitting into **S2-06a: explanation rule/template engine + eligible-cell explanations** and **S2-06b: excluded-cell explanations + proxy/quality caveat rules**. Reduces risk and keeps PRs reviewable. |
| S2-07 Scenario Comparison Engine | 3 | Thin layer over S2-05 | **KEEP AS-IS** | A scenario is just a named weight set fed to S2-05. Small, single concern. |
| **S2-08 Decision Service / API Layer** | 5 | **Green-field (the seam)** | **FULL SPEC** | This is the contract that blocks all of Sprint 3. It needs a documented request/response schema agreed before S3-01 starts. A short design (operations, schemas, in-process-vs-HTTP decision) prevents churn across the whole web app. Spec it, freeze it early. |
| S2-09 Backend Test Suite | 2 | Consolidation | **KEEP AS-IS** | Deliberately small; owns the cross-module integration test + controlled-ranking fixture. |

**Sprint 2 subtotal:** 32 points across 10 tickets (S2-06 now split into S2-06a=3 + S2-06b=2).

---

## Sprint 3 — Web Application

| Task | Points | Novelty | Recommendation | Reasoning |
|------|--------|---------|----------------|-----------|
| **S3-01 Web Skeleton & Integration** | 5 | **Green-field** | **BREAK DOWN** | Bundles two decisions: (1) framework choice + app shell, and (2) wiring the service client + data-quality banner. Suggest **S3-01a: framework selection + app shell + run command** and **S3-01b: service-client integration + data-quality banner**. The framework choice is a decision worth isolating (it constrains every later UI ticket). |
| S3-02 Analysis Controls | 3 | Green-field | **KEEP AS-IS** | Bounded UI panel calling `run_analysis`. |
| **S3-03 Interactive NSW Map** | 5 | Green-field | **BREAK DOWN** | Highest-risk UI ticket (readability at ~5 km resolution across NSW is non-trivial). Suggest **S3-03a: base map + cell rendering + eligible/excluded styling** and **S3-03b: click-to-inspect + display filters (top-N / threshold)**. Lets rendering land and be reviewed before interaction is added. |
| S3-04 Ranked Shortlist Panel | 3 | Green-field | **KEEP AS-IS** | Table bound to engine output + map linkage. Contained. |
| **S3-05 Site-Detail & Explanation View** | 5 | Green-field | **KEEP AS-IS** *(consider splitting only if it slips)* | Single view, but rendering-heavy. It renders the S2-06 structure verbatim, so complexity is bounded by that contract. Keep as one ticket; split into "features + scores" vs "explanation rendering" only if it proves too large mid-sprint. |
| S3-06 Scenario-Comparison UI | 3 | Green-field | **KEEP AS-IS** | Renders `compare_scenarios`; bounded. |
| S3-07 Shortlist Export *(Should)* | 2 | Reuses S1-11 CSV | **KEEP AS-IS** | Thin, and explicitly a "Should" — do not over-invest. |
| S3-08 Sanity-Check Visualisation *(Should)* | 3 | Extends S1-12 | **KEEP AS-IS** | The `pipeline/sanity/` engine exists; this surfaces it. One ticket. |
| **S3-09 Docs, Run Path & E2E Tests** | 3 | Consolidation | **KEEP AS-IS** *(but co-schedule)* | Bounded, but start docs incrementally through the sprint rather than at the end. Not a break-down; a scheduling note. |
| S3-10 Final Demo & Release Candidate | 2 | Assembly | **KEEP AS-IS** | Rehearsal + RC tagging. |

**Sprint 3 subtotal:** 34 points across 12 tickets (S3-01 now split into S3-01a=3 + S3-01b=2; S3-03 into S3-03a=3 + S3-03b=2).

---

## Summary of Recommendations

**Fully spec out — DONE (spec folders created under `.kiro/specs/`):**
- **S2-01** — it is the decision-engine spec; the Checkpoint-A artefact. → `.kiro/specs/s2-01-decision-engine-specification/`
- **S2-05** — the correctness-critical scoring methodology the client signs off. → `.kiro/specs/s2-05-suitability-scoring-ranking/`
- **S2-08** — the backend/web contract that blocks all of Sprint 3; freeze early. → `.kiro/specs/s2-08-decision-service-api/`

**Broken into smaller sub-tasks — DONE (a/b worksheets created):**
- **S2-06** → S2-06a (engine + eligible explanations) / S2-06b (excluded + caveats) — genuinely new, two concerns.
- **S3-01** → S3-01a (shell scaffold) / S3-01b (integration + banner) — the framework decision this split isolated has since been made: **React/Next.js frontend + FastAPI backend over HTTP**, so S3-01a is now "scaffold the decided stack" rather than "choose one".
- **S3-03** → S3-03a (render) / S3-03b (interaction + filters) — highest UI risk.

**Keep as single well-scoped tickets:** S2-02, S2-03, S2-04, S2-07, S2-09, S3-02, S3-04, S3-05, S3-06, S3-07, S3-08, S3-09, S3-10.

**Two cross-cutting scheduling notes (not break-downs):**
- Freeze the **S2-08 service contract** at the sprint boundary so S3-01 integrates against a stable surface.
- Start **S3-09 documentation** incrementally, not as an end-of-sprint scramble.

**Why the three "full spec" choices and not more:** the project already carries formal specs for the Sprint 1 modules these build on, so re-speccing hardening tickets (S2-03, S2-04) would be redundant. Reserve the heavier spec process for (a) the frozen client-signed design (S2-01), (b) the one correctness-critical algorithm (S2-05), and (c) the one contract that many other tickets depend on (S2-08). That is where a design mistake is most expensive to unwind.
