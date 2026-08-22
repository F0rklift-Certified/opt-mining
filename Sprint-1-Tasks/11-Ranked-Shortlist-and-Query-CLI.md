# Task 11 — Generate the Preliminary Ranked Shortlist + Query CLI

**Sprint:** 1 (Week 2)
**Assignee:** TBD
**Status:** Not Started
**Estimated Effort:** 1 day

---

## 1. Objective

Produce the ranked shortlist and the sprint's delivery surface: `python -m pipeline.query`, which answers "what does Opt-Mining know about this location?" for any NSW cell. Shortlist reference shape (from the sprint brief):

| Rank | Site | Score |
|---|---|---|
| 1 | NSWxxx | 0.87 |
| 2 | NSWxxx | 0.84 |
| 3 | NSWxxx | 0.81 |

## 2. Context & Frozen Decisions

- Delivery decision: CLI + files only this sprint (no web-map integration; the prototype Flask/Leaflet app is a later sprint's target).
- The demand caveat must appear in the CLI output: per-cell demand is an **estimated indicator allocated from regional demand — not measured local demand** (Task 4's three-surface rule).
- Exclusion display uses the human labels from `pipeline/exclusions/config.py` verbatim (single source of truth).

## 3. Scope

**In:**
- `rank` column + shortlist CSV
- `pipeline/query.py` — single-file module, `python -m pipeline.query`

**Out:**
- Any recomputation in the CLI (it reads the integrated CSV + meta files only; fully offline)
- Web/map rendering

## 4. Inputs

- Scored integrated table + `scoring_run.meta.json` (Task 10)
- `GridSpec` (`pipeline/grid/spec.py`) for lat/lon → cell resolution
- Reason labels (`pipeline/exclusions/config.py`)

## 5. Implementation Plan

- [ ] Extend `pipeline/score/model.py` output step (or a small `shortlist` writer it calls): dense `rank` over eligible cells by descending score (ties broken by cell_id for determinism); ineligible → null rank. Write the shortlist CSV: `rank, cell_id, centroid_lat, centroid_lon, score, wind_speed_100m_mean, demand_local_proxy_mw, dist_transmission_km, slope_mean_deg, inside_rez` — top `top_n` (default 50).
- [ ] Create `pipeline/query.py`:
  - Args: `--lat/--lon` (mutually exclusive with `--cell-id`), `--area-name nsw`, `--json` (machine-readable dump of the full row).
  - Resolve lat/lon → `(row, col)` via `GridSpec.locate` → cell_id; look up in the integrated CSV (loaded once via pandas; ~20 MB is fine).
  - Print a `banner()`-style card:
    1. Header: cell_id, centroid, area, land_fraction.
    2. Features grouped by domain **with units** (wind m/s incl. p90/max as "best micro-site", demand MW with the caveat line, distances km, terrain, land use, REZ).
    3. Quality flags (q_wind/q_demand/q_infra/q_geo).
    4. Verdict: `Eligible` — or `Excluded: <human labels>` listing all reasons.
    5. If eligible: score, rank, percentile among eligible cells, and the weights scenario used (from `scoring_run.meta.json`).
  - Out-of-NSW / no-data lookups print a clear "not in the NSW analysis set" message and exit 0 (it's an answer, not an error); malformed args exit non-zero.
- [ ] Register nothing in STAGES (query is a lookup tool, not a pipeline stage) — but document it in `pipeline/README.md` §Usage.

## 6. Outputs

| Output | Path |
|---|---|
| `rank` column | appended into `DATA/integrated/optmining_site-screening_0.05deg_nsw.csv` |
| Shortlist | `DATA/integrated/optmining_shortlist_0.05deg_nsw.csv` |
| Query tool | `pipeline/query.py` (code, not data) |

## 7. Configuration Parameters

| Parameter | Default | CLI flag | Meaning |
|---|---|---|---|
| `top_n` | 50 | `--top-n` (on score stage) | shortlist length |
| `--json` | off | `--json` | machine-readable query output |

## 8. Acceptance Criteria

- [ ] `python -m pipeline.query --lat -29.75 --lon 151.51` (White Rock area) and `--cell-id <same cell>` return the identical card; both lookup modes round-trip.
- [ ] An excluded cell's card shows human-readable reasons and **no score/rank**.
- [ ] The demand caveat line appears on every card that shows `demand_local_proxy_mw`.
- [ ] Ocean coordinates → "not in the NSW analysis set", exit 0.
- [ ] Shortlist has exactly `top_n` rows, ranks 1..top_n dense, all eligible, descending score.
- [ ] Rank is deterministic across reruns (tie-break rule verified).

## 9. Tests

`tests/test_query_unit.py`: lat/lon→cell resolution against a fixture table (interior, boundary, outside cases); card renders reasons for an excluded fixture cell; `--json` output parses and matches the CSV row. `tests/test_score_unit.py` additions: dense-rank determinism with ties.

## 10. Risks & Mitigations

- **CSV load latency in the CLI** (~30.5k rows): pandas read is <1 s; if it grows national later, swap to a keyed store then (recorded, not built).

## 11. Dependencies

**Blocked by:** Task 10 (and 8, 9 transitively).
**Blocks:** Task 12.

## 12. Decision Log

| Date | Decision / Surprise | Rationale |
|---|---|---|
