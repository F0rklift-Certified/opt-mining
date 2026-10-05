# S3-10 frozen baseline and snapshot review

The initial preflight repaired stale scoring/explanation artefacts following
the full-NSW geographic refresh at `1b499c2`. The full demo then exposed a
separate problem: eligibility still used New England wind/urban coverage
while integration consumed full-NSW features. Updating two test pins alone
could not resolve that source disagreement.

XINHAO WANG explicitly approved coverage repair, missing-demand exclusion and
a separate NSW centroid boundary rule on 5 October 2026.
`scripts/repair_nsw_baseline.py` compares against immutable pre-repair commit
`a2ad4a7a5f9be683b70f4d6aeef6468ba29d61d5`. The source hash, reason counts
and full audit are in `docs/release/baseline-change.json`.

| Observation | Before | After |
| --- | ---: | ---: |
| Grid rows/identity/order | 47,311 | Same 47,311 |
| Eligible cells | 1,233 | 23,266 |
| Excluded cells | 46,078 | 24,045 |
| Originally ranked cells with changed rank | — | 1,231 of 1,233 |
| Newly eligible / previously eligible now excluded | — | 22,033 / 0 |
| Eligible centroids outside repaired ABS NSW geometry | Not enforced | 0 |

The six-code vocabulary and boundary convention are recorded in the frozen
specification §6.5. Four original rules and thresholds, scoring formula and
default/scenario weights remain unchanged. Full-NSW slope/wind/demand statistics
use exact `cell_id` joins. Normalisation bounds change with eligibility, so
scores and ranks legitimately change.

Fixed S2-09 assertions were reviewed and updated together: counts, default
top-five scores, scenario change count and structured explanation digest.
They remain literal expectations, not copied from the tested input at runtime.
Arithmetic fixtures, exclusion guards and scenario invariants remain enforced.

- Frozen input SHA-256: `499403e0310dc8b7983b9a57156ce4204a1ea8e7b6d6fa18fa43e1b6e33bbe77`.
- Canonical structured explanation digest:
  `9bf40f6cc6f15d8ebbee6978d498beb9a5c62183e3deb64c12c8c431390b6cb8`.
- Wind-led / Grid-led changed ranks: 23,259 of 23,266.

Default rank 1 is `S32.436_E149.086` (0.926467805184629), followed by
`S31.186_E151.686` (0.9260980791263298), `S30.186_E151.636`
(0.9233381909167288), `S32.436_E149.036` (0.9230446420485923) and
`S32.486_E149.086` (0.92257338481588). These are baseline-weight results,
not the Wind-led preset. Scenario explanations are generated per run.

This is an authorised candidate-baseline change, not maintainer review,
client acceptance or ground-truth validation of each cell.
