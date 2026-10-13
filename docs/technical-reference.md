# Opt-Mining Technical Reference (Consolidated)

**Status:** Consolidated reference for Checkpoint D and the S3-10 demo (S3-09).
**Scope:** This is a single entry point that gathers, by linking the authoritative
sources rather than re-deciding or duplicating their frozen tables, everything a
reviewer needs: data provenance, assumptions, limitations, the scoring equations,
exclusions, default weights and the application architecture. Where a value is
frozen (weights, formula, exclusion rules), the authoritative copy stays in its
source document and this page links to it; this page does not fork a second copy.

> ⚠️ **Screening-level tool — read this first.** The Opt-Mining platform performs
> **preliminary screening**. It surfaces higher-ranked candidate cells for
> *further investigation* under a selected set of assumptions and criteria. It
> does **not** identify "the best site to build a wind farm", a "best place to
> build", an optimal location or a final recommendation — and it is never a site
> approval, a project cost, an LCOE, an energy-yield estimate or an
> engineering-grade assessment. Results are produced at the ~5 km (0.05°)
> analysis-grid resolution and indicate only *where to look next*. The
> screening-language commitment is frozen in the Decision-Engine Specification
> [§1.4 Screening language commitment](../Sprint-2-Tasks/decision_engine_specification.md).

> ⚠️ **The electricity demand layer is a PROXY.** `demand_proxy` is a normalized
> proxy *indicator*, **never** measured or actual local demand. It is a NEM-region
> annual-mean operational demand figure allocated **uniformly** to every cell in
> the region, so it discriminates only coarsely between regions and not at all
> within a region. See the method report,
> [`DATA/electricity-demand/demand_feature_method.md`](../DATA/electricity-demand/demand_feature_method.md),
> and data specification §4.2.3. It is described as a proxy everywhere it appears.

---

## 1. Application architecture

The platform follows the Constitution's **data → criteria → scoring →
presentation** separation. Each stage is auditable and the browser contains no
decision logic.

- **Pipeline / engine (Python).** The modular geospatial pipeline builds the
  per-cell feature layers, applies exclusions, integrates them into one frozen
  table, scores and ranks the eligible cells, explains every cell and emits the
  ranked shortlist and sanity check. See the pipeline architecture and stage
  execution order in [`pipeline/README.md`](../pipeline/README.md)
  (sections *Architecture* and *Stage Execution Order*).
- **Decision service (HTTP + OpenAPI).** The S2-08 `Decision_Service`
  (`pipeline.service`) re-materialises the Scored_Table from the frozen
  integrated table at request time and serves the eight read operations over an
  auto-generated OpenAPI contract. The boundary is fixed as HTTP + OpenAPI (not
  an in-process module) — see
  [`docs/adr/ADR-0003-web-stack-nextjs-fastapi-http-openapi.md`](adr/ADR-0003-web-stack-nextjs-fastapi-http-openapi.md).
- **Web app (Next.js / React).** A thin, decision-free client generated from the
  FastAPI OpenAPI contract. It renders service-returned values only and performs
  no scoring, normalisation, ranking or exclusion. See
  [`app/README.md`](../app/README.md) and
  [`app/docker-compose.yml`](../app/docker-compose.yml).

The full stack boots with a single command (`docker compose up --build` from
`app/`); the pipeline runs with a single command (`python -m pipeline`). Both are
documented in the clean-environment run guides in `pipeline/README.md` and
`app/README.md`.

---

## 2. Data provenance

Every dataset — custodial and derived — is recorded in the authoritative
**[Sprint 1 Data Specification](../DATA/data-specification/sprint1_data_specification.md)**
(source, variables, units, CRS, resolution, temporal coverage, licence,
limitations and pipeline use). No data enters the pipeline without an entry
there. Datasets considered but excluded are in
[`sprint1_out_of_scope.md`](../DATA/data-specification/sprint1_out_of_scope.md).

Per-domain generated provenance (SHA-256, byte counts, inputs and regeneration
command for each derived layer) lives in the `DATA_PROVENANCE.md` files:

- Electricity demand (proxy): [`DATA/electricity-demand/DATA_PROVENANCE.md`](../DATA/electricity-demand/DATA_PROVENANCE.md)
- Geographic / environmental: [`DATA/geographic/DATA_PROVENANCE.md`](../DATA/geographic/DATA_PROVENANCE.md)
- Infrastructure: [`DATA/infrastructure/DATA_PROVENANCE.md`](../DATA/infrastructure/DATA_PROVENANCE.md)
- Integrated feature table: [`DATA/integration/DATA_PROVENANCE.md`](../DATA/integration/DATA_PROVENANCE.md)
- Baseline suitability score: [`DATA/scoring/DATA_PROVENANCE.md`](../DATA/scoring/DATA_PROVENANCE.md)
- Site explanations: [`DATA/explanation/DATA_PROVENANCE.md`](../DATA/explanation/DATA_PROVENANCE.md)
- Ranked shortlist: [`DATA/shortlist/DATA_PROVENANCE.md`](../DATA/shortlist/DATA_PROVENANCE.md)
- Validation / sanity report: [`DATA/sanity/DATA_PROVENANCE.md`](../DATA/sanity/DATA_PROVENANCE.md)

The wind-resource provenance and aggregation decisions are documented from
`pipeline/README.md` and the data specification §4.1.

---

## 3. Assumptions

The seven frozen team decisions that materially affect scoring are recorded in
data specification **§2 Team Decisions (Frozen Parameters)**: wind aggregation
statistic (Q1, mean), primary hub height (Q2, 100 m), slope statistic (Q3, mean
for scoring / P90 in explanation), population source (Q4, ABS Census 2021 ERP at
SA2), demand metric (Q5, AEMO operational demand), protected-area exclusion
threshold (Q6, binary — any CAPAD intersection excludes) and infrastructure
distance (Q7, continuous penalty, no hard exclusion).

The default-weight rationale (why each criterion carries the weight it does) is
documented per criterion in
[`pipeline/scoring/scoring_weights.yaml`](../pipeline/scoring/scoring_weights.yaml)
and frozen in the
[Decision-Engine Specification](../Sprint-2-Tasks/decision_engine_specification.md)
(§4). Weights are **user inputs**, not hard-coded constants — retune by editing
the YAML.

---

## 4. Scoring equations

The scoring stage (S1-10, `pipeline/scoring/`) is a transparent, deterministic
**weighted multi-criteria decision analysis (MCDA)** — not a machine-learning
model. For each eligible cell and criterion *i*:

```
norm_i    = (v_i - min_i) / (max_i - min_i)          direction higher_is_better
norm_i    = 1 - (v_i - min_i) / (max_i - min_i)      direction lower_is_better
contrib_i = weight_i * norm_i / W_cell
score     = SUM_i contrib_i                          -> [0, 1]
```

`W_cell` is the sum of the weights actually applied to that cell. Normalisation
bounds (`min_i`, `max_i`) are computed from the **eligible** population on each
run — never hard-coded — so the scale adapts to the candidate set being compared.
Boolean criteria use their definitional `{False -> 0.0, True -> 1.0}` domain; a
criterion constant over the eligible population is filled with a documented
constant and flagged. `rank` 1 is the highest-ranked cell; ties break by
ascending `cell_id`. Every criterion's additive `contrib_{feature}` is written to
the table and verified to sum back to the score on every run.

Authoritative sources: data specification
[§4.7 Baseline Suitability Score](../DATA/data-specification/sprint1_data_specification.md),
the [Decision-Engine Specification](../Sprint-2-Tasks/decision_engine_specification.md)
and the formula header in
[`pipeline/scoring/scoring_weights.yaml`](../pipeline/scoring/scoring_weights.yaml).

---

## 5. Default weights

The six default criteria weights (sourced from
[`pipeline/scoring/scoring_weights.yaml`](../pipeline/scoring/scoring_weights.yaml);
stated here as defaults, not re-decided):

| Criterion | Default weight | Direction | Role |
|-----------|----------------|-----------|------|
| `wind_speed` | 0.35 | higher is better | primary resource indicator |
| `dist_transmission_km` | 0.20 | lower is better | connection cost (≥132 kV line distance) |
| `demand_proxy` | 0.15 | higher is better | offtake prospects (**proxy**, see §2 banner) |
| `dist_substation_km` | 0.10 | lower is better | interconnection complexity |
| `slope_deg` | 0.10 | lower is better | civil-works cost / siting room |
| `inside_rez` | 0.10 | higher is better | REZ policy signal (boolean) |

Weights are relative (the score divides by the sum of applied weights), so the
defaults summing to 1.00 is for readability only. The per-criterion rationale is
in the YAML and frozen in the Decision-Engine Specification §4.

---

## 6. Exclusions

Only eligible cells are scored; the S1-07 exclusion layer rejects ineligible land
so it is never ranked as if it were developable. Exclusion is a separate,
auditable stage — never hidden inside scoring. Rules are **data**, loaded from
[`pipeline/exclusions/exclusion_rules.yaml`](../pipeline/exclusions/exclusion_rules.yaml);
a cell may trigger several. The seven frozen F16 reason codes
(Decision-Engine Specification §6.5) are:

1. `protected_area` — any CAPAD protected-area overlap (binary, frozen decision Q6)
2. `missing_wind_data` — no valid wind-resource value
3. `excessive_slope` — mean slope above the threshold (default 15°)
4. `urban_area` — overlaps an ABS Urban Centre/Locality polygon
5. `offshore_or_marine` — cell centre is not on land
6. `missing_slope_data` — no valid slope value
7. `missing_demand_data` — no valid demand-proxy value

Authoritative source: data specification
[§4.6 Eligibility Table](../DATA/data-specification/sprint1_data_specification.md).

---

## 7. Limitations (consolidated)

These cross-cutting limitations are consolidated here from data specification
§4.5–§4.7 and the Decision-Engine Specification. They are important and must be
read with any result:

- **Screening-level only.** The platform surfaces higher-ranked candidate cells
  for further investigation under the selected assumptions — never a "best site"
  / "best place to build" claim, a site approval or an engineering assessment.
- **Relative scores.** Normalisation is min-max over the eligible population, so a
  cell's score is **relative to the candidate set** and is not a portable absolute
  rating; it changes if the eligible population changes.
- **Demand is a proxy.** `demand_proxy` is a uniform NEM-region allocation (never
  measured local demand), so it discriminates only coarsely between regions and
  not within a region; the ranking is driven mostly by the other five criteria.
- **Linear normalisation.** Distance criteria are normalised linearly; a
  logarithmic transform is defensible but is an explicit future modelling choice.
- **No cost/yield/engineering grade.** The score is a strategic screening
  indicator only — never a project cost, LCOE, yield estimate or engineering-grade
  assessment.
- **Coarse resolution.** Results are at the ~5 km (0.05°) analysis-grid resolution;
  the mean-wind aggregation (Q1) buries sub-cell ridge signals.

---

## 8. Reproducible run

See the clean-environment run guides:

- Pipeline / engine single-command run — `pipeline/README.md`,
  *Clean install & single-command run*.
- Full application stack single-command run — `app/README.md`,
  *Clean-environment reproducible run*.
- End-to-end test (frozen dataset → engine → app output) —
  `tests/integration/test_e2e_dataset_engine_app.py`, run with
  `pytest -v -m "not integration" --ignore=tests/backend tests/integration`.
