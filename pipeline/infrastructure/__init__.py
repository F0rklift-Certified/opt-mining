"""
Infrastructure Pipeline — Geoscience Australia Electricity Infrastructure.

Stages:
    1. download  — Verify pre-downloaded infrastructure files are present
    2. inspect   — Inspect substations, power lines, generators

No probe stage: infrastructure data is pre-downloaded from the GA service.

Usage:
    from pipeline.infrastructure.download import run as infra_download
    from pipeline.infrastructure.inspect import run as infra_inspect
"""
