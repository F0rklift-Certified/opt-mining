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

This section defines the exact per-cell features (Criteria) the decision engine consumes,
organised into the four client-defined Criteria_Groups: **wind**, **demand proxy**,
**infrastructure**, and **geographic / environmental**. For every Criterion it records the
integrated-table column name, units, source, beneficial/adverse Direction, and notes.

Every `integrated-table column` value below is a real column of the integrated feature
table. The authoritative schema is `pipeline/integration/merge.py` `BASE_COLUMNS` and the
ten `SCORED_FEATURE_COLUMNS` re-exported from `pipeline/integration/config.py`; units and
source strings are taken from `COLUMN_UNITS` and the per-layer `LayerSpec.columns` map in
the same module. These Criteria are the inputs to the Scoring_Formula (§3) and the
Default_Weights (§4). Names, units and directions here are Frozen_Decisions governed by §6.

Direction is recorded as exactly `higher_is_better` or `lower_is_better`, per the
Existing_Implementation (`pipeline/scoring/scoring_weights.yaml`). The engine ranks
**higher-ranked candidate cells under the selected assumptions and criteria**; it does not
identify a "best site" (Screening_Language, §1.4).

### §2.1 Wind Criteria_Group

The wind resource is the primary screening variable. It is a single Global Wind Atlas
(GWA) resource Criterion.

| Criterion | Integrated-table column | Units | Source | Direction | Notes |
| --- | --- | --- | --- | --- | --- |
| Mean wind speed at 100 m hub height | `wind_speed` | m/s | GWA v4 (`wind-speed` layer, DTU Global Wind Atlas), sampled per analysis cell | `higher_is_better` | Named GWA resource variable is the `wind-speed` raster at the 100 m height layer (`gwa_v4_wind-speed_100m_nsw.tif`). Aggregated to the cell as the **mean** of valid pixels. |

**Justification of the hub-height and variable choice (Requirement 2.3).** The chosen GWA
variable is `wind-speed` (mean wind speed), and the chosen hub height is **100 m**. Both are
Frozen_Decisions from the Sprint 1 data specification — frozen decision Q1 fixes the
aggregation **statistic = mean** and frozen decision Q2 fixes the **primary hub height =
100 m** (recorded at `pipeline/wind/config.py`, `WIND_FEATURE_SOURCE` /
`WIND_AGG_STATISTIC`). 100 m is selected because it sits within the hub-height band of the
utility-scale turbine classes GWA itself publishes capacity factors for (IEC1/IEC2/IEC3 are
modelled at a 100 m hub), so the resource value is representative of the machines a screened
site would host, while remaining a single consistent height across every cell. Mean wind
speed is used rather than power density or a turbine-specific capacity factor so the
Criterion stays a transparent, turbine-agnostic resource indicator. This is an **input
Criterion only**: the model never predicts wind from wind-derived features, so the model is
not circular (see §3).

### §2.2 Demand-proxy Criteria_Group

The demand Criterion is explicitly a **Demand_Proxy**, allocated below the AEMO (NEM)
region. It is **not** measured local demand — no cell-level metered demand exists in the
MVP; the proxy allocates a NEM-region annual figure and so discriminates between regions
rather than between neighbouring cells.

| Criterion | Integrated-table column | Units | Source | Direction | Notes |
| --- | --- | --- | --- | --- | --- |
| Demand proxy (allocated below the AEMO/NEM region) | `demand_proxy` | normalised 0–1 (uniform allocation of the NEM-region annual mean demand, MW) | AEMO NEM-region annual operational-demand mean, allocated to each cell by its `source_region` | `higher_is_better` | Explicitly a **proxy**, never "measured local demand". Allocated uniformly to every cell within a NEM region (NSW1 = NSW + ACT convention), so it separates regions, not adjacent cells. `source_region` records the region a cell inherits from; the value is null outside every region. |

### §2.3 Infrastructure Criteria_Group

The infrastructure dimension is expressed as **measurable indicators**, not an undefined
aggregate "infrastructure score". Three indicators participate in the score: distance to
transmission, distance to substation, and REZ membership.

| Criterion | Integrated-table column | Units | Source | Direction | Notes |
| --- | --- | --- | --- | --- | --- |
| Distance to nearest transmission line (≥132 kV) | `dist_transmission_km` | km (EPSG:3577 centroid distance) | Geoscience Australia electricity transmission lines, filtered to ≥132 kV | `lower_is_better` | Connection-cost discriminator; closer to a high-voltage line is better. |
| Distance to nearest substation | `dist_substation_km` | km (EPSG:3577 centroid distance) | Geoscience Australia electricity substations | `lower_is_better` | Interconnection-complexity discriminator; partly collinear with transmission distance (§4). |
| Inside a declared NSW Renewable Energy Zone | `inside_rez` | boolean (`true` / `false`) | EnergyCo NSW REZ boundaries | `higher_is_better` | REZ membership indicator; `rez_name` records the declared REZ(s). Boolean Criterion — maps to its definitional `{false → 0.0, true → 1.0}` domain (§5). |

A fourth infrastructure column, `dist_connection_km` (distance to nearest connection
point), is carried in the integrated table for context but is **not** a scored Criterion in
the Default_Weights. There is no aggregate "infrastructure score" column — the dimension is
represented only by the measurable indicators above.

### §2.4 Geographic / environmental Criteria_Group

The geographic/environmental dimension contributes agreed **non-hard-constraint** features.
Hard constraints (for example slope above the exclusion threshold, protected areas) are
applied by the S1-07 exclusion stage and remove a cell from scoring entirely; they are
**not** Criteria here. The single scored Criterion in this group is terrain slope, which
separates cells that pass the hard gate by how steep they still are.

| Criterion | Integrated-table column | Units | Source | Direction | Notes |
| --- | --- | --- | --- | --- | --- |
| Terrain slope | `slope_deg` | degrees (mean of valid Horn-slope pixels) | Horn slope derived from SRTM elevation | `lower_is_better` | Flatter terrain lowers civil-works and turbine-siting cost. A continuous penalty that complements — and never replaces — the S1-07 hard exclusion above the slope threshold. |

Other geographic/environmental columns present in the integrated table (`elevation_m`,
`tri`, `land_use`, `protected_area`) are context or hard-constraint inputs, not agreed
scored Criteria in the Default_Weights. Should a further non-hard-constraint geographic
Criterion be agreed at Checkpoint A, it is added here and to §4 under §6 change control.

### §2.5 Column-name verification (Property P1)

**Property P1 — every criterion resolves to a real column.** Every `integrated-table
column` value named in §2.1–§2.4 was verified, column by column, against the authoritative
integrated feature-table schema: `pipeline/integration/merge.py` `BASE_COLUMNS` (the full
column order) and the ten `SCORED_FEATURE_COLUMNS` re-exported from
`pipeline/integration/config.py`. Units and source strings were cross-checked against
`COLUMN_UNITS` and the per-layer `LayerSpec.columns` maps in `merge.py`. The audit below
records, for every column referenced in §2, the schema constant it was found in.

| §2 column | Role in §2 | In `BASE_COLUMNS`? | In `SCORED_FEATURE_COLUMNS`? | Verification result |
| --- | --- | --- | --- | --- |
| `wind_speed` | Scored Criterion (§2.1 wind) | yes | yes | Confirmed present — no correction needed |
| `demand_proxy` | Scored Criterion (§2.2 demand) | yes | yes | Confirmed present — no correction needed |
| `dist_transmission_km` | Scored Criterion (§2.3 infra) | yes | yes | Confirmed present — no correction needed |
| `dist_substation_km` | Scored Criterion (§2.3 infra) | yes | yes | Confirmed present — no correction needed |
| `inside_rez` | Scored Criterion (§2.3 infra) | yes | yes | Confirmed present — no correction needed |
| `slope_deg` | Scored Criterion (§2.4 geographic) | yes | yes | Confirmed present — no correction needed |
| `dist_connection_km` | Context column (§2.3, not scored) | yes | yes | Confirmed present — no correction needed |
| `source_region` | Allocation key (§2.2 notes) | yes | no | Confirmed present — no correction needed |
| `rez_name` | REZ label (§2.3 notes) | yes | no | Confirmed present — no correction needed |
| `elevation_m` | Context column (§2.4 notes) | yes | yes | Confirmed present — no correction needed |
| `tri` | Context column (§2.4 notes) | yes | no | Confirmed present — no correction needed |
| `land_use` | Context column (§2.4 notes) | yes | yes | Confirmed present — no correction needed |
| `protected_area` | Hard-constraint context (§2.4 notes) | yes | yes | Confirmed present — no correction needed |

**Result.** All thirteen columns referenced in §2 are members of the integrated schema; **no
Criterion required a name correction** under Requirement 2.7. The six scored Criteria
(`wind_speed`, `demand_proxy`, `dist_transmission_km`, `dist_substation_km`, `slope_deg`,
`inside_rez`) additionally match the feature names in the Existing_Implementation weights
file (`pipeline/scoring/scoring_weights.yaml`) exactly; that correspondence is recorded in
the §8 reconciliation log. Property P1 therefore holds.

---

## §3 Scoring formula + weight-normalisation rule

This section states the Scoring_Formula in full and the four rules that make its output
interpretable: the weight-normalisation rule, the eligible-only rule, the null score for
excluded cells, and the not-circular guarantee. It restates the design already realised in
the Existing_Implementation (`pipeline/scoring/score.py` `score_frame`,
`pipeline/scoring/scoring_weights.yaml`, and the pipeline README's `scoring` stage notes);
it does not invent a new one. Every rule below is a Frozen_Decision governed by §6.

The engine surfaces **higher-ranked candidate cells under the selected assumptions and
criteria**; it does not identify a "best site" (Screening_Language, §1.4). The formula is a
transparent, deterministic **weighted multi-criteria decision analysis (MCDA)** — not a
machine-learning model.

### §3.1 The Scoring_Formula

For a cell `i`, the suitability score `S_i` is the weight-normalised sum of that cell's
directional min-max normalised Criterion values:

```
        Σ_k  w_k · n_k(i)
S_i  =  ─────────────────
             W_i
```

where, for each configured Criterion `k` (the six of §2 / §4):

- `w_k` — the Default_Weight of Criterion `k` (a user input from
  `pipeline/scoring/scoring_weights.yaml`; see §4).
- `n_k(i)` — the value of Criterion `k` at cell `i` after directional linear min-max
  normalisation to `[0, 1]`, where 1 is most favourable and 0 least favourable (the
  Normalisation_Method; see §5). Direction is honoured inside `n_k`: for a
  `higher_is_better` Criterion `n_k = (v − lo) / (hi − lo)`, and for a `lower_is_better`
  Criterion `n_k = 1 − (v − lo) / (hi − lo)`.
- `W_i` — the **applied weight sum** for cell `i` (the weight-normalisation denominator;
  see §3.2).

The additive term `contrib_k(i) = w_k · n_k(i) / W_i` is written to the scored table as
`contrib_{feature}`, and the six contributions sum back to `S_i` (verified to a
`1e-9` tolerance on every run). This is the explainability contract: `contrib_wind_speed`
is literally how many points of a cell's score came from wind, so a reviewer can interrogate
why one cell outranked another. `S_i` lies in `[0, 1]`; rank 1 is the highest-scoring
eligible cell, ties broken by ascending `cell_id`.

_(An optional confidence discount multiplies `S_i` and every `contrib_k(i)` by a single
per-cell factor drawn from the carried-through S1-09 `data_confidence` value. It is disabled
by default — on the current NSW data every eligible cell is `high` confidence, so a discount
would be an identical multiplier on every scored cell and would change no ranking. The
discount preserves the contributions-sum-to-score contract because it scales the score and
its contributions identically. It is a confidence treatment, not part of the core
weight-normalised MCDA formula above.)_

### §3.2 Weight-normalisation rule (division by the applied weight sum)

**The weights are relative, not absolute.** `S_i` divides the weighted sum by `W_i`, the sum
of the weights **actually applied** to cell `i`:

```
W_i  =  Σ_{k applied to i}  w_k
```

Two consequences follow, and both are deliberate:

1. **Scale invariance.** Because the numerator and `W_i` scale together, multiplying every
   weight by a constant leaves every score and every ranking unchanged. Only the *relative*
   sizes of the weights matter. The Default_Weights (§4) sum to 1.00 purely for readability,
   not because the formula requires it — the division normalises whatever they sum to.

2. **Per-cell denominator for missing values.** A Criterion with no value for a given cell
   (a null `n_k(i)`) contributes **neither** a numerator term **nor** a share of `W_i` for
   that cell. Each score is therefore a weighted average over the evidence that exists for
   that cell, never a sum in which a data gap is silently scored as the worst possible value.
   On the current NSW data no eligible cell is missing a scored Criterion, so `W_i` equals
   the full weight sum for every scored cell; the per-cell rule is the honest general case
   (see §5.4 for the missing-value policy). A cell with no usable Criterion has `W_i = 0` and
   is left unscored (null) rather than divided by zero; validation reports any such cell
   explicitly.

### §3.3 Eligible-only rule and null score for excluded cells

Only **Eligible_Cells** are scored. A cell is eligible when the S1-07 exclusion layer sets
`eligible = True`; a cell with `eligible = False` — or a null/unknown eligibility — is
**not** eligible and receives:

- a **null** `suitability_score`,
- a **null** `rank`, and
- **null** contributions.

Excluded cells also take **no part** in the normalisation bounds (§5.2): an ineligible
cell's extreme value must not stretch the scale the candidate cells are measured on. This is
the hard-exclusion boundary — hard constraints (protected areas, slope above the exclusion
threshold, offshore, and so on) are applied upstream by S1-07 and remove a cell from scoring
entirely, rather than being expressed as a Criterion here. **Ineligible land is never ranked
as if it were developable.**

### §3.4 Not-circular guarantee

The model is **not circular**. The wind Criterion (`wind_speed`, §2.1) enters the formula
**only as an input** `n_k(i)` term. Nothing in the engine predicts wind from wind-derived
features, and no wind-prediction column is emitted. The score is a transparent weighted
combination of independently-sourced input features (wind resource, demand proxy,
infrastructure distances, REZ membership, slope) — the wind feature is never both an input
and a prediction target. This upholds the constitution's "never build a circular model" rule
and is enforced structurally: the Existing_Implementation contains no weight literal and no
wind-prediction step (`pipeline/scoring/score.py`, `pipeline/scoring/__init__.py`).

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
