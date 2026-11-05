# S4-13: Prepare the Final Architecture and Data-Flow Diagram

**Type:** Task
**Priority:** P1
**Status:** Done — diagram in the handover pack (review pending)
**Source:** [Client Sprint 4 brief](OPT_MINING_Sprint4_Final_Guidance.md), §4 S4-13

## Objective

Provide one clear representation of how all project components fit together.

## Required Work

- [x] Show Data Sources -> Data Processing & Integration -> NSW Analysis Cells -> Validation -> Hard Exclusions -> Normalisation -> MCDA Scoring & Ranking -> Explanation & Scenario Analysis -> Decision-Service API -> Web Application -> Map/Shortlist/Site Details.
- [x] Use terminology consistent with the final implementation.
- [ ] Include the diagram in the project documentation and final presentation.

## Acceptance Criteria

- [x] The diagram accurately reflects the implemented system rather than an aspirational architecture.
- [x] The full flow is shown: Data Sources → Data Processing & Integration → NSW Analysis Cells → Validation → Hard Exclusions → Normalisation → MCDA Scoring & Ranking → Explanation & Scenario Analysis → Decision-Service API → Web Application → Map/Shortlist/Site Details.
- [x] Terminology on the diagram matches the final implementation (component and interface names).
- [ ] The diagram is included in the project documentation and the final presentation.

## Deliverable

Final architecture/data-flow diagram.

## Completion Evidence

**Owner:** Pouya Mousavi. **Produced:** 2026-10-22.

The diagram is `03_Architecture_Data_Flow.svg` / `.png` in the handover pack (kept outside the repository by team decision) and is embedded in the Handover Guide (§6). A landscape version for a slide is in the pack (`06_Presentation/A2 data-flow diagram`); it still has to be inserted into the team's current deck ("v2 feedback"), which shows a four-step process slide instead. It shows the full client chain — Data Sources → Data Processing & Integration → NSW Analysis Cells → Validation → Hard Exclusions → Normalisation → MCDA Scoring & Ranking → Explanation & Scenario Analysis → Decision-Service API → Web Application → Map/Shortlist/Site Details — and names what implements each stage (`pipeline/grid`, `pipeline/exclusions` with its 8 rules, `pipeline/scoring/normalise`, contract 1.3.1 endpoints, `app/web`), with the run store and re-run loop.

**Review outcome:** _pending client review._

Refer to the [Sprint 4 Definition of Done](README.md#definition-of-done) for final acceptance.
