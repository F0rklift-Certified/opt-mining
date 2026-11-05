# Demo Script — guidance §10 Required Final Demonstration

A rehearsed, live end-to-end walkthrough of the Opt-Mining MVP for the final
client demonstration. Every concrete value below was **captured during the
rehearsal of 2026-10-22** against the real running stack on the Sprint 4
baseline (outside-NSW exclusion, QA F-01) and is recorded in
[`rehearsal.json`](rehearsal.json); none is transcribed from an earlier baseline.

Opt-Mining is a **preliminary screening** tool. This demo shows a
**screening-level** flow that surfaces higher-ranked candidate cells for further
investigation. It does **not** show the best site to build a wind farm, nor the
best place to build; it is never a final recommendation or a site approval.

**Rehearsal environment (captured):** API `http://localhost:8000`, web origin
`http://localhost:3000`, production Compose stack
(`docker compose -f docker-compose.yml up --build` from `app/`). Frozen input
SHA `df7073bd`. Rehearsed with
`PYTHONPATH=. python app/rehearse_demo.py --output docs/release/rehearsal.json --external-sanity`.

**Captured run ids (regenerated live on this branch):**

| Run | `run_id` |
| --- | --- |
| Baseline (default weights) | `ecb0a6f1443a9908` |
| Wind-led | `97c0a3ecf702b540` |
| Grid-led | `8f7c098158bf8301` |

**Captured cell counts:** total **47,311**, eligible **23,266**, excluded
**24,045** (`data-quality` reported **28** checks passed).

---

## The three-scenario weight table

Sourced from [`pipeline/scoring/scoring_weights.yaml`](../../pipeline/scoring/scoring_weights.yaml)
(Baseline) and mirrored in
[`app/web/app/shell/AnalysisControls.tsx`](../../app/web/app/shell/AnalysisControls.tsx)
(the Wind-led / Grid-led presets). Weights are relative — the score divides by
the sum of applied weights, so they sum to 1.00 only for readability.

| Criterion | Direction | Baseline | Wind-led | Grid-led |
| --- | --- | --- | --- | --- |
| `wind_speed` | higher is better | 0.35 | 0.55 | 0.25 |
| `dist_transmission_km` | lower is better | 0.20 | 0.15 | 0.35 |
| `demand_proxy` | higher is better | 0.15 | 0.10 | 0.10 |
| `dist_substation_km` | lower is better | 0.10 | 0.05 | 0.10 |
| `slope_deg` | lower is better | 0.10 | 0.05 | 0.05 |
| `inside_rez` | higher is better | 0.10 | 0.10 | 0.15 |

The `demand_proxy` row is a proxy indicator — each NEM region's annual-mean
figure spread across its cells by distance to recorded zone-substation load and
ranked within the region; it is **not** measured or actual local demand.

---

## The nine §10 steps

Each step names the concrete web shell region in
[`app/web/app/shell/AppShell.tsx`](../../app/web/app/shell/AppShell.tsx) and/or
the API operation in [`app/api/app.py`](../../app/api/app.py).

### Step 1 — Start from the documented environment

- **Action:** `docker compose -f docker-compose.yml up --build` from `app/`; open the web origin and
  the API `/docs`. The `DataQualityBanner` (← `GET /data-quality`) renders.
- **Evidence:** both URLs reachable; `smoke_test.py` PASS line captured in
  [`verification.md`](verification.md); `data-quality` passed with **28** checks.

### Step 2 — NSW inputs and default criteria / weights

- **Region:** Analysis controls (`region-analysis-controls`,
  `AnalysisControls.tsx`). Region is fixed to NSW (no selector by design);
  **Baseline** is selected (`DEFAULT_OPTION_ID = "baseline"`) and the six-criterion
  weight table is shown with per-source and interpretation tooltips.
- **Evidence:** the Baseline weights 0.35 / 0.20 / 0.15 / 0.10 / 0.10 / 0.10 and
  the on-mount Baseline run id `ecb0a6f1443a9908`.

### Step 3 — Run the screening

- **Action:** show the on-mount run (or click **Run analysis**); internally
  `POST /runs` with explicit Baseline weights via `buildRunRequest`.
- **Evidence:** run id `ecb0a6f1443a9908`; **23,266** eligible of **47,311**
  cells; the map and the top-10 shortlist populate.

### Step 4 — Show exclusions and explain one excluded site

- **Region:** `GET /runs/{run_id}/exclusions` populates the excluded set; open
  one excluded cell's detail (`GET /runs/{run_id}/sites/{cell_id}` →
  `SiteDetailPanel` "Why excluded"). A high wind value cannot override an
  exclusion.
- **Evidence (captured):** excluded cell **`S28.186_E141.036`**, reason code
  **`outside_nsw_land`** ("Outside NSW (cell centre is not in New South
  Wales)"), with `suitability_score` = null and `rank` = null. A good second
  example to open live is any cell inside a national park (`protected_area`).

### Step 5 — Show the ranked shortlist and the map

- **Regions:** Ranked results (`region-ranked-results`, `RankedShortlist.tsx` ←
  `GET /runs/{run_id}/results?top_n=10`) and Interactive map
  (`region-interactive-map`, `CellMap` ← `GET /runs/{run_id}/cells`). Click a
  shortlist row and a map cell; the shared selection shows the same cell in both.
- **Evidence (captured top band, Wind-led run `97c0a3ecf702b540`):**

  | Rank | `cell_id` | Suitability score |
  | --- | --- | --- |
  | 1 | `S32.436_E149.086` | 0.8824 |
  | 2 | `S32.436_E149.036` | 0.8765 |
  | 3 | `S32.486_E149.086` | 0.8760 |
  | 4 | `S30.186_E151.636` | 0.8731 |
  | 5 | `S30.286_E151.636` | 0.8726 |

  The Baseline run's rank 1 is `S30.586_E151.586` (score 0.8910).

  The CSV export (`shortlistExport.ts`) can be shown opportunistically here; its
  leading `#` disclaimer line carries the screening-level framing into the file.

### Step 6 — Open a high-ranked site and explain its score

- **Region:** click rank 1 → Site detail / explanation (`region-site-detail`,
  `SiteDetailPanel`): total score, per-criterion component scores
  (contributions), raw/derived features, headline, positive factors and
  weaknesses. The **demand-proxy caveat** section is visible.
- **Evidence (captured, Wind-led run):** rank-1 cell `S32.436_E149.086` (the
  Bodangora Wind Farm cell), score **0.8823676167551172**. Its six contributions
  sum to the score within `RECONCILE_TOLERANCE` = 1e-9:

  | Criterion | Contribution |
  | --- | --- |
  | `wind_speed` | 0.473281 |
  | `dist_transmission_km` | 0.148823 |
  | `inside_rez` | 0.100000 |
  | `demand_proxy` | 0.071835 |
  | `dist_substation_km` | 0.049641 |
  | `slope_deg` | 0.038788 |

  The `demand_proxy` contribution reflects a proxy indicator; it is **not**
  measured or actual local demand.

### Step 7 — Change the weighting / scenario and show how/why ranking changes

- **Regions:** (a) Scenario comparison (`region-scenario-comparison`,
  `ScenarioComparison.tsx` ← `POST /scenario-comparison`) with the named form
  `scenario_a` / `scenario_b` (the endpoint also accepts explicit
  `weights_a` / `weights_b`); (b) select **Grid-led** and Run to re-rank the
  live map/shortlist.
- **Evidence (captured, Wind-led vs Grid-led):** **23,266** rows;
  **23,261** cells moved (|rank_a − rank_b| ≥ 1) — a strong, honest
  "how/why ranking changes" signal. Example moved cell `S32.436_E149.086`:
  **rank 1 under Wind-led → rank 4 under Grid-led** (delta −3). The move is
  explained by the weight shift away from `wind_speed` (0.55 → 0.25) and toward
  `dist_transmission_km` (0.15 → 0.35). The rank-delta count here is non-zero;
  had it been zero the rehearsal would record that honestly rather than fail.

### Step 8 — Show a validation / sanity-check result

- **Region:** Sanity check / validation (`region-sanity-check`,
  `SanityCheckPanel.tsx` ← `GET /sanity-check`): the always-on
  model-not-trained caveat, per-check PASS/FAIL, the known-wind-farm quartile
  table (top-ranked-band column), the REZ-representation outcome and the full
  contradictions list; note the baseline-vs-scenario disclosure strip.
- **Evidence (captured):** `top_band_n` = 20; `contradiction_count` = 2; 11 of
  the 14 operating wind farms in the upper quartile; `Bodangora Wind Farm` in the
  top band (rank 9, ~99.97th percentile). The reference set excludes the GA
  extract's mislabelled solar farm and duplicate Gullen Range row (QA F-03).

#### Reference caveats (honest anomalies)

The sanity stage **discloses** divergences, it does not tune them away:

- `Boco Rock` sits outside the upper quartile (rank 6,184, ~73.4th
  percentile) — an honest divergence.
- `Taralga Wind Farm` and `Rye Park Wind Farm` have null rank/percentile: their
  nearest grid cell is excluded/unscored.
- Scenario movement is near-total (23,261 of 23,266) — expected given the large
  weight swing between Wind-led and Grid-led, and recorded as evidence rather
  than tuned.

### Step 9 — Show the supporting GitHub code / tests / docs (required §10 item)

Walk the reviewable PR sequence and the supporting evidence:

- **PR sequence (backend → web → docs):** PR-1 backend decision components &
  service (`pipeline/**`, `app/api/**`, backend tests); PR-2 web integration
  (`app/web/**`, `app/docker-compose.yml`); PR-3 validation, documentation &
  release candidate (`docs/technical-reference.md`, the e2e test, the
  docs-consistency guard, and this `docs/release/**` set, `app/rehearse_demo.py`,
  `tests/backend/test_demo_rehearsal.py`). See
  [`README.md`](README.md).
- **Frozen specs & inputs:** `Sprint-2-Tasks/decision_engine_specification.md`,
  `pipeline/exclusions/exclusion_rules.yaml`,
  `pipeline/scoring/scoring_weights.yaml`.
- **Tests:** the engine / property tests under `tests/`, the end-to-end
  `tests/integration/test_e2e_dataset_engine_app.py`, the rehearsal gate
  `tests/backend/test_demo_rehearsal.py`, and CI
  `.github/workflows/ci.yml`.
- **Docs:** `docs/technical-reference.md`, `pipeline/README.md`, `app/README.md`
  and the AC-evidence map in [`readiness.json`](readiness.json).

---

## Not Checkpoint D

An automated green rehearsal and a passing CI run are **not** Checkpoint-D
acceptance. The `--require-final` rehearsal exits with a distinct non-zero code
(`EXIT_NOT_FINAL`) precisely so a green run is never mistaken for client
sign-off; review, merge and client acceptance gates remain open.
