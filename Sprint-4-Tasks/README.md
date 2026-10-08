# Sprint 4 Final Integration Validation and Delivery

**Client:** Iman Rahimi, OPT-MINING

**Project:** NSW Wind-Energy Site Screening Decision-Support MVP

**Source:** [Client guidance](OPT_MINING_Sprint4_Final_Guidance.md) and [original Word brief](reference/OPT_MINING_Sprint4_Final_Guidance_for_Students.docx)

**Backlog prepared:** 7 October 2026

## Sprint Goal

Deliver a complete, stable and demonstrable web-based OPT-MINING NSW wind-energy site-screening MVP that connects the integrated data pipeline, validation, exclusions, decision engine, ranking, explanations, scenario analysis and web interface.

Complete and validate the existing MVP before adding new functionality. Sprint 4 prioritises integration, reliability, traceability, explainability, testing and handover.

## Required End-to-End Workflow

Launch application → Select scenario/weights → Run analysis → View NSW map → View eligible/excluded sites → View ranked shortlist → Select a site → Inspect explanation/data quality → Change scenario → Rerun → Compare results.

Use the real integrated NSW dataset and the approved backend decision engine throughout.

## Backlog

| ID | Task | Client priority |
| --- | --- | --- |
| [S4-01](S4-01-Complete-Outstanding-Sprint-3-Integration.md) | Complete Outstanding Sprint 3 Integration | P0 |
| [S4-02](S4-02-Interactive-NSW-Suitability-Map.md) | Complete the Interactive NSW Suitability Map | P0 |
| [S4-03](S4-03-Site-Inspection-and-Explainability.md) | Complete Site Inspection and Explainability | P0 |
| [S4-04](S4-04-Analysis-Controls-and-Weight-Handling.md) | Finalise Analysis Controls and Weight Handling | P0 |
| [S4-05](S4-05-Scenario-Comparison.md) | Complete Scenario Comparison | P1 |
| [S4-06](S4-06-Ranked-Shortlist.md) | Finalise the Ranked Shortlist | P0 |
| [S4-07](S4-07-Validate-Screening-Results.md) | Validate the Screening Results | P1 |
| [S4-08](S4-08-Sensitivity-Analysis.md) | Perform Sensitivity Analysis | P1 |
| [S4-09](S4-09-End-to-End-and-Failure-Case-Testing.md) | Complete End-to-End and Failure-Case Testing | P0 |
| [S4-10](S4-10-Methodology-and-Limitations.md) | Make Methodology and Limitations Visible | P1 |
| [S4-11](S4-11-Results-Export.md) | Add Results Export | P2 |
| [S4-12](S4-12-Documentation-and-Reproducibility.md) | Complete Documentation and Reproducibility | P0 |
| [S4-13](S4-13-Architecture-and-Data-Flow-Diagram.md) | Prepare the Final Architecture and Data-Flow Diagram | P1 |
| [S4-14](S4-14-Final-Client-Demonstration-and-Handover.md) | Final Client Demonstration and Handover | P0 |

The [Jira ticket index](Sprint-4-Jira-Tickets.md) supplies a proposed dependency plan. Each task file retains the client's objective, required work, acceptance criterion and deliverable. The source brief does not assign owners or story points; the team should agree those during planning.

All checkboxes start unchecked. Existing Sprint 2/3 implementations may satisfy parts of these tasks after integration and verification, but a task definition does not establish that the current main branch meets its acceptance criterion. These Markdown files are worksheets for the team's board; uploading them does not create Jira issues.

## Priority Rules

| Priority | Meaning | Client rule |
| --- | --- | --- |
| P0 | Essential for final acceptance | Must be completed before final handover. |
| P1 | Required final-quality work | Complete after the core integrated application is stable. |
| P2 | Useful enhancement | Only complete if P0 and P1 work is stable and time remains. |

There are 8 P0 tasks, 5 P1 tasks and 1 P2 task. S4-11 results export is conditional; it does not replace a P0/P1 acceptance requirement.

## Definition of Done

Sprint 4 is complete when the client can obtain the repository, follow the documented setup instructions, launch the OPT-MINING web application, run the NSW wind-site screening analysis, view eligible and excluded locations on the map, inspect and understand individual site results, view the ranked shortlist, modify the decision scenario, rerun the analysis, and obtain reproducible and explainable results without modifying source code.

Moving all Jira tickets to Done is not, by itself, sufficient. Final acceptance depends on integrated product behaviour, reproducibility, documented limitations, the live demonstration and handover. A successful rehearsal should be recorded separately from the client's final acceptance.

## Final Handover Checklist

- [ ] Working OPT-MINING web application.
- [ ] Complete and clean GitHub repository/final release.
- [ ] Reproducible integrated NSW data/pipeline baseline.
- [ ] Decision engine and decision-service integration.
- [ ] Automated tests and final end-to-end test evidence.
- [ ] Validation report.
- [ ] Sensitivity-analysis results.
- [ ] Final README/setup and methodology documentation.
- [ ] Architecture/data-flow diagram.
- [ ] Final presentation and live-demo material.
- [ ] CSV/result export, if implemented.

## Cross-Sprint Continuity

S4-01 integrates approved Sprint 2 and Sprint 3 work in dependency order before establishing the final-sprint baseline. Reuse the existing decision specification, feature definitions, hard exclusions, deterministic explanations, service boundary and applicable tests. Review current implementation evidence against the new client acceptance criteria instead of rebuilding already accepted functionality.

The client brief requests a diagram of Data Sources → Data Processing & Integration → NSW Analysis Cells → Validation → Hard Exclusions → Normalisation → MCDA Scoring & Ranking → Explanation & Scenario Analysis → Decision-Service API → Web Application → Map/Shortlist/Site Details. S4-13 must reconcile this representation with the implemented system.

## Source Identity

The original supplied Word document is retained unchanged. SHA-256:

`6382a9a4ee6f5b31dd1eff4a2749276b8ae36f03c2025b4ca2de94ab04a46078`

Client requirements are transcribed in [OPT_MINING_Sprint4_Final_Guidance.md](OPT_MINING_Sprint4_Final_Guidance.md). Suggested sequencing in the Jira index is a planning aid, not an additional client requirement.
