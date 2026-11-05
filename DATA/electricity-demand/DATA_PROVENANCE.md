# Electricity Demand Data Provenance

| Stage | Output | Inputs | Method | Notes |
|---|---|---|---|---|

| demand.feature | aemo_demand-proxy_2026_nsw.gpkg | AEMO demand aggregate + NEM region geometry + geocoded NSW zone-substation max demand (DNSP DAPR) | Measured/forecast zone-substation load weighted allocation (NSW DNSP DAPR; internal-use) | Derived proxy indicator; not measured local demand |
| demand.geocode | load/nsw_zone_substation_load_points.gpkg | load/nsw_zone_substation_max_demand.csv (NSW DNSP DAPR; Ausgrid recorded + Essential POE50 forecast + Endeavour recorded, MVA) + GA(open) + OSM(ODbL) + Nominatim(ODbL) substation references + Endeavour portal coordinates | Coordinates-present fast-path for Endeavour portal rows (coord_source=portal), else deterministic GA->OSM->Nominatim name-match geocoding (677/709 matched: portal 166 + GA 296 + OSM 160 + Nominatim 55; unmatched name-only rows dropped and listed in load/unmatched_substations.csv) | INTERNAL-USE: DNSP DAPR disclaimers restrict purpose, knowingly accepted — not an open licence. Coordinates: OSM/Nominatim ODbL + GA open + Endeavour portal (not OSM); demand magnitudes restricted DNSP DAPR. Max demand is load, not spare capacity or a guarantee of offtake. Weighting surface for the load_weighted method (the default allocation method; uniform and urban_weighted remain selectable) |
