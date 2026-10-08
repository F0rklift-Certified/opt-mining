# Decision_Service Contract (S2-08)

**Status: FROZEN at the Sprint 2 / Sprint 3 boundary.**

This document is the human-readable narration of the `Decision_Service` HTTP
contract. It is the single boundary between the Sprint 2 decision engine
(`pipeline/`) and the Sprint 3 web application (S3-01 onward). The
machine-readable form of this same contract is the FastAPI-generated **OpenAPI
schema** (see [§2](#2-transport-fastapi-http--openapi)); where a field type or
an enum here and the published `openapi.json` ever disagree, the OpenAPI schema
is authoritative and this document is the defect.

> **Freeze note (Requirement 6.5).** This contract — the OpenAPI schema *and*
> the operation semantics narrated here — is **frozen** at the Sprint 2/Sprint 3
> boundary so that S3-01a (app-shell scaffold) and S3-01b (typed client
> generation) integrate against a stable surface. A change to this contract
> after the freeze is a cross-cutting event: it ripples into every Sprint 3
> ticket that has generated a client from `openapi.json`. Any post-freeze change
> follows the Decision_Engine_Spec §8 change-control process and must be recorded
> in the [Change log](#8-change-log) below with a version bump.

---

## 1. What this service is (and is not)

The `Decision_Service` is a **thin read-and-serve layer** over the materialised
outputs of the decision engine. It performs **no** decision logic of its own:

- It **does not** score, normalise, rank, or compute exclusions. Those all live
  in the Sprint 2 engine stages (S2-03 exclusions, S2-04 normalisation, S2-05
  scoring/ranking, S2-06 explanation, S2-07 scenarios) and are orchestrated
  through their existing `run(verbose=False, ...) -> dict` stage contract.
- It **does** read the materialised engine artefacts and serve them, applying
  only **pure display-level selection** (top-N and minimum-score filters) over a
  completed Run.

This is the structural guarantee behind combined-sprint **AC4** ("scoring and
normalisation are implemented outside the UI"): the Web_Application can only call
this service, so it has no code path by which to recompute a score, a rank, or an
eligibility decision. The map and the ranking table therefore always represent
**one engine output**.

### Materialised engine outputs the service reads

| Artefact | Producer | Location | Layer/format |
| --- | --- | --- | --- |
| Scored_Table | S2-05 `pipeline/scoring/` | `DATA/scoring/optmining_suitability-score_2026_nsw.gpkg` (+ `.csv`) | layer `suitability_score` |
| Eligibility_Table | S2-03 `pipeline/exclusions/` | `DATA/exclusions/optmining_exclusions_2024_nsw.gpkg` | layer default |
| Explanation_Structure | S2-06 `pipeline/explanation/` | `DATA/explanation/optmining_site-explanations_2026_nsw.json` (+ `.csv`) | JSON records |
| Scenario presets | S2-07 `pipeline/scoring/scenarios.yaml` | packaged with the engine | named weight sets |
| Data_Quality_Status | S2-02 `pipeline/validate.py` | `DATA/integration/metadata/integrated_input_validation.json` | check-record JSON |

All served coordinates, where returned, are the grid centroids
(`centroid_lat`, `centroid_lon`) in **EPSG:4326** (the storage CRS), carried
through unchanged. The service performs **no reprojection**; the EPSG:4326
storage / EPSG:3577 computation boundary is handled entirely inside the engine
(distances such as `dist_transmission_km` are already computed in EPSG:3577 by
the upstream stages).

---

## 2. Transport: FastAPI HTTP + OpenAPI

The `Decision_Service` is realised as a **FastAPI application exposing HTTP
endpoints**, consistent with the decided React/Next.js + FastAPI MVP stack
(S3-01a) — it is **not** an in-process module (Requirement 6.4). FastAPI
auto-generates the machine-readable contract; the Next.js/React frontend
generates its typed client from that schema (S3-01b), so the frontend and
backend types cannot drift.

| Published surface | Path | Purpose |
| --- | --- | --- |
| OpenAPI schema (JSON) | `GET /openapi.json` | The machine-readable contract every operation's request/response is described by (Requirement 6.1). |
| Interactive docs (Swagger UI) | `GET /docs` | Browsable API documentation. |
| Alternative docs (ReDoc) | `GET /redoc` | Browsable API documentation. |

The core operation functions (`run_analysis`, `get_ranked_results`, …) are kept
**pure of transport** in `pipeline/service/` so they remain unit-testable without
the HTTP layer; `app.py` maps each to an endpoint below.

### Endpoint mapping

| # | Service_Operation | HTTP method + path | Request | Response |
| --- | --- | --- | --- | --- |
| 1.1 | `run_analysis` | `POST /runs` | `RunRequest` (body) | `RunHandle` |
| 1.2 | `get_ranked_results` | `GET /runs/{run_id}/results` | `run_id` (path), `top_n` & `min_score` (query, optional) | `RankedRow[]` |
| 1.3 | `get_site_detail` | `GET /runs/{run_id}/sites/{cell_id}` | `run_id`, `cell_id` (path) | `SiteDetail` |
| 1.4 | `get_exclusions` | `GET /runs/{run_id}/exclusions` | `run_id` (path) | `ExcludedRow[]` |
| 1.5 | `compare_scenarios` | `POST /scenario-comparison` | `ScenarioComparisonRequest` (body) | `ScenarioComparison` |
| 1.6 | `get_data_quality` | `GET /data-quality` | — | `DataQualityStatus` |

---

## 3. Weights interpretation

The weights the `run_analysis` operation accepts are interpreted **exactly** as
the S2-01 Decision_Engine_Spec (§3.1 Scoring_Formula, §3.2 weight-normalisation
rule) defines them (Requirement 4.2). The service passes weights straight into
the engine; it holds no weight literals and applies no interpretation of its own.

For an **eligible** cell `i` and each configured criterion `k`:

```
contrib_k(i) = w_k · n_k(i) / W_i
suitability_score(i) = Σ_k contrib_k(i)          ∈ [0, 1]
```

where:

- **`w_k`** — the user-supplied weight of criterion `k`. Weights are provided
  either as an explicit weights configuration or by naming a Scenario (§4).
- **`n_k(i)`** — criterion `k`'s value at cell `i` after directional min-max
  normalisation to `[0, 1]` (1 most favourable, 0 least favourable). For a
  `higher_is_better` criterion `n_k = (v − lo) / (hi − lo)`; for a
  `lower_is_better` criterion `n_k = 1 − (v − lo) / (hi − lo)`. The bounds
  `lo`/`hi` are computed **once per Run from the eligible population** (never
  hard-coded), so the scale adapts to the candidate set being compared.
- **`W_i`** — the **applied weight sum** for cell `i`: the sum of the weights of
  the criteria that actually have a value for that cell (the normalisation
  denominator).

**Weights are relative, not absolute** (Decision_Engine_Spec §3.2). Because the
numerator and `W_i` scale together, multiplying every weight by a constant
leaves every score and every ranking unchanged — only the *relative* sizes of
the weights matter. The default weights and each scenario's weights sum to 1.00
purely for readability; **the service does not require weights to sum to one**,
because the division by `W_i` normalises whatever they sum to.

The six frozen scored criteria and their directions (Decision_Engine_Spec §2/§4)
are fixed across every run and every scenario:

| Criterion (`feature`) | Direction |
| --- | --- |
| `wind_speed` | `higher_is_better` |
| `dist_transmission_km` | `lower_is_better` |
| `demand_proxy` | `higher_is_better` |
| `dist_substation_km` | `lower_is_better` |
| `slope_deg` | `lower_is_better` |
| `inside_rez` | `higher_is_better` |

Only the **weights** differ between runs/scenarios; the criteria set and
directions do not. This is what makes two runs comparable: the normalisation
bounds are identical, so a ranking change is attributable purely to the change
in preferences (Decision_Engine_Spec §3.2). Excluded cells receive a **null**
score and **no rank**, and take no part in the normalisation bounds — ineligible
land is never ranked as if it were developable (Decision_Engine_Spec §3.3).

---

## 4. Service operations

Each operation below lists its request and response schema. The data models
referenced are defined in [§5](#5-data-models).

### 4.1 `run_analysis` — `POST /runs` (Requirement 1.1, 4.1, 4.3, 4.4)

Runs the engine under a given weights configuration **or** a named Scenario,
materialises the outputs, and returns a handle identifying the Run. It drives the
S2-05 scoring stage with those weights **unchanged**, reusing the engine — it
duplicates no scoring logic (Requirement 4.3).

**Request — `RunRequest`** (exactly one of `weights` / `scenario` must be given):

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `weights` | `Weights \| null` | one-of | Explicit weights configuration (see `Weights` in §5). |
| `scenario` | `string \| null` | one-of | A named Scenario key from `scenarios.yaml` (e.g. `"wind_led"`, `"grid_led"`). |

**Response — `RunHandle`** (see §5).

**Errors:** if the supplied weights or Scenario are invalid (unknown scenario
name, a negative or non-numeric weight, weights summing to zero, or a feature
that is not a scored criterion), the operation returns an error identifying the
fault and returns **no** Run (Requirement 4.4; HTTP `422`). See [§6](#6-error-handling).

### 4.2 `get_ranked_results` — `GET /runs/{run_id}/results` (Requirement 1.2, 2.4, 3.x, 6.3)

Returns the ranked results for a Run as a selection over the **fixed**
Scored_Table. Accepts an optional Display_Filter. It **never re-scores or
re-ranks** — ranks are the S2-05 ranks, preserved under any filter (Requirement
3.1, 3.2).

**Request:**

| Parameter | In | Type | Required | Notes |
| --- | --- | --- | --- | --- |
| `run_id` | path | `string` | yes | The Run to read. |
| `top_n` | query | `integer > 0 \| null` | no | Keep the `top_n` lowest-`rank` eligible cells. If `top_n` exceeds the eligible count, **every** eligible cell is returned with no padding (Requirement 3.3). |
| `min_score` | query | `number \| null` | no | Keep only cells with `suitability_score ≥ min_score`. A threshold that excludes every cell returns an **empty** array, not an error (Requirement 3.4). |

When both filters are given, both apply (threshold then top-N over the
survivors); ranks are unchanged either way.

**Response — `RankedRow[]`** (see §5), ordered ascending by `rank` (rank 1
first). Only eligible cells (non-null score and rank) appear.

### 4.3 `get_site_detail` — `GET /runs/{run_id}/sites/{cell_id}` (Requirement 1.3, 2.3, 6.2, 7.2)

Returns a single cell's full detail for a Run: its features, per-criterion
component scores (`contrib_*`), total score, rank, eligibility, and the S2-06
Explanation_Structure.

**Consistency guarantee (Requirement 2.3):** the `suitability_score` and `rank`
returned here for a `cell_id` are **identical** to those `get_ranked_results`
returns for the same `cell_id` in the same Run. The table and the map show one
engine output.

**Request:**

| Parameter | In | Type | Required |
| --- | --- | --- | --- |
| `run_id` | path | `string` | yes |
| `cell_id` | path | `string` | yes |

**Response — `SiteDetail`** (see §5).

**Errors:** an unknown `cell_id` in the Run returns an error naming the missing
`cell_id` (Requirement 7.2; HTTP `404`).

### 4.4 `get_exclusions` — `GET /runs/{run_id}/exclusions` (Requirement 1.4)

Returns the excluded cells for a Run with their machine- and human-readable
exclusion reason(s), read from the Eligibility_Table.

**Request:** `run_id` (path).

**Response — `ExcludedRow[]`** (see §5).

### 4.5 `compare_scenarios` — `POST /scenario-comparison` (Requirement 1.5, 4.3)

Compares two named Scenarios, returning a per-cell rank comparison. Each
scenario's ranks are produced via the **S2-05 engine** (not a second scorer);
the two scenarios share the same criteria, directions, and eligible-population
normalisation bounds, so a rank change is attributable purely to the weight
difference.

**Request — `ScenarioComparisonRequest`:**

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `scenario_a` | `string` | yes | A named Scenario key. |
| `scenario_b` | `string` | yes | A named Scenario key. |

**Response — `ScenarioComparison`** (see §5).

### 4.6 `get_data_quality` — `GET /data-quality` (Requirement 1.6, 5.1–5.3)

Surfaces the S2-02 Data_Quality_Status for the frozen integrated dataset, so the
Web_Application can render a data-quality banner. When the frozen dataset has
failed a blocking data-quality check, the failure is reported here (Requirement
5.2), and the service never emits a Run result derived from a failed dataset
without also making the failure retrievable via this operation (Requirement 5.3).

**Request:** none.

**Response — `DataQualityStatus`** (see §5).

---

## 5. Data models

The canonical types are the FastAPI/Pydantic models published in
`openapi.json`. The tables below narrate their fields. `null` denotes a nullable
field; `[T]` denotes an array of `T`.

### `RunHandle` (Requirement 6.2)

| Field | Type | Notes |
| --- | --- | --- |
| `run_id` | `string` | Identifier for the materialised Run; used in the `GET /runs/{run_id}/...` paths. |
| `weights_id` | `string` | Stable identifier of the weight set used (the scenario key, or a content-derived id for explicit weights). |
| `scenario` | `string \| null` | The named Scenario, when the Run was launched from one; `null` for an explicit-weights Run. |

### `Weights` (request sub-model for `run_analysis`)

Mirrors the `scoring_weights.yaml` / scenario `criteria` structure so it is
validated by the **same** engine parser (`pipeline/scoring/weights.py`), never a
duplicate validator.

| Field | Type | Notes |
| --- | --- | --- |
| `criteria` | `[Criterion]` | One entry per scored criterion. |

`Criterion`:

| Field | Type | Notes |
| --- | --- | --- |
| `feature` | `string` | One of the six frozen criteria (§3). |
| `weight` | `number ≥ 0` | Relative weight; not required to sum to one (§3). |
| `direction` | `"higher_is_better" \| "lower_is_better"` | Fixed per criterion (§3). |
| `rationale` | `string` | Non-empty rationale, per the weights-as-data contract. |

### `RankedRow` (Requirement 6.3)

| Field | Type | Notes |
| --- | --- | --- |
| `cell_id` | `string` | Analysis-cell id; joins to the grid. |
| `suitability_score` | `number` | The S2-05 score in `[0, 1]` (never recomputed). |
| `rank` | `integer` | The S2-05 rank (1 = highest-ranked); preserved under any filter. |
| `key_components` | `{string: number}` | Per-criterion component values for the cell (the `contrib_{feature}` shares), keyed by criterion `feature`. |

### `SiteDetail` (Requirement 6.2, 6.3)

| Field | Type | Notes |
| --- | --- | --- |
| `cell_id` | `string` | Analysis-cell id. |
| `features` | `{string: value}` | The cell's input feature values (e.g. `wind_speed`, `dist_transmission_km`, `slope_deg`, `inside_rez`, …). |
| `contributions` | `{string: number}` | Per-criterion contribution (`contrib_{feature}`); the shares sum to `suitability_score`. |
| `suitability_score` | `number \| null` | The S2-05 score; identical to `get_ranked_results` for this cell (Requirement 2.3). Null for an excluded cell. |
| `rank` | `integer \| null` | The S2-05 rank; identical to `get_ranked_results`. Null for an excluded cell. |
| `eligible` | `boolean` | Whether the cell passed the S2-03 hard exclusions. |
| `explanation` | `Explanation_Structure` | The S2-06 deterministic explanation (below). |

### `Explanation_Structure` (Requirement 6.2 — S2-06 fields, carried verbatim)

The service returns the S2-06 record **unchanged**; it neither renames nor
reorders its fields. An **eligible** cell carries:

| Field | Type | Notes |
| --- | --- | --- |
| `cell_id` | `string` | |
| `eligible` | `boolean` | `true` on this path. |
| `headline` | `string` | Screening-level headline (identical for every eligible cell). |
| `positive_factors` | `[string]` | The criteria contributing most to the score, phrased with a qualitative band. |
| `weaknesses` | `[string]` | The criteria the cell scores poorly on. |
| `proxy_caveats` | `[string]` | Caveats for proxy criteria (e.g. the demand proxy). |
| `data_quality_notes` | `[string]` | The S1-09 composite data-confidence notes. |

An **excluded** cell carries `cell_id`, `eligible = false`, `exclusion_reasons`
(a list of `{code, text}` pairs), `proxy_caveats`, and `data_quality_notes`.

### `ExcludedRow` (Requirement 1.4)

| Field | Type | Notes |
| --- | --- | --- |
| `cell_id` | `string` | Analysis-cell id. |
| `reason_codes` | `[string]` | Machine-readable exclusion rule codes (the `triggered_rules` / `exclusion_reasons[].code` vocabulary from S2-03/F16). |
| `reason_text` | `string` | Human-readable reason(s), joined in rule-config order. |

### `ScenarioComparison` (Requirement 1.5)

| Field | Type | Notes |
| --- | --- | --- |
| `labels` | `{a: string, b: string}` | The two Scenario keys compared. |
| `rows` | `[ScenarioComparisonRow]` | Per-cell rank comparison. |

`ScenarioComparisonRow`:

| Field | Type | Notes |
| --- | --- | --- |
| `cell_id` | `string` | Analysis-cell id. |
| `rank_a` | `integer \| null` | Rank under `scenario_a` (null if not eligible/ranked). |
| `rank_b` | `integer \| null` | Rank under `scenario_b` (null if not eligible/ranked). |
| `rank_delta` | `integer \| null` | `rank_a − rank_b` where both are present; null otherwise. |

### `DataQualityStatus` (Requirement 6.2, 6.3 — S2-02 shape)

Mirrors the S2-02 machine-readable validation result (`{name, expected,
observed, passed}` check records with an overall verdict), carried through
unchanged.

| Field | Type | Notes |
| --- | --- | --- |
| `passed` | `boolean` | The overall verdict (`all_passed` over the input-contract checks, including the baseline hash match). `false` means the frozen dataset failed a blocking check. |
| `checks` | `[DataQualityCheck]` | The per-check records. |

`DataQualityCheck`:

| Field | Type | Notes |
| --- | --- | --- |
| `name` | `string` | The check name. |
| `expected` | `string` | The expected value/condition. |
| `observed` | `string` | The observed value. |
| `passed` | `boolean` | Whether this check passed. No silent passes — every check is reported. |

---

## 6. Error handling

The service fails **clearly** rather than returning a misleading empty success
(Requirement 7). It distinguishes an empty-but-valid result from an error.

| Condition | Behaviour | HTTP | Req |
| --- | --- | --- | --- |
| Invalid weights / unknown Scenario | Error identifying the fault; **no** Run created. | `422` | 4.4 |
| Requested Run does not exist | Error naming the missing Run. | `404` | 7.1 |
| Requested `cell_id` not in the Run | Error naming the missing `cell_id`. | `404` | 7.2 |
| A required materialised engine output is missing/unreadable | Error **naming the missing input**; never a fabricated result. | `503` | 7.3 |
| Top-N exceeds the eligible count | Empty-but-valid: returns **all** eligible cells, no padding. | `200` | 3.3 |
| `min_score` threshold excludes every cell | Empty-but-valid: returns an **empty** array. | `200` | 3.4 |

Empty-but-valid results (top-N over the count, an all-excluding threshold) are
returned as empty sets with a `200`, **never** as an error (Requirement 7.4).

---

## 7. Correctness properties enforced by the service

- **P1 — One engine output.** For a Run, the score and rank of any `cell_id` are
  identical across `get_ranked_results` and `get_site_detail` (Requirement 2.3).
- **P2 — Filters do not re-score.** For any Display_Filter, the score and rank of
  every returned cell equal its unfiltered Run values (Requirement 3.1, 3.2).
- **P3 — No recompute path.** No scoring / normalisation / ranking / exclusion
  arithmetic exists in `pipeline/service/`; every served value traces to a
  materialised engine output (Requirement 2.1, 2.2, 2.4).
- **P4 — Empty-but-valid.** Top-N over the eligible count returns all eligible
  cells with no padding; an all-excluding threshold returns an empty set, not an
  error (Requirement 3.3, 3.4).
- **P5 — Scenario reuse.** `compare_scenarios` produces each scenario's ranks via
  the S2-05 engine, not a second scorer (Requirement 4.3).
- **P6 — Honest failure.** Missing Run / `cell_id` / engine output each yield an
  error naming the fault, never a misleading empty success (Requirement 7.x).

---

## 8. Change log

| Version | Date | Change | Process |
| --- | --- | --- | --- |
| 1.0 | Sprint 2/3 boundary | Initial frozen contract: six operations, endpoint mapping, data models, weights interpretation, error handling. | Frozen per Requirement 6.5. |

Any post-freeze change to this contract or the published OpenAPI schema follows
the Decision_Engine_Spec §8 change-control process, bumps the version above, and
must be propagated to the Sprint 3 generated client (S3-01b) as a cross-cutting
event.
