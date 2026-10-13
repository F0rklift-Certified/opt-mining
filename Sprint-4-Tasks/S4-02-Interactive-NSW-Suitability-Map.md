# S4-02: Complete the Interactive NSW Suitability Map

**Type:** Task
**Priority:** P0
**Status:** Backlog — acceptance evidence to be reviewed
**Source:** [Client Sprint 4 brief](OPT_MINING_Sprint4_Final_Guidance.md), §4 S4-02

## Objective

Make the spatial screening results usable and understandable through the web interface.

## Required Work

- [ ] Render NSW analysis cells/sites on the map.
- [ ] Clearly distinguish eligible and excluded cells.
- [ ] Visualise relative suitability for eligible cells without presenting excluded cells as merely low scoring.
- [ ] Provide a clear map legend and meaningful labels.
- [ ] Support zoom and pan.
- [ ] Maintain acceptable rendering performance with the intended NSW dataset.

## Acceptance Criteria

- [ ] A user can visually distinguish eligible, excluded and relatively higher/lower suitability areas on the NSW map.
- [ ] Eligible and excluded cells are visually distinct, and relative suitability for eligible cells is shown on a continuous scale (excluded cells are not presented as merely low-scoring).
- [ ] A clear legend and meaningful labels explain the styling.
- [ ] Zoom and pan work, and the full NSW grid renders readably (not visually overwhelmed) at the intended resolution.
- [ ] Cell data, coordinates and eligibility/score values come from the decision-service engine output — no recomputation or reprojection in the UI.
- [ ] The rendered layer represents the same engine output as the ranked shortlist (consistent IDs/scores/eligibility).

## Deliverable

Working map component integrated with the real decision-engine results.

## Completion Evidence

Record the implementation PR/commit, relevant tests or reproducible outputs, and the review outcome here before closing this task. Refer to the [Sprint 4 Definition of Done](README.md#definition-of-done) for final acceptance.
