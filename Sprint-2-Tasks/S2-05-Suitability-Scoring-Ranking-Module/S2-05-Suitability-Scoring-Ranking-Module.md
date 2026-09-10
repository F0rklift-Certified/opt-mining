# S2-05: Suitability Scoring & Ranking Module (Configurable Weights, Tested)

**Type:** Story
**Priority:** High
**Story Points:** 5
**Labels:** scoring, ranking, decision-engine
**Blocked by:** S2-04
**Blocks:** S2-06, S2-07

---

## Objective

Deliver the transparent weighted multi-criteria baseline engine that scores and ranks every eligible cell, with configurable weights, deterministic output, and per-criterion contributions retained for explanation.

---

## Context

Guidance Steps 5 and 6. Sprint 1's `pipeline/scoring/` already implements the pure weighted-MCDA function (`score.py`), ranking (`rank.py`), a weights loader/validator (`weights.py`) and `contrib_{feature}` explainability columns. This task confirms it satisfies the combined-sprint acceptance criteria, closes any gaps against the frozen S2-01 spec, and raises test coverage. It is primarily hardening + verification, not green-field build.

---

## Deliverables

1. Confirmed scoring + ranking module: `S_i = w_W·W_i + w_D·D_i + w_I·I_i + w_G·G_i`.
2. Configurable weights with enforced/auto-normalised interpretation.
3. Per-cell component scores, total score, deterministic rank and per-criterion contributions.

---

## Acceptance Criteria

- [ ] The engine implements the documented weighted-MCDA formula from S2-01 (satisfies **AC6**)
- [ ] Weights are **configurable inputs** loaded at runtime, not hard-coded; defaults documented (satisfies **AC5**)
- [ ] Weights are enforced or auto-normalised so their interpretation is unambiguous (e.g. sum to 1)
- [ ] Only **eligible** cells are scored; excluded cells receive null score/rank/contributions and take no part in normalisation bounds or ranking
- [ ] Every eligible cell has component scores, total score and a **deterministic** rank (ties broken by a documented, stable rule)
- [ ] Per-criterion contributions are retained and verified to sum back to the total score on every run (satisfies **AC7** upstream data)
- [ ] The scoring computation is **pure** (DataFrame + weights in, scored DataFrame out; no file I/O) so it is independently testable and swappable
- [ ] The model does not use wind data to predict wind data (no circular modelling)
- [ ] Scoring is implemented **outside the UI** and covered by tests (satisfies **AC4**)
- [ ] Unit tests verify scoring with known inputs/outputs, weight re-normalisation, tie-breaking and the eligible-only rule

---

## Technical Notes

- Build on `pipeline/scoring/score.py` / `rank.py` / `weights.py`. The README already documents the exact formula and the eligible-only, contributions-sum-to-score guarantees — verify against them.
- Cross-cutting impact: this is the single source of scores. The map (S3-03) and shortlist (S3-04) must render *this* output — the UI must never recompute scores (AC4). The scenario engine (S2-07) calls this module with alternate weights.
- Keep the score/rank/contribution schema stable; it is the contract for S2-06, S2-07 and the S2-08 service layer.
