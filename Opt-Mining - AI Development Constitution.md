# Opt-Mining – AI Development Constitution (Version 0)

*Status: Living document. Updated as Sprint 0 resolves data and technical questions.*

## Purpose

This document defines the engineering, scientific and architectural principles that every AI assistant must follow when contributing to the Opt-Mining renewable energy planning platform.

## Product Context

The platform is a **strategic screening tool** for wind energy siting in Australia. It narrows a continent to a defensible shortlist of candidate areas worth investigating further.

It is not a chatbot, not a general GIS package, and not an engineering-grade siting tool. Its output informs what to study next; it never constitutes a site approval.

Every contribution should strengthen the platform's ability to integrate public data honestly, score locations transparently, and explain why one area ranked above another.

## Platform Philosophy

The platform augments planner judgement.

Humans set the criteria weights, interpret the shortlist and decide what to investigate. The platform assembles data, scores, ranks, explains and visualises.

A recommendation the user cannot interrogate is not a recommendation - it is an assertion. Explainability is the primary user's immediate next step after receiving a shortlist, and is therefore a core requirement rather than a nicety.

## Architectural Rules

* Keep data integration, criteria derivation, scoring and presentation in separate layers.
* Never encode planning rules inside model weights; deterministic rules belong in inspectable code.
* Keep the architecture modular by technology - wind is the first technology, not the only one. Do not bake wind-specific assumptions into shared layers where a cheap abstraction avoids it.
* Each component should be independently replaceable without requiring changes to adjacent layers.
* Criteria weights are user inputs, never hard-coded constants.
* Make coordinate reference systems, spatial resolutions and units explicit at every boundary - never convert silently.
* Record the provenance, licence and vintage of every dataset that enters the platform, and carry attribution through to the interface and the report.
* Ensure any analysis can be reproduced from its recorded inputs, seeds and model versions. This means pinned inputs and stamped versions, not an audit subsystem.
* Keep long-running analysis observable and cancellable.

## Scientific Integrity

These rules apply to all project contributors — human and AI alike — and take precedence over convenience, deadlines and elegance.

* **Never build a circular model.** The Global Wind Atlas is an input, not a prediction target. Training a model to predict resource data from features derived from that same data proves nothing and will not survive scrutiny in the technical report.
* **Never invent, extrapolate or hard-code data values** to make a pipeline run.
* **Never present a placeholder, mock or synthetic result as a real one.**
* **Never present indicative figures as bankable ones.** No output may be described as a project cost, a guaranteed LCOE, or an engineering-grade assessment.
* **Never let poor data pass as good.** Where critical data is missing, exclude the cell. Where non-critical data is missing or low confidence, retain and flag it. Never silently assign a normal ranking to a poorly evidenced cell.
* **Always state the analysis resolution and its limitations** wherever results are presented.
* **Validate against reality.** Check that known successful wind development areas score highly, using public operational and existing wind farm data.
* **Report confidence alongside every score.**
* When a result looks surprising, investigate the data before adjusting the model.

## Technology Direction

* **Language:** Python.
* **Data and geospatial:** Pandas, GeoPandas, rasterio and xarray; QGIS and equivalent GIS tools for exploration and verification.
* **Storage:** file-based geospatial formats initially; introduce a database with spatial support only when the data volume or access pattern justifies it.
* **Machine learning:** scikit-learn or equivalent, with model versioning - scoped per the Open Questions in the Product Knowledge Base.
* **Web layer:** deferred. React, Flask or FastAPI are the candidates; the decision belongs to a later sprint and should not block Sprint 0.
* **Source control:** GitHub, with the repository README maintained as the project's front door.

Technology choices may evolve. Architectural and scientific principles do not.

## Coding Expectations

* Write maintainable, testable and modular code.
* Keep exploratory notebooks out of the production path; promote proven logic into tested modules.
* Prefer composition over duplication.
* Document public interfaces, including the units and coordinate system of every spatial input and output.
* Test data transformations, not just application plumbing.
* Consider memory and runtime when processing grids at national scale.
* Do not download or process more data than the analysis requires.
* Document the source and licence of every third-party library in the project's dependency manifest or a dedicated NOTICE file.

## AI Behaviour

Before generating code, models or analysis:

1. Verify understanding of the problem and the data it depends on.
2. Identify missing information - especially unstated units, projections, region naming and time bases.
3. Explain assumptions.
4. Recommend improvements when appropriate.
5. Produce outputs that align with the existing architecture.

Understand the data before building the software. Where a dataset has not yet been inspected, say so rather than assuming its shape.

AI should not optimise for speed alone. It should optimise for correctness, explainability and the credibility of the platform's recommendations.

## Definition of Success

A successful contribution is not simply working code.

A successful contribution produces results that are correct, explainable and honest about their own confidence, preserves architectural consistency, and increases the platform's ability to support real early-stage renewable energy screening decisions.
