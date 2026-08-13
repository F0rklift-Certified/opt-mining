# Opt-Mining – Vision & Strategy

*Status: Living document. Updated as Sprint 0 resolves data and technical questions.*

## Vision

To become the decision-support platform for renewable energy planning in Australia, helping planners identify which locations are most suitable for future development by combining resource, demand, infrastructure and environmental data into a single, explainable assessment.

## Mission

Opt-Mining helps renewable energy developers and planners answer one practical question:

> Which locations appear most suitable for future renewable energy development, based on resource availability, electricity demand, infrastructure accessibility and other selected constraints?

The platform integrates public Australian datasets, scores candidate locations against multiple criteria, and produces a ranked shortlist a planner can interrogate, compare and take forward into detailed feasibility work.

## The Problem

Australia's transition to low-carbon energy is constrained less by ambition than by early-stage screening.

Before any detailed technical, environmental, financial or regulatory feasibility study begins, someone must decide which areas are worth studying at all. That decision requires reconciling wind resource data, electricity demand, grid infrastructure and land constraints - datasets that are published separately, in different formats, at different resolutions, by different bodies. Today that reconciliation is largely manual, producing one-off studies that are slow to build, hard to reproduce and quickly stale.

The greatest cost is rarely the analysis itself. It is the time lost integrating data, the assumptions that go unrecorded, and the inability to re-run a study when priorities change.

## Our Belief

Planners do not need another map viewer.

They need a system that weighs resource, demand, infrastructure and constraints together, and can explain why one location scored above another.

## What Opt-Mining Is

Opt-Mining is a **strategic screening tool**.

It narrows a continent to a defensible shortlist of candidate areas worth investigating further. It is explicitly not an engineering-grade siting tool, and its output is not a site approval.

Rather than replacing established geospatial and energy modelling tools, the platform integrates their public data, scores candidate locations against transparent criteria, and presents the result as a ranked, explainable comparison.

## Core Principles

* **Screening, not approval.** Output supports the decision about what to investigate next - never the decision to build.
* **Explainability is the product.** A planner must be able to inspect why a site was recommended and compare it against others. A ranking nobody can interrogate has no value.
* **Honest uncertainty.** Where data is sparse or low quality, the platform says so rather than presenting an equally confident score.
* **No false precision.** The platform never presents indicative figures as bankable numbers.
* **Multiple criteria, not one.** Suitability is a weighted judgement across resource, demand, infrastructure and environment - not maximum generation alone.
* **Modular by technology.** Wind is the first technology, not the only one; solar and storage must be addable without re-architecting.
* **Documented limitations.** Analysis resolution and its consequences are stated wherever results are shown.
* **Reproducible.** The same inputs and model version produce the same result.
* **Provenance preserved.** Dataset source, licence, vintage and attribution travel with the data through to the interface and the report.

## Users

### Primary - Renewable energy developers and planners

Early-stage screening. They need to identify and compare promising candidate areas before committing to detailed feasibility work, then decide which locations deserve further investigation.

Their workflow after receiving a shortlist is the product's real test: inspect why each site was recommended, compare characteristics side by side, and choose what to pursue.

### Secondary - Infrastructure planners and regional energy authorities

Regional assessment using a consistent, documented methodology. Not a design target for the MVP.

## Strategy

**Governing principle:** Depth over breadth. A smaller, complete, technically defensible and well-tested system is always preferred over a broader system with incomplete features.

Prove one technology end to end rather than covering several shallowly.

1. **Sprint 0 - understand the data.** Inventory, inspect and document candidate datasets before building anything. Identify integration problems; do not attempt to solve them all yet.
2. **Build the wind MVP.** One complete wind-energy screening system: data pipeline, criteria, exclusions, suitability scoring, ranked shortlist, interactive map.
3. **Validate.** Check that known successful wind development areas receive high suitability scores, using publicly available operational and existing wind farm data.
4. **Extend if time allows.** Portfolio optimisation, solar, seasonal matching, scenario comparison and indicative cost - in that order of defensibility.
5. **Gather industry feedback** through events such as All Energy Australia and Australian Energy Week, and use it to decide what justifies investment toward a commercial product.

A complete wind system is worth more than an incomplete wind-and-solar system.
