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

- [x] For each of the four criteria (wind, demand proxy, infrastructure, geographic/environmental) the **exact** per-cell feature(s) are named, with source, units and beneficial/adverse direction (satisfies **AC3**)
- [x] Wind uses a named GWA resource variable (e.g. `wind_speed_100m_ms`); the height/variable choice is justified
- [x] Demand feature is explicitly labelled a **spatial demand proxy** allocated below the AEMO region — never "local demand"
- [x] Infrastructure uses measurable indicators (distance to transmission/substation, REZ membership) — no undefined "infrastructure score"
- [x] Geographic/environmental uses agreed measurable non-hard-constraint features (e.g. slope)
- [x] The scoring formula is written out: `S_i = w_W·W_i + w_D·D_i + w_I·I_i + w_G·G_i` with the weight-normalisation rule stated
- [x] Default weights are listed **with a written rationale each** and labelled as documented assumptions (satisfies **AC5**)
- [x] The normalisation method and direction per feature are specified (input to S2-04)
- [x] Outlier and missing-value handling policy is stated
- [x] The document explicitly reconciles any differences from the current `scoring_weights.yaml`
- [x] Screening-level language is used throughout; no "best site" absolute claims

---

## Feature Contract (FROZEN at Checkpoint A)

Frozen in `decision_engine_specification.md` §2. Column names are the real integrated-table
columns verified against `pipeline/integration/merge.py` / `config.py` (spec §2.5, Property P1).

| Criterion | Feature (column) | Units | Source | Direction | Notes |
|-----------|------------------|-------|--------|-----------|-------|
| Wind (W) | `wind_speed` | m/s | GWA v4 (`wind-speed` 100 m layer) | higher_is_better | mean wind speed at 100 m hub height; input Criterion only (not circular) |
| Demand (D) | `demand_proxy` | normalised 0–1 (NEM-region annual mean, MW) | AEMO NEM-region, allocated by `source_region` | higher_is_better | proxy, NOT local demand; NSW1 = NSW + ACT |
| Infrastructure (I) | `dist_transmission_km`, `dist_substation_km`, `inside_rez` | km (EPSG:3577) / bool | Geoscience Australia + EnergyCo REZ | lower_is_better / lower_is_better / higher_is_better | measurable indicators, no aggregate "infrastructure score"; `dist_connection_km` carried but not scored |
| Geographic (G) | `slope_deg` | degrees (Horn slope) | SRTM-derived | lower_is_better | non-hard constraint; complements the S1-07 hard exclusion |

---

## Technical Notes

- The scoring methodology must remain a reusable module, testable independently and reusable by OPT-MINING (guidance §3) — the spec must not describe UI-embedded logic.
- Weights are user inputs, never hard-coded constants — the spec fixes the **defaults** and their rationale, not immutable values.
- Cross-cutting impact: freezing feature names here fixes the input contract for S2-02, S2-04, S2-05, S2-06 and the S2-08 service layer. Renaming a feature later ripples through all of them plus the web app — treat as change-controlled.

---

## Completion Notes

Delivered on branch `checkpoint-a` (commit `docs: finalize decision-engine specification`).

**Approach.** This task *formalises and freezes* the decision design; it writes no pipeline code and adds no runtime stage. The Sprint 1 weighted-MCDA scorer (`pipeline/scoring/`) already exists, so the specification restates and reconciles that design against one agreed, version-controlled contract rather than re-implementing it. Where the spec could have diverged from `pipeline/scoring/scoring_weights.yaml`, the reconciliation log records the actual outcome instead of assuming agreement.

**What was delivered.**

- `Sprint-2-Tasks/decision_engine_specification.md` — the frozen design note (§1–§8), and the Client Checkpoint A (Decision design) artefact. Sign-off date 2026-09-10.
  - §2 — the criteria feature contract: for each of the four criteria groups the exact integrated-table column, units, source and beneficial/adverse direction. Wind is the named GWA `wind-speed` 100 m variable with hub-height/variable justification (frozen decisions Q1/Q2); demand is explicitly a **spatial demand proxy** allocated below the AEMO/NEM region (never "local demand"); infrastructure uses measurable indicators (`dist_transmission_km`, `dist_substation_km`, `inside_rez`) with no aggregate "infrastructure score"; geographic uses `slope_deg` as a non-hard-constraint feature.
  - §2.5 — Property P1 column-name verification: all thirteen referenced columns confirmed present in the integrated schema (`BASE_COLUMNS` / `SCORED_FEATURE_COLUMNS`); no criterion required a name correction.
  - §3 — the scoring formula `S_i = Σ_k w_k·n_k(i) / W_i` written out in full, with the weight-normalisation rule (division by the applied weight sum, scale-invariance, per-cell missing-value denominator), the eligible-only / null-for-excluded rule, and the not-circular guarantee.
  - §4 — the six default weights (wind 0.35, transmission 0.20, demand 0.15, substation 0.10, slope 0.10, REZ 0.10) listed with a written rationale each and labelled as **documented assumptions, not objectively correct business values** (Property P3 confirms every weight carries a rationale).
  - §5 — the normalisation method (directional linear min-max, bounds from the eligible population fixed per run), and the explicit outlier and missing-value policies (input to S2-04).
  - §6 — frozen decisions (F1–F15) and change control tied to the data-specification §8 process.
  - §8 — the reconciliation log against `scoring_weights.yaml`: every scored criterion (feature, weight, direction, rationale) and every non-criterion parameter reconciled as **`consistent`** — no frozen value diverged, so task 8.2 propagation was a documented no-op.
- Screening-level language is used throughout (§1.4); the document makes no "best site" / "optimal" absolute claims.
- Cross-references wired (§1.5): `pipeline/README.md` and the data-specification (§4.7, with a §4.5 pointer) both point to this spec as the authoritative decision-engine design.

**Checkpoint A / Jira.** Recorded in §1.3 — epic KAN-35, issue [KAN-37](https://optmining.atlassian.net/browse/KAN-37) (S2-01), related [KAN-38](https://optmining.atlassian.net/browse/KAN-38) (S2-02). Checkpoint A sign-off date 2026-09-10.

**Frozen decisions.** This document *creates* the frozen decision baseline (F1–F15) for the decision engine. No pre-existing frozen parameter was changed — the spec restates a design already realised in code — so no data-spec §8 change-control process was triggered; any later change to a frozen parameter must follow §6 / data-spec §8.
