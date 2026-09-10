

OPT-MINING | Software Development Studio
Combined Sprint 2 & 3 Guidance  |  Client: Iman Rahimi, OPT-MINING

## OPT-MINING
## Combined Sprint 2 & 3
## Implementation Guidance
## Renewable Energy Site Planning & Decision Support Platform

From integrated NSW data to a working web-based decision-support MVP
Client guidance for the student development team


Client Iman Rahimi, OPT-MINING
Project stage Sprint 1 completed; Sprint 2 and Sprint 3 combined
Combined sprint focus Decision engine + web application integration
Target outcome Working, explainable NSW wind-site screening MVP


OPT-MINING | Software Development Studio
Combined Sprint 2 & 3 Guidance  |  Client: Iman Rahimi, OPT-MINING
## 1. Overall Direction After Sprint 1
Thank you everyone for completing Sprint 1. We now need to move beyond data integration and turn the
integrated NSW spatial dataset into a usable decision-support product. I am therefore combining the previously
planned Sprint 2 (suitability/decision engine) and Sprint 3 (web prototype) into one implementation sprint.
The objective is not to add more datasets or build an unnecessarily complex AI system. The objective is to
connect the data foundation to transparent decision logic and expose that logic through a working web
application.
## COMBINED SPRINT GOAL
Deliver a working web-based NSW wind-energy site-screening MVP that applies hard
exclusions, calculates transparent suitability scores, ranks candidate sites, visualises them
on a map, and explains why a site received its result.
- Definition of Done
At the end of this combined sprint, I should be able to open the application and:
- View candidate NSW analysis cells/sites on an interactive map.
- Apply the agreed hard exclusions and see which sites are eligible or excluded.
- Choose or adjust transparent criterion weights for wind, demand proxy, infrastructure and
geographic/environmental suitability.
- Run the analysis and obtain a ranked shortlist of eligible sites.
- Click a site and see its underlying feature values, overall score and an understandable explanation of the
result.
- Compare at least two different weighting/scenario configurations.
- Trace displayed results back to the integrated Sprint 1 data and documented methodology.
A polished commercial platform is not required. A reliable, reproducible and explainable MVP is required.
## 3. Required Architecture
Please preserve separation between data, decision logic and presentation. The intended flow is:
Sprint 1 integrated data
## ↓
Validation / feature preparation
## ↓
Hard exclusions
## ↓
## Normalisation
## ↓
Suitability / decision engine
## ↓
Ranking + explanation
## ↓
Web API/service layer if needed
## ↓
Interactive web application

OPT-MINING | Software Development Studio
Combined Sprint 2 & 3 Guidance  |  Client: Iman Rahimi, OPT-MINING
The scoring methodology must not be implemented only inside the user-interface code. It should be a reusable
module that can be tested independently and later reused by OPT-MINING.
## 4. Detailed Implementation Steps
Step 1 — Freeze and Validate the Sprint 1 Integrated Dataset
Use the completed Sprint 1 integrated NSW dataset as the baseline input. Do not restart data discovery unless
a critical defect is identified. Add automated validation checks for required columns, unique Site/Cell IDs, valid
coordinates/geometries, expected units/ranges, missing values and eligibility-related fields. The application
must fail clearly or flag a data-quality problem rather than silently producing rankings from invalid input.
## Step 2 — Finalise Hard Exclusion Rules
Create a dedicated exclusion component. Hard exclusions must be applied before suitability scoring. Each
excluded cell must retain a machine-readable and human-readable reason (for example
protected/environmentally restricted area, invalid geometry/data, or another rule that the team has technically
justified). Do not allow a high wind score to compensate for a hard exclusion. Keep thresholds/rules
configurable where appropriate and document every rule.
## Step 3 — Define Exact Decision Features
For each of the four criteria, specify the exact per-cell feature(s) used by the decision engine. Avoid vague
variables such as 'infrastructure score' without explaining how it is calculated. Wind may use the selected GWA
resource variable; demand must remain explicitly labelled as a spatial demand proxy where allocated below the
AEMO region; infrastructure should use measurable indicators such as distance to transmission/substation
and/or REZ membership; geographic/environmental suitability should use the agreed measurable features such
as slope or other non-hard constraints.
## Step 4 — Normalise Features Correctly
Convert features measured on different scales into comparable suitability components. Document the
selected normalisation method and direction. For example, higher wind resource may be better, while greater
distance to transmission is normally worse. Handle outliers and missing values explicitly. Normalisation
parameters should be reproducible and should not change unpredictably simply because a user filters the map.
Step 5 — Implement the Baseline Suitability Engine
Implement a transparent weighted multi-criteria baseline. A suitable MVP structure is S_i = w_W W_i + w_D D_i +
w_I I_i + w_G G_i for eligible site i, where the component scores are normalised and the weights are
configurable. The exact weighting defaults must be documented as assumptions rather than presented as
objectively correct business values. Enforce or automatically normalise weights so that their interpretation is
clear.
Step 6 — Produce Ranking and Site-Level Explanation
For every eligible site, calculate component scores, total score and rank. Preserve enough information to
explain the result. A site explanation should identify its strongest positive factors, important weaknesses, any
proxy variables used and relevant data-quality limitations. Avoid an LLM dependency for the core explanation;
deterministic template/rule-based explanations are sufficient and more auditable for this MVP.
## Step 7 — Implement Scenario / Weight Comparison
Support at least two decision configurations so users can see that ranking depends on preferences. For
example, one scenario may emphasise wind resource while another emphasises grid/infrastructure
accessibility. The user should be able to change weights or select saved presets, rerun the analysis and observe

OPT-MINING | Software Development Studio
Combined Sprint 2 & 3 Guidance  |  Client: Iman Rahimi, OPT-MINING
changes in ranking. Do not call these scenarios probabilistic uncertainty scenarios unless they actually model
uncertainty.
Step 8 — Build the Web Application
Deliver the product as a lightweight web application rather than a desktop executable. Use a framework
appropriate to the team's skills (for example a Python web/dashboard framework or a separated
frontend/backend if already justified by the team's architecture). The interface should prioritise functionality
and clarity over visual effects. It should contain a map, controls/criteria, ranked results and site-
detail/explanation views.
Step 9 — Interactive NSW Map
Visualise eligible and excluded/candidate locations appropriately without making the map unreadable. Users
should be able to inspect a site and retrieve its ID, score, key criteria and eligibility information. Where practical,
provide filters such as top-N sites or minimum suitability threshold. The map must represent the same analysis
results as the ranking table; avoid separate duplicated calculations in the UI.
Step 10 — Results and Shortlist Panel
Provide a ranked table/list linked to the map. At minimum show Site ID, total suitability score/rank and
important component values. Allow the user to inspect a selected site in more detail. Export of the ranked
shortlist (for example CSV) is desirable if it can be implemented without distracting from the core MVP.
Step 11 — Validation and Sanity Checking
Test whether the resulting spatial pattern is credible. Compare high-ranking areas against defensible external
references such as known NSW wind developments and/or Renewable Energy Zones as a sanity check, while
recognising that the model is not trained to reproduce those locations. Investigate obvious contradictions. Also
create small controlled test cases where the expected ranking is known so that the scoring code itself can be
verified.
Step 12 — Testing, Documentation and Reproducibility
Add unit tests for decision functions and integration tests for the end-to-end flow. Document how to install, run
and reproduce the application from a clean environment. Record data provenance, assumptions, limitations,
scoring equations, exclusions, default weights and application architecture. Avoid absolute claims such as
'best site to build a wind farm'; use screening-level language such as 'higher-ranked candidate under the
selected assumptions and criteria'.
## 5. Minimum Web Application Screens / Functions
Component Minimum requirement Priority
Analysis controls
Region fixed to NSW for MVP; criteria
weights/presets; run/update analysis.
## Must
Interactive map
Display candidate sites/cells and allow
site inspection.
## Must
Ranked shortlist
Rank eligible sites using the same
decision-engine output.
## Must
Site detail
Show raw/derived features, component
scores, total score and eligibility.
## Must
## Explanation
Explain main positive/negative factors and
relevant proxy/quality caveats.
## Must
Scenario comparison
Compare at least two weighting
## Must

OPT-MINING | Software Development Studio
Combined Sprint 2 & 3 Guidance  |  Client: Iman Rahimi, OPT-MINING
configurations.
## Export
Download shortlist/results as CSV or
similar.
## Should
Advanced dashboard styling Commercial-grade visual polish. Could
- Suggested Jira / GitHub Work Breakdown
The team should convert the following into appropriately sized Jira stories/tasks and PRs. Ownership is for the
student team to decide; the client is defining outcomes, not assigning individual students.
- Decision-engine specification: final features, directions, formulas, assumptions and default configuration.
- Hard-exclusion module with exclusion-reason reporting and tests.
- Feature normalisation module with tests.
- Suitability scoring and ranking module with configurable weights and tests.
- Explanation and scenario-comparison logic.
- Web application skeleton and application-to-engine integration.
- Interactive map and site-detail interaction.
- Ranked shortlist/results panel and optional export.
- Validation/sanity-check analysis.
- End-to-end testing, documentation, deployment/run instructions and final demo preparation.
Please keep PRs reviewable. Avoid one very large final PR containing the entire combined sprint. A useful
pattern is to merge tested backend decision components first, then web integration, then
validation/documentation.
- Acceptance Criteria for the Combined Sprint
ID Acceptance criterion
## AC1
A reproducible NSW integrated dataset from Sprint 1 is
successfully consumed by the application.
## AC2
Hard exclusions are applied before scoring and the reason for
exclusion is retained.
## AC3
Every scoring feature has a documented definition, unit/source
and beneficial/adverse direction.
## AC4
Normalisation and scoring are implemented outside the UI and
covered by tests.
## AC5
Weights are configurable and their interpretation/default values
are documented.
## AC6
Eligible sites receive component scores, total scores and
deterministic rankings.
## AC7
The application provides understandable site-level explanations
and does not misrepresent the demand proxy.
## AC8
The web application provides an interactive NSW map and ranked
shortlist.
## AC9
At least two weighting scenarios/configurations can be
compared.
## AC10
Results receive technical sanity checking against defensible
reference locations/regions.
## AC11
A clean installation/run path and technical documentation are

OPT-MINING | Software Development Studio
Combined Sprint 2 & 3 Guidance  |  Client: Iman Rahimi, OPT-MINING
provided.
## AC12
The MVP uses screening-level claims and clearly documents
important limitations.
## 8. Priority: Must / Should / Could
MUST complete
- Hard exclusions and exclusion reasons.
- Exact decision features and transparent normalisation.
- Configurable suitability scoring and ranking.
- Working web application connected to the real Sprint 1 data.
- Interactive NSW map, ranked shortlist and site details.
- Tests, documentation and reproducible execution.
SHOULD complete
- Scenario/weight comparison with useful presets.
- Clear explanation of ranking drivers and data-quality/proxy caveats.
- Shortlist export and practical filtering.
- External sanity-check visualisation or analysis.
COULD complete only after the above is stable
- More polished UI/branding.
- Additional states or national expansion.
- Additional criteria/datasets that clearly improve the MVP.
- Explicitly Out of Scope for This Combined Sprint
Unless all required functionality is already complete and stable, please do not divert effort into:
- LLM/chatbot or agentic-AI functionality.
- Deep learning or predictive ML added only for technical novelty.
- Complex mathematical/multi-objective optimisation.
- Solar, battery or other technology expansion beyond the agreed wind-site MVP.
- A production-scale national platform.
- Commercial cloud architecture, payment systems, authentication or other enterprise features not required
for the SDS demonstration.
These are valid future OPT-MINING directions, but the current priority is to deliver a defensible end-to-end
screening product.
## 10. Required Final Demonstration
For the combined sprint review, please demonstrate the system end-to-end rather than only showing slides:
- Start the application from the documented environment.
- Show the NSW analysis inputs and current default criteria/weights.
- Run the screening process.
- Show exclusions and explain at least one excluded site.
- Show the ranked shortlist and map.

OPT-MINING | Software Development Studio
Combined Sprint 2 & 3 Guidance  |  Client: Iman Rahimi, OPT-MINING
- Open one high-ranked site and explain the factors behind its score.
- Change the weighting/scenario and demonstrate how/why the ranking changes.
- Show a validation/sanity-check result.
- Briefly show the relevant GitHub code/tests and documentation supporting reproducibility.
## 11. Client Review Checkpoints
Please use short checkpoints during the combined sprint so methodological problems are identified before the
final integration.
Checkpoint What I want to review Expected evidence
A — Decision design
Final features, exclusions, normalisation
and scoring design.
Short design note + Jira/PR references.
B — Backend working
Exclusion, scoring, ranking and tests on
real NSW data.
Runnable output + PRs/tests.
C — Web integration
Map, controls, ranking and site-detail view
connected to backend.
Working application demo.
D — Final acceptance
Validation, documentation, limitations and
complete end-to-end demonstration.
Release candidate / final PR.


## Client: Iman Rahimi
Organisation: OPT-MINING