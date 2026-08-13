# Task 5 — Data Integration Analysis & Site Definition Proposal

**Sprint:** 0 (Week 1)
**Assignee:** _[Name]_ (collaborative — depends on findings from Tasks 1–4)
**Status:** Not Started
**Estimated Effort:** 1–2 days (begin after Tasks 1–4 are substantially complete)

---

## 1. Objective

Synthesise the findings from the four data investigation tasks (wind, demand, infrastructure, geographic) into a consolidated data inventory, identify cross-dataset integration challenges, propose the four core criteria for Version 1, and recommend how the system should define a "site."

This is the thinking-and-synthesis task. Its output directly shapes the platform architecture in Sprint 1.

---

## 2. Context

Tasks 1–4 each investigate data in isolation. This task asks: **how do these datasets fit together?**

The Product Knowledge Base already proposes:
- A ~5km grid cell as the site definition
- Four core criteria: wind resource, demand, infrastructure accessibility, geographic/environmental suitability
- NSW-first as a computational fallback if national scale is too expensive

This task validates those proposals against the actual data found, identifies gaps and conflicts, and produces a concrete recommendation the team can implement.

---

## 3. Prerequisites

This task depends on outputs from:
- [x] Task 1 — Wind Resource Data Investigation (findings + integration issues)
- [x] Task 2 — Electricity Demand Data Investigation (findings + integration issues)
- [x] Task 3 — Electricity Infrastructure Data Investigation (findings + integration issues)
- [x] Task 4 — Geographic & Environmental Data Investigation (findings + integration issues)

You can begin this task once each of the above has at least completed their inspection and documented their integration issues. It does not need to wait for every section to be perfect.

---

## 4. Consolidated Data Inventory

*Compile the master table from all four investigation tasks. This becomes the single reference for the team.*

| # | Dataset Name | Source | Domain | Format | CRS | Spatial Resolution | Temporal Coverage | Licence | Usable? | Priority |
|---|-------------|--------|--------|--------|-----|-------------------|-------------------|---------|---------|----------|
| 1 | | | Wind | | | | | | | |
| 2 | | | Wind | | | | | | | |
| 3 | | | Demand | | | | | | | |
| 4 | | | Infrastructure | | | | | | | |
| 5 | | | Infrastructure | | | | | | | |
| 6 | | | Geographic | | | | | | | |
| 7 | | | Geographic | | | | | | | |
| 8 | | | Geographic | | | | | | | |
| ... | | | | | | | | | | |

---

## 5. Cross-Dataset Integration Issues

*Collect all integration issues from Tasks 1–4 into a single matrix. Add any new issues discovered when comparing datasets against each other.*

### 5a. Coordinate Reference System (CRS) Alignment

| Dataset | Native CRS | Target CRS | Transformation Required? | Notes |
|---------|-----------|------------|--------------------------|-------|
|         |           |            |                          |       |

**Recommendation for project-wide CRS:** _[Fill in — likely EPSG:4326 or EPSG:7844 GDA2020]_

### 5b. Spatial Resolution Alignment

| Dataset | Native Resolution | Target (~5km grid) | Aggregation Method | Notes |
|---------|------------------|--------------------|--------------------|-------|
| Global Wind Atlas | ~250m | 5km cell | Mean / Max? | |
| DEM | ~30m | 5km cell | Mean elevation + derived slope | |
| Protected Areas | Vector (polygon) | 5km cell | Fraction of cell covered | |
| Transmission Lines | Vector (line) | 5km cell | Distance to nearest | |
| Demand (AEMO) | NEM region | 5km cell | Population-weighted proxy | |

### 5c. Temporal Alignment

| Dataset | Temporal Nature | Time Range | Alignment Strategy |
|---------|----------------|------------|--------------------|
| Wind Atlas | Long-term mean (static) | ~2008–2017? | Use as-is |
| AEMO Demand | Time series | [years found] | Aggregate to annual/seasonal mean |
| Infrastructure | Snapshot (current) | [vintage] | Use as-is |
| Protected Areas | Snapshot (current) | [vintage] | Use as-is |
| DEM | Static | N/A | Use as-is |

### 5d. Naming & Coding Inconsistencies

| Issue | Datasets Affected | Example | Resolution |
|-------|-------------------|---------|------------|
| State naming | Multiple | "NSW" vs "New South Wales" vs "1" | Lookup table |
| NEM region vs state | Demand + Infrastructure | "NSW1" vs "NSW" | Mapping |
| | | | |

### 5e. Coverage Gaps

| Gap | Affected Criterion | Impact | Mitigation |
|-----|-------------------|--------|------------|
| NEM demand does not cover WA/NT | Demand | Cannot score WA/NT for demand | Document; exclude from V1 or use alternative source |
| | | | |

### 5f. Full Integration Issues Register

*Master list — combine all issues from Tasks 1–4 plus new ones identified here:*

| # | Issue | Source Task | Severity | Resolution Strategy | Owner | Resolved? |
|---|-------|-----------|----------|--------------------:|-------|-----------|
| 1 | | Task 1 | | | | |
| 2 | | Task 2 | | | | |
| 3 | | Task 3 | | | | |
| ... | | | | | | |

---

## 6. Proposed Core Criteria (Version 1)

*Based on the data actually available, propose the four criteria. For each, define what it measures, what data source feeds it, and how it would be computed at the grid-cell level.*

### Criterion 1: Wind Resource Potential

| Aspect | Proposal |
|--------|----------|
| What it measures | |
| Data source | |
| Variable(s) used | |
| Per-cell computation | |
| Units of the derived feature | |
| Known limitations | |

### Criterion 2: Electricity Demand Indicator

| Aspect | Proposal |
|--------|----------|
| What it measures | |
| Data source | |
| Variable(s) used | |
| Per-cell computation | |
| Spatial allocation method | |
| Units of the derived feature | |
| Known limitations | |

### Criterion 3: Grid & Infrastructure Accessibility

| Aspect | Proposal |
|--------|----------|
| What it measures | |
| Data source(s) | |
| Variable(s) used | |
| Per-cell computation | |
| Distance metric (Euclidean / network?) | |
| Units of the derived feature | |
| Known limitations | |

### Criterion 4: Geographic & Environmental Suitability

| Aspect | Proposal |
|--------|----------|
| What it measures | |
| Data source(s) | |
| Hard exclusions (list) | |
| Suitability penalties (list) | |
| Per-cell computation | |
| Units of the derived feature | |
| Known limitations | |

### Criteria Summary Table

| # | Criterion | Primary Data Source | Feature Type | Hard Exclusion Component? |
|---|-----------|--------------------:|:------------:|:-------------------------:|
| 1 | Wind Resource | | Continuous | No |
| 2 | Demand Indicator | | Continuous | No |
| 3 | Infrastructure Access | | Distance-based | Possible threshold |
| 4 | Geographic Suitability | | Composite | Yes (protected areas) |

---

## 7. Site Definition Recommendation

*The Product Knowledge Base proposes a ~5km grid cell. Evaluate this against what you now know about the data.*

### Options Considered

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A — Geographic grid (~5km)** | Divide Australia into uniform cells | Consistent; all data can be mapped to it; resolution-agnostic | Arbitrary boundaries; cells may straddle features; large number of cells nationally |
| **B — Existing towns/locations** | Analyse predefined settlement locations | Fewer points; human-interpretable | Misses remote high-resource areas; biased toward population |
| **C — Predefined regions (SA2, LGA)** | Use ABS statistical areas | Official boundaries; links to census data | Irregular sizes; urban areas very small, rural very large |
| **D — Hexagonal grid (H3)** | Hexagonal cells at ~5km equivalent | Equal-area; better adjacency | More complex; less familiar |

### Recommendation

*State which option you recommend and why. Address:*

- Is ~5km feasible given the data resolutions found?
- How many cells would this produce for Australia? For NSW only?
- What CRS and grid specification would you use?
- Is the Product Knowledge Base's proposal of ~5km validated by the data, or should it be adjusted?

### Computational Feasibility

| Scope | Estimated Cell Count | Feasible on Available Hardware? | Notes |
|-------|---------------------|-------------------------------|-------|
| All of Australia | ~300,000+ (estimate) | | |
| NSW only | ~30,000 (estimate) | | |
| Single REZ | ~few hundred | | |

---

## 8. Recommended Scope for Sprint 1

*Based on everything above, what should Sprint 1 actually build first?*

- [ ] Full national coverage, or start with one state (NSW)?
- [ ] All four criteria, or start with wind + one other?
- [ ] Which integration issues must be resolved in Sprint 1 vs can be deferred?
- [ ] What is the minimum data needed to produce an end-to-end pipeline demo?

---

## 9. Open Questions for Team Discussion

*List unresolved questions that require team discussion or decision:*

| # | Question | Options | Recommendation | Decision |
|---|----------|---------|----------------|----------|
| 1 | | | | _[To be decided in team meeting]_ |
| 2 | | | | |
| 3 | | | | |

---

## 10. Acceptance Criteria

- [ ] Consolidated data inventory table is complete (all datasets from Tasks 1–4)
- [ ] Cross-dataset integration issues are documented in a single register
- [ ] CRS alignment recommendation is made
- [ ] Spatial resolution alignment strategy is documented for each dataset → 5km cell
- [ ] Temporal alignment strategy is documented
- [ ] Four core criteria are proposed with data source, computation method, and limitations
- [ ] Site definition options are evaluated and a recommendation is made
- [ ] Computational feasibility is estimated (cell counts for national vs state scope)
- [ ] Sprint 1 scope recommendation is provided
- [ ] Open questions for team discussion are listed

---

## 11. References

- Product Knowledge Base: see `Opt-Mining - Product Knowledge Base.md`
- AI Development Constitution: see `Opt-Mining - AI Development Constitution.md`
- Task 1 findings: see `01-Wind-Resource-Data-Investigation.md`
- Task 2 findings: see `02-Electricity-Demand-Data-Investigation.md`
- Task 3 findings: see `03-Electricity-Infrastructure-Data-Investigation.md`
- Task 4 findings: see `04-Geographic-Environmental-Data-Investigation.md`
