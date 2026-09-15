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

- [x] The engine implements the documented weighted-MCDA formula from S2-01 (satisfies **AC6**)
- [x] Weights are **configurable inputs** loaded at runtime, not hard-coded; defaults documented (satisfies **AC5**)
- [x] Weights are enforced or auto-normalised so their interpretation is unambiguous (e.g. sum to 1)
- [x] Only **eligible** cells are scored; excluded cells receive null score/rank/contributions and take no part in normalisation bounds or ranking
- [x] Every eligible cell has component scores, total score and a **deterministic** rank (ties broken by a documented, stable rule)
- [x] Per-criterion contributions are retained and verified to sum back to the total score on every run (satisfies **AC7** upstream data)
- [x] The scoring computation is **pure** (DataFrame + weights in, scored DataFrame out; no file I/O) so it is independently testable and swappable
- [x] The model does not use wind data to predict wind data (no circular modelling)
- [x] Scoring is implemented **outside the UI** and covered by tests (satisfies **AC4**)
- [x] Unit tests verify scoring with known inputs/outputs, weight re-normalisation, tie-breaking and the eligible-only rule

---

## Technical Notes

- Build on `pipeline/scoring/score.py` / `rank.py` / `weights.py`. The README already documents the exact formula and the eligible-only, contributions-sum-to-score guarantees — verify against them.
- Cross-cutting impact: this is the single source of scores. The map (S3-03) and shortlist (S3-04) must render *this* output — the UI must never recompute scores (AC4). The scenario engine (S2-07) calls this module with alternate weights.
- Keep the score/rank/contribution schema stable; it is the contract for S2-06, S2-07 and the S2-08 service layer.

---

## Status

**COMPLETE.** The full S2-05 spec (`.kiro/specs/s2-05-suitability-scoring-ranking/`, all 12 task groups) has been executed.

This was a verify-and-conform effort over the existing `pipeline/scoring/` module. The scoring engine (`score.py` / `rank.py` / `weights.py` / `normalise.py` / `validate.py` / `run.py`) was verified to conform to the frozen S2-01 Decision_Engine_Spec — **no divergence found, no conforming code changes needed.**

Work added:

- **Property tests** in `tests/scoring/test_scoring_properties.py`: Property 1 (scores bounded), Property 2 (contributions reconstruct score), Property 3 (eligible-only), Property 4 (deterministic scoring + deterministic ranking with tie-break), Property 5 (weights are data, not code).
- **Controlled hand-computed ranking fixture** at `tests/scoring/test_controlled_ranking.py` — the key safeguard against a subtly wrong formula.
- **Strengthened seeded-bad-table validation test** to assert the specific rank-contiguity check.

**Client Checkpoint B passed:** end-to-end run on the real 47,311-cell NSW integrated table scored 1,233 eligible cells (score range [0.2180, 0.9324]); 9/9 no-silent-passes validation checks passed; full scoring test suite 163 passed.

The `score` / `rank` / `contrib_{feature}` schema is stable and is the contract for S2-06, S2-07, and S2-08.
