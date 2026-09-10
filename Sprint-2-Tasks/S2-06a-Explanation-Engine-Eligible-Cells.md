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

- [ ] A deterministic rule/template engine maps a scored cell to a structured explanation, with **no LLM dependency**
- [ ] For any eligible cell, the explanation identifies its **strongest positive factors** and **important weaknesses**, derived from the S2-05 `contrib_{feature}` contributions (satisfies **AC7**, eligible path)
- [ ] Explanations are **deterministic** — same input yields identical text
- [ ] The explanation is produced by the backend, not the UI, and returned in a structured form the web app renders
- [ ] The structured schema is documented (the contract S2-06b extends and S2-08/S3-05 consume)
- [ ] Screening-level language throughout ("higher-ranked candidate under the selected assumptions"), never "best site"
- [ ] Unit tests assert explanation content for a high-scoring cell and a marginal cell

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
