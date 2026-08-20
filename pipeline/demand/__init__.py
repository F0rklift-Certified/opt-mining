"""
Electricity Demand Pipeline — AEMO NEM Operational Demand.

Stages:
    1. download  — Fetch half-hourly demand ZIPs from AEMO NEMWeb
    2. validate  — Strict quality gate (duplicates, continuity, completeness)
    3. inspect   — Statistical summary and inspection report
    4. aggregate — Annual mean demand per NEM region (clean CSV for Task 5)

Usage:
    python -m pipelines.demand                        # run all stages
    python -m pipelines.demand --only download        # run one stage
    python -m pipelines.demand --skip-download        # skip a stage
"""
