# Task 10 — Add a Simple Baseline Suitability Model

**Sprint:** 1 (Week 2)
**Assignee:** TBD
**Status:** Not Started
**Estimated Effort:** 1 day

---

## 1. Objective

A transparent weighted-sum suitability score over eligible cells — simple enough to explain in one sentence, parameterised enough that weights are always user inputs.

## 2. Context & Frozen Decisions

- Constitution: **"Criteria weights are user inputs, never hard-coded constants."** Defaults exist but are explicitly labelled a default scenario.
- **Q1/Q3**: the scoring inputs are the frozen default statistics — `wind_speed_100m_mean` and `slope_mean_deg` (p90 variants remain available as alternative inputs via config, satisfying "report multiple, let user choose").
- **Q7**: infrastructure distances enter as continuous penalties (inverted), no cliff.
- Scoring reads exclusion output only through the `eligible` flag — no exclusion logic may be re-implemented or overridden here (Task 7 boundary).

## 3. Scope

**In:**
- `pipeline/score/` package: weight handling + scoring stage
- Normalisation method decision (documented below)

**Out:**
- Shortlist + query CLI (Task 11)
- Any ML/statistical fitting — this is a baseline linear model by design
- Scenario management UI (JSON files are the interface)

## 4. Inputs

- Integrated table with quality flags (Tasks 8, 9)

## 5. Implementation Plan

- [ ] Create `pipeline/score/config.py`:
  - `DEFAULT_CRITERIA`: `wind_speed_100m_mean` (benefit), `demand_local_proxy_mw` (benefit), `dist_transmission_km` (cost → inverted), `dist_substation_km` (cost → inverted), `slope_mean_deg` (cost → inverted).
  - `DEFAULT_WEIGHTS` (e.g. wind 0.40, demand 0.20, transmission 0.20, substation 0.10, slope 0.10) with the mandatory label in the docstring: *"Default scenario — user-overridable, never authoritative. Weights are user inputs (Constitution §Architectural Rules)."*
  - **Normalisation decision (documented here):** min–max over **eligible cells only**, cost criteria as `1 − norm`. Rationale: transparent, explainable, adequate for a baseline. Known limitation recorded: sensitive to outliers; percentile-rank and p1/p99-clipped min-max noted as future `normalisation` parameter values, not implemented now.
- [ ] Create `pipeline/score/weights.py`: load/validate a weights JSON (`{"wind": 0.4, ...}`) and/or repeatable `--weight name=value` overrides; enforce Σw = 1 (normalise with WARN if within 1%, fail otherwise); unknown criterion names fail loudly.
- [ ] Create `pipeline/score/model.py` with `run(area_name="nsw", weights_path=None, weight_overrides=None, top_n=50, verbose=False) -> dict`:
  1. Filter to eligible cells; normalise each criterion; invert costs; `score = Σ wᵢ·normᵢ` → [0, 1].
  2. Ineligible cells get `score = null` (never 0 — an excluded cell has no score, not a bad one).
  3. Append `score` into the integrated CSV; write `scoring_run.meta.json` recording the weights actually used, normalisation method, criteria min/max, timestamp, input hash.
- [ ] Register stage `score.rank` (flags `--weights`, `--weight` repeatable, `--top-n` passed through to Task 11's shortlist writer).

## 6. Outputs

| Output | Path |
|---|---|
| `score` column | appended into `DATA/integrated/optmining_site-screening_0.05deg_nsw.csv` |
| Run record | `DATA/integrated/scoring_run.meta.json` |

## 7. Configuration Parameters

| Parameter | Default | CLI flag | Meaning |
|---|---|---|---|
| `weights_path` | None (defaults used) | `--weights` | JSON scenario file |
| `weight_overrides` | None | `--weight name=value` (repeatable) | ad-hoc overrides |
| `top_n` | 50 | `--top-n` | shortlist size (consumed by Task 11) |

## 8. Acceptance Criteria

- [ ] All eligible scores ∈ [0, 1]; all ineligible cells have null score.
- [ ] Monotonicity: increasing a benefit criterion (or decreasing a cost criterion) for one cell, ceteris paribus, never lowers its score (property test).
- [ ] `--weight wind=0.8` demonstrably reorders the top ranks vs defaults (test asserts ordering change).
- [ ] Weights failing Σ=1 by >1% are rejected with a clear message.
- [ ] `scoring_run.meta.json` fully reproduces the run (weights, normalisation, input hash).

## 9. Tests

`tests/test_score_unit.py`: normalisation bounds on synthetic frames; cost inversion; monotonicity property; weight validation (sum, unknown names); null-score-for-excluded invariant.

## 10. Risks & Mitigations

- **Min–max outlier sensitivity** (one extreme cell compresses everyone else): criteria min/max recorded in the run meta so distortion is visible; clipped variant pre-specified as the follow-up.
- **Weight bikeshedding**: defaults are a placeholder scenario; Task 12's sensitivity check shows how much they matter before anyone argues about them.

## 11. Dependencies

**Blocked by:** Tasks 8, 9.
**Blocks:** Tasks 11, 12.

## 12. Decision Log

| Date | Decision / Surprise | Rationale |
|---|---|---|
