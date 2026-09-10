# Decision-Engine Specification & Frozen Configuration

> **Status:** Draft — authored under spec `s2-01-decision-engine-specification`.
> Sections §1–§7 are authored; §8 (reconciliation log) is a scaffolded placeholder authored
> in task 8 of this spec.

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
following locations so it is discoverable across the repository (Requirement 1.2). The
cross-reference wiring is **complete** (task 7):

| Location | Reference added | Status |
| --- | --- | --- |
| `pipeline/README.md` | Link to `Sprint-2-Tasks/decision_engine_specification.md` as the authoritative decision-engine / scoring design, in the `scoring` (S1-10) stage note | ✅ Wired (task 7) |
| `DATA/data-specification/sprint1_data_specification.md` (§4.7, with a pointer from §4.5) | References the Decision_Engine_Spec as the authoritative source for the scoring criteria, weights and normalisation method | ✅ Wired (task 7, under the data-spec §8 change-control process, v1.8) |

> **§4.5 vs §4.7 note.** The upstream requirement and design name Data_Specification **§4.5**
> as the scoring-parameter anchor, but in the current Data_Specification **§4.5 is the
> *Integrated Feature Table*** (the scoring *input*) and the scoring parameters live in **§4.7
> *Baseline Suitability Score*** (added under the data-spec §8 process as v1.5). The
> cross-reference is therefore placed in **§4.7**, and a pointer from §4.5 directs a reader on
> to §4.7 and to this specification. Both section numbers are recorded so neither pointer goes
> stale (see §6.3).

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

This section records the **Default_Weights** — the starting weight assigned to each of the
six scored Criteria (§2) in the Scoring_Formula (§3). The values, Directions, and rationale
text below reproduce the Existing_Implementation weights file
(`pipeline/scoring/scoring_weights.yaml`) faithfully; that file is the authoritative source
and this section restates it, it does not redefine it. Because weights are **user inputs,
never hard-coded constants** (the constitution rule realised by that YAML file carrying no
weight literal in code), any consumer may retune them — the table below is the shipped
starting point, not a fixed law.

> **These are documented assumptions, not objectively correct business values.**
> The six weights below encode one reasonable, defensible ordering of screening priorities
> for the MVP. They are **not** claimed to be optimal, uniquely correct, or the "right"
> business weighting — no such objective answer exists for a screening exercise. They are a
> transparent, interrogable starting point that a reviewer can question and change. Weights
> are relative (§3.2): they sum to 1.00 purely for readability, and multiplying them all by a
> constant changes no score and no ranking. The engine surfaces **higher-ranked candidate
> cells under the selected assumptions and criteria** (Screening_Language, §1.4) — a
> different, equally documented weighting would surface a different ranking, and that is a
> feature of the design, not a defect.

### §4.1 Default_Weights table

| Criterion (integrated-table column) | Weight | Direction | Rationale (documented assumption) |
| --- | --- | --- | --- |
| Mean wind speed (`wind_speed`) | **0.35** | `higher_is_better` | Primary resource indicator. Energy yield scales roughly with the cube of wind speed, so it dominates project viability more than any other screening variable and carries the largest single weight. Source: GWA 100 m mean wind speed (spec §4.1.1) — an **input** feature only; the model never predicts wind from wind-derived features (no circular modelling, §3.4). |
| Distance to transmission (`dist_transmission_km`) | **0.20** | `lower_is_better` | Connection cost is a major capex component and scales with line length, so distance to the nearest ≥132 kV line is the second-strongest discriminator between otherwise similar cells. Source: spec §4.3.1; centroid distance computed in EPSG:3577. |
| Demand proxy (`demand_proxy`) | **0.15** | `higher_is_better` | Proximity to electrical demand improves offtake prospects and reduces transmission losses. Weighted below the physical grid distances because the MVP proxy is a NEM-region annual mean allocated uniformly to every cell (spec §4.2.3), so it discriminates between regions rather than between neighbouring cells. |
| Distance to substation (`dist_substation_km`) | **0.10** | `lower_is_better` | Substation proximity reduces interconnection complexity and works scope. Weighted at half the transmission-line criterion because it is partly collinear with it — a cell near a substation is usually near a line — and double-counting the same effect would inflate it. Source: spec §4.3.2. |
| Terrain slope (`slope_deg`) | **0.10** | `lower_is_better` | Flatter terrain lowers civil-works, access-road and crane-pad cost and widens turbine-siting options within a cell. A continuous penalty here complements the S1-07 hard exclusion above 15 degrees: cells that pass the gate are still separated by how steep they are. Source: derived Horn slope from SRTM (spec §4.4.6). |
| Inside a declared NSW REZ (`inside_rez`) | **0.10** | `higher_is_better` | Cells inside a declared NSW Renewable Energy Zone benefit from coordinated network planning, committed transmission investment and an established access regime. Boolean, so it maps to its definitional `{false → 0.0, true → 1.0}` domain (§5.6). Weighted modestly because it is a policy signal rather than a physical measurement, and REZ boundaries change between planning cycles. Source: spec §4.3.3. |
| **Sum** | **1.00** | — | Sums to 1.00 for readability only; the weight-normalisation rule (§3.2) divides by the applied weight sum, so the absolute total is immaterial to the ranking. |

### §4.2 Weight-ordering assumptions (Requirement 4.2)

The **relative** ordering above encodes the documented screening priorities and is the part
worth reviewing at Checkpoint A. In words:

1. **Wind dominates (0.35).** The cubic yield relationship makes the resource the single most
   consequential screening variable, so it carries more than a third of the weight — larger
   than any two other Criteria combined except the two grid-distance terms.
2. **Grid connection is second (0.20 + 0.10).** Transmission distance (0.20) outranks
   substation distance (0.10); substation distance is deliberately halved to avoid
   double-counting the largely collinear "near the grid" signal.
3. **Demand proxy is mid-weight (0.15).** Ranked below the physical grid distances precisely
   because it is a region-level **proxy** (§2.2), not a cell-level measurement.
4. **Slope and REZ membership are the light touches (0.10 each).** Slope is a continuous
   penalty on top of the hard exclusion, and REZ membership is a policy signal that shifts
   between planning cycles, so neither is allowed to swamp the physical resource and
   connection terms.

Each of these is an **assumption open to revision**. Changing any weight is a
Frozen_Decision governed by §6 and must be applied consistently across every recording
location (this specification §4.1, `pipeline/scoring/scoring_weights.yaml`, and the
data-specification §4.5); the reconciliation against the current YAML values is recorded in
§8.

### §4.3 Rationale-completeness verification (Property P3)

**Property P3 — every default weight carries a rationale.** Every one of the six default
Criteria in §4.1 has a non-empty written rationale, reproduced faithfully from the
Existing_Implementation. The audit below confirms this column by column.

| Criterion | Weight present? | Direction present? | Rationale non-empty? |
| --- | --- | --- | --- |
| `wind_speed` | yes (0.35) | yes (`higher_is_better`) | yes |
| `dist_transmission_km` | yes (0.20) | yes (`lower_is_better`) | yes |
| `demand_proxy` | yes (0.15) | yes (`higher_is_better`) | yes |
| `dist_substation_km` | yes (0.10) | yes (`lower_is_better`) | yes |
| `slope_deg` | yes (0.10) | yes (`lower_is_better`) | yes |
| `inside_rez` | yes (0.10) | yes (`higher_is_better`) | yes |

**Result.** All six default Criteria carry a weight, a Direction, and a non-empty rationale;
none is left unexplained. Property P3 therefore holds.

---

## §5 Normalisation method + outlier/missing policy

This section fixes the **Normalisation_Method** — the rule that converts each Criterion's
raw values, measured in incompatible units (m/s, km, degrees, boolean, a 0–1 proxy), into
the comparable `[0, 1]` components `n_k(i)` the Scoring_Formula (§3) sums. It restates the
method already realised in the Existing_Implementation (`pipeline/scoring/normalise.py`
`compute_bounds` / `normalise_value` / `normalise_series`, the structural constants in
`pipeline/scoring/config.py`, and the method-report text in `pipeline/scoring/report.py`);
it does not invent a new one. Every rule below is a Frozen_Decision governed by §6.

Normalisation only rescales; it never re-ranks. On a common `[0, 1]` scale, **1 is most
favourable and 0 least favourable**, so a directional min-max lets the engine surface
**higher-ranked candidate cells under the selected assumptions and criteria** without ever
claiming a "best site" (Screening_Language, §1.4).

### §5.1 Directional linear min-max per Criterion (Requirement 5.1)

Each Criterion `k` is rescaled by a **linear** min-max transform to `[0, 1]`, with the
Direction of §2 / §4 applied inside the transform. For a raw value `v` at cell `i`, with
lower bound `lo_k` and upper bound `hi_k` (§5.2):

```
higher_is_better:   n_k(i) = (v − lo_k) / (hi_k − lo_k)
lower_is_better:    n_k(i) = 1 − (v − lo_k) / (hi_k − lo_k)
```

The result is clamped to the inclusive `[0, 1]` range, so a value lying outside the bounds
saturates at 0 or 1 rather than pushing a component — and therefore a score — out of range
(this can arise only if bounds from another population are ever supplied; see §5.3). The
transform is **purely linear** for every Criterion: no logarithmic, power, or other
non-linear reshaping is applied to any Criterion, including the distance Criteria
(`dist_transmission_km`, `dist_substation_km`). A log transform for distances is a
defensible alternative — it would compress differences between far-apart cells and expand
them between nearby ones — but that is a modelling judgement, so it is left to an explicit
future change under §6 change control rather than applied silently. The Direction each
Criterion uses is exactly as recorded in §2 and §4: `higher_is_better` for `wind_speed`,
`demand_proxy`, and `inside_rez`; `lower_is_better` for `dist_transmission_km`,
`dist_substation_km`, and `slope_deg`.

The transform is a **pure function** of `(value, lo_k, hi_k, direction)`: identical inputs
always produce identical outputs, with no I/O and no dependence on the weights, so the
normalisation step is deterministic and independently reproducible.

### §5.2 Bounds from the eligible population, fixed per run (Requirement 5.2)

The bounds `lo_k` and `hi_k` for each continuous Criterion are the **minimum and maximum of
that Criterion over the Eligible_Cells only** (`eligible = True`, §3.3), computed fresh from
the integrated feature table on every analysis run — **never hard-coded**. Ineligible cells
take **no part** in any bound: the score compares candidate sites against one another, so an
excluded cell's extreme value must not stretch the scale the candidates are measured on.

The bounds are **fixed for the whole analysis run**. They are a property of the eligible
population computed once when the run scores the table, **not** a function of any downstream
display filter. A user narrowing what the web application shows — by REZ, by score band, by
region — re-filters the *view*; it does **not** recompute the normalisation bounds and does
**not** change any cell's `suitability_score`, `n_k(i)`, or `rank`. A cell's score is a
stable property of the run, so the same cell cannot appear more or less suitable merely
because the viewer changed what else is on screen. Each `Bounds` record additionally carries
the raw `observed_min` / `observed_max` and the count of eligible cells that had a value, so
the method report (`scoring_method.md`, §3 of that report) shows both the rule applied and
the data it was applied to.

### §5.3 Outlier-handling policy (Requirement 5.3)

The frozen outlier policy is **no separate outlier treatment**: the linear min-max of §5.1
is applied to the full eligible population with **no trimming, winsorising, percentile
capping, or robust-statistic substitution**, and the min and max are the true population
extremes, not clipped quantiles. Two consequences are recorded honestly rather than hidden:

1. **Extremes set the scale.** Because `lo_k` and `hi_k` are the genuine eligible-population
   min and max, a single extreme eligible cell widens the range and compresses the spread of
   the remaining cells on that Criterion. This is accepted for the MVP screening exercise:
   the transform stays transparent and reproducible, and no cell is silently reshaped by an
   undocumented statistical rule.
2. **Saturation, not overflow.** The only clamping applied is the `[0, 1]` clamp of §5.1.
   Within a single run every eligible value lies between its own population bounds by
   construction, so it maps inside `[0, 1]` without clamping; the clamp is a guard that keeps
   a component in range if bounds from a different population are ever supplied, in which case
   an out-of-range value saturates at 0 or 1 rather than distorting the score.

Any future adoption of an outlier transform (a percentile cap or a log rescale for
distances, for example) is a change to a Frozen_Decision and must follow §6 change control
and be reflected in every recording location.

### §5.4 Missing-value policy — never bias-imputed (Requirement 5.4)

A missing Criterion value is **never imputed to a default that biases the score**, and in
particular is **never scored as zero or as the worst possible value**. The frozen rule:

- A null (or non-numeric, hence NaN) value for Criterion `k` at cell `i` produces a **null**
  normalised component `n_k(i)` — the null is preserved, not filled.
- That Criterion is then **excluded from that cell's weighted average**: it contributes
  **neither** a numerator term **nor** a share of the applied weight sum `W_i` (§3.2). Each
  score is therefore a weighted average over the evidence that exists for the cell, never a
  sum in which a data gap masquerades as an unfavourable measurement.
- The carried-through S1-09 `data_confidence` value is what flags the gap; the score is not
  quietly depressed to signal it.

Scoring a missing feature as zero would penalise a cell for a hole in the data rather than
for a property of the land, which the constitution forbids ("never let poor data pass as
good", cutting both ways). On the current NSW data no eligible cell is missing a scored
Criterion, so `W_i` equals the full weight sum for every scored cell; the per-cell rule is
the honest general case. A cell for which **no** Criterion has a value has `W_i = 0`, is left
**unscored** (null score, null rank, null contributions) rather than divided by zero, and is
reported explicitly by validation — it can never pass silently.

### §5.5 Constant-criterion rule — no divide-by-zero (Requirement 5.5)

When a continuous Criterion has the **same value for every eligible cell**, its bounds
collapse to `lo_k == hi_k` and the min-max expression `(v − lo_k) / (hi_k − lo_k)` is `0/0`.
The frozen rule avoids the divide-by-zero without dropping the Criterion:

- Every eligible cell is assigned the **documented constant fill**
  `CONSTANT_CRITERION_VALUE = 1.0` for that Criterion (a null value still stays null, per
  §5.4); **no division is performed**.
- The Criterion is **flagged as constant** so the method report tells the reader it carried
  **no discriminating information** on that run.

The value `1.0` (rather than `0.0`) is used so a Criterion sitting uniformly at its only
observed value is not penalised for lack of variation. A constant Criterion adds the **same**
amount to every eligible cell's score, so it shifts the absolute scores uniformly and
**cannot change the ranking** — the shortlist reads as though it were scored on the remaining
non-constant Criteria. The special case where *no* eligible cell has a value is treated as a
constant Criterion for this purpose (bounds `0.0/0.0`, flagged), consistent with §5.4.

### §5.6 Boolean definitional mapping (Requirement 5.6)

A boolean Criterion (currently `inside_rez`, §2.3) is mapped by its **definitional domain**,
not by the observed population min/max:

```
False → 0.0        True → 1.0        (definitional bounds lo = 0.0, hi = 1.0)
```

The Direction is then applied exactly as in §5.1. `inside_rez` is `higher_is_better`, so the
definitional mapping already gives the intended `False → 0.0`, `True → 1.0`; a
`lower_is_better` boolean would invert to `False → 1.0`, `True → 0.0`. Using the definitional
domain rather than the observed extremes is what makes a **uniform** boolean behave honestly:
an all-`False` `inside_rez` scores **0** for every cell ("no cell is in a REZ") instead of
triggering the constant-criterion fill of §5.5 and handing every cell full marks (`1.0`) for
a benefit none of them has. The observed min/max are still recorded alongside the definitional
bounds in the method report so a reader can see both the rule and the data.

### §5.7 Method-summary verification

The table below records, for each of the six normalisation policies fixed above, the
Existing_Implementation location that realises it — so this specification restates the
shipped behaviour rather than asserting it.

| Policy (this §5) | Requirement | Realised in the Existing_Implementation |
| --- | --- | --- |
| Directional linear min-max, clamped `[0, 1]` | 5.1 | `normalise.py` `normalise_value` / `normalise_series`; directions in `config.py` (`HIGHER_IS_BETTER`, `LOWER_IS_BETTER`) |
| Bounds from the eligible population, fixed per run | 5.2 | `normalise.py` `compute_bounds` (eligible rows only, computed fresh); `score.py` `score_frame` (bounds computed once per run) |
| No separate outlier treatment; true min/max; `[0, 1]` clamp | 5.3 | `normalise.py` (no trim/winsorise; population extremes); method-report "Normalisation is LINEAR" note in `report.py` |
| Missing values null, excluded from `W_i`, never zero-scored | 5.4 | `normalise.py` `as_float` / `normalise_series` (nulls preserved); `score.py` `score_frame` (per-cell applied weight; unscorable → null) |
| Constant-criterion fill `1.0`, no divide-by-zero, flagged | 5.5 | `config.py` `CONSTANT_CRITERION_VALUE`; `normalise.py` `compute_bounds` (`is_constant`) / `normalise_value` / `normalise_series` |
| Boolean definitional `{False → 0.0, True → 1.0}` domain | 5.6 | `config.py` `BOOLEAN_BOUNDS`; `normalise.py` `is_boolean_series` / `compute_bounds` |

The exact numeric bounds used, the per-Criterion rule applied, and the constant/boolean flags
are written to `DATA/scoring/metadata/scoring_method.md` on every run (built by
`report.build_method_report`), so the values this section governs are auditable per run
rather than only described here.

---

## §6 Frozen decisions + change-control locations

This section names every parameter this specification treats as a **Frozen_Decision**,
states the governance process that any change must follow, and enumerates every location
each frozen parameter is recorded so a change can be applied consistently and no location is
left stale. It is the governance backbone that lets a later change to a scored Criterion, a
Direction, the Normalisation_Method, the Scoring_Formula, or a Default_Weight be applied in
lock-step across the repository rather than drifting silently — the known duplication hazard
the project's holistic-awareness rule calls out.

Nothing here changes a value. The values themselves are fixed in §2–§5; this section fixes
**how they may change** and **where the change must land**. Consistent with the rest of this
document, it uses Screening_Language: the parameters below configure how the engine surfaces
**higher-ranked candidate cells under the selected assumptions and criteria**, never a "best
site" (§1.4).

### §6.1 Which parameters are Frozen_Decisions (Requirement 6.1)

The parameters below are the Frozen_Decisions of this specification. They divide into two
distinct **freeze classes**, because the project already governs them differently and this
section must not blur that distinction:

- **Contract-frozen** — the *shape* of the decision engine: which Criteria are scored, each
  Criterion's integrated-table column, units and Direction, the Normalisation_Method and its
  policies, and the Scoring_Formula with its rules. These are fixed by this specification (the
  Checkpoint-A contract) and every downstream Sprint 2/3 task builds against them. A change to
  any of these is a specification change governed by §6.2.

- **User-input defaults** — the six **Default_Weight values** (§4.1). By constitutional rule
  ("Criteria weights are user inputs, never hard-coded constants") and by the
  Existing_Implementation's design, the weights live in a runtime config file
  (`pipeline/scoring/scoring_weights.yaml`) and carry **no literal in `pipeline/scoring/`
  code**. Retuning a weight is a **config edit**, not a code or §2 change. They are listed
  here as Frozen_Decisions because they are the **documented default assumptions** shipped at
  Checkpoint A: the *shipped default set* is frozen and its rationale reviewed, even though any
  consumer may supply a different weights file at run time (`--scoring-weights PATH`).

| # | Frozen_Decision | Value (fixed in) | Freeze class |
| --- | --- | --- | --- |
| F1 | The scored Criteria set — exactly the six of §2 (`wind_speed`, `demand_proxy`, `dist_transmission_km`, `dist_substation_km`, `slope_deg`, `inside_rez`); adding or removing a scored Criterion | §2, §4.1 | Contract-frozen |
| F2 | Each Criterion's integrated-table column name and units | §2.1–§2.4 | Contract-frozen |
| F3 | Each Criterion's Direction (`higher_is_better` / `lower_is_better`) | §2, §4.1, §5.1 | Contract-frozen |
| F4 | The wind variable + hub height (GWA `wind-speed`, 100 m mean) — itself resting on data-spec frozen decisions Q1 (mean) and Q2 (100 m) | §2.1 | Contract-frozen (also data-spec Q1/Q2) |
| F5 | The Scoring_Formula (weighted MCDA, `S_i = Σ_k w_k·n_k(i) / W_i`) | §3.1 | Contract-frozen |
| F6 | The weight-normalisation rule (division by the applied weight sum `W_i`) | §3.2 | Contract-frozen |
| F7 | The eligible-only rule and null score/rank/contributions for excluded cells | §3.3 | Contract-frozen |
| F8 | The not-circular guarantee (wind is an input Criterion only, never a prediction target) | §3.4 | Contract-frozen |
| F9 | The Normalisation_Method — directional linear min-max, clamped `[0, 1]` | §5.1 | Contract-frozen |
| F10 | Bounds computed from the Eligible_Cell population, fixed per run (not per UI filter) | §5.2 | Contract-frozen |
| F11 | The outlier policy — no separate outlier treatment; true population min/max | §5.3 | Contract-frozen |
| F12 | The missing-value policy — null preserved, excluded from `W_i`, never zero-/worst-imputed | §5.4 | Contract-frozen |
| F13 | The constant-criterion rule — `CONSTANT_CRITERION_VALUE = 1.0`, flagged, no divide-by-zero | §5.5 | Contract-frozen |
| F14 | The boolean definitional mapping — `{False → 0.0, True → 1.0}` domain | §5.6 | Contract-frozen |
| F15 | The six shipped Default_Weight **values** (0.35 / 0.20 / 0.15 / 0.10 / 0.10 / 0.10) | §4.1 | User-input default |

The slope-scoring statistic (**mean**, per data-spec frozen decision **Q3**) and the "no
infrastructure hard-exclusion — continuous penalty only" stance (data-spec frozen decision
**Q7**) are inherited frozen decisions from the Data_Specification §2 rather than newly frozen
here; F1/F3 (slope as a `lower_is_better` scored Criterion) and §2.4/§3.3 (slope penalty
complements, never replaces, the S1-07 hard gate) build directly on them, and a change to Q3
or Q7 is governed by the Data_Specification's own §8 "Modifying a Frozen Parameter" process.

### §6.2 The change-control process (Requirement 6.2)

Any change to a Frozen_Decision above is governed by the **Data_Specification §8 change-control
process** (`DATA/data-specification/sprint1_data_specification.md` §8, titled *Change Control*).
The applicable sub-process depends on the freeze class:

- **Contract-frozen parameters (F1–F14)** follow the §8 **"Modifying a Frozen Parameter"**
  sub-process: (1) team consensus, (2) documented rationale — why the original decision no
  longer holds, with evidence, (3) impact assessment — which downstream stages and results are
  affected, and (4) a document version bump. Because these parameters are the Checkpoint-A
  contract, a change also requires re-review at (or a documented amendment to) Checkpoint A,
  and the two documentation-consistency checks (P1 column-name, P2 reconciliation completeness)
  must pass again.

- **User-input default weights (F15)** are, by the Existing_Implementation's design and the
  Data_Specification's own §8 record (the §4.7 v1.5 entry), a **runtime user input**, not a
  data-spec §2 frozen parameter (Q1–Q7). Retuning a weight for a single run is a config edit
  that needs no specification change. But **changing the shipped default set** — the assumptions
  presented and signed off at Checkpoint A — is a change to a documented default and MUST be
  applied consistently across all three recording locations in §6.3 under the same §8 discipline
  (rationale + impact assessment + version bump), so the shipped defaults never drift between the
  specification, the YAML, and the Data_Specification. This is the mechanism task 8.2 exercises
  if the §8 reconciliation surfaces a value that must change.

In all cases the governing principle is Requirement 6.4: **if a Frozen_Decision changes, the
change is reflected in every enumerated location so that no location records a stale value.**

### §6.3 Recording locations for every Frozen_Decision (Requirement 6.3)

Every Frozen_Decision is recorded in **at least these three locations**, which must be kept in
lock-step:

1. **This specification** — `Sprint-2-Tasks/decision_engine_specification.md` (the authoritative
   Checkpoint-A decision design; §2–§5 as tabulated in §6.1).
2. **The Existing_Implementation weights/config** — `pipeline/scoring/scoring_weights.yaml` for
   the Criteria set, Directions, Default_Weight values and rationales; the normalisation and
   formula rules are additionally realised in `pipeline/scoring/` (`config.py`, `normalise.py`,
   `score.py`, `report.py`) as tabulated in §5.7.
3. **The Data_Specification** — `DATA/data-specification/sprint1_data_specification.md`, in the
   **§4.7 Baseline Suitability Score** entry (which records the formula, the six default
   weights + Directions, the normalisation/boolean/constant rules and the change-control note)
   and, for the inherited resource decisions, the **§2 frozen-decisions table** (Q1 wind
   statistic, Q2 hub height, Q3 slope statistic, Q7 infrastructure penalty-not-exclusion).

> **Documented gap — §4.5 vs §4.7 (to be resolved under task 8.2 / task 7).** This spec's
> upstream requirement and design refer to the scoring criteria/weights/normalisation as living
> in Data_Specification **§4.5**. In the current Data_Specification, **§4.5 is the *Integrated
> Feature Table*** (the S1-08 scoring *input*), and the scoring parameters — formula, the six
> default weights, Directions and the normalisation method — are actually recorded in **§4.7
> Baseline Suitability Score** (added under §8 as v1.5). The enumeration above therefore cites
> **§4.7** as the true present-day location. This mismatch is flagged here rather than silently
> "corrected": task 7 adds the cross-reference from the Data_Specification back to this
> Decision_Engine_Spec (the §1.5 stub names §4.5 as the anchor point), and task 8.2 applies any
> frozen-value change across all locations under the §8 process. Until then, a reader following
> the §4.5 pointer must be directed on to §4.7 for the scoring parameters. Both section numbers
> are recorded here so neither pointer goes stale.

### §6.4 Frozen-decision enumeration audit (Property P4)

**Property P4 — frozen decisions are fully enumerated.** Every Frozen_Decision in §6.1 lists at
least the three recording locations of §6.3. The audit below confirms this parameter by
parameter: "this spec" is the §6.1 *Value (fixed in)* section; "weights YAML / `pipeline/scoring/`"
is location 2; "Data_Spec" is location 3 (§4.7 for the scoring contract, plus the §2 Q-decision
where one is inherited).

| Frozen_Decision | 1. This spec | 2. `scoring_weights.yaml` / `pipeline/scoring/` | 3. Data_Specification | ≥ 3 locations? |
| --- | --- | --- | --- | --- |
| F1 Criteria set | §2, §4.1 | `criteria:` list (six entries) | §4.7 (Variables / Criteria weights rows) | yes |
| F2 Columns + units | §2.1–§2.4 | `feature:` keys; units in comments | §4.7 (Units row) + §4.5 (source columns) | yes |
| F3 Directions | §2, §4.1, §5.1 | `direction:` per criterion | §4.7 (Criteria weights row) | yes |
| F4 Wind variable + 100 m | §2.1 | `feature: wind_speed` + rationale | §4.7; §2 Q1/Q2; §4.1.1 | yes |
| F5 Scoring_Formula | §3.1 | header comment + `score.py` `score_frame` | §4.7 (Method row) | yes |
| F6 Weight-normalisation rule | §3.2 | header comment (`/ SUM(weights applied)`) + `score.py` | §4.7 (Method row, `W_cell`) | yes |
| F7 Eligible-only / null-excluded | §3.3 | header comment + `score.py` | §4.7 (Method / Coverage rows); §4.6 | yes |
| F8 Not-circular | §3.4 | header comment ("no circular modelling") + absence of any wind-prediction step | §4.7 (Method / Role rows) | yes |
| F9 Directional min-max | §5.1 | `normalise.py`; `config.py` directions | §4.7 (Method row) | yes |
| F10 Eligible-population bounds, per run | §5.2 | `normalise.py` `compute_bounds`; `score.py` | §4.7 (Method row, "computed from the eligible population on each run") | yes |
| F11 Outlier policy | §5.3 | `normalise.py` (no trim/winsorise) | §4.7 (Method / Known-limitations rows) | yes |
| F12 Missing-value policy | §5.4 | `normalise.py` / `score.py` (null preserved, per-cell `W`) | §4.7 (Method row); §8 v1.5 deviation note | yes |
| F13 Constant-criterion `1.0` | §5.5 | `config.py` `CONSTANT_CRITERION_VALUE`; `normalise.py` | §4.7 (Method row) | yes |
| F14 Boolean `{0,1}` mapping | §5.6 | `config.py` `BOOLEAN_BOUNDS`; `normalise.py` | §4.7 (Method row, "definitional {0, 1} domain") | yes |
| F15 Six default weights | §4.1 | `weight:` per criterion (0.35/0.20/0.15/0.10/0.10/0.10) | §4.7 (Criteria weights row: "Defaults: …") | yes |

**Result.** All fifteen Frozen_Decisions list at least the three required recording locations
(this specification, `pipeline/scoring/scoring_weights.yaml` / `pipeline/scoring/`, and the
Data_Specification), with the §4.5→§4.7 pointer discrepancy explicitly recorded in §6.3 so no
location silently goes stale. Property P4 therefore holds.

---

## §7 Traceability matrix

This section makes the specification **traceable to the combined-sprint acceptance criteria**
so the client can confirm at Checkpoint A that the decision design satisfies them. It maps
every defined Criterion to **AC3** (Requirement 7.1), the Default_Weights and the
weight-normalisation rule to **AC5** (Requirement 7.2), and records the four Criteria_Groups
against combined-sprint **guidance Step 3** so every group is demonstrably covered
(Requirement 7.3). The three combined-sprint acceptance criteria referenced here are:

- **AC3 — Documented criteria.** Every scoring Criterion has a documented definition, its
  unit/source, and its beneficial/adverse Direction.
- **AC5 — Configurable, documented weights.** The weights are configurable and their
  interpretation and default values are documented (not hard-coded, not presented as
  objective business truths).
- **Guidance Step 3 — Named, non-vague criteria groups.** The four decision dimensions (wind,
  demand proxy, infrastructure, geographic/environmental) are covered by named, measurable
  features; no vague aggregate such as an unexplained "infrastructure score"; defaults are
  documented as assumptions.

Consistent with the rest of this document, the traceability below concerns how the engine
surfaces **higher-ranked candidate cells under the selected assumptions and criteria**
(Screening_Language, §1.4) — it never traces to, or claims, a "best site".

### §7.1 Criterion → AC3 (Requirement 7.1)

Every scored Criterion of §2 maps to **AC3**: each has a documented definition, a named
unit and source, and a recorded Direction. The section anchor is where the full definition
lives; AC3 is satisfied when all three columns (definition, unit/source, Direction) are
present and non-empty for the Criterion.

| Criterion (integrated-table column) | Criteria_Group | Definition (§) | Unit / source (§) | Direction (§) | AC3 satisfied |
| --- | --- | --- | --- | --- | --- |
| `wind_speed` | Wind | §2.1 (GWA 100 m mean wind speed) | m/s / GWA v4 `wind-speed` 100 m (§2.1) | `higher_is_better` (§2.1, §4.1) | ✅ definition + unit/source + Direction all present |
| `demand_proxy` | Demand proxy | §2.2 (NEM-region annual-demand proxy, allocated below the region) | normalised 0–1 from AEMO NEM-region annual mean MW (§2.2) | `higher_is_better` (§2.2, §4.1) | ✅ definition + unit/source + Direction all present |
| `dist_transmission_km` | Infrastructure | §2.3 (distance to nearest ≥132 kV transmission line) | km, EPSG:3577 / Geoscience Australia transmission lines (§2.3) | `lower_is_better` (§2.3, §4.1) | ✅ definition + unit/source + Direction all present |
| `dist_substation_km` | Infrastructure | §2.3 (distance to nearest substation) | km, EPSG:3577 / Geoscience Australia substations (§2.3) | `lower_is_better` (§2.3, §4.1) | ✅ definition + unit/source + Direction all present |
| `inside_rez` | Infrastructure | §2.3 (membership of a declared NSW REZ) | boolean / EnergyCo NSW REZ boundaries (§2.3) | `higher_is_better` (§2.3, §4.1) | ✅ definition + unit/source + Direction all present |
| `slope_deg` | Geographic / environmental | §2.4 (terrain slope, mean Horn-slope) | degrees / Horn slope from SRTM elevation (§2.4) | `lower_is_better` (§2.4, §4.1) | ✅ definition + unit/source + Direction all present |

**AC3 result.** All six scored Criteria carry a documented definition, a named unit and
source, and a recorded Direction. AC3 is satisfied for every Criterion.

### §7.2 Default_Weights + weight-normalisation rule → AC5 (Requirement 7.2)

**AC5** requires that the weights are *configurable* and that their *interpretation and
defaults are documented*. Both halves are traced below.

| AC5 sub-claim | Where satisfied in this spec | Existing_Implementation anchor | AC5 satisfied |
| --- | --- | --- | --- |
| Weights are **configurable** (user inputs, not hard-coded) | §4 preamble; §6.1 F15 (User-input default class); §6.2 (config edit vs default-set change) | `pipeline/scoring/scoring_weights.yaml` (loaded at runtime; `--scoring-weights PATH`); no weight literal in `pipeline/scoring/` code | ✅ |
| Each weight has a **documented default value** | §4.1 Default_Weights table (0.35 / 0.20 / 0.15 / 0.10 / 0.10 / 0.10) | `weight:` per criterion in `scoring_weights.yaml`; data-spec §4.7 ("Defaults: …") | ✅ |
| Each default weight has a **documented rationale**, labelled an assumption | §4.1 rationale column; §4.2 ordering assumptions; §4.3 P3 audit; §4 assumption callout | `rationale:` per criterion in `scoring_weights.yaml` | ✅ |
| The **weight-normalisation rule** makes the weights' interpretation unambiguous | §3.2 (division by the applied weight sum `W_i`; weights are relative, scale-invariant) | header comment `/ SUM(weights applied)` + `score.py` `score_frame`; data-spec §4.7 (Method row, `W_cell`) | ✅ |

**AC5 result.** The weights are configurable user inputs; every default value carries a
documented, rationalised interpretation labelled as an assumption; and §3.2 fixes the
weight-normalisation rule so the weights' meaning is unambiguous. AC5 is satisfied.

### §7.3 The four Criteria_Groups → guidance Step 3 (Requirement 7.3)

Combined-sprint **guidance Step 3** requires that all four client decision dimensions are
covered by named, measurable features — with no vague aggregate — and that defaults are
presented as assumptions. Each group is recorded against Step 3 below.

| Criteria_Group (guidance Step 3 dimension) | Covered by (Criteria) | Section | Step 3 requirement met |
| --- | --- | --- | --- |
| **Wind** | `wind_speed` (named GWA 100 m mean resource variable, not a vague "wind score") | §2.1 | ✅ Named, measurable resource Criterion with a justified hub height/variable |
| **Demand proxy** | `demand_proxy` (explicitly a Demand_Proxy allocated below the AEMO region; never "measured local demand") | §2.2 | ✅ Named, measurable proxy Criterion, honestly labelled |
| **Infrastructure** | `dist_transmission_km`, `dist_substation_km`, `inside_rez` (measurable indicators, **not** an undefined "infrastructure score") | §2.3 | ✅ Named, measurable indicators — the vague-aggregate anti-pattern is explicitly avoided |
| **Geographic / environmental** | `slope_deg` (agreed non-hard-constraint terrain Criterion; hard constraints handled upstream by S1-07) | §2.4 | ✅ Named, measurable non-hard-constraint Criterion |

**Step 3 result.** All four Criteria_Groups are covered by named, measurable Criteria; the
infrastructure dimension uses concrete indicators rather than an undefined aggregate; and the
Default_Weights (§4) are labelled documented assumptions, not objective business values. The
guidance Step 3 requirement is met for every group.

### §7.4 Screening-language audit (Property P5)

**Property P5 — screening language only.** This specification describes model output using
Screening_Language and contains **no absolute superlative claim** — no "best site",
"optimal location", "the correct answer", or equivalent — asserting that the engine
identifies an objectively best site. Every description of the engine's output frames it as
**higher-ranked candidate cells under the selected assumptions and criteria** (§1.4).

The audit distinguishes two cases and confirms both hold:

1. **No positive superlative describes model output.** The only occurrences of superlative
   terms in this document are **negation clauses that forbid such claims** (for example §1.4
   "does not identify an objectively 'best site'", and the repeated "does not identify a 'best
   site'" reminders in §2, §3, §4, §5 and §6). A clause that *prohibits* the claim is the
   commitment itself, not a violation of it — P5 forbids asserting a best site, not naming the
   thing being ruled out.
2. **Ranking mechanics use ordinal language, not superlatives.** Where the document explains
   the `rank` field it says "rank 1 is the highest-scoring eligible cell" (§3.1) — an ordinal,
   run-relative statement about the score ordering, not an absolute claim that the top cell is
   the objectively best place to build. Weights are documented assumptions (§4) and a different
   documented weighting yields a different ranking, which the document states explicitly.

**P5 result.** No absolute "best site" / "optimal" claim describes the model output anywhere
in the document; the superlatives that appear are the negation clauses that forbid such
claims. Property P5 holds.

---

## §8 Reconciliation log

_Placeholder — authored in task 8._

Line-by-line reconciliation against `pipeline/scoring/scoring_weights.yaml` and
`pipeline/scoring/`. One row per criterion: parameter, spec value, implementation value,
status (`consistent` | `resolved`), resolution. Where consistent, that consistency is
stated explicitly.
