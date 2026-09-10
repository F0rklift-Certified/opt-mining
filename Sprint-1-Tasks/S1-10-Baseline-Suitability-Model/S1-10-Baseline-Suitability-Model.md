# S1-10: Add a Simple Baseline Suitability Model

**Type:** Story  
**Priority:** Medium  
**Story Points:** 5  
**Labels:** scoring, model  
**Blocked by:** S1-08, S1-09  
**Blocks:** S1-11

---

## Objective

Implement a transparent, deterministic baseline suitability scoring model. This is NOT a machine-learning black box — it is a weighted multi-criteria scoring function that the user can fully interrogate and understand.

---

## Context

The integrated feature table (S1-08) contains all the information needed to compare cells. This task defines HOW cells are compared — the scoring formula.

The Constitution states:
- "Criteria weights are user inputs, never hard-coded constants"
- "The platform augments planner judgement"
- "A recommendation the user cannot interrogate is not a recommendation — it is an assertion"
- "Never build a circular model" — the wind data is an input feature, not a prediction target

The baseline model should be simple enough that anyone can understand why one cell scored higher than another.

---

## Deliverables

1. Scoring module at `pipeline/scoring/`
2. Default weights configuration with documented rationale
3. Scored output table with per-cell scores and per-criterion contributions

---

## Acceptance Criteria

- [x] Scoring module (`pipeline/scoring/`) takes the integrated feature table as input
- [x] Criteria weights are **configurable inputs** (loaded from config file, not hard-coded)
- [x] Default weights are documented with rationale for each
- [x] Scoring formula is documented, deterministic, and reproducible
- [x] Only **eligible** cells (from exclusion layer) receive a score; excluded cells get `score = NULL`
- [x] Score is normalised to [0, 1] range
- [x] Output: `cell_id | suitability_score | rank | confidence`
- [x] **Explainability:** for any cell, the contribution of each criterion to its final score is retrievable (per-criterion sub-scores)
- [x] Model does NOT use wind data to predict wind data (no circular modelling)
- [x] Unit tests verify scoring logic with known inputs/outputs

---

## Scoring Approach (Suggested Baseline)

### Step 1: Normalise each feature to [0, 1]

For "higher is better" features (e.g. wind speed):
```
normalised = (value - min) / (max - min)
```

For "lower is better" features (e.g. distance to transmission):
```
normalised = 1 - (value - min) / (max - min)
```

### Step 2: Apply weights

```
score = Σ (weight_i × normalised_feature_i) / Σ weight_i
```

### Step 3: Apply confidence discount (optional)

```
adjusted_score = score × confidence_factor
```

---

## Default Weights Config Example

```yaml
# scoring_weights.yaml
criteria:
  wind_speed:
    weight: 0.35
    direction: higher_is_better
    rationale: "Primary resource indicator — drives energy yield"
    
  dist_transmission_km:
    weight: 0.20
    direction: lower_is_better
    rationale: "Connection cost is a major capex component"
    
  dist_substation_km:
    weight: 0.10
    direction: lower_is_better
    rationale: "Substation proximity reduces connection complexity"
    
  demand_proxy:
    weight: 0.15
    direction: higher_is_better
    rationale: "Proximity to demand reduces transmission losses"
    
  slope_deg:
    weight: 0.10
    direction: lower_is_better
    rationale: "Flatter terrain reduces construction cost"
    
  inside_rez:
    weight: 0.10
    direction: higher_is_better
    rationale: "REZ locations have coordinated infrastructure planning"
```

---

## Example Output

| cell_id | suitability_score | rank | wind_contrib | transmission_contrib | demand_contrib | slope_contrib | rez_contrib | confidence |
|---------|-------------------|------|--------------|---------------------|----------------|---------------|-------------|------------|
| NSW001  | 0.87              | 1    | 0.31         | 0.18                | 0.14           | 0.09          | 0.10        | high       |
| NSW002  | 0.84              | 2    | 0.33         | 0.12                | 0.11           | 0.08          | 0.10        | high       |
| NSW003  | 0.81              | 3    | 0.35         | 0.16                | 0.09           | 0.07          | 0.10        | high       |

---

## Technical Notes

- This is a Multi-Criteria Decision Analysis (MCDA) approach — well-established in spatial planning
- Normalisation bounds (min/max) should be computed from the eligible cell population, not hard-coded
- Consider whether to use linear normalisation or a different function (e.g. logarithmic for distances)
- The scoring module should be independent of data loading — it receives a DataFrame and returns a scored DataFrame
- Per the Constitution: "Each component should be independently replaceable without requiring changes to adjacent layers"
