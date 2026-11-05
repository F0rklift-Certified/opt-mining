# OPT-MINING Sprint 4 Final Guidance

**Source:** [Original client Word document](reference/OPT_MINING_Sprint4_Final_Guidance_for_Students.docx).

The text below transcribes the supplied client brief. Formatting is adapted for GitHub; the original document remains the source of authority.


OPT-MINING

Sprint 4 - Final Sprint Brief

Final Integration, Validation & Delivery


Renewable Energy Site Planning & Decision Support Platform
Client direction to the student development team

- **Client:** Iman Rahimi, OPT-MINING
- **Project:** NSW Wind-Energy Site Screening Decision-Support MVP
- **Sprint:** Sprint 4 - Final Sprint
- **Primary focus:** Integration, validation, testing, documentation and handover
- **Scope principle:** Complete and validate the existing MVP before adding new functionality

## 1. Message to the Team

Thank you everyone for the progress across the previous sprints. We have now reached the final development sprint. The purpose of Sprint 4 is not to expand the project into new research areas or add major new features. The priority is to complete the current web application, integrate all existing components, validate the decision-support results, test the system end-to-end, and hand over a stable and reproducible OPT-MINING MVP.

By the end of this sprint, It is  expected to be able to obtain the repository, follow the documented setup instructions, launch the application, run the NSW wind-site screening analysis, inspect eligible and excluded sites, understand the ranking and explanations, change the decision scenario, rerun the analysis, and obtain reproducible results without modifying source code.

## 2. Sprint Goal

Deliver a complete, stable and demonstrable web-based OPT-MINING NSW wind-energy site-screening MVP that connects the integrated data pipeline, validation, exclusions, decision engine, ranking, explanations, scenario analysis and web interface.

## 3. Required End-to-End Workflow

The final product must support the following workflow using the real integrated NSW dataset:

Launch application -> Select scenario/weights -> Run analysis -> View NSW map -> View eligible/excluded sites -> View ranked shortlist -> Select a site -> Inspect explanation/data quality -> Change scenario -> Rerun -> Compare results

## 4. Sprint 4 Backlog

### S4-01 - Complete Outstanding Sprint 3 Integration

Priority: P0   |   Objective: Create one stable application baseline before adding any final-sprint enhancements.

#### Required work

Merge approved Sprint 2 and Sprint 3 work in the correct dependency order.

Complete any remaining web-to-decision-service integration.

Complete outstanding analysis controls, map rendering, click-to-inspect and ranked-results integration.

Resolve merge conflicts, failed checks and integration defects.

Confirm that the frontend uses the approved backend decision engine; do not duplicate scoring logic in the UI.

Record the final integrated dataset/configuration version used for the Sprint 4 baseline.

Acceptance criteria: A clean checkout can start the integrated application and execute the core analysis flow without manually running intermediate scripts.

Deliverable: Stable Sprint 4 baseline/release branch or tag, with all required Sprint 2-3 components integrated.

### S4-02 - Complete the Interactive NSW Suitability Map

Priority: P0   |   Objective: Make the spatial screening results usable and understandable through the web interface.

#### Required work

Render NSW analysis cells/sites on the map.

Clearly distinguish eligible and excluded cells.

Visualise relative suitability for eligible cells without presenting excluded cells as merely low scoring.

Provide a clear map legend and meaningful labels.

Support zoom and pan.

Maintain acceptable rendering performance with the intended NSW dataset.

Acceptance criteria: A user can visually distinguish eligible, excluded and relatively higher/lower suitability areas on the NSW map.

Deliverable: Working map component integrated with the real decision-engine results.

### S4-03 - Complete Site Inspection and Explainability

Priority: P0   |   Objective: Allow a user to understand why a site is eligible, excluded, highly ranked or weakly ranked.

#### Required work

For eligible sites show Site/Cell ID, suitability score, rank, wind value/score, demand proxy, infrastructure indicator(s), geographic/environmental indicator(s), criterion contributions, positive factors, weaknesses and data-quality/confidence information.

For excluded sites show Site/Cell ID, ineligible status, exclusion reason(s) and relevant data-quality information.

Do not assign a normal suitability rank to an excluded site.

Use the existing deterministic explanation engine; an LLM is not required.

Ensure explanations are derived from the same backend analysis results displayed elsewhere in the application.

Acceptance criteria: Selecting a site from the map or shortlist opens a consistent, understandable site-detail view with traceable explanations.

Deliverable: Integrated Site Detail / Why This Site? panel.

### S4-04 - Finalise Analysis Controls and Weight Handling

Priority: P0   |   Objective: Allow users to configure and run screening scenarios without editing source code.

#### Required work

Provide default criterion weights.

Provide named scenario presets.

Allow custom weights for Wind, Demand Proxy, Infrastructure and Geographic/Environmental criteria.

Validate or normalise user-entered weights consistently with the approved decision-engine specification.

Provide Reset to Default and Run Analysis actions.

Clearly display the currently active scenario/configuration.

Acceptance criteria: Changing valid weights or selecting a preset and running the analysis invokes the approved backend decision engine and can change the ranking.

Deliverable: Final analysis-control panel connected to the decision service.

### S4-05 - Complete Scenario Comparison

Priority: P1   |   Objective: Demonstrate that OPT-MINING supports decision exploration rather than presenting one fixed ranking.

#### Required work

Support comparison of at least Default, Wind-focused and Infrastructure-focused/custom scenarios.

Where practical, show score change, rank change and changes in Top-N membership.

Identify sites that remain relatively stable across scenarios.

Use the same approved decision engine for every scenario; do not implement alternative frontend scoring.

Acceptance criteria: A user can rerun at least two materially different scenarios and observe/explain resulting ranking changes.

Deliverable: Scenario-comparison view or reproducible comparison output.

### S4-06 - Finalise the Ranked Shortlist

Priority: P0   |   Objective: Provide a clear shortlist of eligible candidate sites synchronised with the map.

#### Required work

Display Rank, Site ID, suitability score and key criterion information.

Provide a practical Top-N option such as Top 10/25/50 where useful.

Selecting a ranked result should locate/highlight the corresponding map cell and open its details.

Ensure the shortlist is generated from the backend decision-engine output, not recalculated in the UI.

Acceptance criteria: The shortlist and map remain synchronised and show consistent scores, ranks and site identifiers.

Deliverable: Final ranked-results panel.

### S4-07 - Validate the Screening Results

Priority: P1   |   Objective: Assess whether the model output is geographically and practically plausible without forcing it to reproduce existing developments.

#### Required work

Compare selected high-ranked areas against defensible external reference information such as known NSW wind developments and/or NSW Renewable Energy Zones (REZs).

Document the comparison method and reference information used.

Identify areas of agreement and disagreement.

Investigate plausible reasons for disagreement, including data limitations, criteria, exclusions and modelling assumptions.

Do not tune results merely to make known developments rank highly.

Acceptance criteria: The team can explain whether the spatial screening pattern appears credible and clearly document important limitations.

Deliverable: validation_report.md (or equivalent) plus reproducible supporting outputs.

### S4-08 - Perform Sensitivity Analysis

Priority: P1   |   Objective: Show how dependent the shortlist is on decision preferences and weights.

#### Required work

Run several meaningful weighting scenarios.

Compare Top-N sites across scenarios.

Report rank/score changes.

Identify relatively robust sites and highly weight-sensitive sites.

Interpret the results rather than only presenting tables.

Acceptance criteria: The team demonstrates how preference changes affect recommendations and identifies important sensitivity in the ranking.

Deliverable: Concise sensitivity-analysis report and reproducible outputs.

### S4-09 - Complete End-to-End and Failure-Case Testing

Priority: P0   |   Objective: Verify the whole product, not only individual backend functions.

#### Required work

Test the full workflow from application launch through scenario selection, analysis, map, shortlist, site inspection and rerun.

Test invalid weights and extreme weight combinations.

Test missing/invalid input and missing criterion values.

Test excluded-site selection.

Test empty/no-result filters.

Test backend/API failure handling where applicable.

Ensure failures produce clear user-facing messages rather than silent or misleading results.

Acceptance criteria: The complete application flow passes documented tests and common failure cases are handled safely.

Deliverable: Final test report/checklist and automated tests where appropriate.

### S4-10 - Make Methodology and Limitations Visible

Priority: P1   |   Objective: Ensure users understand what the application results do and do not mean.

#### Required work

State that the suitability score is a relative screening score under the selected data, criteria, assumptions and weights.

Do not describe the score as a probability of project success or as proof that a location is objectively the best site.

Continue to identify cell-level demand as a spatial demand proxy, not measured local electricity consumption.

Keep relevant data-quality/confidence caveats accessible in the application.

Use consistent terminology across the UI, documentation and final presentation.

Acceptance criteria: A non-developer user can understand the interpretation and major limitations of the displayed results.

Deliverable: User-facing methodology/limitations text integrated into the application.

### S4-11 - Add Results Export

Priority: P2   |   Objective: Allow useful downstream use of the screening shortlist if time permits.

#### Required work

Provide CSV export of ranked eligible results if technically feasible after P0/P1 functionality is stable.

Include useful fields such as cell_id, rank, suitability_score and the four criterion groups or their key values.

Ensure exported results correspond to the active scenario.

Acceptance criteria: The exported file reproduces the currently displayed analysis results and identifies the active scenario/configuration.

Deliverable: CSV export function.

### S4-12 - Complete Documentation and Reproducibility

Priority: P0   |   Objective: Enable another developer or assessor to understand, install and run the final system.

#### Required work

Document project purpose and scope.

Document system architecture and repository structure.

Document dependencies and installation.

Document how to start backend/service components and the web application.

Document data sources, data pipeline and CRS/spatial methodology.

Document hard exclusions, criteria/features, normalisation, weighting/scoring and ranking.

Document the demand-proxy methodology, explainability, scenario analysis, validation, testing and known limitations.

Test the instructions from a clean environment.

Acceptance criteria: A technically competent user can follow the documentation and reproduce the final application without undocumented manual intervention.

Deliverable: Final README/setup guide and supporting technical documentation.

### S4-13 - Prepare the Final Architecture and Data-Flow Diagram

Priority: P1   |   Objective: Provide one clear representation of how all project components fit together.

#### Required work

Show Data Sources -> Data Processing & Integration -> NSW Analysis Cells -> Validation -> Hard Exclusions -> Normalisation -> MCDA Scoring & Ranking -> Explanation & Scenario Analysis -> Decision-Service API -> Web Application -> Map/Shortlist/Site Details.

Use terminology consistent with the final implementation.

Include the diagram in the project documentation and final presentation.

Acceptance criteria: The diagram accurately reflects the implemented system rather than an aspirational architecture.

Deliverable: Final architecture/data-flow diagram.

### S4-14 - Final Client Demonstration and Handover

Priority: P0   |   Objective: Demonstrate and hand over the completed MVP in a reproducible state.

#### Required work

Launch the actual application rather than using screenshots or mock-ups.

Show the NSW map and active criteria/weights.

Run the analysis.

Show eligible and excluded cells.

Show the ranked shortlist.

Select an eligible site and explain its result.

Select or demonstrate an excluded site and its exclusion reason.

Change the scenario/weights, rerun and demonstrate ranking changes.

Present validation and sensitivity-analysis findings.

Demonstrate export if implemented.

Hand over the final repository, documentation, tests, reports, diagrams and presentation/demo material.

Acceptance criteria: The client can reproduce the demonstrated workflow from the handed-over repository and documentation.

Deliverable: Final release/handover package and live demonstration.

## 5. Priority Rules

| Priority | Meaning | Rule |
| --- | --- | --- |
| P0 | Essential for final acceptance | Must be completed before final handover. |
| P1 | Required final-quality work | Complete after the core integrated application is stable. |
| P2 | Useful enhancement | Only complete if P0 and P1 work is stable and time remains. |

## 6. Sprint 4 Definition of Done

Sprint 4 is complete when I can obtain the repository, follow the documented setup instructions, launch the OPT-MINING web application, run the NSW wind-site screening analysis, view eligible and excluded locations on the map, inspect and understand individual site results, view the ranked shortlist, modify the decision scenario, rerun the analysis, and obtain reproducible and explainable results without modifying source code.

Moving all Jira tickets to Done is not, by itself, sufficient. Final acceptance is based on the integrated behaviour of the product, its reproducibility, its documented limitations, and the quality of the final demonstration and handover.

## 7. Final Handover Checklist

Working OPT-MINING web application.

Complete and clean GitHub repository/final release.

Reproducible integrated NSW data/pipeline baseline.

Decision engine and decision-service integration.

Automated tests and final end-to-end test evidence.

Validation report.

Sensitivity-analysis results.

Final README/setup and methodology documentation.

Architecture/data-flow diagram.

Final presentation and live-demo material.

CSV/result export if implemented.

## 8. Client Closing Direction

The final sprint should demonstrate the value of the system we have built across the previous sprints. Please prioritise reliability, traceability, explainability and a complete user workflow over adding new technical features. A smaller, stable and defensible MVP is more valuable than a broader application containing unfinished components.

Client: Iman Rahimi

Organisation: OPT-MINING
