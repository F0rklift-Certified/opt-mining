# Requirements Document

## Introduction

This feature delivers Sprint 2 task S2-01 ("Decision-Engine Specification & Frozen Configuration") for the Opt-Mining renewable-energy site-screening platform. Its sole deliverable is an **authoritative, version-controlled specification document** that fixes the exact per-cell features, their beneficial/adverse directions, the normalisation method, the scoring formula, and the default weighting configuration used by the decision engine. It is the artefact reviewed and signed off at **Client Checkpoint A (Decision design)**.

This is a **documentation and governance** feature, not a code feature. It writes no pipeline code and adds no runtime stage. What it produces is the frozen contract that every downstream Sprint 2 task (S2-04 normalisation, S2-05 scoring/ranking, S2-06 explanation) and the whole Sprint 3 web application build against. Where the specification and the existing Sprint 1 implementation (`pipeline/scoring/`, `pipeline/scoring/scoring_weights.yaml`) disagree, this document is the place the disagreement is reconciled and recorded.

The combined Sprint 2/3 client guidance (Step 3) is explicit: vague variables such as an unexplained "infrastructure score" are not acceptable, and scoring defaults must be documented as **assumptions**, not presented as objectively correct business values. The Opt-Mining constitution reinforces this: criteria weights are user inputs, and a recommendation the user cannot interrogate is an assertion rather than a recommendation. Accordingly this specification names measurable features, states directions and units, writes the scoring formula out in full, and records a written rationale for every default weight.

Because several parameters fixed here are **frozen decisions**, any later change to a frozen parameter must follow the data-specification section 8 change-control process and be reflected in every place the parameter is recorded (this specification, `pipeline/scoring/scoring_weights.yaml`, and the data specification). This document specifies **requirements only**. Design and tasks are out of scope here.

## Glossary

- **Decision_Engine_Spec**: The single authoritative specification document produced by this feature, stored at `Sprint-2-Tasks/decision_engine_specification.md` and referenced from the pipeline README and the data specification. It is the Checkpoint-A artefact.
- **Criterion**: A single named, measurable per-cell feature that participates in the suitability score, together with its source, units, beneficial/adverse direction, and default weight.
- **Criteria_Group**: One of the four client-defined decision dimensions — wind, demand proxy, infrastructure, geographic/environmental — each realised by one or more Criteria.
- **Direction**: The monotonic relationship between a Criterion's raw value and suitability, recorded as exactly `higher_is_better` or `lower_is_better`.
- **Demand_Proxy**: The spatial demand feature, explicitly a proxy allocated below the AEMO region, never described as measured local demand.
- **Scoring_Formula**: The transparent weighted multi-criteria expression `S_i = w_W·W_i + w_D·D_i + w_I·I_i + w_G·G_i` (generalised to the configured Criteria), together with the weight-normalisation rule.
- **Default_Weights**: The shipped default weight, direction, and rationale for every Criterion, labelled as documented assumptions.
- **Normalisation_Method**: The documented rule (linear min-max, directional) converting each Criterion's raw values to a comparable `[0, 1]` suitability component, together with the outlier and missing-value policy.
- **Existing_Implementation**: The Sprint 1 scoring code (`pipeline/scoring/`) and its shipped weights file (`pipeline/scoring/scoring_weights.yaml`) that this specification reconciles against.
- **Frozen_Decision**: A parameter fixed by this specification whose later change requires the data-specification section 8 change-control process and consistent update everywhere it is recorded.
- **Data_Specification**: The authoritative dataset specification at `DATA/data-specification/sprint1_data_specification.md`, whose section 4 details datasets and whose section 8 defines change control.
- **Screening_Language**: Preliminary-screening phrasing (for example "higher-ranked candidate under the selected assumptions and criteria") used in place of absolute claims such as "best site".

## Requirements

### Requirement 1: A single authoritative specification document

**User Story:** As the client reviewing at Checkpoint A, I want one authoritative decision-engine specification, so that the whole team builds against a single agreed design rather than scattered assumptions.

#### Acceptance Criteria

1. THE Decision_Engine_Spec SHALL exist as a single version-controlled document at a documented path within the repository.
2. THE Decision_Engine_Spec SHALL be referenced from the pipeline README and the Data_Specification so that it is discoverable as the authoritative decision design.
3. THE Decision_Engine_Spec SHALL identify itself as the Client Checkpoint A design artefact and record the Jira/PR references associated with its review.
4. THE Decision_Engine_Spec SHALL use Screening_Language throughout and SHALL NOT present the model output using absolute claims such as "best site".

### Requirement 2: Exact per-cell features for each criteria group

**User Story:** As a scoring-model developer, I want the exact feature columns named for each of the four criteria groups, so that there is no ambiguity about what the engine consumes.

#### Acceptance Criteria

1. THE Decision_Engine_Spec SHALL define, for each of the four Criteria_Groups (wind, demand proxy, infrastructure, geographic/environmental), the exact per-cell feature column name(s) used by the decision engine.
2. THE Decision_Engine_Spec SHALL record, for every Criterion, its source, its units, and its beneficial/adverse Direction.
3. THE Decision_Engine_Spec SHALL specify the wind Criterion as a named Global Wind Atlas resource variable and SHALL record a justification for the chosen hub height and variable.
4. THE Decision_Engine_Spec SHALL label the demand Criterion explicitly as a Demand_Proxy allocated below the AEMO region and SHALL NOT describe it as measured local demand.
5. THE Decision_Engine_Spec SHALL specify the infrastructure Criteria as measurable indicators such as distance to transmission, distance to substation, and REZ membership, and SHALL NOT use an undefined aggregate such as "infrastructure score".
6. THE Decision_Engine_Spec SHALL specify the geographic/environmental Criteria as agreed measurable non-hard-constraint features such as slope.
7. WHERE a named Criterion feature does not exactly match a column present in the integrated feature table, THE Decision_Engine_Spec SHALL correct the Criterion name to match the real integrated-table column.

### Requirement 3: The scoring formula stated in full

**User Story:** As a reviewer, I want the scoring formula written out with its weight-normalisation rule, so that the ranking is transparent and reproducible.

#### Acceptance Criteria

1. THE Decision_Engine_Spec SHALL state the Scoring_Formula in full as a weighted sum over the configured Criteria.
2. THE Decision_Engine_Spec SHALL state the weight-normalisation rule (for example division by the sum of the applied weights) so that the interpretation of the weights is unambiguous.
3. THE Decision_Engine_Spec SHALL state that only eligible cells receive a score and that excluded cells receive a null score, consistent with the hard-exclusion component.
4. THE Decision_Engine_Spec SHALL state that the model is not circular — the wind feature is an input Criterion only and never a prediction target.

### Requirement 4: Default weights documented as assumptions with rationale

**User Story:** As a reviewer, I want each default weight to carry a written rationale and to be labelled an assumption, so that I can understand and challenge the baseline without mistaking it for a business truth.

#### Acceptance Criteria

1. THE Decision_Engine_Spec SHALL list the Default_Weights, giving each Criterion a weight, a Direction, and a non-empty written rationale.
2. THE Decision_Engine_Spec SHALL label the Default_Weights as documented assumptions rather than objectively correct business values.
3. THE Decision_Engine_Spec SHALL reconcile the Default_Weights against the Existing_Implementation weights file and SHALL record any differences and the resolution of each difference.
4. WHERE the Decision_Engine_Spec and the Existing_Implementation are consistent, THE Decision_Engine_Spec SHALL state that consistency explicitly so the reader knows no divergence remains.

### Requirement 5: Normalisation method and outlier/missing-value policy

**User Story:** As a scoring-model developer, I want the normalisation method and the outlier/missing-value policy fixed, so that the engine converts features on different scales into comparable components reproducibly.

#### Acceptance Criteria

1. THE Decision_Engine_Spec SHALL specify the Normalisation_Method and the Direction for each Criterion.
2. THE Decision_Engine_Spec SHALL state that normalisation bounds are computed from the eligible cell population and are fixed per analysis run rather than changing when a user filters a display.
3. THE Decision_Engine_Spec SHALL state the outlier-handling policy.
4. THE Decision_Engine_Spec SHALL state the missing-value policy, and SHALL require that missing values are never silently imputed to a default that biases the score.
5. THE Decision_Engine_Spec SHALL state the rule for a Criterion that is constant over the eligible population, so that no divide-by-zero occurs.
6. WHERE a Criterion is a boolean feature, THE Decision_Engine_Spec SHALL state its definitional mapping to the `[0, 1]` range consistent with its Direction.

### Requirement 6: Frozen-decision governance

**User Story:** As a data-governance reviewer, I want the parameters this specification freezes to be governed by change control, so that they cannot drift silently across the codebase.

#### Acceptance Criteria

1. THE Decision_Engine_Spec SHALL identify which of its parameters are Frozen_Decisions.
2. THE Decision_Engine_Spec SHALL state that any change to a Frozen_Decision requires the Data_Specification section 8 change-control process.
3. THE Decision_Engine_Spec SHALL enumerate every location a Frozen_Decision is recorded (this specification, the Existing_Implementation weights file, and the Data_Specification) so that a change can be applied consistently in all of them.
4. IF a Frozen_Decision is changed, THEN THE change SHALL be reflected in every enumerated location, so that no location records a stale value.

### Requirement 7: Traceability to acceptance criteria

**User Story:** As the client, I want the specification traceable to the combined-sprint acceptance criteria, so that I can confirm the design satisfies AC3 and AC5.

#### Acceptance Criteria

1. THE Decision_Engine_Spec SHALL map each defined Criterion to combined-sprint acceptance criterion AC3 (documented definition, unit/source, direction).
2. THE Decision_Engine_Spec SHALL map the Default_Weights and the weight-normalisation rule to combined-sprint acceptance criterion AC5 (weights configurable, interpretation/defaults documented).
3. THE Decision_Engine_Spec SHALL record the four Criteria_Groups against the guidance Step 3 requirement so that every criteria group is demonstrably covered.
