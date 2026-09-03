# S1-10 — Baseline Suitability Model: Completion Notes

**Status:** Implemented, tested and documented. 500/500 tests pass (380 pre-existing + 120 new).
**Stage:** `scoring`, registered between `integration` (S1-08) and `validate`.
**Run:** `python -m pipeline --only scoring` — 1.1 s over all 47,311 cells.

---

## What was built

A transparent, deterministic weighted **multi-criteria decision analysis (MCDA)** — not a machine-learning model. Every eligible cell gets a score in [0, 1], a rank, and one contribution column per criterion showing exactly how many points of the score came from where.

### New subpackage — `pipeline/scoring/`

| Module | Responsibility |
|--------|----------------|
| `__init__.py` | Stage docstring and position in the pipeline sequence |
| `config.py` | Paths, vocabularies, tolerances — composed from upstream configs, **no weight literals** |
| `scoring_weights.yaml` | Criteria weights, directions and rationales — **the user input** |
| `weights.py` | `Criterion` / `WeightsConfig` dataclasses, `load_weights` with fail-before-write validation |
| `load.py` | `load_integrated` — the sole feature-reading path; halts on any missing column |
| `normalise.py` | `compute_bounds` / `normalise_series` — directional min-max from the eligible population |
| `score.py` | `score_frame` — the **pure** Scoring_Function (DataFrame in, DataFrame out, no I/O) |
| `rank.py` | `assign_ranks` — descending by score, ties by ascending `cell_id` |
| `write.py` | Scored_Table assembly, atomic GeoPackage + CSV writers |
| `report.py` | Method report, validation report, derived-product provenance triple |
| `validate.py` | Nine no-silent-passes checks |
| `run.py` | `run(verbose=False, ...) -> dict` stage entry point |

### Files changed outside the subpackage

- `pipeline/config.py` — `scoring` added to `STAGES` (after `integration`, before `validate`) and to `DOMAINS`
- `pipeline/__main__.py` — `_get_runner` branch, `_build_kwargs` forwarding, `--scoring-weights`, `--confidence-discount` / `--no-confidence-discount`, docstrings
- `pipeline/validate.py` — two cross-domain checks (scored `cell_id` set equals the grid; scored cells match the S1-07 eligibility flag)
- `pipeline/README.md` — stage order, architecture tree, CLI options, expected outputs, import examples, scope note
- `DATA/data-specification/sprint1_data_specification.md` — **v1.4 → v1.5**: new §4.7, §7 mapping row, §8 "Applied" paragraph, change-history entry
- `tests/test_pipeline_structure.py` — `TestScoringImports` plus stage-order and domain assertions

### New tests (120)

- `tests/test_scoring.py` — 72 unit tests: hand-computed normalisation and scores, config faults, loader faults, validation faults, ranking, confidence, missing values, run contract, orchestrator wiring
- `tests/test_scoring_properties.py` — 16 Hypothesis property tests (100+ examples each) covering all 16 design properties
- `tests/test_scoring_integration.py` — 12 full-grid tests: one row per cell, eligibility agreement, reconciliation, byte-identical regeneration, report content, **validate-against-reality**
- `tests/test_scoring_documentation.py` — 14 tests asserting the README and specification match the runtime stage configuration

---

## Results on the committed data

| Measure | Value |
|---------|-------|
| Cells | 47,311 |
| Scored (eligible) | 1,233 |
| Excluded (null score, no rank) | 46,078 |
| Score range | 0.218 – 0.932 (mean 0.646) |
| Contribution reconciliation | worst residual **4.4e-16** (tolerance 1e-9) |
| Validation | 9/9 checks pass |
| Regeneration | CSV byte-identical across reruns |

### Validate against reality

The Constitution requires checking that known successful wind development areas score highly. Both operating New England wind farms do:

| Wind farm | Score | Rank | Percentile |
|-----------|-------|------|------------|
| Sapphire Wind Farm | 0.887 | 47 / 1,233 | top 3.7% |
| White Rock Wind Farm | 0.834 | 167 / 1,233 | top 13.5% |

This is now a regression guard in the test suite (top-quartile threshold). S1-12 formalises the check.

---

## Three findings that need a reviewer's decision

All three come from the data, not the code. Each is recorded in the generated method report §7 and in specification §4.7 / §8.

### 1. Confidence is three-valued, not two

Requirements 10.2 and 14.6 specify `confidence` as exactly `high` or `low`. The S1-09 layer this stage consumes emits **three** levels — `high` 1,600 / `medium` 45,711 / `low` 0.

Collapsing `medium` into either neighbour would fabricate a confidence the data does not support, which requirement 10.4 forbids explicitly ("rather than fabricating a confidence value") and the Constitution forbids twice ("Never let poor data pass as good"; "Report confidence alongside every score").

**Decision taken:** carry the upstream value through verbatim. `CONFIDENCE_LEVELS` is composed from `integration/config.py` so it cannot drift, and validation asserts membership — an unexpected value is still an explicit failure. On the current data every scored cell is `high`, so the two-value expectation holds observationally for the scored population.

### 2. `demand_proxy` is constant across every eligible cell

Its eligible-population min and max are both 1.0, because the S1-04 MVP proxy allocates one NEM-region annual mean uniformly. This triggers the constant-criterion rule in the **real** run, not only in theory.

**Consequence:** `demand_proxy` adds a flat 0.15 to every eligible score. It cannot discriminate between cells and **cannot change the ranking** — the shipped model effectively ranks on five criteria, not six. It inflates absolute scores without adding information. The method report flags this on every run and names the criterion.

This resolves when the demand proxy is disaggregated below the NEM region. Until then, read the absolute scores with that 0.15 in mind.

### 3. The two spec documents disagree on the default weights

The ticket specifies wind 0.35 / substation 0.10; `design.md` shows wind 0.30 / substation 0.15 but labels its example "illustrative".

**Decision taken:** the ticket's values, because they are already quoted in `pipeline/integration/confidence_weights.yaml` and in specification §4.5. Using the design's numbers would have left the repository contradicting itself in three places.

---

## One rule the specification did not cover

**Null criterion values for an eligible cell.** Requirements 1.5 halts when a criterion *column* is missing, but nothing states what happens when a *value* is null.

**Rule implemented:** the criterion is excluded from that cell's weighted average and the denominator is the sum of the weights actually applied — matching requirement 5.1's own phrase, "the sum of the applied Criterion weights". The contribution column is null. Scoring the gap as zero would penalise a cell for a deficiency in the data rather than a property of the land.

A cell where *no* criterion has a value would have a zero denominator; it receives a null score and is reported explicitly by validation rather than becoming an infinity. On the current data no eligible cell is missing a criterion, so every scored cell used the full weight sum.

---

## One bug found and fixed

`validate()` raised a numpy broadcasting error when handed a table with the wrong row count, instead of reporting a failure. A validator that crashes tells you less than one that fails. The eligibility check now aligns by `cell_id` rather than by row position and reports a clean FAIL on malformed input. Caught by `test_missing_row_fails`.

---

## Design decisions worth knowing

- **Boolean criteria use their definitional {0, 1} domain**, not the observed population min/max. An all-`False` `inside_rez` therefore scores 0 for every cell rather than triggering the constant fill and awarding every cell full marks for a benefit none of them has.
- **`CONSTANT_CRITERION_VALUE = 1.0`** per the design. Since a constant criterion shifts every score identically, the choice cannot affect ranking — only the absolute scale.
- **Ties break by ascending `cell_id`**, making `rank` a strict 1..n permutation rather than a dense rank with shared positions.
- **Normalisation is min-max over the eligible population**, so **scores are relative to the candidate set being compared**. A cell's 0.93 is not a portable absolute rating and will shift if the eligible population changes. This is inherent to MCDA, not a defect, but it matters for how S1-11 presents the shortlist.
- **Normalisation is linear.** A logarithmic transform for distance criteria is defensible and is noted in the report as an explicit future change rather than applied silently.
- **The confidence discount is disabled by default.** Every eligible cell is `high` confidence, so a discount would be an identical multiplier on every scored cell — it would change every score and change no ranking, which is misleading precision rather than information.

---

## Constitutional compliance

| Requirement | How it is met |
|-------------|---------------|
| "Criteria weights are user inputs, never hard-coded constants" | All weights in `scoring_weights.yaml`; a test scans the package source to assert no weight literal appears in it |
| "A recommendation the user cannot interrogate is not a recommendation" | Per-criterion contributions written for every scored cell, **verified** to reconcile on every run |
| "Never build a circular model" | `wind_speed` is an input criterion only; a property test asserts no wind prediction column exists |
| "Never let poor data pass as good" | Excluded cells get a null score, never a number; missing values are excluded from the average, not scored as zero |
| "Report confidence alongside every score" | S1-09 confidence carried through verbatim on every row |
| "Each component independently replaceable" | `score_frame` is pure — a DataFrame and a config in, a DataFrame out, no I/O |
| "CRS explicit at every boundary" | Input CRS asserted equal to EPSG:4326; the stage halts rather than reprojecting |
| "Record provenance" | Manifest, `DATA_PROVENANCE.md` block and source-register row, all labelling the table a derived product, with the `weights_config_id` that produced the scores |
| "Validate against reality" | Both operating wind farms rank in the top 14%; locked in as a regression guard |
| "No silent passes" | Nine checks, each reporting expected / observed / explicit pass-fail, all written to the report whether they pass or fail |

---

## Suggested follow-ups (not blocking S1-10)

1. **Disaggregate the demand proxy** below the NEM region so `demand_proxy` becomes a discriminating criterion rather than a constant offset.
2. **Migrate S1-07 to consume the feature tables** (already an open item in `pipeline/exclusions/__init__.py`). Eligibility is currently restricted to the New England REZ window by a raster-coverage artefact, so the 1,233 scored cells are a window rather than a statewide candidate set.
3. **Consider log-normalising the distance criteria** — a modelling judgement worth an explicit decision now that the linear default is documented.
4. **S1-11** consumes `optmining_suitability-score_2026_nsw.gpkg`; `centroid_lat` / `centroid_lon` are carried through so it need not re-join the grid.
