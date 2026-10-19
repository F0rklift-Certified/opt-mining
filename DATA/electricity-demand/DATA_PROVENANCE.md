# Electricity Demand Data Provenance

| Stage | Output | Inputs | Method | Notes |
|---|---|---|---|---|

| demand.feature | aemo_demand-proxy_2026_nsw.gpkg | AEMO demand aggregate + NEM region geometry + ABS UCL 2021 urban footprint | Urban-footprint weighted allocation (ABS UCL 2021) | Derived proxy indicator; not measured local demand |
| demand.geocode | load/nsw_zone_substation_load_points.gpkg | load/nsw_zone_substation_max_demand.csv (NSW DNSP DAPR; Ausgrid recorded + Essential POE50 forecast, MVA) + GA NSW substation points | Deterministic name-match geocoding (296/543 matched; unmatched dropped and listed in load/unmatched_substations.csv) | INTERNAL-USE: DNSP DAPR disclaimers restrict purpose, knowingly accepted — not an open licence. Max demand is load, not spare capacity or a guarantee of offtake. Weighting surface for the opt-in load_weighted method |
