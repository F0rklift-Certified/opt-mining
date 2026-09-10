# S1-09: Data Quality and Confidence Layer

**Type:** Story  
**Priority:** Medium  
**Story Points:** 3  
**Labels:** quality, confidence  
**Blocked by:** S1-08  
**Blocks:** S1-10  
**Status:** Complete  
**Completed:** 2026-09-03

---

## Objective

Add a data-quality and confidence assessment to the integrated dataset so that downstream scoring can account for certainty. Cells with low confidence should not be excluded, but their limitations must be transparent.

---

## Context

Not all cells have equal data quality. Some may have:
- Missing features (e.g. no demand proxy for remote areas)
- Low-resolution source data (e.g. wind data interpolated over a large area)
- Known data limitations documented in S1-01

The Constitution requires: "Report confidence alongside every score" and "Where non-critical data is missing or low confidence, retain and flag it. Never silently assign a normal ranking to a poorly evidenced cell."

---

## Deliverables

1. Confidence scoring methodology document
2. Per-cell confidence score/flag added to the integrated table
3. Summary report on data quality distribution

---

## Acceptance Criteria

- [x] Each cell in the integrated table has a composite `data_confidence` score or categorical flag (e.g. high / medium / low)
- [x] Confidence reflects:
  - Number of missing or null features
  - Spatial resolution mismatch between source data and cell size
  - Known data limitations (from S1-01 specification)
  - Distance from nearest measured/modelled data point (if applicable) — not applicable to any Sprint 1 source; stated in the methodology
- [x] Confidence methodology is documented:
  - How is the composite score calculated?
  - What thresholds define high/medium/low?
  - Which features are weighted more heavily?
- [x] Cells with low confidence are **not excluded** but clearly flagged
- [x] Per-feature confidence flags (from S1-03 through S1-06) are preserved in the integrated table
- [x] Summary report includes:
  - Distribution of confidence scores (histogram or table)
  - Count of cells at each confidence level
  - Geographic pattern of low-confidence areas (are they clustered?)
  - Most common reason for reduced confidence

---

## Confidence Scoring Approach (Suggested)

```
For each cell:
  completeness = count(non_null_features) / total_features
  resolution_match = average(feature_resolution_scores)  # 1.0 = native match, 0.5 = interpolated
  
  confidence = weighted_average(completeness, resolution_match)
  
  If confidence >= 0.8 → "high"
  If confidence >= 0.5 → "medium"
  If confidence < 0.5  → "low"
```

---

## Example Output (added to integrated table)

| cell_id | ... features ... | data_confidence | confidence_score | confidence_notes |
|---------|-----------------|-----------------|------------------|------------------|
| NSW001  | ...             | high            | 0.92             | —                |
| NSW002  | ...             | medium          | 0.67             | Missing demand proxy |
| NSW003  | ...             | low             | 0.41             | Missing wind data, low-res elevation |

---

## Summary Report Example

```
Data Quality Summary — Sprint 1 Integrated Table
=================================================
Total cells:    12,847

Confidence Distribution:
  High (≥0.8):    8,924 (69.5%)
  Medium (0.5–0.8): 2,891 (22.5%)
  Low (<0.5):     1,032 (8.0%)

Most Common Quality Issues:
  1. Missing demand proxy data:     1,456 cells
  2. Low-resolution wind data:        892 cells
  3. Incomplete land-use coverage:    634 cells

Geographic Patterns:
  Low-confidence cells concentrated in western NSW 
  (sparse population data, limited infrastructure mapping)
```

---

## Technical Notes

- This is a metadata/quality layer, not a filter — it does not remove cells
- The confidence score will be used by the scoring model (S1-10) to weight or caveat results
- Per the Constitution: "Report confidence alongside every score"
- Consider whether confidence should influence the suitability score directly or be reported alongside it

---

## Completion Notes

- Implemented as `pipeline/integration/confidence.py` with its configuration in `pipeline/integration/confidence_weights.yaml`, applied **inside the `integration` stage** (S1-08) between the join and validation via `merge.attach_confidence()`. The three columns `data_confidence`, `confidence_score`, `confidence_notes` are appended to the Integrated NSW Feature Table (GeoPackage and CSV), so S1-10 reads one table. `python -m pipeline --only integration --confidence-weights PATH` overrides the packaged config; the config is validated before any input is read.
- Formula: `confidence_score = soft × Σ_f w_f · avail_f · resolution_f · limitation_f · flag_f / Σ_f w_f`, rounded to 3 dp; `data_confidence` high ≥ 0.8, medium ≥ 0.5, else low. Weights mirror the S1-10 example for its six criteria (wind 0.35, transmission 0.20, demand 0.15, substation 0.10, slope 0.10, REZ 0.10) plus 0.05 each for elevation, land use, protected area and connection distance (Σw = 1.20). Resolution factors: 1.0 for every source at or finer than the 0.05° cell, 0.5 for the demand proxy (one NEM-region mean allocated uniformly). Limitation factors on a four-point scale (1.00 / 0.95 / 0.90 / 0.75) with a data-spec citation per feature. Upstream flag factors apply only to a layer's present features (wind no_data 0.0; demand medium 0.75, low 0.5; geographic low 0.5 on elevation/slope/land use; infrastructure low 1.0 because that flag is a pure function of the null connection distance, already counted). S1-07's urban-coverage `data_flags` string is note-only (factor 1.0). The maximum attainable score under the defaults is **0.870**. Full methodology: `DATA/integration/metadata/confidence_method.md`.
- Deliverables: methodology document (`metadata/confidence_method.md`), per-cell columns in the integrated table, summary report (`metadata/confidence_summary.md`: counts and shares, histogram, distinct score profiles, ranked reasons for all and eligible cells, eligibility cross-tab, lattice neighbour agreement with a random baseline, 1°×1° blocks, bounding boxes). The manifest and `DATA_PROVENANCE.md` record the config path, version and SHA-256. Six new fatal validation checks in `merge_validation.md` (columns present, score in [0, 1], vocabulary, threshold consistency, non-empty notes, full recount via `assess()`).
- Real run, 2026-09-03: 47,311 cells; **high 1,600 (3.4%), medium 45,711 (96.6%), low 0**; five distinct scores — 0.830 (1,600 cells: the New-England-REZ raster window), 0.699 (471), 0.680 (38,374), 0.668 (229, demand assigned by boundary overlap), 0.633 (6,637, outside every NEM region). Most common reasons: missing connection-point distance (47,311, every cell — AEMO KCI has no coordinates), urban-centre coverage unconfirmed (45,911), missing elevation and slope (45,711 each), missing land use (45,240), missing demand proxy (6,637). Geographic pattern: both levels are strongly clustered (90.2% of high cells and 99.6% of medium cells have every lattice neighbour at the same level, against 0.0% and 75.9% expected at random) — the high set is exactly the raster coverage window.
- **Finding:** every one of the 1,233 eligible cells has the identical evidence profile and therefore the identical confidence (0.830, high); the only in-eligible variation is the urban-coverage note on 115 of them. The composite currently separates the REZ window from the rest of NSW rather than ranking shortlist candidates against each other, because the heavily weighted wind and GA-distance evidence is present statewide while the missing evidence (geographic rasters, connection points) sits in low-weight features. This is reported, not tuned away; extending the SRTM/NLUM clips to the NSW bbox (data spec §8 prerequisites) or geocoding the KCI source would change it.
- Deliberately not inputs: `tri`, `rez_name`, `source_region`, `protected_area_name`, eligibility, `triggered_rules` and `exclusion_reason` (S1-07's "Missing wind data" is its own NE-REZ-clip artefact; `wind_speed` is the canonical evidence). "Distance from nearest measured/modelled data point" is not applicable to any source and is stated as such in the methodology. Whether S1-10 discounts the score by `confidence_score` or only reports `data_confidence` remains S1-10's decision; both columns are provided.
- Data specification amended to v1.4 (v1.3 was taken by the S1-04/S1-07 entries added on the S1-08 branch) (§4.5 columns, confidence row, limitations; §7 row; §8 Applied paragraph). README, S1-08 Completion Notes cross-referenced.
- Gaps deliberately left: the resolution and limitation factors are documented judgements on a fixed scale, tunable by config; no `low` cells exist under the default thresholds; the upstream `wind_confidence` and `infra_confidence` flags carry no information on the current data (all `valid` / all `low`) and would need upstream changes (persisting per-cell valid-pixel counts; dropping the null connection distance from S1-05's required set) to become informative.
