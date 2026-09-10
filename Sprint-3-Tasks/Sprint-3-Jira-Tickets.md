# Sprint 3 — Jira Tickets

**Epic:** Sprint 3 — Explainable NSW Wind-Site Screening Web MVP

**Sprint Objective:** Build a lightweight web application on top of the Sprint 2 decision service that lets a user view candidate NSW sites on a map, apply exclusions, adjust weights/scenarios, obtain a ranked shortlist, inspect a site with an understandable explanation, compare scenarios, and trace results back to the Sprint 1 data.

**Outcome:** An openable, reproducible, explainable MVP that meets the combined-sprint Definition of Done end-to-end.

**Checkpoints:** C (Web integration), D (Final acceptance).

**Hard rule:** the UI consumes the S2-08 service and never recomputes decision logic (AC4). The map and the ranked table must show the same engine output (AC8).

---

## S3-01a: Application Shell Scaffold (Next.js/React + FastAPI)

**Type:** Story
**Priority:** Highest
**Story Points:** 3
**Labels:** web-app, frontend, backend, architecture, nextjs, react, fastapi
**Blocked by:** S2-08
**Blocks:** S3-01b
**Sizing recommendation:** First half of the split former S3-01

**Stack decision (agreed):** React/Next.js frontend + FastAPI backend over HTTP with an OpenAPI contract. This resolves the framework question and fixes the S2-08 service boundary as HTTP (not in-process).

### Description

Scaffold the decided stack — a FastAPI backend exposing the S2-08 operations over HTTP (publishing OpenAPI) and a Next.js/React frontend shell with placeholder regions for controls, map, results and site detail — runnable from documented commands.

### Acceptance Criteria

- [ ] Browser-based Next.js/React app, not a desktop executable
- [ ] FastAPI backend scaffold exposes the S2-08 operations over HTTP and publishes an OpenAPI schema (`/openapi.json` / `/docs`)
- [ ] Next.js/React frontend shell contains placeholder regions for controls, map, ranked results, site detail/explanation
- [ ] Frontend↔backend boundary is HTTP; no decision logic in the frontend
- [ ] Region fixed to NSW for the MVP
- [ ] Both apps run from documented commands (e.g. `uvicorn` for the API, `next dev`/`next start`)
- [ ] Stack decision + rationale recorded (short ADR)
- [ ] Runs from a single documented command in a clean environment
- [ ] Functionality/clarity prioritised over visual effects; no decision logic in the shell

---

## S3-01b: Decision-Service Integration & Data-Quality Banner

**Type:** Story
**Priority:** Highest
**Story Points:** 2
**Labels:** web-app, integration, frontend, nextjs, react, fastapi
**Blocked by:** S3-01a
**Blocks:** S3-02, S3-03a, S3-04, S3-06
**Sizing recommendation:** Second half of the split former S3-01

### Description

Wire the Next.js/React frontend to the FastAPI backend via a typed HTTP client generated from the OpenAPI schema so the shell renders real engine output, and surface the S2-02 data-quality status as a banner — no decision logic in the UI.

### Acceptance Criteria

- [ ] Frontend loads real data via the FastAPI S2-08 endpoints over HTTP — no decision logic in the UI (supports AC4)
- [ ] Typed client generated from the FastAPI OpenAPI schema so frontend/backend types cannot drift
- [ ] Sprint 1 integrated dataset successfully consumed via the engine (AC1 at app level)
- [ ] Data-quality banner surfaces the S2-02 status when flagged (via get_data_quality)
- [ ] The typed client is the thin, shared, single integration point, ready for S3-02/03/04/05/06
- [ ] Frontend performs no scoring, normalisation, ranking or exclusion computation

---

## S3-02: Analysis Controls (Weights / Presets / Run)

**Type:** Story
**Priority:** High
**Story Points:** 3
**Labels:** web-app, controls, frontend
**Blocked by:** S3-01b
**Blocks:** S3-06
**Sizing recommendation:** Keep as-is

### Description

Controls panel: region fixed to NSW, adjustable criterion weights and/or selectable presets, and a run/update action that re-invokes the decision service.

### Acceptance Criteria

- [ ] Region fixed to NSW for the MVP
- [ ] User can adjust weights and/or select a saved preset (AC5)
- [ ] Active weights and their interpretation are visible
- [ ] Run/update action re-invokes the S2-08 service and refreshes results
- [ ] Weights sent to the service; UI performs no scoring/normalisation (supports AC4)
- [ ] Default weights match the documented S2-01 assumptions
- [ ] Invalid weight input handled gracefully (no silent bad run)

---

## S3-03a: Base Map & Cell Rendering (Eligible/Excluded Styling)

**Type:** Story
**Priority:** High
**Story Points:** 3
**Labels:** web-app, map, visualisation, frontend
**Blocked by:** S3-01b
**Blocks:** S3-03b
**Sizing recommendation:** First half of the split former S3-03 (highest UI risk)

### Description

Render an interactive NSW base map with the analysis cells from engine output, readable at ~5 km resolution, with eligible and excluded/candidate cells visually distinguished.

### Acceptance Criteria

- [ ] Displays candidate sites/cells across NSW and stays readable (AC8, render half)
- [ ] Eligible and excluded/candidate cells visually distinguished
- [ ] Cell data comes from the S2-08 service — no recomputation in the UI
- [ ] Coordinates come from engine output (grid centroids/geometry in EPSG:4326) — no reprojection in the UI
- [ ] The rendered layer represents the same engine output as the ranked table (supports AC4)

---

## S3-03b: Map Click-to-Inspect & Display Filters

**Type:** Story
**Priority:** High
**Story Points:** 2
**Labels:** web-app, map, visualisation, frontend
**Blocked by:** S3-03a
**Blocks:** S3-05
**Sizing recommendation:** Second half of the split former S3-03

### Description

Add click-to-inspect (returning ID, score, key criteria, eligibility) and display filters (top-N and/or minimum threshold) to the rendered map.

### Acceptance Criteria

- [ ] Clicking a site returns ID, score, key criteria and eligibility
- [ ] Where practical, top-N and/or minimum-threshold filters provided
- [ ] Filters affect only display, not the scoring/normalisation population (via the S2-08 service over fixed output)
- [ ] The click event exposes a selection contract that S3-05 consumes
- [ ] Interaction renders the same engine output as the ranked table — no recomputation (supports AC4)

---

## S3-04: Ranked Shortlist / Results Panel

**Type:** Story
**Priority:** High
**Story Points:** 3
**Labels:** web-app, results, frontend
**Blocked by:** S3-01b
**Blocks:** S3-05
**Sizing recommendation:** Keep as-is

### Description

Ranked table/list of eligible sites, linked to the map, showing at minimum Site ID, total score/rank and important component values, with row-select to open site detail.

### Acceptance Criteria

- [ ] Ranked table/list uses the same S2-08 engine output as the map (AC8)
- [ ] Each row shows at minimum Site ID, total score, rank and important component values
- [ ] Selecting a row opens site detail (S3-05)
- [ ] Table and map stay in sync
- [ ] Ranking is the deterministic engine ranking — no UI re-sort by recomputed scores
- [ ] Ordering matches the S2-05 rank exactly

---

## S3-05: Site-Detail & Explanation View

**Type:** Story
**Priority:** High
**Story Points:** 5
**Labels:** web-app, explanation, site-detail, frontend
**Blocked by:** S3-03b, S3-04
**Blocks:** S3-07
**Sizing recommendation:** Keep as-is (split only if it slips)

### Description

On site selection, show raw/derived feature values, per-criterion component scores, total score, eligibility and the deterministic S2-06a/S2-06b explanation.

### Acceptance Criteria

- [ ] Shows raw/derived features, component scores, total score and eligibility
- [ ] Explanation identifies main positive factors and important weaknesses (AC7)
- [ ] Proxy variables labelled as proxies; demand proxy never shown as measured local demand (AC7)
- [ ] Relevant data-quality/confidence caveats shown
- [ ] Excluded site shows exclusion reason(s) clearly
- [ ] Content comes from S2-06a/S2-06b/S2-08 — UI generates no explanation text itself
- [ ] Screening-level language, never "best site"

---

## S3-06: Scenario-Comparison UI

**Type:** Story
**Priority:** High
**Story Points:** 3
**Labels:** web-app, scenarios, frontend
**Blocked by:** S3-02, S2-07
**Blocks:** S3-07
**Sizing recommendation:** Keep as-is

### Description

Let the user compare at least two weighting configurations and observe how ranking changes, rendering the S2-07 comparison output.

### Acceptance Criteria

- [ ] User can select/compare at least two weighting scenarios (AC9)
- [ ] Comparison shows how ranking differs (side-by-side ranks or rank delta)
- [ ] Changing weights/preset, rerunning, observing ranking changes is demonstrable
- [ ] Uses S2-07 engine output — no UI-side re-ranking
- [ ] Labelled as weighting/preference scenarios, not uncertainty scenarios
- [ ] At least two useful presets available (e.g. wind-led vs grid-led)

---

## S3-07: Shortlist Export (CSV)

**Type:** Story
**Priority:** Medium *(Should)*
**Story Points:** 2
**Labels:** web-app, export, frontend
**Blocked by:** S3-04
**Blocks:** —
**Sizing recommendation:** Keep as-is (do not over-invest; it is a "Should")

### Description

Allow the user to download the ranked shortlist/results as CSV, reusing the S1-11 Shortlist_CSV schema and disclaimer.

### Acceptance Criteria

- [ ] User can download the ranked shortlist/results as CSV
- [ ] Exported rows match the displayed shortlist exactly
- [ ] Columns include at least rank, Site ID, total score, key components, eligibility
- [ ] Export carries the preliminary-screening disclaimer (consistent with AC12)
- [ ] Export triggers no recomputation

---

## S3-08: Sanity-Check / Validation Visualisation

**Type:** Story
**Priority:** Medium *(Should)*
**Story Points:** 3
**Labels:** web-app, validation, sanity-check
**Blocked by:** S2-09, S3-03a
**Blocks:** S3-09
**Sizing recommendation:** Keep as-is

### Description

Surface a sanity-check comparing top-ranked areas against defensible external references (known NSW wind developments and/or REZ), building on `pipeline/sanity/` (S1-12).

### Acceptance Criteria

- [ ] Top-ranked areas compared against known NSW wind developments and/or REZ (AC10)
- [ ] Presented with caveats — the model is not trained to reproduce those locations
- [ ] Obvious contradictions investigated and documented
- [ ] Result reachable from the app (view, overlay or linked report)
- [ ] Each check reports expected vs observed with an explicit pass/fail
- [ ] Reflects the same engine output as the map/shortlist

---

## S3-09: Docs, Reproducible Run Path & End-to-End Tests

**Type:** Story
**Priority:** High
**Story Points:** 3
**Labels:** documentation, testing, reproducibility
**Blocked by:** S3-05, S3-06
**Blocks:** S3-10
**Sizing recommendation:** Keep as-is (start docs incrementally through the sprint)

### Description

Integration tests for the end-to-end flow, a clean install/run path, and documentation of provenance, assumptions, limitations, scoring equations, exclusions, default weights and architecture — in screening-level language.

### Acceptance Criteria

- [ ] Clean install/run path and technical documentation provided (AC11)
- [ ] Docs record provenance, assumptions, limitations, scoring equations, exclusions, default weights, architecture
- [ ] Integration tests cover the end-to-end flow (frozen dataset → engine → app output)
- [ ] App installs and runs from a clean environment following only the documented steps
- [ ] Screening-level language; important limitations documented; no "best site" claims (AC12)
- [ ] Demand proxy described as a proxy everywhere in docs
- [ ] Tests run in CI

---

## S3-10: Final Demo Preparation & Release Candidate

**Type:** Story
**Priority:** High
**Story Points:** 2
**Labels:** demo, release, documentation
**Blocked by:** S3-09
**Blocks:** —
**Sizing recommendation:** Keep as-is

### Description

Prepare the release candidate and rehearse the end-to-end demonstration for Client Checkpoint D, following the guidance §10 sequence.

### Acceptance Criteria

- [ ] App starts from the documented environment (per S3-09)
- [ ] Demo shows: NSW inputs + default weights → run screening → exclusions + explain one excluded site → ranked shortlist + map → open a high-ranked site and explain its score → change scenario and show how/why ranking changes → validation/sanity result → supporting code/tests/docs
- [ ] Screening-level claims; important limitations documented (AC12)
- [ ] All Must-priority ACs (AC1–AC9, AC11) demonstrably met end-to-end
- [ ] Release candidate tagged; final PR reviewable (not one giant PR)
- [ ] Known gaps / uncompleted Should/Could items listed honestly

---

## Summary — Sprint 3 Dependency Graph

```
S3-01a (Next.js/React + FastAPI shell scaffold)   ◄── blocked by S2-08
  └── S3-01b (Typed HTTP client integration + data-quality banner)
        ├── S3-02 (Controls) ──────────────────────────┐
        ├── S3-03a (Map render) ── S3-03b (Map interaction + filters) ┐
        ├── S3-04 (Shortlist) ──────────────────────────────────────┴── S3-05 (Site detail + explanation) ──┐
        └── S3-06 (Scenario UI, needs S2-07) ──────────────────────────────────────────────────────────────┤
            S3-07 (Export, Should)                                                                           │
            S3-08 (Sanity viz, needs S2-09 + S3-03a) ──┐                                                     │
                                                       └── S3-09 (Docs + e2e) ◄──────────────────────────────┘
                                                              └── S3-10 (Demo + RC)
```

---

## Import Notes

- **Total Story Points:** ~34 across 12 tickets (S3-01 split into S3-01a=3 + S3-01b=2; S3-03 split into S3-03a=3 + S3-03b=2).
- **Critical Path:** S3-01a → S3-01b → (S3-02, S3-03a, S3-04 parallel) → S3-03b → S3-05 → S3-09 → S3-10.
- **Parallelisable:** S3-02, S3-03a and S3-04 once S3-01b is done; S3-06/07/08 slot in as upstreams complete.
- **Broken down:** S3-01 → S3-01a (framework + shell) / S3-01b (service integration + banner); S3-03 → S3-03a (render) / S3-03b (interaction + filters).
- **Must vs Should:** S3-07 and S3-08 are "Should" — complete only after Must-priority tickets are stable.
- **Checkpoint gates:** C after S3-01b/S3-03b/S3-04/S3-05 connected to the backend; D after S3-09/S3-10.
- Merge web integration after the backend, then validation/documentation, per client guidance §6.
