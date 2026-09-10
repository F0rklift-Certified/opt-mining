# S3-09: Docs, Reproducible Run Path & End-to-End Tests

**Type:** Story
**Priority:** High
**Story Points:** 3
**Labels:** documentation, testing, reproducibility
**Blocked by:** S3-05, S3-06
**Blocks:** S3-10

---

## Objective

Provide integration tests for the end-to-end flow, a clean install/run path, and documentation covering provenance, assumptions, limitations, scoring equations, exclusions, default weights and application architecture — using screening-level language throughout.

---

## Context

Guidance Step 12 and §7 (AC11, AC12). This ticket makes the MVP reproducible and defensible. It builds on the Sprint 1 documentation set (`pipeline/README.md`, the data specification) and the Sprint 2 decision-engine spec.

---

## Deliverables

1. Integration test(s) covering data → engine → app end-to-end.
2. A clean-environment install/run guide.
3. Consolidated documentation of architecture, equations, exclusions, weights, assumptions and limitations.

---

## Acceptance Criteria

- [ ] A clean install/run path and technical documentation are provided (satisfies **AC11**)
- [ ] Documentation records: data provenance, assumptions, limitations, scoring equations, exclusions, default weights and application architecture
- [ ] Integration tests cover the end-to-end flow (frozen dataset → engine → app output)
- [ ] The app can be installed and run from a clean environment following only the documented steps
- [ ] Documentation uses **screening-level** language and clearly documents important limitations; no "best site to build a wind farm" claims (satisfies **AC12**)
- [ ] The demand proxy is correctly described as a proxy everywhere it appears in docs
- [ ] Tests run in CI (`.github/workflows/ci.yml`)

---

## Technical Notes

- Extend the existing `pipeline/README.md` and data specification rather than starting parallel docs; link the S2-01 decision-engine spec.
- Keep the run path a single documented command where possible, consistent with the Sprint 1 "single command runs the pipeline" pattern.
- Cross-cutting impact: this is the evidence base for Checkpoint D and the final demo (S3-10).
