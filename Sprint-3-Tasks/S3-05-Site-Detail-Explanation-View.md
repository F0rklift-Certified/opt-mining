# S3-05: Site-Detail & Explanation View

**Type:** Story
**Priority:** High
**Story Points:** 5
**Labels:** web-app, explanation, site-detail, frontend
**Blocked by:** S3-03, S3-04
**Blocks:** S3-07

---

## Objective

When a user selects a site (from the map or the shortlist), show its raw/derived feature values, per-criterion component scores, total score, eligibility, and the deterministic explanation of its result.

---

## Context

Guidance Step 10 (site detail) and Step 6 (explanation), §5 (Site detail + Explanation — Must). This view renders the S2-06 explanation structure and the S2-05 component scores. It is where the app "explains why a site received its result" — a headline goal of the combined sprint.

---

## Deliverables

1. A site-detail panel bound to `get_site_detail`.
2. Rendering of component scores + total + eligibility.
3. Rendering of the deterministic explanation (positive factors, weaknesses, proxy caveats, data-quality notes).

---

## Acceptance Criteria

- [ ] Selecting a site shows its raw/derived features, per-criterion component scores, total score and eligibility
- [ ] The explanation identifies main positive factors and important weaknesses (satisfies **AC7**)
- [ ] Proxy variables are labelled as proxies — the demand proxy is never presented as measured local demand (satisfies **AC7**)
- [ ] Relevant data-quality/confidence caveats are shown
- [ ] For an excluded site, the exclusion reason(s) are shown clearly
- [ ] All content comes from the S2-06/S2-08 output — the UI does not generate its own explanation text
- [ ] Screening-level language is used ("higher-ranked candidate under the selected assumptions"), never "best site"

---

## Technical Notes

- Renders the S2-06 explanation JSON structure verbatim into UI elements — no UI-side re-derivation of factors.
- Cross-cutting impact: consumes the S2-06 explanation contract and the S2-03 reason vocabulary; the selection trigger comes from S3-03/S3-04.
