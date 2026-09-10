"""
Opt-Mining Data Pipeline — Wind, Geographic, Infrastructure & Demand.

Domain subpackages:
    pipeline.wind           — Global Wind Atlas data investigation
    pipeline.geographic     — Boundaries, elevation, land use, protected areas
    pipeline.infrastructure — Geoscience Australia Electricity Infrastructure
    pipeline.demand         — AEMO NEM operational demand
    pipeline.grid           — Common analysis cell grid (S1-02)
    pipeline.exclusions     — Exclusion layer / Eligibility_Table (S1-07)
    pipeline.integration    — Integrated NSW Feature Table (S1-08) + Task 5 analysis

Shared utilities:
    pipeline.common.geo     — ArcGIS REST, atomic writes, banners, human_bytes
    pipeline.config         — Project-level constants (bbox, GDAL env, stages)
    pipeline.validate       — Cross-domain integration checks

Each domain subpackage exposes stage modules with a run() entry point:
    from pipeline.wind.probe import run as wind_probe
    from pipeline.geographic.download import run as geo_download
    from pipeline.infrastructure.inspect import run as infra_inspect
    from pipeline.integration.merge import run as integration_run

Usage:
    python -m pipeline                       # run all stages
    python -m pipeline --only wind           # run one domain
    python -m pipeline --only wind.probe     # run one stage
    python -m pipeline --skip demand         # skip a domain
    python -m pipeline --skip-validate       # skip cross-domain checks
"""
