# S3-02: Analysis Controls (Weights / Presets / Run)

**Type:** Story
**Priority:** High
**Story Points:** 3
**Labels:** web-app, controls, frontend
**Blocked by:** S3-01
**Blocks:** S3-06

---

## Objective

Provide the controls panel: region fixed to NSW, adjustable criterion weights and/or selectable presets, and a run/update-analysis action that re-invokes the decision service.

---

## Context

Guidance Step 8 and §5 (Analysis controls — Must). Weights are user inputs (AC5). This panel is how the user expresses preferences; it sends them to the S2-08 service and never scores locally.

---

## Deliverables

1. A controls panel with weight inputs and/or preset selector.
2. A run/update action wired to `run_analysis`.
3. Display of the currently active weights/preset.

---

## Acceptance Criteria

- [ ] Region is fixed to NSW for the MVP
- [ ] The user can adjust criterion weights and/or select a saved preset (satisfies **AC5**)
- [ ] The currently active weights and their interpretation (e.g. normalised to sum 1) are visible
- [ ] A run/update-analysis action re-invokes the S2-08 service and refreshes results
- [ ] Weights are sent to the service; the UI performs no scoring or normalisation itself (supports **AC4**)
- [ ] Default weights match the documented S2-01 assumptions
- [ ] Invalid weight input is handled gracefully (validation message, no silent bad run)

---

## Technical Notes

- Presets here are the S2-07 scenario presets — reuse that config, do not define a second preset list.
- Changing weights must trigger a full re-run through the service so normalisation bounds stay fixed per run (never per UI filter) — this preserves the S2-04 guarantee.
