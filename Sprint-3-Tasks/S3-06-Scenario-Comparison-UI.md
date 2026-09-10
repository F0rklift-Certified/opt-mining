# S3-06: Scenario-Comparison UI

**Type:** Story
**Priority:** High
**Story Points:** 3
**Labels:** web-app, scenarios, frontend
**Blocked by:** S3-02, S2-07
**Blocks:** S3-07

---

## Objective

Let the user compare at least two weighting configurations and observe how the ranking changes between them.

---

## Context

Guidance Step 7 and §5 (Scenario comparison — Must). The comparison logic lives in the S2-07 engine; this ticket renders it. The guidance warns not to present these as probabilistic uncertainty scenarios.

---

## Deliverables

1. A scenario selector for at least two configurations/presets.
2. A side-by-side or delta comparison of rankings.
3. Clear labelling of scenarios as preference-based.

---

## Acceptance Criteria

- [ ] The user can select/compare at least **two** weighting scenarios (satisfies **AC9**)
- [ ] The comparison shows how the ranking differs between scenarios (e.g. side-by-side ranks or rank delta)
- [ ] Changing weights or picking a preset, rerunning, and observing ranking changes is demonstrable
- [ ] Comparison uses S2-07 engine output — no UI-side re-ranking
- [ ] Scenarios are labelled as **weighting/preference** scenarios, not probabilistic uncertainty scenarios
- [ ] At least two useful presets are available (e.g. wind-led vs grid-led)

---

## Technical Notes

- Calls `compare_scenarios` on the S2-08 service; reuses the S2-07 preset config surfaced in S3-02.
- Cross-cutting impact: this is the visible proof of AC9 for the final demo (Step 7 of the demo script).
