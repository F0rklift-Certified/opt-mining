"""
Infrastructure Pipeline — Geoscience Australia Electricity Infrastructure.

Stages:
    1. download  — Verify pre-downloaded infrastructure files are present
    2. inspect   — Inspect substations, power lines, generators
    3. features  — Build per-cell infrastructure features on the common grid

No probe stage: infrastructure data is pre-downloaded from the GA service.

Usage:
    from pipeline.infrastructure.download import run as infra_download
    from pipeline.infrastructure.inspect import run as infra_inspect
"""
