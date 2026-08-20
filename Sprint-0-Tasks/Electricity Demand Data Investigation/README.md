# Electricity Demand Data Investigation — MOVED

The pipeline scripts that previously lived here have been consolidated into a single orchestrated pipeline at:

    pipelines/demand/

## New Location

```
pipelines/demand/
├── __main__.py      # CLI orchestrator
├── config.py        # Shared configuration
├── download.py      # Stage 1: Download from AEMO NEMWeb
├── validate.py      # Stage 2: Quality gate (6 checks)
├── inspect.py       # Stage 3: Statistical summary
├── aggregate.py     # Stage 4: Annual regional summary (NEW)
└── README.md        # Full documentation
```

## Usage

```bash
# From project root:
python -m pipelines.demand                    # full pipeline
python -m pipelines.demand --only aggregate   # single stage
python -m pipelines.demand --skip-download --input-csv path/to/csv
```

## What Remains Here

- `02-Electricity-Demand-Data-Investigation.md` — Original investigation documentation (Task 2)
- `DATA_PROVENANCE.md` — Data provenance record
- `aemo_operational_demand_daily_2025.csv` — Original sample data
- `inspection_summary.txt` — Original inspection output
- `raw/` — Raw AEMO ZIP archives

These are kept for reference. The canonical pipeline code is now at `pipelines/demand/`.
