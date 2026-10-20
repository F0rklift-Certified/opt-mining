# NSW zone-substation load data — geocoding & the `load_weighted` demand method

This directory holds the real NSW DNSP zone-substation **maximum-demand** data and
the geocoded load-point layer that drives the opt-in `load_weighted` demand
allocation method (`pipeline.demand.feature`). See **`SOURCES.md`** in this
directory for the full acquisition log, extraction method, per-row caveats,
10-row verification and the licence findings — this README only summarises the
geocoding and the model.

## Files

| File | What it is |
|---|---|
| `nsw_zone_substation_max_demand.csv` | The canonical extract: **709** zone substations. `max_demand` is in **MVA**. The 543 Essential+Ausgrid rows are **name-only** (`latitude`/`longitude`/`locality` blank); the 166 appended Endeavour rows carry **precise portal coordinates** (blank `locality`). |
| `endeavour_portal/` | The Endeavour DAPR portal pop-up extraction: `endeavour_zone_substation_max_demand.csv` (166 rows, project schema, WITH coordinates), `endeavour_zone_substation_full_panel_detail.csv` (reference), `SOURCES_endeavour.md` (full provenance, licence, 10-row re-verification) and `screenshots/`. |
| `nsw_zone_substation_load_points.gpkg` (layer `load_points`) | Derived, geocoded load points (EPSG:4326) — the weighting surface for `load_weighted`. Built by `pipeline.demand.geocode_load`. Carries `coord_source` (`portal`/`ga`/`osm`/`nominatim`) and the booleans `osm_low_confidence` and `nominatim_low_confidence` alongside the existing columns. |
| `unmatched_substations.csv` | The **name-only** substations that could NOT be geocoded by any of the three name sources and were **dropped** (never given invented coordinates). Portal rows never appear here. Listed for review. |
| `raw/` | The unmodified source workbooks/PDFs (Essential, Ausgrid, Endeavour). SHAs in `SOURCES.md`. |

## Coverage & the data as it stands (honest summary)

- **Ausgrid — 177 rows**: *recorded* peak demand, summer 2024/25 (MVA).
- **Essential — 366 rows**: POE50 **forecast** peak demand, summer 2025/26 (MVA). Essential publishes no recorded per-substation maximum.
- **Endeavour — 166 rows**: *recorded* actual peak demand, higher of summer/winter 2025 `Actual (MVA)` (MVA), extracted from the Endeavour DAPR portal map pop-ups and appended with **precise portal coordinates**. This closes the last real coverage gap — Greater Western Sydney / Blue Mountains / Illawarra / South Coast now carry **direct load points** (previously 0). The 20 proposed/no-recorded-demand Endeavour substations are **excluded at source** and never enter the CSV (see `endeavour_portal/SOURCES_endeavour.md`).

The file therefore **mixes forecast and recorded** figures (Essential is
forecast; Ausgrid and Endeavour are recorded) and includes some
**sub-transmission / voltage-split** rows (e.g. `Terranora 110/66kV`,
`Cudgen 11kV`/`Cudgen 33kV`). All are MVA and all are kept; the model uses only
the *relative* shape (see below), but the forecast-vs-recorded mix is a real
like-with-unlike limitation. The Endeavour **season-year label** is ambiguous
(the DAPR PDF reads 2025 as both 2024/25 and 2025/26 in different places — see
`endeavour_portal/SOURCES_endeavour.md`); this is **immaterial to the
shape-based model**, which uses only the relative MVA magnitudes.

## Geocoding (how the points got coordinates)

`pipeline.demand.geocode_load` gives each substation a coordinate. Rows that
**already carry** a valid coordinate (the 166 Endeavour portal rows) take a
**coordinates-already-present fast-path** and are emitted directly; the name-only
rows (Essential/Ausgrid) are geocoded from three sources, **GA primary + OSM
second + Nominatim third**, all deterministic and all name-only (those load rows
carry no locality):

0. **Portal fast-path (coordinates already present).** Any demand row whose
   `latitude`/`longitude` is non-empty and inside the NSW bounding box
   (`config.NSW_BBOX_*`) is a **precise** point and is emitted directly with
   `coord_source="portal"` and GA-precise confidence — it **bypasses**
   GA/OSM/Nominatim entirely (re-geocoding a point we already have by name would
   be lossy and could relocate it). These are the Endeavour DAPR portal
   positions (WGS84). A row with blank/non-numeric/out-of-NSW coordinates is
   **not** trusted and falls through to the name tiers below.
1. **Geoscience Australia (primary).** Match the substation name against the GA
   NSW substation point layer
   (`DATA/infrastructure/substations/ga_substations_2026_nsw.geojson`, 586
   points). Normalise both sides: lower-case, **strip voltage suffixes**
   (`110/66kV`, `33/11kV`, `11kV`, `132kV` …), drop punctuation, collapse
   whitespace. Join on the normalised name; where several GA points share one
   normalised name pick one deterministically by `(locality, latitude,
   longitude)`. A GA hit emits `coord_source="ga"`.
2. **OpenStreetMap (second).** On a GA miss, match against the OSM NSW named
   `power=substation` layer
   (`DATA/infrastructure/substations/osm_substations_nsw.geojson`, built by
   `scripts/_acquire_osm_substations_nsw.py`). OSM names its sites `Campsie Zone
   Substation` / `Boronia Street ZS`, so OSM-side normalisation additionally
   **strips the site suffix** (`zone substation`/`substation`/`ZS`/`ZSS`) and
   applies a conservative street-abbreviation expansion (`St`→`Street`,
   `Dr`→`Drive`, `Cr`→`Crescent`, `Rd`→`Road`, `Mt`→`Mount`). An OSM hit passes
   an **operator-agreement gate** — where the OSM element carries an `operator`
   it must match the row's DNSP (ausgrid↔`Ausgrid`, essential↔`Essential
   Energy`, endeavour↔`Endeavour Energy`) — then emits `coord_source="osm"`,
   flagged `osm_low_confidence` where the operator is absent or the match needed
   abbreviation expansion. Duplicate OSM names resolve by `(operator, latitude,
   longitude)`.
3. **Nominatim (OSM place-geocoding, third).** On a GA **and** OSM miss, match
   the name against the Nominatim snapshot
   (`DATA/infrastructure/substations/nominatim_substations_nsw.geojson`, built by
   `scripts/_acquire_nominatim_substations_nsw.py`). Nominatim is a **place
   geocoder**: `"<name> NSW"` returns a **suburb/locality CENTROID**, not the
   substation itself — typically a few km off. That is acceptable **only**
   because `load_weighted` uses a 15 km distance-decay / 40 km radius (see the
   model below), so a centroid still lands in the right decay neighbourhood. It
   is therefore strictly a **lower-confidence** tier: every Nominatim hit emits
   `coord_source="nominatim"` with `nominatim_low_confidence=True` **always**,
   and is never mixed with GA/Overpass precision — an analyst can filter or
   down-weight these cells. The acquisition applies hard safeguards (NSW bounding
   box, `class ∈ {boundary, place}` allow-list, a tuned importance floor of
   **0.15**, and a one-shot base-name fallback that strips a trailing
   directional/descriptor qualifier). Nominatim never overrides a GA or OSM hit.
4. **Unmatched by all three sources are dropped** (coordinates are never
   invented) and written to `unmatched_substations.csv`.

**Match rate: 677 of 709 substations matched (≈95.5%) — portal 166 + GA 296 +
OSM 160 + Nominatim 55; 21 OSM matches and all 55 Nominatim matches flagged
low-confidence; 32 unmatched/dropped.** The 166 Endeavour rows match via the
portal fast-path (precise, never low-confidence). OSM closes the Sydney-metro gap the GA
transmission layer lacked (Campsie, City South, Chatswood, Mascot, Manly,
Miranda, Lidcombe, Darling Harbour, Port Botany …, operator-confirmed as
Ausgrid). Nominatim then recovers the Ausgrid Hunter/Newcastle distribution
substations neither layer carries as features (Metford, Edgeworth, Cessnock
South, Nelson Bay, Croudace Bay, Raymond Terrace, Mount Hutton, Swansea,
Stockton, New Lambton …) plus a tail of small Essential localities, as suburb
centroids. The residual 32 are genuine **non-place asset names** that must stay
dropped (`Graving Dock No 1/2`, `Mitchell Line`, `RNS Hospital`, the `TransGrid …
Total … Supply` rows, `Powercor Robinvale … Euston Distribution Supply`) plus a
few sub-floor/ambiguous localities. Re-run
`python -m pipeline.demand.geocode_load` to regenerate the layer, the unmatched
list and the manifest entry (which records all three source SHAs).

### OSM / Nominatim licence / attribution (ODbL)

Both OSM-sourced coordinate tiers (OSM `power=substation` features AND Nominatim
place centroids) are **© OpenStreetMap contributors, licensed under the Open
Database License (ODbL) 1.0**
([openstreetmap.org/copyright](https://www.openstreetmap.org/copyright)). Using
them in this internal screening model with attribution satisfies ODbL; the
share-alike obligation attaches only to a *distributed* derived database, not to
internal use. The OSM snapshot manifest records the exact Overpass query, SHA and
this credit; the Nominatim snapshot manifest records the search URL, per-name
query, the safeguard thresholds, SHA, this credit, and a pointer to the
[Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/)
(≤1 req/sec, cached snapshot, never re-queried at run time). Note the provenance
split: **coordinates come from OSM(ODbL) + Nominatim(ODbL) + GA(open) +
Endeavour-portal** (the Endeavour coordinates are precise substation positions
from the Endeavour DAPR portal, **NOT** OSM), while **demand magnitudes come
from the DNSP DAPR data (restricted, internal-use — see `SOURCES.md` and
`endeavour_portal/SOURCES_endeavour.md`)**; the two carry different reuse rights.

## The model (`load_weighted`)

Real zone-substation max demand sets the within-region **shape**; the AEMO
regional aggregate (`MEAN_DEMAND_MW` per NEM region) sets the **level**. Per cell:

```
w_cell = Σ_s  load_mva_s · exp(-d(cell, s) / LOAD_DECAY_LENGTH_M)   [+ floor]
```

over geocoded substations `s` within `LOAD_SEARCH_RADIUS_M` of the cell centroid
(distances in EPSG:3577). The existing weighted branch then rescales per NEM
region so each region's total is conserved **exactly**:
`raw_cell = w_cell / Σ_region(w_cell) · MEAN_DEMAND_MW_region`. Because only the
relative shape is used, the MVA-vs-MW and forecast-vs-recorded mismatches never
affect conservation. Decay length and search radius are documented config
constants (`pipeline/demand/config.py`). Cells beyond every substation's radius
fall back to the floor and are flagged `medium`.

**The Endeavour demand gap is now closed.** Endeavour contributes **166
recorded-actual demand rows** with precise portal coordinates, so Greater
Western Sydney / Blue Mountains / Illawarra / South Coast — previously with **0**
Endeavour demand rows — now carry direct load points. Under `load_weighted` this
moved **574 cells** off the no-coverage floor and up to `high`
(floored no-coverage cells fell from 21,764 to 21,190), with the drop
**concentrated almost entirely (564 of 574) in the Endeavour footprint**: the
Illawarra/South-Coast band went from 202 floored cells to **0**, and the Blue
Mountains / outer-west fringe also improved. Much of the inner Greater Western
Sydney metro was already off the floor via nearby Ausgrid points (whose 40 km
radius reached west), so the new coverage is dominated by the peripheral regions
Ausgrid did not reach. The portal points are **precise** (not low-confidence),
so no down-weighting flag applies to them.

## Licence (internal use — documented decision)

None of the three NSW DNSPs publishes this data under an open licence; their DAPR
disclaimers restrict the purpose (see `SOURCES.md`, and
`endeavour_portal/SOURCES_endeavour.md` for Endeavour's verbatim disclaimer,
published under **NER clause 5.13.2** "should only be used for that purpose").
Use here is a **knowingly accepted INTERNAL-USE decision by the project owner**,
consistent with the Essential and Ausgrid treatment and recorded honestly. This
is **not** a grant of an open licence, and max demand is **load, not spare
capacity and not a guarantee of offtake**.

## Reproduce

```
# (one-off, manual) refresh the Nominatim place-centroid snapshot for the
# GA+Overpass-unmatched names — hits the public endpoint at <=1 req/sec; see the
# Nominatim usage policy. Normally you keep the committed snapshot and skip this.
python scripts/_acquire_nominatim_substations_nsw.py
python -m pipeline.demand.geocode_load                     # build the load-point layer (GA + OSM + Nominatim)
python -m pipeline.demand --only feature --allocation-method load_weighted
```

`load_weighted` is **opt-in**; the default allocation method stays
`urban_weighted` until the real-load surface is validated.
