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

- [x] Each feature is normalised to a comparable [0, 1] component with a documented direction (higher-is-better vs lower-is-better) (satisfies **AC3**)
- [x] Normalisation and scoring are implemented **outside the UI** and covered by tests (satisfies **AC4**)
- [x] Normalisation bounds are computed from the **eligible population**, documented and **reproducible** — they must not change simply because a user filters the map (bounds are fixed per analysis run, not per UI filter)
- [x] Outliers are handled explicitly with a documented method
- [x] Missing values are handled explicitly (never silently imputed to a default that biases the score)
- [x] A constant feature over the eligible population is handled without divide-by-zero and flagged
- [x] Boolean features use their definitional {False→0, True→1} domain
- [x] Unit tests cover higher/lower direction, min/max boundaries, missing values, outliers and the constant-feature case

---

## Technical Notes

- Refactor/expose `pipeline/scoring/normalise.py` rather than writing a second normaliser — a divergent second implementation is the exact cross-component inconsistency the project rules forbid.
- The "bounds fixed per run, not per UI filter" requirement is the critical correctness constraint: the web app (S3-02/S3-03) filters the *display*, never the normalisation population.

---

## Completion Notes

Delivered on branch `s2-04` (commit `feat: expose feature normalisation as a standalone tested component`).

**Approach.** The existing directional min-max normaliser in `pipeline/scoring/normalise.py` was *surfaced* as a standalone, decoupled component rather than reimplemented — a divergent second normaliser is exactly what the project rules and this task's Technical Notes forbid. The scoring stage now runs the same code as the standalone surface.

**What was built.**

- `pipeline/scoring/normalise.py`
  - `NormSpec(feature, direction)` — the decoupled per-feature contract (validates direction at construction).
  - `SpecLike` — a structural `Protocol` (`feature`, `direction`) that both `NormSpec` and the scoring `Criterion` satisfy, so the normalisation path no longer imports the weights/`Criterion` types.
  - `normalise_frame(df, specs, *, bounds=None)` — the standalone entry point: DataFrame in, normalised DataFrame out (one `norm_{feature}` column per spec), callable independently of scoring and of data loading.
- `pipeline/scoring/score.py` — `normalised_frame` now delegates to `normalise_frame` (single source of truth).
- `pipeline/scoring/README.md` (new) — documented method, the six-feature direction table, and the outlier / missing-value / constant / boolean policy, cross-referencing decision-engine spec §5 as the frozen authoritative source.
- `tests/scoring/test_normalise_standalone.py` (new) — 26 unit tests covering the standalone API and boundary/degenerate cases (min/max endpoints, saturation clamp, nulls, constant, all-null, boolean domain incl. all-`False` and `lower_is_better` inversion, scalar formula, and `normalised_frame == normalise_frame`).
- `tests/scoring/test_scoring_documentation.py` — added a consistency test that the README direction table matches the shipped `scoring_weights.yaml`.

**Verification.** `tests/scoring` 149 passed; full suite 882 passed, 5 skipped, 0 failures.

**Frozen decisions.** No frozen parameter was changed — `pipeline/scoring/scoring_weights.yaml` and the decision-engine specification §5 are untouched — so no data-spec §8 change-control process was triggered. This is a refactor/exposure of behaviour already frozen at Checkpoint A.
