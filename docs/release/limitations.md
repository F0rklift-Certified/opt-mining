# Limitations & Assumptions — S3-10 release candidate

This is a review-facing restatement of the consolidated limitations in
[`docs/technical-reference.md`](../technical-reference.md) §7. It **links** the
authoritative sources rather than forking their frozen tables; where a value is
frozen (weights, exclusion rules, provenance) the linked document remains the
source of truth.

Opt-Mining is a **preliminary screening** tool. It performs **screening-level**
analysis only: it surfaces higher-ranked candidate cells for *further
investigation* under a selected set of assumptions and criteria. It does **not**
identify the best site to build a wind farm; it is **not** the best place to
build; it is never an optimal location, a final recommendation, a site approval, a project
cost, an LCOE, an energy-yield estimate or an engineering-grade assessment.

## Core limitations

- **Screening-level only.** Results indicate *where to look next* at the
  analysis-grid resolution, not a buildable-site decision. A top-ranked cell is
  **not** the best site, and is **never** the best place, for a project — that
  determination needs site-specific investigation outside this tool.
- **Relative scores.** Normalisation bounds are computed from the *eligible*
  population on each run (min-max), so a score is relative to the candidate set
  actually compared, not a portable absolute rating. A score of 0.91 is "near
  the top of this run", not a physical quantity.
- **Demand is a proxy.** The `demand_proxy` layer is a NEM-region annual-mean
  operational-demand figure allocated **uniformly** to every cell in a region.
  It is a proxy indicator; it is **not** measured or actual local demand, so it
  discriminates only coarsely between regions and not at all within a region.
  See [`DATA/electricity-demand/demand_feature_method.md`](../../DATA/electricity-demand/demand_feature_method.md).
- **Linear normalisation.** A single linear min-max per criterion, with no
  piecewise thresholds, diminishing returns or interaction terms.
- **No cost / yield / engineering-grade modelling.** No capex/opex, LCOE,
  capacity factor, wake, grid-hosting-capacity or civil-engineering modelling is
  performed.
- **Coarse resolution (~5 km).** The ~5 km (0.05°) analysis grid and mean-wind
  aggregation bury sub-cell ridge and micro-siting signals.

## Frozen assumptions (seven team decisions)

Documented in the data specification §2 and
[`docs/technical-reference.md`](../technical-reference.md) §"Assumptions":

1. Wind aggregation statistic — mean.
2. Hub height — 100 m.
3. Slope statistic — mean for scoring / P90 in explanation.
4. Population source — ABS Census 2021 ERP at SA2.
5. Demand metric — AEMO operational demand (the proxy above).
6. Protected-area exclusion — binary.
7. Infrastructure distance — continuous penalty, no hard exclusion.

The seven frozen exclusion reason codes (`protected_area`, `missing_wind_data`,
`excessive_slope`, `urban_area`, `offshore_or_marine`, `missing_slope_data`,
`missing_demand_data`) are data in
[`pipeline/exclusions/exclusion_rules.yaml`](../../pipeline/exclusions/exclusion_rules.yaml);
S3-10 changed none of them.

## Known gaps and Should / Could items not delivered

Listed honestly for the Checkpoint-D review. All are explicitly deferred by the
guidance §8 (Should / Could / Out of scope) and are acceptable to omit for the
MVP:

- **Optional browser (Playwright) end-to-end test** (`app/web/e2e/final-demo.spec.ts`)
  — **not delivered**. Kept Should-level; headless-browser CI is heavier and
  flakier, and the §10 flow is already covered end-to-end by
  `tests/integration/test_e2e_dataset_engine_app.py`, `app/smoke_test.py` and
  the rehearsal gate `tests/backend/test_demo_rehearsal.py`.
- **Commercial-grade UI polish / branding** — not in scope for the MVP shell.
- **National expansion** — the tool is fixed to NSW; other states/national
  coverage is a separate, change-controlled effort.
- **Additional datasets** (e.g. finer demand, cadastre, environmental overlays
  beyond the frozen set) — deferred.

## Reference-check caveats (honest anomalies)

The sanity stage checks the screening against defensible reference locations and
**discloses** divergences rather than tuning them away. The model is **not**
trained or fitted to reproduce known wind-farm or REZ locations, so overlap is
corroboration, not a fitted target. From the live rehearsal
([`rehearsal.json`](rehearsal.json)):

- Most known wind farms land in the upper quartile; `Bodangora Wind Farm`
  reaches the top band (rank 2).
- `Boco Rock` is an honest divergence — outside the upper quartile (rank 11,225,
  ~65th percentile) — disclosed, not suppressed.
- `Taralga Wind Farm` and `Rye Park Wind Farm` have null rank/percentile because
  their nearest grid cell is excluded/unscored.
- `contradiction_count` = 2, surfaced in the panel rather than hidden.

See [`demo-script.md`](demo-script.md) for the step-8 walkthrough and
[`readiness.json`](readiness.json) for the AC-by-AC evidence map.
