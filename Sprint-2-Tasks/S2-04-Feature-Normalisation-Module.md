# S2-04: Feature Normalisation Module (Standalone, Tested)

**Type:** Story
**Priority:** High
**Story Points:** 3
**Labels:** normalisation, decision-engine
**Blocked by:** S2-01, S2-02
**Blocks:** S2-05

---

## Objective

Provide a documented, tested, standalone normalisation component that converts features on different scales into comparable [0, 1] suitability components, with an explicit direction per feature and explicit outlier/missing-value handling.

---

## Context

Guidance Step 4. Normalisation already exists inside `pipeline/scoring/normalise.py` (directional min-max, bounds from the eligible population). This task **surfaces it as an independently testable component** with a documented method and a defined policy for outliers and missing values, and guarantees the parameters do not change unpredictably when a user filters the map.

---

## Deliverables

1. A normalisation module callable independently of scoring and of data loading (DataFrame in, normalised DataFrame out).
2. Documented method, direction table and outlier/missing-value policy.
3. Unit tests including boundary and degenerate cases.

---

## Acceptance Criteria

- [ ] Each feature is normalised to a comparable [0, 1] component with a documented direction (higher-is-better vs lower-is-better) (satisfies **AC3**)
- [ ] Normalisation and scoring are implemented **outside the UI** and covered by tests (satisfies **AC4**)
- [ ] Normalisation bounds are computed from the **eligible population**, documented and **reproducible** — they must not change simply because a user filters the map (bounds are fixed per analysis run, not per UI filter)
- [ ] Outliers are handled explicitly with a documented method
- [ ] Missing values are handled explicitly (never silently imputed to a default that biases the score)
- [ ] A constant feature over the eligible population is handled without divide-by-zero and flagged
- [ ] Boolean features use their definitional {False→0, True→1} domain
- [ ] Unit tests cover higher/lower direction, min/max boundaries, missing values, outliers and the constant-feature case

---

## Technical Notes

- Refactor/expose `pipeline/scoring/normalise.py` rather than writing a second normaliser — a divergent second implementation is the exact cross-component inconsistency the project rules forbid.
- The "bounds fixed per run, not per UI filter" requirement is the critical correctness constraint: the web app (S3-02/S3-03) filters the *display*, never the normalisation population.
