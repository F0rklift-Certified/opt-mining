# S2-06b: Excluded-Cell Explanations & Proxy/Data-Quality Caveats

**Type:** Story
**Priority:** High
**Story Points:** 2
**Labels:** explanation, decision-engine
**Blocked by:** S2-03, S2-06a
**Blocks:** S2-08

---

> **Split note:** This is the second half of the former **S2-06**. S2-06a built the engine and eligible-cell explanations. S2-06b adds the **excluded**-cell path and the **proxy** and **data-quality** caveat rules that complete AC7.

## Objective

Extend the S2-06a explanation engine to explain **excluded** sites (their exclusion reasons) and to surface **proxy** caveats and **data-quality** limitations for every site, completing the deterministic explanation to the full combined-sprint acceptance bar.

---

## Context

Guidance Step 6. AC7 requires explanations to call out proxy variables (the demand proxy must never be presented as measured local demand) and relevant data-quality limitations, and to explain excluded sites. S2-06a delivered the engine and eligible-cell factors; this ticket adds the caveat rules and the excluded-cell branch, consuming the S2-03 reason schema and the S1-09/S2-02 confidence data.

---

## Deliverables

1. Excluded-cell explanations stating machine- and human-readable exclusion reasons.
2. Proxy-caveat rules (demand proxy labelled as a proxy).
3. Data-quality/confidence caveat rules.
4. Tests asserting excluded-cell and caveat content.

---

## Acceptance Criteria

- [x] For any excluded cell, the explanation states the machine- and human-readable exclusion reason(s) from S2-03
- [x] Any **proxy variable** used is called out as a proxy — the demand proxy is never described as measured local demand (satisfies **AC7**, proxy caveat)
- [x] Relevant **data-quality limitations** (from the S1-09 confidence flag / S2-02 checks) are surfaced in the explanation
- [x] The excluded-cell and caveat output reuses the S2-06a structured schema (extended, not forked) and remains deterministic with no LLM dependency
- [x] Screening-level language throughout
- [x] Unit tests assert explanation content for an excluded cell and for a cell with a proxy caveat and a low-confidence caveat

---

## Explanation Structure (extends S2-06a)

```json
{
  "cell_id": "NSW002",
  "eligible": false,
  "exclusion_reasons": [{"code": "protected_area", "text": "Protected area: Oxley Wild Rivers NP"}],
  "proxy_caveats": ["Demand shown is a spatial proxy allocated below the AEMO region, not measured local demand"],
  "data_quality_notes": ["Confidence: medium — one feature interpolated"]
}
```

---

## Technical Notes

- Consumes the S2-03 reason vocabulary (coordinate codes with that ticket) and the S1-09/S2-02 confidence/quality data. Does not recompute eligibility or scores.
- Extends the S2-06a schema in place — do not create a second explanation structure.
- Cross-cutting impact: completes the explanation contract that S2-08 `get_site_detail` returns and the S3-05 view renders.

---

## Status: DONE

Extended the existing `explanation` stage (S2-06a) **in place** — no forked schema, no new stage, no LLM. Both paths now carry the AC7 caveats.

### What was built

`pipeline/explanation/`:
- `caveats.py` (new) — the PURE, deterministic caveat builders: `proxy_caveats` emits a criterion's configured caveat only when it is marked `proxy: true` in the templates AND the cell actually used it (non-null value); `data_quality_notes` always surfaces the S1-09 confidence level (including `high`) and appends the `confidence_notes` reasons when present. No phrase literal in source.
- `engine.py` — added `explain_excluded_cell` (emits `cell_id`, `eligible: false`, the F16 `exclusion_reasons` pairs, and the two caveat fields) and attached `proxy_caveats` + `data_quality_notes` to the eligible `explain_cell`. New `CellConfidence` and `ExcludedCellInput` dataclasses; `CriterionView` gained `participated`.
- `load.py` — reads the columns the scoring loader drops (`triggered_rules`, `exclusion_reason`, `data_confidence`, `confidence_notes`) and assembles excluded-cell inputs. **Option B:** the integrated table does not carry the paired `exclusion_reasons` JSON, so the `{code, text}` pairs are **reconstructed** from the two delimited F16 forms (codes authoritative for the count), halting on any count mismatch — the frozen S2-02 baseline is not mutated. The eligible reconciliation guard is unchanged.
- `templates.py` + `explanation_templates.yaml` (v1.1) — a `proxy: true` marker + required `proxy_caveat` per criterion (`demand_proxy` is the shipped proxy), and a `data_quality` phrasing block; all superlative-checked at load. Phrasing remains user-input data.
- `config.py` — added `FIELD_EXCLUSION_REASONS`/`FIELD_PROXY_CAVEATS`/`FIELD_DATA_QUALITY_NOTES`, `EXCLUDED_FIELDS`, `ALL_FIELDS` (CSV header union), and composed the input-column names from `exclusions.config.OUTPUT_COLUMNS`, `exclusions.rules.REASON_DELIMITER` and `integration.config.CONFIDENCE_COLUMNS`.
- `write.py` — routes eligible/excluded inputs to the right engine function, CSV header is the `ALL_FIELDS` union (each record fills only its own path's columns; reasons flattened to `code: text`), and the frozen schema doc gained the excluded/caveat fields + an excluded example.
- `validate.py` — grew from 6 to 10 no-silent-passes checks: count over eligible + excluded, eligibility partition, F16 reason shape on excluded records, no reasons on eligible records, exactly one known-level data-quality note per record, proxy caveats only for configured proxies, and superlatives banned across every field.
- `run.py` / `report.py` — excluded + caveat counts wired into the summary, printout, method report and provenance.

### Acceptance-criteria evidence

- **Excluded reasons** — `explain_excluded_cell` emits the F16 `{code, text}` pairs; asserted by `tests/explanation/test_engine.py` and the full-run test.
- **Proxy caveat (AC7)** — the `demand_proxy` caveat surfaces only when the cell used the demand feature; the demand proxy is never described as measured local demand. Asserted in `test_caveats.py` / `test_engine.py`.
- **Data-quality limitations** — the S1-09 level is surfaced on every record with reasons appended; asserted in `test_caveats.py`.
- **Schema extended, not forked; deterministic, no LLM** — one structure, byte-identical across reruns (verified on the real NSW data).
- **Screening-level language** — banned superlatives rejected at config load and asserted absent across all fields by validation.
- **Unit tests** — an excluded cell, a proxy-caveat cell and a low-confidence cell are asserted explicitly; 130 tests in `tests/explanation/` pass.

### Full-run verification

`python -m pipeline --only explanation` over the real NSW data: **1,233** eligible + **46,078** excluded = **47,311** explained; excluded reason codes `{missing_wind_data: 45,711, protected_area: 6,740, urban_area: 62, excessive_slope: 55}`; **40,674** records carry the demand-proxy caveat; every record carries exactly one confidence note; **10/10** validation checks passed; outputs byte-stable across reruns.

### Cross-cutting updates

Data specification (v1.10: §4.10 extended, §7 mapping row, §8 change-control note), `pipeline/README.md` (CLI + stage-sequence + stage-description + file tree), and a stale S2-06a-era stage-order test in `tests/shortlist/test_shortlist_docs_consistency.py` corrected (`explanation` sits between `scoring` and `shortlist`). The F16 reason-code vocabulary (Decision-Engine Spec §6.5) is **consumed, not changed**.

### Scope boundary / design note

**Option B** was chosen for the excluded reasons: the loader reconstructs the F16 pairs from the two delimited forms the integrated table already carries, rather than materialising the paired `exclusion_reasons` column on the frozen S1-08 baseline (which S2-02 forbids mutating). Should the paired column later be materialised on the integrated table, that is a separate S1-08/integration change and the loader can switch to reading it directly.
