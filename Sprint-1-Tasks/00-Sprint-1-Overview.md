# Sprint 1 — From Data Investigation to an Integrated NSW Site Dataset

**Sprint:** 1 (2 weeks)
**Status:** Not Started

---

## Objective

Build the first reproducible end-to-end NSW renewable-energy site-screening dataset and pipeline. By the end of Sprint 1, anyone on the team can select an analysis cell in NSW and see everything Opt-Mining knows about that location:

```
raw data → validation → spatial standardisation → common grid → feature engineering → exclusions → integrated site dataset
```

Sprint 0 was exploration; Sprint 1 is **controlled implementation**. The dataset universe is frozen (Task 1), the analysis cell is fixed (Task 2), and every feature is generated automatically by registered pipeline stages — no hand-prepared CSVs anywhere.

## Task Map

| # | Task sheet | Brief step | Owner | Effort |
|---|---|---|---|---|
| 1 | [Freeze the Sprint 0 Data Specification](01-Freeze-Data-Specification.md) | 1 | TBD | 1 d |
| 2 | [Finalise the Common Analysis Cell](02-Common-Analysis-Cell.md) | 2 | TBD | 1.5 d |
| 3 | [Wind Feature Layer](03-Wind-Feature-Layer.md) | 3 | TBD | 2 d |
| 4 | [Demand Feature Layer](04-Demand-Feature-Layer.md) | 4 | TBD | 2.5 d |
| 5 | [Infrastructure Features](05-Infrastructure-Feature-Layer.md) | 5 | TBD | 2.5 d |
| 6 | [Geographic & Environmental Features](06-Geographic-Environmental-Features.md) | 6 | TBD | 2 d |
| 7 | [Exclusion Layer](07-Exclusion-Layer.md) | 7 | TBD | 1 d |
| 8 | [Integrated NSW Feature Table](08-Integrated-NSW-Feature-Table.md) | 8 | TBD | 1 d |
| 9 | [Data Quality & Confidence](09-Data-Quality-and-Confidence.md) | 9 | TBD | 0.5 d |
| 10 | [Baseline Suitability Model](10-Baseline-Suitability-Model.md) | 10 | TBD | 1 d |
| 11 | [Ranked Shortlist + Query CLI](11-Ranked-Shortlist-and-Query-CLI.md) | 11 | TBD | 1 d |
| 12 | [Validation / Sanity Check & Signoff](12-Validation-and-Sanity-Check.md) | 12 | TBD (all review) | 1.5 d |

## Dependency Graph

```
01 Decision freeze (Day 1 — gates everything)
        │
02 Grid & cell index
        │
   ┌────┼────────┬──────────┐
03 Wind  04 Demand  05 Infra  06 Geographic     ← parallel, one per person-thread
   └────┴────┬───┴──────────┘
07 Exclusion layer
        │
08 Integrated feature table
        │
09 Quality & confidence
        │
10 Baseline suitability model
        │
11 Shortlist + query CLI
        │
12 Validation & signoff
```

Two substeps do **not** wait for Task 2 and start Day 1 in parallel: **4a** — ABS SA2 ERP acquisition + AEMO demand re-download (the raw data is gitignored and absent locally); **5a** — EnergyCo REZ format spike + scipy pin (the sprint's riskiest technical item: the REZ boundaries are shapefiles and the frozen dependency set has no vector driver).

## Two-Week Timeline

| Days | Thread A | Thread B | Thread C |
|---|---|---|---|
| 1 | 01 decision freeze | 4a ERP + AEMO re-download | 5a REZ spike + scipy |
| 2–3 | 02 grid | 04 demand allocation | 05 infrastructure distances |
| 4–5 | 03 wind | 04 finish → 06 support | 05 finish → 06 geographic |
| 6–7 | 07 exclusions → 08 table | 06 (NLUM/CAPAD half) | 06 (SRTM half) → 12 check design |
| 8–9 | 09 quality, review | 10 scoring → 11 shortlist/CLI | 12 validation |
| 10 | signoff, buffer | 11 polish | 12 report |

Critical path: 02 → slowest of {03..06} → 07 → 08 → 09 → 10 → 11 → 12.

## Frozen Decisions (recorded by Task 1)

Q1 wind statistic: **mean** default, p90 carried, max explanation-only · Q2 height: **100 m** primary, 150 m sensitivity · Q3 slope: **mean** penalty input, p90 reported · Q4 population: **ABS SA2 Census 2021 ERP** · Q5 demand: **Operational Demand** · Q6 protected areas: **binary** CAPAD exclusion · Q7 infrastructure distance: **continuous, no hard threshold** · New: `min_land_fraction = 0.5` land rule. All remain configurable parameters — never hard-coded.

Sprint-level implementation decisions: delivery = files + `python -m pipeline.query` CLI (no web map this sprint) · dependencies = **scipy only** added (polygon work via rasterize, no geopandas/shapely; CSV primary, no Parquet/pyarrow) · `distance_to_nearest_connection_point` **dropped** (AEMO KCI has no coordinates; `dist_substation_km` is the honest measurable).

## Definition of Done

Fresh clone + `pip install -r requirements.txt` + network, this sequence completes without manual data preparation:

```
python -m pipeline --only demand                    # 3-yr AEMO window regenerated
python -m pipeline --only grid.build
python -m pipeline --only features.wind
python -m pipeline --only features.demand
python -m pipeline --only features.infrastructure
python -m pipeline --only features.geographic
python -m pipeline --only exclusions.apply
python -m pipeline --only features.assemble         # integrated table (+ quality flags)
python -m pipeline --only score.rank                # score, rank, shortlist
python -m pipeline --only integration.validate      # ground-truth checks
python -m pipeline.query --lat -29.75 --lon 151.51  # White Rock area: eligible, high rank
python -m pipeline.query --cell-id <same-cell>      # identical card by id
pytest                                              # all offline tests green
```

Expected artifacts:

- `DATA/DATA_SPECIFICATION.md` — frozen spec, grid ratification, integrated-table schema, all decisions dated
- `DATA/grid/optmining_grid-cells_0.05deg_nsw.csv` + manifest/report
- `DATA/features/optmining_{wind,demand,infrastructure,geographic}-features_0.05deg_nsw.csv` + reports
- `DATA/integrated/optmining_site-screening_0.05deg_nsw.csv` / `.geojson` / `.meta.json`
- `DATA/integrated/optmining_exclusions_0.05deg_nsw.csv` + `metadata/exclusion_summary.md`
- `DATA/integrated/metadata/quality_report.md`
- `DATA/integrated/optmining_shortlist_0.05deg_nsw.csv` + `scoring_run.meta.json`
- `DATA/integrated/metadata/validation_integration.md`
- Updated `pipeline/README.md` (decision column, new stages, query usage); Task 5 §9 decision cells filled; no `_[Team decision]_` placeholders anywhere

And: White Rock + Sapphire are eligible and rank in the agreed top share; every excluded cell carries a human-readable reason; every failed validation check has a written explanation and follow-up item.

## Signoff

*Appended by Task 12 at sprint end: task → final status → deviations from sheet.*
