# Demand proxy: from constant 0.150 to real zone-substation load

**Status:** Implemented (merged to `docs/sprint-4-final-backlog`)

**Date:** 2026-10-19 → 2026-10-21

**Scope:** `pipeline/demand/*`, the geocoding of DNSP demand data, the
integration → scoring → shortlist chain, and the demand-method default.

**Final commit:** `d85372c` (chain of work from `5f8f555` baseline).

---

## Why this document exists

This records a multi-step investigation and implementation that began with a
single question — *why does every cell show a demand value of 0.150?* — and ended
with the demand proxy being driven by real NSW zone-substation load as the default
allocation method. It captures the decisions, the evidence behind each, the data
provenance, and the honest limitations, so a future reader does not have to
reconstruct the reasoning from commit history.

---

## The starting problem

Every analysis cell showed the same demand contribution, surfaced in the app as
`0.150`. Investigation found two compounding causes:

1. **Uniform regional allocation.** The demand feature spread a single NEM-region
   annual-mean demand figure equally across every cell in the region
   (`raw_cell_demand = MEAN_DEMAND_MW_region / N_cells_region`). Every assigned
   cell therefore received an identical raw value.
2. **Per-region max normalisation on top of that.** Because all cells shared one
   raw value, `raw / region_max` normalised to `1.0` for every assigned cell.

So the stored `demand_proxy` was literally `1.0` everywhere, and `1.0 × 0.15`
(its scoring weight) produced the constant `0.150` seen on the map. This was a
documented MVP limitation, not a bug in the arithmetic.

`demand_proxy` is one of ~9 scoring criteria and carries a weight of **0.15**
(wind speed is 0.35, distance-to-transmission 0.20). It is a secondary factor.

---

## What changed, in order

The work proceeded as a sequence of investigations, each followed by an
implement-and-review workflow in an isolated git worktree. The scoring criterion
itself — `demand_proxy`, `higher_is_better`, weight `0.15`, range `[0, 1]`, one
row per cell, EPSG:4326 storage / EPSG:3577 compute, per-region demand
conservation — was **never changed**. Only the *weighting surface* that
distributes regional demand across cells changed.

### 1. Urban-footprint weighting (`urban_weighted`)

Replaced uniform allocation with a surface weighted by each cell's overlap with
ABS Urban Centres & Localities (UCL) 2021 urban footprint, reusing the existing
`_urban_overlap` spatial pattern. Demand is distributed as
`w_cell / Σ w_region × MEAN_DEMAND_MW_region`, which conserves each region's total
exactly. Result: NSW1 went from 1 distinct proxy value to 1,337; demand varies
within a region. Band multipliers were wired in but set to 1.0 (footprint-only
baseline, tunable later without a schema change). This became the new default at
the time.

Honest limit: urban footprint is a coarse proxy for electricity demand (no
load-centre or feeder data).

### 2. Real zone-substation demand (`load_weighted`)

Acquired real max-demand data from the three NSW Distribution Network Service
Providers' Distribution Annual Planning Reports (DAPRs):

- **Ausgrid** — recorded actual peak demand, summer 2024/25 (MVA).
- **Essential Energy** — POE50 forecast peak demand, summer 2025/26 (MVA);
  Essential publishes no recorded per-substation maximum.
- **Endeavour Energy** — recorded actual, extracted from the DAPR mapping-portal
  pop-ups (its figures are not published as a table); 166 zone substations.

The model: real zone-substation load sets the **shape** of demand within a
region; the AEMO regional aggregate still sets the **level**, via a per-region
rescale (`w_cell = Σ_s load_mva_s · exp(−d/d0)` over substations within a radius,
then rescaled per NEM region). This preserves exact conservation and absorbs the
MVA-vs-MW and forecast-vs-recorded mismatches, because only the relative shape is
used. `d0 = 15 km`, search radius `40 km`.

Introduced as a selectable `--allocation-method load_weighted`; the default stayed
`urban_weighted` until validated.

### 3. Geocoding the demand data (four tiers)

The DAPR demand rows carried names but (mostly) no coordinates, so substations had
to be located before their load could be placed on the grid. A deterministic,
tiered geocoder was built, each tier lower precision than the last and flagged as
such; unmatched substations are **dropped, never given invented coordinates**:

1. **GA** — Geoscience Australia substation layer (transmission-weighted; precise).
2. **OSM Overpass** — mapped `power=substation` features (precise), with an
   operator-agreement gate; recovered the Sydney-metro distribution substations GA
   lacks.
3. **Nominatim** — place/suburb centroids for substations absent from OSM
   features (lower precision; always flagged `nominatim_low_confidence`; tolerable
   only because of the 15 km decay). Recovered the Ausgrid Hunter/Newcastle block.
4. **Endeavour portal coordinates** — the Endeavour rows arrived with precise
   portal marker coordinates, so they bypass name-geocoding entirely
   (`coord_source="portal"`).

Coverage rose across these steps from 54.5% → 84.0% → 94.1%, and Endeavour added
166 precise points that closed the Western Sydney / Blue Mountains / Illawarra /
South Coast gap entirely (that region previously had zero demand data).

### 4. Baseline rebuild + demand-confidence transparency

Before changing the default, two prerequisites landed:

- **Rebuilt the stale committed chain.** The committed integration → scoring →
  shortlist outputs were still from the legacy `uniform` era (demand_proxy = 1.0).
  They were regenerated under the then-current `urban_weighted` default so the
  committed baseline reflected reality.
- **Added an informational `demand_coord_confidence` column** (high / low / n/a)
  propagated from the load points through to the scored/shortlist output, so any
  cell whose demand signal rode a low-confidence (Nominatim/OSM) substation is
  auditable. It is strictly metadata — it does not feed back into `demand_proxy`,
  the score, the weights, or the ranking (proven: score/rank bit-identical with
  and without the column).

### 5. Flipping the default to `load_weighted`

A side-by-side comparison of the shortlists under both methods informed the
decision (see "The decision to flip" below). The default was then flipped to
`load_weighted`, the full chain regenerated, and all method-report/provenance docs
updated. `uniform` and `urban_weighted` remain selectable via `--allocation-method`.

---

## The decision to flip the default

A rigorous comparison (`.agents/tasks/demand-method-comparison/`) scored the grid
under both methods, changing only the demand input, and found:

- **`load_weighted` fixes a real defect.** On eligible (rural) land,
  `urban_weighted`'s surface is effectively degenerate (3 distinct values, 72% at
  the floor). Max-normalisation then handed full demand weight to 44 out-of-state
  Queensland border cells, none in a REZ, promoting them into NSW's top-100.
  `load_weighted`'s top-100 is 100% NSW, 100% in-REZ, near measured load.
- **But demand barely moves the decision-relevant top.** At weight 0.15, the
  shortlist is governed by wind / transmission / REZ. `load_weighted`'s top-100 is
  ~98–100% identical to a demand-blind baseline. The visible shortlist payoff is
  modest; the real win is correctness and the removal of the QLD artefact.

Verdict: **flip**, because it is more accurate, built on real data, and removes a
concrete artefact — sequenced behind the baseline rebuild and the confidence tier.
Noted explicitly: if demand should *shape* the shortlist more, the lever is the
**weight (0.15)**, not the method — a separate, deliberate preference decision.

Post-flip verification confirmed the prediction: top-100 100% NSW / in-REZ, all 44
QLD artefact cells evicted, conservation exact (≤1e-6), proxy ∈ [0,1], null → low
confidence, demand weight unchanged at 0.15.

---

## Data provenance and licensing

Provenance is deliberately split, because the parts have different reuse rights:

- **Demand magnitudes** — NSW DNSP DAPR data (Ausgrid, Essential, Endeavour). The
  DAPR disclaimers restrict the data to their regulatory purpose and are **not**
  open licences. Use here is a **knowingly accepted internal-use decision by the
  project owner**, recorded in `DATA/electricity-demand/load/SOURCES.md`. This is
  not a grant of an open licence.
- **Coordinates** — GA (open), OSM and Nominatim (© OpenStreetMap contributors,
  ODbL 1.0), and Endeavour portal marker positions. The ODbL share-alike
  obligation attaches only to a *distributed* derived database, not to internal
  use; attribution is required and recorded.

Full acquisition logs, SHAs, per-row caveats and the extraction/verification notes
live in `DATA/electricity-demand/load/SOURCES.md` and
`DATA/electricity-demand/load/README.md`.

---

## Honest limitations (carried into the method reports)

- **`demand_proxy` is a proxy, not measured local demand or spare capacity.** Max
  demand is where load *is*, not a guarantee of network headroom or future offtake.
- **Mixed metrics.** Essential is forecast (POE50); Ausgrid and Endeavour are
  recorded actuals. Used only for relative shape, but it is a like-with-unlike mix.
- **Low-confidence coordinates exist.** 55 Nominatim suburb-centroid points and 21
  OSM low-confidence points are a few km off the true substation (tolerable under
  the 15 km decay). They are flagged and, at weight 0.15, do not reach the
  shortlist — but they would matter if the weight were raised.
- **Endeavour season/year label is ambiguous.** The DAPR PDF contradicts itself on
  whether "2025" means summer 2024/25 or 2025/26. Immaterial to the shape-based
  model; noted, not resolved.
- **~87 substations remain unmatched.** Genuine non-place asset names and tiny
  remote localities thin in all coordinate sources. Dropped, listed in
  `load/unmatched_substations.csv`; their absence barely affects the surface.
- **Demand is secondary.** At weight 0.15 the proxy does not decide the shortlist;
  wind, transmission and REZ membership do.

---

## Where things stand

- Default allocation method: **`load_weighted`** (real zone-substation demand
  across all three NSW DNSPs). `uniform` and `urban_weighted` remain selectable.
- Geocoding: four-tier (GA → OSM → Nominatim → Endeavour portal), ~94% of
  substations located, each tier precision-flagged, unmatched dropped not invented.
- Committed integration → scoring → shortlist outputs reflect the `load_weighted`
  default; `demand_coord_confidence` surfaces low-confidence demand signals for
  audit without affecting the ranking.
- The scoring criterion and its 0.15 weight are unchanged throughout.

## Pointers

- Pipeline: `pipeline/demand/feature.py`, `pipeline/demand/geocode_load.py`,
  `pipeline/demand/config.py` (`DEFAULT_ALLOCATION_METHOD`).
- Data & provenance: `DATA/electricity-demand/load/{README.md,SOURCES.md}`,
  `DATA/electricity-demand/demand_feature_method.md`,
  `DATA/electricity-demand/DATA_PROVENANCE.md`.
- Analysis behind the flip: `.agents/tasks/demand-method-comparison/findings.md`
  (and the earlier `.agents/tasks/spatial-demand-weighting/`,
  `real-load-demand-data/`, `osm-substation-geocoding/`,
  `nominatim-geocode-fallback/` investigation reports).
