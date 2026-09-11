# `pipeline/scoring` — Baseline Suitability Model (stage `scoring`)

The `scoring` stage is a transparent, deterministic **weighted multi-criteria
decision analysis (MCDA)** — not a machine-learning model. It runs immediately
after `integration` and before `validate`:

```
... → exclusions → integration → scoring → validate
```

For every **eligible** cell (S1-07 `eligible = True`) it normalises each scored
feature to a comparable `[0, 1]` component, combines them as a weight-normalised
sum, writes each feature's additive contribution (`contrib_{feature}`) alongside
the score, and ranks the eligible cells. Excluded cells receive a **null** score
and no rank — ineligible land is never ranked as if it were developable.

The weights, directions and rationales are **user inputs** loaded at runtime
from [`scoring_weights.yaml`](./scoring_weights.yaml) (or `--scoring-weights
PATH`); no weight literal appears anywhere in this subpackage's source.

> **Authoritative decision design.** The frozen decision-engine contract — the
> scored criteria, their directions, the scoring formula and the normalisation
> method and policies — lives in
> [`Sprint-2-Tasks/decision_engine_specification.md`](../../Sprint-2-Tasks/decision_engine_specification.md).
> This README restates the normalisation part of that contract; where the two
> disagree, the specification is the source of truth (changes follow its §6 /
> the data-spec §8 change-control process).

---

## Feature Normalisation (S2-04)

Normalisation converts features on different scales (m/s, km, degrees, a
boolean, a 0–1 proxy) into comparable `[0, 1]` **suitability components**, with
an explicit direction per feature and explicit handling of outliers, missing
values and degenerate populations. It is implemented in
[`normalise.py`](./normalise.py) as an **independently testable component** —
DataFrame in, normalised DataFrame out — with no dependence on the weights or
the data loader:

```python
from pipeline.scoring.normalise import NormSpec, normalise_frame

out = normalise_frame(df, [NormSpec("wind_speed", "higher_is_better")])
# -> DataFrame with a `norm_wind_speed` column in [0, 1]
```

`NormSpec(feature, direction)` is the decoupled per-feature instruction;
`SpecLike` is the structural protocol both `NormSpec` and the scoring
`Criterion` satisfy, so the scoring stage and this standalone surface run the
**same code** (`score.normalised_frame` delegates to `normalise_frame`). There
is no second normaliser.

### Method

Each feature `k` is rescaled by a **linear** min-max transform with its
Direction applied inside the transform, then clamped to `[0, 1]`:

```
higher_is_better:   n_k = (v − lo_k) / (hi_k − lo_k)
lower_is_better:    n_k = 1 − (v − lo_k) / (hi_k − lo_k)
```

`1` is most favourable and `0` least favourable. The bounds `lo_k` / `hi_k` are
the min and max of the **rows passed in** — the eligible population when the
scoring stage calls it — computed **fresh on each call and never hard-coded**.
Passing the eligible rows is what fixes the bounds **per analysis run, not per
UI filter**: a user narrowing the map re-filters the *view*, it does not call
the normaliser with a narrower frame, so no cell's normalised value or score
moves. (Decision-engine spec §5.1–§5.2.)

### Direction table

Each scored feature carries one direction. Higher-is-better features increase
the component as the raw value rises; lower-is-better features invert it. This
table restates [`scoring_weights.yaml`](./scoring_weights.yaml) — the shipped
source of the directions — and the doc-consistency test asserts the two agree.

| Feature (integrated-table column) | Units | Direction | Meaning |
| --- | --- | --- | --- |
| `wind_speed` | m/s | `higher_is_better` | Stronger wind resource is more favourable. |
| `dist_transmission_km` | km | `lower_is_better` | Closer to a ≥132 kV line is more favourable. |
| `demand_proxy` | 0–1 proxy | `higher_is_better` | More allocated demand is more favourable. |
| `dist_substation_km` | km | `lower_is_better` | Closer to a substation is more favourable. |
| `slope_deg` | degrees | `lower_is_better` | Flatter terrain is more favourable. |
| `inside_rez` | boolean | `higher_is_better` | Inside a declared NSW REZ is more favourable. |

### Outlier, missing-value and degenerate-case policy

Each rule is frozen in decision-engine spec §5 (F11–F14); the module implements
that contract.

| Case | Policy | Why |
| --- | --- | --- |
| **Outliers** (§5.3) | **No separate treatment.** The true population min/max set the scale — no trimming, winsorising or percentile capping. The only clamp is the `[0, 1]` saturation guard, which matters solely when bounds from another population are supplied. | Keeps the transform transparent and reproducible; no cell is silently reshaped by an undocumented statistical rule. Extremes widening the range is recorded honestly rather than hidden. |
| **Missing values** (§5.4) | A null (or non-numeric → NaN) stays **null**. It is never imputed to zero or the worst value, and is left out of that cell's weighted average (it contributes neither a numerator term nor a share of the applied weight sum `W_i`). | Scoring a gap as zero would penalise a cell for a hole in the data rather than for a property of the land. The carried-through confidence value flags the gap instead. |
| **Constant feature** (§5.5) | If a feature has one value over the passed rows, `(v − lo)/(hi − lo)` is `0/0`. Every cell is assigned `CONSTANT_CRITERION_VALUE = 1.0` and the feature is **flagged** as constant — **no division is performed**. A feature with *no* value over the passed rows is treated the same way (bounds `0.0/0.0`, flagged). | Avoids divide-by-zero without dropping the feature. A constant feature adds the same amount to every score, so it cannot change the ranking; `1.0` (not `0.0`) avoids penalising a feature for lack of variation. |
| **Boolean feature** (§5.6) | A boolean uses its **definitional** `{False → 0.0, True → 1.0}` domain, not the observed extremes; the Direction is then applied. | An all-`False` `inside_rez` scores `0` for every cell ("no cell is in a REZ") instead of triggering the constant fill and awarding every cell full marks for a benefit none of them has. |

The exact numeric bounds, the per-feature rule applied, and the constant/boolean
flags are written to `DATA/scoring/metadata/scoring_method.md` on every run, so
the values are auditable per run rather than only described here.

### Tests

* [`tests/scoring/test_normalise_standalone.py`](../../tests/scoring/test_normalise_standalone.py)
  — the standalone `NormSpec` / `normalise_frame` surface and the boundary /
  degenerate cases (min/max endpoints, saturation clamp, nulls, constant,
  all-null, boolean domain including all-`False` and `lower_is_better`
  inversion, and `normalised_frame == normalise_frame`).
* [`tests/scoring/test_scoring.py::TestNormalisation`](../../tests/scoring/test_scoring.py)
  — the same rules through the scoring `Criterion` path.
