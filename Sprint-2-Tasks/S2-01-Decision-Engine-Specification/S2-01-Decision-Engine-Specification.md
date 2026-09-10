# S2-01: Decision-Engine Specification & Frozen Configuration

**Type:** Task
**Priority:** Highest
**Story Points:** 3
**Labels:** decision-engine, documentation, data-governance
**Blocked by:** —
**Blocks:** S2-02, S2-04, S2-05, S2-06

---

## Objective

Before further coding, produce a single authoritative decision-engine specification that fixes the exact per-cell features, their directions, the normalisation method, the scoring formula, and the default weighting configuration. This is the document reviewed at **Client Checkpoint A (Decision design)**.

---

## Context

The guidance (Step 3) warns against vague variables such as "infrastructure score" with no explanation of how they are calculated, and requires that scoring defaults be documented as *assumptions*, not presented as objectively correct business values.

Sprint 1 already implemented a working weighted-MCDA scorer (`pipeline/scoring/`) with weights in `pipeline/scoring/scoring_weights.yaml`. This task does **not** re-implement it — it *formalises and freezes* the design so every downstream task (normalisation, scoring, explanation) and the web app build against one agreed contract. Where the spec and the current code disagree, this document is the place to reconcile them.

Per the project's frozen-decision convention, any parameter frozen here must follow the data-specification §8 change-control process if later changed.

---

## Deliverables

1. `Sprint-2-Tasks/decision_engine_specification.md` — the frozen design note.
2. A confirmed default weights configuration (reconciled with `pipeline/scoring/scoring_weights.yaml`).
3. Checkpoint-A design note with Jira/PR references.

---

## Acceptance Criteria

- [ ] For each of the four criteria (wind, demand proxy, infrastructure, geographic/environmental) the **exact** per-cell feature(s) are named, with source, units and beneficial/adverse direction (satisfies **AC3**)
- [ ] Wind uses a named GWA resource variable (e.g. `wind_speed_100m_ms`); the height/variable choice is justified
- [ ] Demand feature is explicitly labelled a **spatial demand proxy** allocated below the AEMO region — never "local demand"
- [ ] Infrastructure uses measurable indicators (distance to transmission/substation, REZ membership) — no undefined "infrastructure score"
- [ ] Geographic/environmental uses agreed measurable non-hard-constraint features (e.g. slope)
- [ ] The scoring formula is written out: `S_i = w_W·W_i + w_D·D_i + w_I·I_i + w_G·G_i` with the weight-normalisation rule stated
- [ ] Default weights are listed **with a written rationale each** and labelled as documented assumptions (satisfies **AC5**)
- [ ] The normalisation method and direction per feature are specified (input to S2-04)
- [ ] Outlier and missing-value handling policy is stated
- [ ] The document explicitly reconciles any differences from the current `scoring_weights.yaml`
- [ ] Screening-level language is used throughout; no "best site" absolute claims

---

## Feature Contract (fill in and freeze)

| Criterion | Feature (column) | Units | Source | Direction | Notes |
|-----------|------------------|-------|--------|-----------|-------|
| Wind (W) | `wind_speed_100m_ms` | m/s | GWA v4 | higher_is_better | |
| Demand (D) | `demand_proxy` | proxy index | AEMO-allocated | higher_is_better | proxy, NOT local demand |
| Infrastructure (I) | `dist_transmission_km`, `dist_substation_km`, `inside_rez` | km / bool | GA | lower_is_better / higher_is_better | |
| Geographic (G) | `slope_deg` | degrees | SRTM-derived | lower_is_better | non-hard constraint |

---

## Technical Notes

- The scoring methodology must remain a reusable module, testable independently and reusable by OPT-MINING (guidance §3) — the spec must not describe UI-embedded logic.
- Weights are user inputs, never hard-coded constants — the spec fixes the **defaults** and their rationale, not immutable values.
- Cross-cutting impact: freezing feature names here fixes the input contract for S2-02, S2-04, S2-05, S2-06 and the S2-08 service layer. Renaming a feature later ripples through all of them plus the web app — treat as change-controlled.
