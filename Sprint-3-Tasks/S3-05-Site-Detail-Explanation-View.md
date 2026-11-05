# S3-05: Site-Detail & Explanation View

**Type:** Story
**Priority:** High
**Story Points:** 5
**Labels:** web-app, explanation, site-detail, frontend
**Blocked by:** S3-03, S3-04
**Blocks:** S3-07
**Status:** ✅ Done

---

## Objective

When a user selects a site (from the map or the shortlist), show its raw/derived feature values, per-criterion component scores, total score, eligibility, and the deterministic explanation of its result.

---

## Context

Guidance Step 10 (site detail) and Step 6 (explanation), §5 (Site detail + Explanation — Must). This view renders the S2-06 explanation structure and the S2-05 component scores. It is where the app "explains why a site received its result" — a headline goal of the combined sprint.

---

## Deliverables

1. A site-detail panel bound to `get_site_detail`.
2. Rendering of component scores + total + eligibility.
3. Rendering of the deterministic explanation (positive factors, weaknesses, proxy caveats, data-quality notes).

---

## Acceptance Criteria

- [x] Selecting a site shows its raw/derived features, per-criterion component scores, total score and eligibility
- [x] The explanation identifies main positive factors and important weaknesses (satisfies **AC7**)
- [x] Proxy variables are labelled as proxies — the demand proxy is never presented as measured local demand (satisfies **AC7**)
- [x] Relevant data-quality/confidence caveats are shown
- [x] For an excluded site, the exclusion reason(s) are shown clearly
- [x] All content comes from the S2-06/S2-08 output — the UI does not generate its own explanation text
- [x] Screening-level language is used ("higher-ranked candidate under the selected assumptions"), never "best site"

---

## Technical Notes

- Renders the S2-06 explanation JSON structure verbatim into UI elements — no UI-side re-derivation of factors.
- Cross-cutting impact: consumes the S2-06 explanation contract and the S2-03 reason vocabulary; the selection trigger comes from S3-03/S3-04.

---

## Completion Record

**Completed:** 2026-10-12 — commit `eb8c536` ("feat: add S3-05 site-detail & explanation panel").

### What was built

- **`app/web/app/shell/SiteDetailPanel.tsx`** — a dedicated component (one-per-region pattern) that replaces the earlier five-fact stub in the site-detail region. It renders the `get_site_detail` payload for the selected site:
  - Header facts: site ID, rank, suitability (total score), eligibility.
  - Per-criterion **component scores** (`SiteDetail.contributions`) and **raw/derived features** (`SiteDetail.features`), both iterated in served order (no UI sorting).
  - The S2-06 **explanation** (`SiteDetail.explanation`) rendered verbatim, with optional-field guards and both-path isolation:
    - Eligible path: `headline`, `positive_factors`, `weaknesses`, `proxy_caveats`, `data_quality_notes`.
    - Excluded path: `exclusion_reasons` (`{code, text}`), `proxy_caveats`, `data_quality_notes`.
  - Null `suitability_score` / `rank` on excluded cells handled gracefully.
- **`app/web/app/shell/AppShell.tsx`** — the `region-site-detail` body now renders `SiteDetailPanel`, reusing the existing shared selection / loading / error wiring (map S3-03b and shortlist S3-04 both drive it). Not re-architected.
- **`app/web/app/globals.css`** — new `om-detail*` styles matching the existing `om-*` convention.
- **`app/web/app/shell/SiteDetailPanel.test.tsx`** — covers the eligible path, the excluded path, and the absent-optional-array case; asserts the proxy-caveat text renders and no "best site" copy appears.

### Verification

- Frontend suite green: `npm test -- --runInBand` (178 tests, incl. the `scope-guard` thin-client guards), `npm run typecheck`, `npm run build`.
- Decision-free: all explanation text comes from the served S2-06/S2-08 payload; the UI authors only static section headings. No scoring/ranking/normalisation math; all HTTP stays in `app/web/app/api/decision-service.ts`.
- Reviewed and APPROVED. Three non-blocking notes recorded: the run-level "excluded cells in run" count was intentionally dropped from this per-site region; the Features table reuses the criterion `COMPONENT_LABELS` map (unknown keys render as served); and the demand-as-proxy framing renders only when the server supplies `proxy_caveats` (per the verbatim rule).

### Related follow-up

A runtime HTTP 503 surfaced during manual testing of this view (an unreadable/corrupt materialised run wedging the Decision-Service read path). Root cause was unrelated to S3-05; it was fixed separately in commit `4d7d84f` — a writable `DATA/service` dev-override mount plus a self-heal readability guard in `pipeline/service/runs.py::materialise_run`. A production run-store durability note was captured for later deployment work.
