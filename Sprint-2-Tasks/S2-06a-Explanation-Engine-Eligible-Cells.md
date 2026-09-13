# S2-06a: Explanation Rule/Template Engine & Eligible-Cell Explanations

**Type:** Story
**Priority:** High
**Story Points:** 3
**Labels:** explanation, decision-engine
**Blocked by:** S2-05
**Blocks:** S2-06b, S2-08

---

> **Split note:** This is the first half of the former **S2-06** (Deterministic Site-Level Explanation Generator), broken down per the sizing recommendation. S2-06a builds the deterministic rule/template engine and the explanation for **eligible** cells. S2-06b adds **excluded**-cell explanations and the proxy/data-quality caveat rules.

## Objective

Build the deterministic, template/rule-based explanation engine and use it to explain every eligible site — strongest positive factors and important weaknesses — with no LLM dependency, derived from the S2-05 per-criterion contributions.

---

## Context

Guidance Step 6. This is genuinely new: the scoring module retains per-criterion contributions (`contrib_{feature}`) but there is no human-readable narrative. The guidance is explicit — deterministic template/rule-based explanations are sufficient and more auditable for this MVP; avoid an LLM dependency. This ticket owns the **engine** and the **eligible-cell path**; the excluded-cell path and caveat rules are S2-06b.

---

## Deliverables

1. A deterministic explanation module (rule/template engine) mapping a scored cell to a structured explanation.
2. A template/rule set (configurable phrasing) driving the narrative.
3. Eligible-cell explanations with positive factors and weaknesses.
4. Tests asserting explanation content for eligible cells.

---

## Acceptance Criteria

- [x] A deterministic rule/template engine maps a scored cell to a structured explanation, with **no LLM dependency**
- [x] For any eligible cell, the explanation identifies its **strongest positive factors** and **important weaknesses**, derived from the S2-05 `contrib_{feature}` contributions (satisfies **AC7**, eligible path)
- [x] Explanations are **deterministic** — same input yields identical text
- [x] The explanation is produced by the backend, not the UI, and returned in a structured form the web app renders
- [x] The structured schema is documented (the contract S2-06b extends and S2-08/S3-05 consume)
- [x] Screening-level language throughout ("higher-ranked candidate under the selected assumptions"), never "best site"
- [x] Unit tests assert explanation content for a high-scoring cell and a marginal cell

---

## Explanation Structure (owned here; extended by S2-06b)

```json
{
  "cell_id": "NSW001",
  "eligible": true,
  "headline": "Higher-ranked candidate under the selected assumptions and criteria",
  "positive_factors": ["Strong wind resource (top decile)", "Inside a REZ"],
  "weaknesses": ["Moderate distance to transmission"]
}
```

---

## Technical Notes

- Consumes the S2-05 `contrib_{feature}` columns; ranks factors by contribution magnitude. Does not recompute scores.
- The template/rule set is data (configurable phrasing), consistent with the weights-as-data principle.
- Cross-cutting impact: the structure defined here is extended by S2-06b (proxy/quality caveats, excluded path) and consumed by S2-08 `get_site_detail` and the S3-05 site-detail view. Keep the schema stable.

---

## Status: DONE

Implemented as a new domain-sequential pipeline stage `explanation`, registered in `config.STAGES` immediately after `scoring` and before `shortlist`. Delivered on branch `s2-06`.

### What was built

`pipeline/explanation/`:
- `engine.py` — the pure, deterministic `explain_cell`: positive factors ranked by the persisted S2-05 `contrib_{feature}` (never recomputed), weaknesses by normalised value, each factor carrying a qualitative band; one screening-level headline.
- `load.py` — reads the S2-05 Scored_Table + the S1-08 integrated table and recomputes the normalised values with the **shared** `pipeline/scoring/normalise.py` (no second normaliser). A reconciliation guard asserts the recomputed contributions reproduce the persisted ones within `scoring.config.RECONCILE_TOLERANCE` before anything is written, so the bands are provably derived from the values that produced the score. **S2-05's output schema is left unchanged.**
- `templates.py` + `explanation_templates.yaml` — phrasing, band labels and thresholds as validated user-input data (weights-as-data); no phrase literal in source.
- `bands.py`, `write.py`, `validate.py`, `report.py`, `run.py` — band derivation (boolean/constant aware), atomic JSON+CSV writers + frozen schema doc, no-silent-passes validation, method + validation reports and the provenance triple, and the `run(verbose=False, ...) -> dict` stage entry point.

Outputs (`DATA/explanation/`): `optmining_site-explanations_2026_nsw.json` + `.csv`, plus `metadata/` (`explanation_schema.md`, `explanation_method.md`, `explanation_validation.md`, `explanation_manifest.json`, `source_register.csv`) and `DATA_PROVENANCE.md`.

### Acceptance-criteria evidence

- **Deterministic, no LLM** — pure `engine.explain_cell`; byte-identical JSON/CSV across reruns (verified on the real NSW data).
- **Positive factors + weaknesses from `contrib_{feature}` (AC7 eligible path)** — ranked by persisted contribution; qualitative band from the recomputed normalised value.
- **Backend-produced, structured** — the stage emits the JSON records; the web app renders them (no UI-side logic).
- **Schema documented / frozen** — `DATA/explanation/metadata/explanation_schema.md`; the eligible `Explanation_Structure` (`cell_id`, `eligible`, `headline`, `positive_factors`, `weaknesses`) is the contract **S2-06b extends** (excluded path + proxy/data-quality caveats) and **S2-08 `get_site_detail` / S3-05 consume**.
- **Screening-level language** — the headline reads "Higher-ranked candidate under the selected assumptions and criteria"; "best/optimal site" phrasing is rejected at config load and asserted absent by validation.
- **Unit tests** — a high-scoring and a marginal cell are asserted explicitly; 69 tests total in `tests/explanation/` (config, templates, bands, engine, load/reconciliation guard, write byte-stability, validation, pipeline wiring, full `run()` integration).

### Full-run verification

`python -m pipeline --only explanation` over the real NSW Scored_Table: **1,233** eligible cells explained, reconciliation passed, **6/6** validation checks passed, outputs byte-stable across reruns.

### Cross-cutting updates

`pipeline/config.py` (`STAGES`/`DOMAINS`), `pipeline/__main__.py` (dispatch + `--explanation-templates`, reusing `--scoring-weights`), `pipeline/README.md`, and the data specification (v1.9: §4.10 dataset entry, §7 mapping row, §8 change-control note).

### Scope boundary

Eligible-cell path only. The **excluded-cell** path and the **proxy / data-quality caveat** rules are **S2-06b**, which extends this schema in place.
