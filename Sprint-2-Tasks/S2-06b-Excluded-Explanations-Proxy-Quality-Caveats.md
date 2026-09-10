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

- [ ] For any excluded cell, the explanation states the machine- and human-readable exclusion reason(s) from S2-03
- [ ] Any **proxy variable** used is called out as a proxy — the demand proxy is never described as measured local demand (satisfies **AC7**, proxy caveat)
- [ ] Relevant **data-quality limitations** (from the S1-09 confidence flag / S2-02 checks) are surfaced in the explanation
- [ ] The excluded-cell and caveat output reuses the S2-06a structured schema (extended, not forked) and remains deterministic with no LLM dependency
- [ ] Screening-level language throughout
- [ ] Unit tests assert explanation content for an excluded cell and for a cell with a proxy caveat and a low-confidence caveat

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
