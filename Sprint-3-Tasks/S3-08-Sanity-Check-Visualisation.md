# S3-08: Sanity-Check / Validation Visualisation

**Type:** Story
**Priority:** Medium *(Should)*
**Story Points:** 3
**Labels:** web-app, validation, sanity-check
**Blocked by:** S2-09, S3-03
**Blocks:** S3-09

---

## Objective

Surface a sanity-check result that compares high-ranking areas against defensible external references (known NSW wind developments and/or Renewable Energy Zones), and investigate obvious contradictions.

---

## Context

Guidance Step 11 and §5 (external sanity-check — Should). Sprint 1's S1-12 `pipeline/sanity/` already runs known-wind-farm comparison, exclusion validation, spot-checks and score-distribution plausibility, writing `outputs/sprint1_validation_report.md`. This ticket extends that to the combined-sprint bar and makes the result visible in (or alongside) the app.

---

## Deliverables

1. A sanity-check comparison of top-ranked areas vs reference locations/REZ.
2. A visualisation or report surfaced in/with the app.
3. Documented investigation of any obvious contradictions.

---

## Acceptance Criteria

- [ ] Top-ranked areas are compared against defensible external references (known NSW wind developments and/or REZ) (satisfies **AC10**)
- [ ] The comparison is presented with appropriate caveats — the model is not trained to reproduce those locations
- [ ] Obvious contradictions are investigated and documented
- [ ] The sanity result is reachable from the app (a view, an overlay, or a linked report)
- [ ] Each check reports expected vs observed with an explicit pass/fail (no silent passes)
- [ ] The visualisation reflects the same engine output as the map/shortlist

---

## Technical Notes

- Build on `pipeline/sanity/` (S1-12); reuse its reference wind-farm dataset and REZ comparison rather than re-deriving.
- Sanity checks are read-only: the stage never re-scores or re-ranks. Systematic issues are logged as Sprint issues, not silently patched.
- Cross-cutting impact: this closes AC10 and feeds the Step-8 "show a validation/sanity-check result" item in the final demo.
