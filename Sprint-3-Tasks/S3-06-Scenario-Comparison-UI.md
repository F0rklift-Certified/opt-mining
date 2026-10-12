# S3-06: Scenario-Comparison UI

**Type:** Story
**Priority:** High
**Story Points:** 3
**Labels:** web-app, scenarios, frontend
**Blocked by:** S3-02, S2-07
**Blocks:** S3-07

---

## Objective

Let the user compare at least two weighting configurations and observe how the ranking changes between them.

---

## Context

Guidance Step 7 and §5 (Scenario comparison — Must). The comparison logic lives in the S2-07 engine; this ticket renders it. The guidance warns not to present these as probabilistic uncertainty scenarios.

---

## Deliverables

1. A scenario selector for at least two configurations/presets.
2. A side-by-side or delta comparison of rankings.
3. Clear labelling of scenarios as preference-based.

---

## Acceptance Criteria

- [x] The user can select/compare at least **two** weighting scenarios (satisfies **AC9**)
- [x] The comparison shows how the ranking differs between scenarios (e.g. side-by-side ranks or rank delta)
- [x] Changing weights or picking a preset, rerunning, and observing ranking changes is demonstrable
- [x] Comparison uses S2-07 engine output — no UI-side re-ranking
- [x] Scenarios are labelled as **weighting/preference** scenarios, not probabilistic uncertainty scenarios
- [x] At least two useful presets are available (e.g. wind-led vs grid-led)

---

## Technical Notes

- Calls `compare_scenarios` on the S2-08 service; reuses the S2-07 preset config surfaced in S3-02.
- Cross-cutting impact: this is the visible proof of AC9 for the final demo (Step 7 of the demo script).

---

## Status: Done

Delivered on branch `s3-06-scenario-comparison-ui`. All six acceptance criteria
met, additively on the approved S3-04 shell: a new `ScenarioComparison` panel is
wired into `AppShell` as a fifth labelled region, and all comparison math stays
server-side in the S2-07 engine (via the S2-08 `compare_scenarios` operation).
The `compareScenarios` client method and OpenAPI schema were already current, so
no schema regeneration was needed — the UI only renders engine output.

### Completion Notes

**Two-scenario selector reusing S3-02 presets (AC1 / AC6).** The panel offers
two radio groups (Scenario A / Scenario B) populated from the existing
`WEIGHTING_OPTIONS` in `AnalysisControls.tsx`, filtered to the named S2-07
presets (`editable === false`): Wind-led and Grid-led. The presets are NOT a new
hard-coded list — they come from the single S3-02 source of truth. Radio groups
(not a `<select>`) keep the shell's R1.2 "no combobox/listbox" guard intact,
matching the AnalysisControls convention.

**Side-by-side ranks + rank delta from the engine (AC2 / AC4).** On "Compare
scenarios", `AppShell` calls `service.compareScenarios({ scenario_a, scenario_b })`
through the one shared client and passes the result to the panel, which renders a
per-cell table of `rank_a`, `rank_b` and `rank_delta` exactly as served. Rows are
shown in the engine's order (ascending rank under scenario A), top slice only —
a display selection, never a re-sort or recomputation. There is no scoring,
ranking or delta arithmetic in the UI; the `rank_delta` is read verbatim. The
scope-guard test (bans `fetch`/`.sort`/`.reduce`/decision-math in shell source)
still passes.

**Rerun observes ranking changes (AC3).** Changing either radio group and
clicking Compare again re-issues the request with the new scenario keys (guarded
by an independent staleness ref) and re-renders the returned ranks/deltas,
demonstrating how the ranking shifts between preference sets. Loading and error
states mirror the other shell components (a `role="alert"` failure message that
does not hide the rest of the shell).

**Preference-not-probability framing (AC5).** The panel leads with an explicit
note that these are weighting/preference scenarios — different judgements about
what matters — and are **not** probabilistic or uncertainty scenarios: no
scenario is more or less likely and the comparison carries no probabilities. The
delta caption spells out that a negative delta means a cell ranks better under
scenario A and a positive delta better under scenario B.

### Verification

From `app/web`: `npm run typecheck` clean; `npm test -- --runInBand` green
(9 suites, 120 tests, incl. the new `ScenarioComparison` component tests, the
extended `AppShell.integration` scenario-comparison tests, and the `scope-guard`
guard); `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run build` succeeds.
Live end-to-end rendering against the running decision service is a manual check
(the unit tests mock the client's `compareScenarios`); the request wiring, the
engine-order rendering, the no-recomputation guard, and the preference-framing
copy are all covered by tests. See `app/web/.agents/tasks/s3-06-verification.md`.

### Commits

- _(committed by the release step)_ — S3-06 scenario-comparison UI.

### Update: editable custom scenario weights (AC3 extended)

The comparison now lets the user EDIT a scenario's weighting parameters, not
only pick a fixed preset. The two named presets (Wind-led / Grid-led) are kept
exactly as before; each scenario side (A and B) can instead be set to **Custom
weights**, which reveals an editable table over the SIX frozen criteria. The
criteria set and their directions stay fixed — only the weights change — so both
sides remain comparable. The Custom editor mirrors the S3-02 AnalysisControls
pattern exactly (same `FEATURE_LABELS`, the same `type="number"` controls, the
same `.om-weights` table, the shared `validateWeights` guard) and edits only the
touched criterion, carrying the other five through unchanged. It seeds from a
preset so it opens on sensible values.

Still engine-only, no UI re-ranking. On Compare, each side is sent as EITHER a
scenario key OR an explicit `weights` configuration through the single
`compareScenarios` client; the engine does all scoring/normalisation/ranking and
returns `rank_a` / `rank_b` / `rank_delta`, which the UI renders verbatim.
Changing a Custom weight and re-running re-issues the request and re-renders. The
scope-guard (bans `fetch`/`.sort`/`.reduce`/decision-math in shell source) still
passes.

Backend contract extended + schema regenerated. `ScenarioComparisonRequest`
(both `app/api/models.py` and `pipeline/service/app.py`) gained optional
per-side `weights_a` / `weights_b` fields alongside the now-optional
`scenario_a` / `scenario_b`; the named-key-only form stays valid.
`compare_scenarios` resolves each side through `run_analysis(weights=...)` or
`run_analysis(scenario=...)` — reusing `resolve_weights` / the engine parser as
the single validator (no new validator; invalid weights raise
`ScoringConfigError` → 422). The frontend OpenAPI schema + `generated.ts` were
regenerated from the updated backend models (`npm run generate:api-client`).

Verification (custom-weights extension): backend `pytest tests/service/test_scenarios.py`
14 passed (incl. new custom-weights, invalid-weights-422, both-sides-custom, and
preset-unchanged cases) and the backend contract/passthrough/snapshot suites
pass; frontend `npm run typecheck` clean, `npm test` 126 passed (9 suites),
`npm run build` succeeds. Evidence:
`app/web/.agents/tasks/s3-06-custom-weights-verification.md`.
