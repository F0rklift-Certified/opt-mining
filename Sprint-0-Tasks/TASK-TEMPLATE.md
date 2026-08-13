# Task Template — Sprint 0 Data Investigation

*This template defines the scaffold that every Sprint 0 investigation document follows. Copy the relevant sections into your document and fill them in as you work.*

---

## How to Use This Template

Each investigation document follows the same structure so that outputs are consistent and can be assembled into the final Sprint 0 deliverables (Data Inventory, Data Dictionary, Integration Issues Log, and Recommendations).

Fill in every section. If a section is not applicable, write "N/A" with a brief explanation why.

---

## Document Scaffold

### 1. Objective

*One or two sentences describing what this investigation aims to answer.*

### 2. Investigation Checklist

*A checklist of specific things to find out. Tick items off as you complete them.*

- [ ] Item 1
- [ ] Item 2
- [ ] ...

### 3. Data Sources Investigated

*For each source you look at, record:*

| Source Name | URL | Format(s) | Licence | Download Available? | Notes |
|-------------|-----|-----------|---------|---------------------|-------|
|             |     |           |         |                     |       |

### 4. Sample Data Downloaded

*For each sample you download:*

| File Name | Source | Size | Spatial Coverage | Temporal Coverage | Location in Repo |
|-----------|--------|------|------------------|-------------------|------------------|
|           |        |      |                  |                   |                  |

Keep samples small and manageable. Do not download hundreds of gigabytes.

### 5. Data Inspection Summary

*For each dataset you open and inspect:*

| Dataset | Columns/Variables | Row Count | Missing Values | Coordinate Fields | Units | Date/Time Fields | Usable? |
|---------|-------------------|-----------|----------------|-------------------|-------|------------------|---------|
|         |                   |           |                |                   |       |                  |         |

### 6. Data Dictionary

*For each promising dataset, create a data dictionary. One table per dataset.*

**Dataset:** [Name]
**Source:** [URL or reference]
**Format:** [CSV / GeoJSON / NetCDF / GeoTIFF / etc.]
**CRS:** [Coordinate Reference System, e.g. EPSG:4326]
**Temporal Range:** [Start – End, or "Static"]
**Spatial Resolution:** [e.g. 250m, 1km, 5km, state-level, NEM region]

| Field/Column Name | Data Type | Units | Description | Example Value | Missing Values? |
|-------------------|-----------|-------|-------------|---------------|-----------------|
|                   |           |       |             |               |                 |

### 7. Integration Issues Identified

*Document any problems that will need to be solved when combining this data with other datasets.*

| Issue | Description | Severity (High/Med/Low) | Suggested Resolution | Resolved? |
|-------|-------------|-------------------------|----------------------|-----------|
|       |             |                         |                      |           |

Common issues to look for:
- Different coordinate reference systems (CRS)
- Different spatial resolutions
- Missing or inconsistent coordinates
- Different temporal ranges or granularity
- Different units
- Inconsistent region/state naming
- Missing observations or gaps
- Incompatible file formats

### 8. Key Findings & Recommendations

*Summarise what you found. What is usable? What needs more work? What should be prioritised?*

### 9. Acceptance Criteria

*How do we know this task is done? List the concrete outputs expected.*

- [ ] Criterion 1
- [ ] Criterion 2
- [ ] ...

---

## Notes for the Team

- **Be honest about gaps.** If data is not available or not usable, say so clearly.
- **Do not over-download.** A representative sample is sufficient for Sprint 0.
- **Document everything.** The value of Sprint 0 is the documentation, not the data itself.
- **Flag surprises early.** If something does not match expectations, raise it with the team.
- **Reference the Product Knowledge Base** for context on how each dataset feeds into the platform.
