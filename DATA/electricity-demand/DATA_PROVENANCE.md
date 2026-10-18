# Electricity Demand Data Provenance

| Stage | Output | Inputs | Method | Notes |
|---|---|---|---|---|

| demand.feature | aemo_demand-proxy_2026_nsw.gpkg | AEMO demand aggregate + NEM region geometry + ABS UCL 2021 urban footprint | Urban-footprint weighted allocation (ABS UCL 2021) | Derived proxy indicator; not measured local demand |
