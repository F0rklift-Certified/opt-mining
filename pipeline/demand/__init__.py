"""
Electricity Demand Pipeline — AEMO NEM Operational Demand.

Stages:
    1. download  — Fetch half-hourly demand ZIPs from AEMO NEMWeb
    2. validate  — Strict quality gate (duplicates, continuity, completeness)
    3. inspect   — Statistical summary and inspection report
    4. aggregate — Annual mean demand per NEM region
    5. feature — Per-cell demand proxy on the common analysis grid

Usage:
    python -m pipeline.demand                         # run all stages
    python -m pipeline.demand --only download         # run one stage
    python -m pipeline.demand --skip-download         # skip a stage
"""
