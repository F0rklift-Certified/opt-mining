# Decision-Engine Specification & Frozen Configuration

> **Status:** Draft — authored under spec `s2-01-decision-engine-specification`.
> Sections §2–§8 are scaffolded placeholders authored in later tasks of this spec.

---

## §1 Purpose & Checkpoint-A status

### 1.1 Purpose — the single authoritative decision design

This document is the **single authoritative decision-engine specification** for the
Opt-Mining renewable-energy site-**screening** platform. It fixes, in one
version-controlled place, the exact per-cell features (Criteria), their
beneficial/adverse Directions, the Normalisation_Method, the Scoring_Formula, and the
Default_Weights used by the decision engine.

Every downstream Sprint 2 task (S2-04 normalisation, S2-05 scoring/ranking, S2-06
explanation) and the whole Sprint 3 web application build against the frozen contract
recorded here. Where this specification and the existing Sprint 1 implementation
(`pipeline/scoring/`, `pipeline/scoring/scoring_weights.yaml`) disagree, **this document
is the place the disagreement is reconciled and recorded** (see §8).

This document specifies the decision design only. It writes no pipeline code and adds no
runtime stage.

### 1.2 Client Checkpoint A artefact

This document **is the Client Checkpoint A (Decision design) artefact**. It is the
specification reviewed and signed off at Checkpoint A. Checkpoint A is a client sign-off
gate, not a code merge: §1–§8 must be complete and the two documentation-consistency
checks (P1 column-name, P2 reconciliation completeness) must pass before it is presented
for client sign-off.

### 1.3 Jira / PR references

_The following references are recorded at Checkpoint A review (task 9)._

| Reference | Identifier |
| --- | --- |
| Sprint task | S2-01 — Decision-Engine Specification & Frozen Configuration |
| Jira issue | _TBD — recorded at Checkpoint A_ |
| Pull request | _TBD — recorded at Checkpoint A_ |
| Checkpoint | Client Checkpoint A (Decision design) |
| Sign-off date | _TBD — recorded at Checkpoint A_ |

### 1.4 Screening language commitment

This specification commits to **Screening_Language** throughout. The Opt-Mining platform
performs **preliminary screening**: it surfaces higher-ranked candidate cells under a
selected set of assumptions and criteria. It does not identify an objectively "best
site".

Accordingly, this document and everything derived from it describe model output using
preliminary-screening phrasing — for example "higher-ranked candidate under the selected
assumptions and criteria" — and **never** use absolute superlative claims such as "best
site", "optimal location", or "the correct answer" to describe model output. Weights are
user inputs and the score is interrogable; a ranking the reader cannot question would be
an assertion rather than a screening result.

### 1.5 Cross-references

This specification is the authoritative decision design and is referenced from the
following locations so it is discoverable across the repository. _(Cross-reference wiring
is completed in task 7; the target locations are listed here.)_

| Location | Reference to add | Status |
| --- | --- | --- |
| `pipeline/README.md` | Link to `Sprint-2-Tasks/decision_engine_specification.md` as the authoritative decision-engine / scoring design | _TBD — task 7_ |
| `DATA/data-specification/sprint1_data_specification.md` (§4.5) | Reference the Decision_Engine_Spec as the authoritative source for scoring criteria, weights and normalisation | _TBD — task 7_ |

---

## §2 Criteria feature contract

_Placeholder — authored in task 2._

One table per Criteria_Group (wind, demand proxy, infrastructure,
geographic/environmental). Columns: Criterion, integrated-table column, units, source,
Direction, notes. Every Criterion column name is verified against
`pipeline/integration/config.py` (`OUTPUT_COLUMNS` / `SCORED_FEATURE_COLUMNS`).

- **§2.1** Wind Criteria_Group
- **§2.2** Demand-proxy Criteria_Group
- **§2.3** Infrastructure Criteria_Group
- **§2.4** Geographic / environmental Criteria_Group
- **§2.5** Column-name verification (Property P1)

---

## §3 Scoring formula + weight-normalisation rule

_Placeholder — authored in task 3._

Scoring_Formula `S_i = Σ_k w_k · n_k(i)`; the weight-normalisation rule (division by the
sum of the applied weights); the eligible-only rule and null score for excluded cells;
and the not-circular guarantee (wind is an input Criterion only, never a prediction
target).

---

## §4 Default weights (assumptions + rationale)

_Placeholder — authored in task 4._

Table of the default Criteria with weight, Direction and a non-empty written rationale
each, labelled as documented assumptions rather than objectively correct business values.

---

## §5 Normalisation method + outlier/missing policy

_Placeholder — authored in task 5._

Directional linear min-max per Criterion; bounds computed from the eligible cell
population and fixed per run (not per UI filter); outlier policy; missing-value policy
(never bias-imputed); constant-criterion rule (no divide-by-zero); boolean definitional
mapping.

---

## §6 Frozen decisions + change-control locations

_Placeholder — authored in task 6._

Which parameters are Frozen_Decisions; the data-specification section-8 process governs
any change; enumeration of every recording location (this specification,
`pipeline/scoring/scoring_weights.yaml`, data-specification §4.5).

---

## §7 Traceability matrix

_Placeholder — authored in task 7._

Maps each Criterion → AC3, the Default_Weights + weight-normalisation rule → AC5, and the
four Criteria_Groups → combined-sprint guidance Step 3.

---

## §8 Reconciliation log

_Placeholder — authored in task 8._

Line-by-line reconciliation against `pipeline/scoring/scoring_weights.yaml` and
`pipeline/scoring/`. One row per criterion: parameter, spec value, implementation value,
status (`consistent` | `resolved`), resolution. Where consistent, that consistency is
stated explicitly.
