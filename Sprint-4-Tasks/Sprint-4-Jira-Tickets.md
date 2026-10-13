# Sprint 4 Jira Tickets

**Epic:** Sprint 4 — Final Integration, Validation and Delivery

**Source:** [Client final-sprint guidance](OPT_MINING_Sprint4_Final_Guidance.md)

**Sprint goal and final acceptance:** [Sprint 4 README](README.md)

The tickets below preserve the client's numbered backlog and P0/P1/P2 priorities. Three P0 items were split for sizing and reviewability — **S4-09 → S4-09a/S4-09b**, **S4-12 → S4-12a/S4-12b**, **S4-14 → S4-14a/S4-14b** — giving 17 tickets (11 P0, 5 P1, 1 P2); each split pair together covers the original client scope. Owners and story points are intentionally unassigned because the source brief does not provide them. All acceptance checkboxes remain unchecked pending evidence and review.

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
| [S4-09a](S4-09a-End-to-End-Workflow-Testing.md) | P0 | S4-02, S4-03, S4-04, S4-05, S4-06, S4-10 |
| [S4-09b](S4-09b-Failure-Case-Testing.md) | P0 | S4-09a |
| [S4-10](S4-10-Methodology-and-Limitations.md) | P1 | S4-01 |
| [S4-11](S4-11-Results-Export.md) | P2 | S4-04, S4-06 |
| [S4-12a](S4-12a-Setup-and-Installation-Documentation.md) | P0 | S4-01 |
| [S4-12b](S4-12b-Methodology-Documentation-and-Clean-Environment-Reproduction.md) | P0 | S4-12a, S4-07, S4-08, S4-09a, S4-09b, S4-10, S4-13 |
| [S4-13](S4-13-Architecture-and-Data-Flow-Diagram.md) | P1 | S4-01 |
| [S4-14a](S4-14a-Final-Handover-Package.md) | P0 | S4-01, S4-02, S4-03, S4-04, S4-05, S4-06, S4-07, S4-08, S4-09a, S4-09b, S4-10, S4-12a, S4-12b, S4-13 |
| [S4-14b](S4-14b-Live-Client-Demonstration.md) | P0 | S4-14a |

- Establish S4-01's integrated baseline first.
- Complete map, controls and shortlist integration; connect site details and scenario comparison to the same analysis output.
- Start validation, sensitivity analysis, methodology and architecture documentation as their inputs become stable.
- Run S4-09a happy-path tests on the integrated product, then S4-09b failure-case tests; complete S4-12a setup docs early and S4-12b methodology docs + clean-environment reproduction once inputs are stable.
- Assemble the S4-14a handover package once P0/P1 work is stable, then run the S4-14b live demonstration against that frozen release.
- S4-11 may begin only after P0/P1 work is stable and time remains; if implemented, include its export tests and demonstration in S4-09a/S4-09b and S4-14b.

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
- [ ] Approved Sprint 2 and Sprint 3 work is merged in dependency order with no outstanding conflicts and all CI checks green.
- [ ] Remaining web↔decision-service integration (analysis controls, map, click-to-inspect, ranked results) is wired to the backend engine.
- [ ] The frontend uses the approved backend decision engine; no duplicated scoring/normalisation in the UI.
- [ ] The integrated dataset and configuration version used for the baseline is recorded.
- [ ] A release branch or tag marks the stable Sprint 4 baseline.

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
- [ ] Eligible/excluded cells are visually distinct; relative suitability for eligible cells is shown on a continuous scale (excluded cells not presented as merely low-scoring).
- [ ] A clear legend and meaningful labels explain the styling.
- [ ] Zoom and pan work; the full NSW grid renders readably at the intended resolution.
- [ ] Cell data, coordinates and eligibility/score values come from the engine output — no recomputation or reprojection in the UI.
- [ ] The rendered layer represents the same engine output as the ranked shortlist.

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
- [ ] For an eligible site: Site/Cell ID, suitability score, rank, wind value/score, demand proxy, infrastructure indicator(s), geographic/environmental indicator(s), criterion contributions, positive factors, weaknesses and data-quality/confidence are shown.
- [ ] For an excluded site: Site/Cell ID, ineligible status, exclusion reason(s) and data-quality info are shown, with no normal rank.
- [ ] Map selection and shortlist selection open the same site-detail view for the same cell.
- [ ] Explanations come from the existing deterministic explanation engine (no LLM) and the same backend analysis results shown elsewhere.

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
- [ ] Default criterion weights are provided and shown on load.
- [ ] Named presets are selectable; custom weights can be set for Wind, Demand Proxy, Infrastructure and Geographic/Environmental.
- [ ] User-entered weights are validated/normalised per the approved decision-engine specification.
- [ ] Reset to Default and Run Analysis actions both work.
- [ ] The active scenario/configuration is clearly displayed.

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
- [ ] At least Default, Wind-focused and Infrastructure-focused/custom scenarios can be compared.
- [ ] Where practical, score change, rank change and Top-N membership changes are shown.
- [ ] Relatively stable sites across scenarios are identifiable.
- [ ] Every scenario uses the same approved decision engine; no alternative frontend scoring.
- [ ] The comparison output is reproducible from documented inputs.

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
- [ ] Each row shows Rank, Site ID, suitability score and key criterion information.
- [ ] A practical Top-N option (e.g. Top 10/25/50) is available where useful.
- [ ] Selecting a ranked result locates/highlights the corresponding map cell and opens its detail view.
- [ ] The shortlist comes from the backend decision-engine output, not recalculated in the UI.
- [ ] Only eligible sites appear in the ranked shortlist.

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
- [ ] The external reference information used (known NSW wind developments and/or REZs) is named and cited.
- [ ] The comparison method is documented and reproducible.
- [ ] Areas of agreement and disagreement are identified, with plausible reasons for disagreement.
- [ ] Results are not tuned to make known developments rank highly, and this is stated.
- [ ] Supporting outputs are reproducible from documented commands and name the dataset/config version.

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
- [ ] Several meaningful weighting scenarios are run and documented.
- [ ] Top-N sites are compared across scenarios with reported rank/score changes.
- [ ] Relatively robust and highly weight-sensitive sites are identified.
- [ ] The report interprets the results, not only tables.
- [ ] Outputs are reproducible from documented commands and name the dataset/config version.

### Deliverable

Concise sensitivity-analysis report and reproducible outputs.

---

## S4-09a: Complete End-to-End Workflow Testing (Happy Path)

**Type:** Task

**Priority:** P0

**Status:** Backlog

**Worksheet:** [S4-09a-End-to-End-Workflow-Testing.md](S4-09a-End-to-End-Workflow-Testing.md)

> Split from the former S4-09. S4-09a verifies the happy-path workflow; S4-09b (below) exercises failure and edge cases.

### Objective

Verify the whole product on the intended end-to-end workflow, not only individual backend functions.

### Required Work

- [ ] Test the full workflow from application launch through scenario selection, analysis, map, shortlist, site inspection and rerun.
- [ ] Confirm the frontend exercises the approved backend decision engine throughout (no UI-side scoring).
- [ ] Capture the test as a repeatable script/checklist, run against a clean checkout of the Sprint 4 baseline.
- [ ] Record the environment, dataset/config version and commands used so the run is reproducible.

### Acceptance Criteria

- [ ] A documented end-to-end test exercises launch → scenario/weights → run analysis → NSW map → eligible/excluded cells → ranked shortlist → site inspection → change scenario → rerun → compare, and passes on a clean checkout.
- [ ] Map, shortlist and site-detail views show consistent cell IDs, scores and ranks sourced from the same backend analysis output.
- [ ] A rerun with changed weights produces an observably different ranking.
- [ ] The test is reproducible from documented commands and names the dataset/config version used.
- [ ] Automated coverage exists where practical; any manual step is explicitly recorded as such.

### Deliverable

End-to-end (happy-path) test script/checklist plus evidence of a passing run, and automated tests where appropriate.

---

## S4-09b: Complete Failure-Case Testing

**Type:** Task

**Priority:** P0

**Status:** Backlog

**Worksheet:** [S4-09b-Failure-Case-Testing.md](S4-09b-Failure-Case-Testing.md)

> Split from the former S4-09. Blocked by S4-09a.

### Objective

Verify the product fails safely: common invalid inputs, edge cases and backend failures produce clear user-facing messages rather than silent or misleading results.

### Required Work

- [ ] Test invalid weights and extreme weight combinations (all-zero, negative, single-criterion, out-of-range).
- [ ] Test missing/invalid input and missing criterion values.
- [ ] Test excluded-site selection.
- [ ] Test empty/no-result filters.
- [ ] Test backend/API failure handling where applicable (service down, timeout, malformed response).
- [ ] Ensure failures produce clear user-facing messages rather than silent or misleading results.

### Acceptance Criteria

- [ ] Invalid and extreme weight inputs are rejected or normalised per the decision-engine specification, with a clear message; the app does not crash or show a misleading ranking.
- [ ] Missing/invalid inputs and missing criterion values have a documented safe outcome rather than a silent failure.
- [ ] Selecting an excluded site shows its ineligible status and exclusion reason, never a normal rank.
- [ ] An empty/no-result filter shows an explicit "no results" state rather than a blank or stale view.
- [ ] Backend/API failure produces a clear user-facing error and leaves the app recoverable.
- [ ] Each failure case is documented with trigger, expected behaviour and observed result; automated coverage exists where practical.

### Deliverable

Final failure-case test report/checklist and automated tests where appropriate.

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
- [ ] The UI states the suitability score is a relative screening score under the selected data, criteria, assumptions and weights.
- [ ] The score is never described as a probability of success or as proof of the objectively best site.
- [ ] Cell-level demand is identified as a spatial demand proxy, not measured local consumption.
- [ ] Relevant data-quality/confidence caveats are accessible in the application.
- [ ] Terminology is consistent across UI, documentation and final presentation.

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
- [ ] The CSV contains the named fields (cell_id, rank, suitability_score and the four criterion groups or key values).
- [ ] Exported rows/values match the on-screen ranked eligible results for the active scenario.
- [ ] The active scenario/configuration is identified in the file.
- [ ] Export is implemented only after P0/P1 work is stable.

### Deliverable

CSV export function.

---

## S4-12a: Complete Setup and Installation Documentation

**Type:** Task

**Priority:** P0

**Status:** Backlog

**Worksheet:** [S4-12a-Setup-and-Installation-Documentation.md](S4-12a-Setup-and-Installation-Documentation.md)

> Split from the former S4-12. S4-12a covers install/run; S4-12b (below) covers methodology docs + clean-environment reproduction.

### Objective

Enable another developer or assessor to understand, install and start the final system.

### Required Work

- [ ] Document project purpose and scope.
- [ ] Document system architecture and repository structure.
- [ ] Document dependencies and installation.
- [ ] Document how to start backend/service components and the web application.

### Acceptance Criteria

- [ ] The README states project purpose and scope in terms a non-developer can follow.
- [ ] Repository structure and the main components are described and match the actual tree.
- [ ] Dependencies/versions are listed with installation steps for the supported platform(s).
- [ ] Documented start commands bring up the backend/service and web app, naming required environment variables.
- [ ] Documented versions/commands match the Sprint 4 baseline recorded in S4-01.

### Deliverable

Final README/setup guide covering purpose, architecture, dependencies and start-up.

---

## S4-12b: Methodology Documentation and Clean-Environment Reproduction

**Type:** Task

**Priority:** P0

**Status:** Backlog

**Worksheet:** [S4-12b-Methodology-Documentation-and-Clean-Environment-Reproduction.md](S4-12b-Methodology-Documentation-and-Clean-Environment-Reproduction.md)

> Split from the former S4-12. Blocked by S4-12a and the validation/testing/diagram inputs.

### Objective

Document the methodology and known limitations, and prove the final system reproduces from a clean environment with no undocumented manual steps.

### Required Work

- [ ] Document data sources, data pipeline and CRS/spatial methodology.
- [ ] Document hard exclusions, criteria/features, normalisation, weighting/scoring and ranking.
- [ ] Document the demand-proxy methodology, explainability, scenario analysis, validation, testing and known limitations.
- [ ] Test the full install-and-run instructions from a clean environment.

### Acceptance Criteria

- [ ] Methodology docs cover data sources, pipeline and CRS/spatial handling, consistent with the implementation.
- [ ] Hard exclusions, criteria/features, normalisation, weighting/scoring and ranking match the approved decision-engine specification.
- [ ] Demand-proxy methodology, explainability, scenario analysis, validation, testing and limitations are documented; the demand proxy is clearly a spatial proxy, not measured consumption.
- [ ] A clean-environment reproduction is performed and recorded (environment, dataset/config version, commands, resulting state).
- [ ] The reproduction succeeds without undocumented manual intervention; gaps are fixed and re-tested or recorded as limitations.

### Deliverable

Supporting technical/methodology documentation plus a recorded clean-environment reproduction result.

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
- [ ] The full flow is shown: Data Sources → Data Processing & Integration → NSW Analysis Cells → Validation → Hard Exclusions → Normalisation → MCDA Scoring & Ranking → Explanation & Scenario Analysis → Decision-Service API → Web Application → Map/Shortlist/Site Details.
- [ ] Terminology on the diagram matches the final implementation.
- [ ] The diagram is included in the project documentation and the final presentation.

### Deliverable

Final architecture/data-flow diagram.

---

## S4-14a: Assemble the Final Handover Package

**Type:** Task

**Priority:** P0

**Status:** Backlog

**Worksheet:** [S4-14a-Final-Handover-Package.md](S4-14a-Final-Handover-Package.md)

> Split from the former S4-14. S4-14a assembles the reproducible handover package; S4-14b (below) is the live demonstration.

### Objective

Produce a complete, reproducible handover package: the final release of the MVP with all supporting material.

### Required Work

- [ ] Create the final release/tag of the Sprint 4 baseline.
- [ ] Hand over the final repository, documentation, tests, reports (validation + sensitivity), diagrams and presentation/demo material.
- [ ] Confirm the released build runs the documented end-to-end workflow against the real integrated NSW dataset.
- [ ] Cross-check the handover against the Final Handover Checklist.

### Acceptance Criteria

- [ ] A final release/tag exists and corresponds to the verified Sprint 4 baseline (dataset/config version recorded).
- [ ] The package contains the working web app, repository, setup + methodology docs, automated tests + E2E evidence, validation report, sensitivity results, architecture/data-flow diagram and presentation/demo material (export if S4-11 done).
- [ ] Every Final Handover Checklist item is present and linked, or explicitly marked not-done with a reason.
- [ ] The client can reproduce the documented end-to-end workflow from the package without modifying source code.

### Deliverable

Final release/handover package.

---

## S4-14b: Final Live Client Demonstration

**Type:** Task

**Priority:** P0

**Status:** Backlog

**Worksheet:** [S4-14b-Live-Client-Demonstration.md](S4-14b-Live-Client-Demonstration.md)

> Split from the former S4-14. Blocked by S4-14a; runs against the frozen release.

### Objective

Demonstrate the completed MVP live, running the actual application end-to-end from the handed-over release.

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

### Acceptance Criteria

- [ ] The demonstration runs the live application (not screenshots/mock-ups) from the S4-14a release.
- [ ] The full workflow is shown: map + active weights → run → eligible/excluded cells → ranked shortlist → eligible-site explanation → excluded-site reason → scenario change + rerun showing ranking change.
- [ ] Validation and sensitivity-analysis findings are presented, and export is demonstrated if S4-11 was implemented.
- [ ] A successful rehearsal is recorded separately from the client's final acceptance.
- [ ] The client can reproduce the demonstrated workflow from the handed-over package.

### Deliverable

Live demonstration and its recorded rehearsal evidence.
