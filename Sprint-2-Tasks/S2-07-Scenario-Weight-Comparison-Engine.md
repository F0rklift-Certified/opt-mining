# S2-07: Scenario / Weight-Comparison Engine

**Type:** Story
**Priority:** High
**Story Points:** 3
**Labels:** scenarios, decision-engine
**Blocked by:** S2-05
**Blocks:** S2-08

---

## Objective

Support at least two decision configurations (scenarios) so users can see that ranking depends on preferences — running the engine under different weight sets and returning comparable ranked outputs.

---

## Context

Guidance Step 7. The scoring module (S2-05) already accepts a weights config at runtime, so a scenario is just a named weight set fed to the same pure function. This task adds the **scenario abstraction** — named presets, running the engine per scenario, and a comparison structure the UI (S3-06) can render. The guidance warns: do not call these "probabilistic uncertainty scenarios" — they model preferences, not uncertainty.

---

## Deliverables

1. A scenario definition format (named preset → weight set).
2. At least two documented preset scenarios (e.g. wind-led vs infrastructure-led).
3. A comparison result comparing rankings across scenarios.

---

## Acceptance Criteria

- [ ] At least **two** weighting scenarios/configurations can be defined and run (satisfies **AC9**)
- [ ] Presets are documented (e.g. "Wind-led" emphasising wind resource; "Grid-led" emphasising infrastructure accessibility)
- [ ] Each scenario reuses the S2-05 scoring function unchanged — no duplicate scoring logic
- [ ] Running two scenarios produces two ranked outputs plus a comparison (e.g. rank delta per cell)
- [ ] Users can change weights or select a saved preset, rerun, and observe ranking changes
- [ ] Scenarios are labelled as **preference/weighting** scenarios, explicitly **not** probabilistic uncertainty scenarios
- [ ] Normalisation bounds remain consistent across scenarios for a given eligible population (only weights differ)
- [ ] Unit tests verify that different weights produce different, correctly re-ranked outputs

---

## Scenario Preset Example

```yaml
# scenarios.yaml
scenarios:
  wind_led:
    label: "Wind-led"
    description: "Emphasises wind resource quality"
    weights: { wind_speed: 0.55, dist_transmission_km: 0.15, demand_proxy: 0.15, slope_deg: 0.05, inside_rez: 0.10 }
  grid_led:
    label: "Grid-led"
    description: "Emphasises grid/infrastructure accessibility"
    weights: { wind_speed: 0.25, dist_transmission_km: 0.35, demand_proxy: 0.15, slope_deg: 0.05, inside_rez: 0.20 }
```

---

## Technical Notes

- A scenario is data (a weight set), not code — keep presets in a config file, consistent with the weights-as-user-input principle.
- Cross-cutting impact: the comparison structure is the contract for the S3-06 scenario-comparison UI and is exposed via the S2-08 service layer.
