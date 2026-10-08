# Sprint 4 Jira Tickets

**Epic:** Sprint 4 — Final Integration, Validation and Delivery

**Source:** [Client final-sprint guidance](OPT_MINING_Sprint4_Final_Guidance.md)

**Sprint goal and final acceptance:** [Sprint 4 README](README.md)

The 14 tickets below preserve the client's numbered backlog and P0/P1/P2 priorities. Owners and story points are intentionally unassigned because the source brief does not provide them. All acceptance checkboxes remain unchecked pending evidence and review.

## Proposed Dependency Plan

This plan is inferred from the workflow and task interfaces for team planning. The client brief does not prescribe these dependency edges. Work can start in parallel; the dependencies indicate final verification prerequisites. Confirm the sequence during sprint planning.

| Task | Priority | Final verification prerequisites |
| --- | --- | --- |
| [S4-01](S4-01-Complete-Outstanding-Sprint-3-Integration.md) | P0 | Approved Sprint 2/3 work |
| [S4-02](S4-02-Interactive-NSW-Suitability-Map.md) | P0 | S4-01 |
| [S4-03](S4-03-Site-Inspection-and-Explainability.md) | P0 | S4-01, S4-02, S4-06 |
| [S4-04](S4-04-Analysis-Controls-and-Weight-Handling.md) | P0 | S4-01 |
| [S4-05](S4-05-Scenario-Comparison.md) | P1 | S4-04, S4-06 |
| [S4-06](S4-06-Ranked-Shortlist.md) | P0 | S4-01, S4-02 |
| [S4-07](S4-07-Validate-Screening-Results.md) | P1 | S4-01 |
| [S4-08](S4-08-Sensitivity-Analysis.md) | P1 | S4-04, S4-05 |
| [S4-09](S4-09-End-to-End-and-Failure-Case-Testing.md) | P0 | S4-02, S4-03, S4-04, S4-05, S4-06, S4-10 |
| [S4-10](S4-10-Methodology-and-Limitations.md) | P1 | S4-01 |
| [S4-11](S4-11-Results-Export.md) | P2 | S4-04, S4-06 |
| [S4-12](S4-12-Documentation-and-Reproducibility.md) | P0 | S4-01, S4-07, S4-08, S4-09, S4-10, S4-13 |
| [S4-13](S4-13-Architecture-and-Data-Flow-Diagram.md) | P1 | S4-01 |
| [S4-14](S4-14-Final-Client-Demonstration-and-Handover.md) | P0 | S4-01, S4-02, S4-03, S4-04, S4-05, S4-06, S4-07, S4-08, S4-09, S4-10, S4-12, S4-13 |

- Establish S4-01's integrated baseline first.
- Complete map, controls and shortlist integration; connect site details and scenario comparison to the same analysis output.
- Start validation, sensitivity analysis, methodology and architecture documentation as their inputs become stable.
- Run final S4-09 tests on the integrated product, then complete clean-environment S4-12 reproduction and S4-14 client handover.
- S4-11 may begin only after P0/P1 work is stable and time remains; if implemented, include its export tests and demonstration in S4-09/S4-14.

## Ticket Worksheets

## S4-01: Complete Outstanding Sprint 3 Integration

**Type:** Task

**Priority:** P0

**Status:** Backlog

**Worksheet:** [S4-01-Complete-Outstanding-Sprint-3-Integration.md](S4-01-Complete-Outstanding-Sprint-3-Integration.md)

### Objective

Create one stable application baseline before adding any final-sprint enhancements.

### Required Work

- [ ] Merge approved Sprint 2 and Sprint 3 work in the correct dependency order.
- [ ] Complete any remaining web-to-decision-service integration.
- [ ] Complete outstanding analysis controls, map rendering, click-to-inspect and ranked-results integration.
- [ ] Resolve merge conflicts, failed checks and integration defects.
- [ ] Confirm that the frontend uses the approved backend decision engine; do not duplicate scoring logic in the UI.
- [ ] Record the final integrated dataset/configuration version used for the Sprint 4 baseline.

### Acceptance Criteria

- [ ] A clean checkout can start the integrated application and execute the core analysis flow without manually running intermediate scripts.

### Deliverable

Stable Sprint 4 baseline/release branch or tag, with all required Sprint 2-3 components integrated.

---

## S4-02: Complete the Interactive NSW Suitability Map

**Type:** Task

**Priority:** P0

**Status:** Backlog

**Worksheet:** [S4-02-Interactive-NSW-Suitability-Map.md](S4-02-Interactive-NSW-Suitability-Map.md)

### Objective

Make the spatial screening results usable and understandable through the web interface.

### Required Work

- [ ] Render NSW analysis cells/sites on the map.
- [ ] Clearly distinguish eligible and excluded cells.
- [ ] Visualise relative suitability for eligible cells without presenting excluded cells as merely low scoring.
- [ ] Provide a clear map legend and meaningful labels.
- [ ] Support zoom and pan.
- [ ] Maintain acceptable rendering performance with the intended NSW dataset.

### Acceptance Criteria

- [ ] A user can visually distinguish eligible, excluded and relatively higher/lower suitability areas on the NSW map.

### Deliverable

Working map component integrated with the real decision-engine results.

---

## S4-03: Complete Site Inspection and Explainability

**Type:** Task

**Priority:** P0

**Status:** Backlog

**Worksheet:** [S4-03-Site-Inspection-and-Explainability.md](S4-03-Site-Inspection-and-Explainability.md)

### Objective

Allow a user to understand why a site is eligible, excluded, highly ranked or weakly ranked.

### Required Work

- [ ] For eligible sites show Site/Cell ID, suitability score, rank, wind value/score, demand proxy, infrastructure indicator(s), geographic/environmental indicator(s), criterion contributions, positive factors, weaknesses and data-quality/confidence information.
- [ ] For excluded sites show Site/Cell ID, ineligible status, exclusion reason(s) and relevant data-quality information.
- [ ] Do not assign a normal suitability rank to an excluded site.
- [ ] Use the existing deterministic explanation engine; an LLM is not required.
- [ ] Ensure explanations are derived from the same backend analysis results displayed elsewhere in the application.

### Acceptance Criteria

- [ ] Selecting a site from the map or shortlist opens a consistent, understandable site-detail view with traceable explanations.

### Deliverable

Integrated Site Detail / Why This Site? panel.

---

## S4-04: Finalise Analysis Controls and Weight Handling

**Type:** Task

**Priority:** P0

**Status:** Backlog

**Worksheet:** [S4-04-Analysis-Controls-and-Weight-Handling.md](S4-04-Analysis-Controls-and-Weight-Handling.md)

### Objective

Allow users to configure and run screening scenarios without editing source code.

### Required Work

- [ ] Provide default criterion weights.
- [ ] Provide named scenario presets.
- [ ] Allow custom weights for Wind, Demand Proxy, Infrastructure and Geographic/Environmental criteria.
- [ ] Validate or normalise user-entered weights consistently with the approved decision-engine specification.
- [ ] Provide Reset to Default and Run Analysis actions.
- [ ] Clearly display the currently active scenario/configuration.

### Acceptance Criteria

- [ ] Changing valid weights or selecting a preset and running the analysis invokes the approved backend decision engine and can change the ranking.

### Deliverable

Final analysis-control panel connected to the decision service.

---

## S4-05: Complete Scenario Comparison

**Type:** Task

**Priority:** P1

**Status:** Backlog

**Worksheet:** [S4-05-Scenario-Comparison.md](S4-05-Scenario-Comparison.md)

### Objective

Demonstrate that OPT-MINING supports decision exploration rather than presenting one fixed ranking.

### Required Work

- [ ] Support comparison of at least Default, Wind-focused and Infrastructure-focused/custom scenarios.
- [ ] Where practical, show score change, rank change and changes in Top-N membership.
- [ ] Identify sites that remain relatively stable across scenarios.
- [ ] Use the same approved decision engine for every scenario; do not implement alternative frontend scoring.

### Acceptance Criteria

- [ ] A user can rerun at least two materially different scenarios and observe/explain resulting ranking changes.

### Deliverable

Scenario-comparison view or reproducible comparison output.

---

## S4-06: Finalise the Ranked Shortlist

**Type:** Task

**Priority:** P0

**Status:** Backlog

**Worksheet:** [S4-06-Ranked-Shortlist.md](S4-06-Ranked-Shortlist.md)

### Objective

Provide a clear shortlist of eligible candidate sites synchronised with the map.

### Required Work

- [ ] Display Rank, Site ID, suitability score and key criterion information.
- [ ] Provide a practical Top-N option such as Top 10/25/50 where useful.
- [ ] Selecting a ranked result should locate/highlight the corresponding map cell and open its details.
- [ ] Ensure the shortlist is generated from the backend decision-engine output, not recalculated in the UI.

### Acceptance Criteria

- [ ] The shortlist and map remain synchronised and show consistent scores, ranks and site identifiers.

### Deliverable

Final ranked-results panel.

---

## S4-07: Validate the Screening Results

**Type:** Task

**Priority:** P1

**Status:** Backlog

**Worksheet:** [S4-07-Validate-Screening-Results.md](S4-07-Validate-Screening-Results.md)

### Objective

Assess whether the model output is geographically and practically plausible without forcing it to reproduce existing developments.

### Required Work

- [ ] Compare selected high-ranked areas against defensible external reference information such as known NSW wind developments and/or NSW Renewable Energy Zones (REZs).
- [ ] Document the comparison method and reference information used.
- [ ] Identify areas of agreement and disagreement.
- [ ] Investigate plausible reasons for disagreement, including data limitations, criteria, exclusions and modelling assumptions.
- [ ] Do not tune results merely to make known developments rank highly.

### Acceptance Criteria

- [ ] The team can explain whether the spatial screening pattern appears credible and clearly document important limitations.

### Deliverable

validation_report.md (or equivalent) plus reproducible supporting outputs.

---

## S4-08: Perform Sensitivity Analysis

**Type:** Task

**Priority:** P1

**Status:** Backlog

**Worksheet:** [S4-08-Sensitivity-Analysis.md](S4-08-Sensitivity-Analysis.md)

### Objective

Show how dependent the shortlist is on decision preferences and weights.

### Required Work

- [ ] Run several meaningful weighting scenarios.
- [ ] Compare Top-N sites across scenarios.
- [ ] Report rank/score changes.
- [ ] Identify relatively robust sites and highly weight-sensitive sites.
- [ ] Interpret the results rather than only presenting tables.

### Acceptance Criteria

- [ ] The team demonstrates how preference changes affect recommendations and identifies important sensitivity in the ranking.

### Deliverable

Concise sensitivity-analysis report and reproducible outputs.

---

## S4-09: Complete End-to-End and Failure-Case Testing

**Type:** Task

**Priority:** P0

**Status:** Backlog

**Worksheet:** [S4-09-End-to-End-and-Failure-Case-Testing.md](S4-09-End-to-End-and-Failure-Case-Testing.md)

### Objective

Verify the whole product, not only individual backend functions.

### Required Work

- [ ] Test the full workflow from application launch through scenario selection, analysis, map, shortlist, site inspection and rerun.
- [ ] Test invalid weights and extreme weight combinations.
- [ ] Test missing/invalid input and missing criterion values.
- [ ] Test excluded-site selection.
- [ ] Test empty/no-result filters.
- [ ] Test backend/API failure handling where applicable.
- [ ] Ensure failures produce clear user-facing messages rather than silent or misleading results.

### Acceptance Criteria

- [ ] The complete application flow passes documented tests and common failure cases are handled safely.

### Deliverable

Final test report/checklist and automated tests where appropriate.

---

## S4-10: Make Methodology and Limitations Visible

**Type:** Task

**Priority:** P1

**Status:** Backlog

**Worksheet:** [S4-10-Methodology-and-Limitations.md](S4-10-Methodology-and-Limitations.md)

### Objective

Ensure users understand what the application results do and do not mean.

### Required Work

- [ ] State that the suitability score is a relative screening score under the selected data, criteria, assumptions and weights.
- [ ] Do not describe the score as a probability of project success or as proof that a location is objectively the best site.
- [ ] Continue to identify cell-level demand as a spatial demand proxy, not measured local electricity consumption.
- [ ] Keep relevant data-quality/confidence caveats accessible in the application.
- [ ] Use consistent terminology across the UI, documentation and final presentation.

### Acceptance Criteria

- [ ] A non-developer user can understand the interpretation and major limitations of the displayed results.

### Deliverable

User-facing methodology/limitations text integrated into the application.

---

## S4-11: Add Results Export

**Type:** Task

**Priority:** P2

**Status:** Backlog

**Worksheet:** [S4-11-Results-Export.md](S4-11-Results-Export.md)

### Objective

Allow useful downstream use of the screening shortlist if time permits.

### Required Work

- [ ] Provide CSV export of ranked eligible results if technically feasible after P0/P1 functionality is stable.
- [ ] Include useful fields such as cell_id, rank, suitability_score and the four criterion groups or their key values.
- [ ] Ensure exported results correspond to the active scenario.

### Acceptance Criteria

- [ ] The exported file reproduces the currently displayed analysis results and identifies the active scenario/configuration.

### Deliverable

CSV export function.

---

## S4-12: Complete Documentation and Reproducibility

**Type:** Task

**Priority:** P0

**Status:** Backlog

**Worksheet:** [S4-12-Documentation-and-Reproducibility.md](S4-12-Documentation-and-Reproducibility.md)

### Objective

Enable another developer or assessor to understand, install and run the final system.

### Required Work

- [ ] Document project purpose and scope.
- [ ] Document system architecture and repository structure.
- [ ] Document dependencies and installation.
- [ ] Document how to start backend/service components and the web application.
- [ ] Document data sources, data pipeline and CRS/spatial methodology.
- [ ] Document hard exclusions, criteria/features, normalisation, weighting/scoring and ranking.
- [ ] Document the demand-proxy methodology, explainability, scenario analysis, validation, testing and known limitations.
- [ ] Test the instructions from a clean environment.

### Acceptance Criteria

- [ ] A technically competent user can follow the documentation and reproduce the final application without undocumented manual intervention.

### Deliverable

Final README/setup guide and supporting technical documentation.

---

## S4-13: Prepare the Final Architecture and Data-Flow Diagram

**Type:** Task

**Priority:** P1

**Status:** Backlog

**Worksheet:** [S4-13-Architecture-and-Data-Flow-Diagram.md](S4-13-Architecture-and-Data-Flow-Diagram.md)

### Objective

Provide one clear representation of how all project components fit together.

### Required Work

- [ ] Show Data Sources -> Data Processing & Integration -> NSW Analysis Cells -> Validation -> Hard Exclusions -> Normalisation -> MCDA Scoring & Ranking -> Explanation & Scenario Analysis -> Decision-Service API -> Web Application -> Map/Shortlist/Site Details.
- [ ] Use terminology consistent with the final implementation.
- [ ] Include the diagram in the project documentation and final presentation.

### Acceptance Criteria

- [ ] The diagram accurately reflects the implemented system rather than an aspirational architecture.

### Deliverable

Final architecture/data-flow diagram.

---

## S4-14: Final Client Demonstration and Handover

**Type:** Task

**Priority:** P0

**Status:** Backlog

**Worksheet:** [S4-14-Final-Client-Demonstration-and-Handover.md](S4-14-Final-Client-Demonstration-and-Handover.md)

### Objective

Demonstrate and hand over the completed MVP in a reproducible state.

### Required Work

- [ ] Launch the actual application rather than using screenshots or mock-ups.
- [ ] Show the NSW map and active criteria/weights.
- [ ] Run the analysis.
- [ ] Show eligible and excluded cells.
- [ ] Show the ranked shortlist.
- [ ] Select an eligible site and explain its result.
- [ ] Select or demonstrate an excluded site and its exclusion reason.
- [ ] Change the scenario/weights, rerun and demonstrate ranking changes.
- [ ] Present validation and sensitivity-analysis findings.
- [ ] Demonstrate export if implemented.
- [ ] Hand over the final repository, documentation, tests, reports, diagrams and presentation/demo material.

### Acceptance Criteria

- [ ] The client can reproduce the demonstrated workflow from the handed-over repository and documentation.

### Deliverable

Final release/handover package and live demonstration.
