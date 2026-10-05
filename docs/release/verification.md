# S3-10 verification — 5 October 2026

The full technical demonstration passes on the repaired candidate baseline.
Merge review and client Checkpoint D are separate, still-open gates.

| Local gate | Actual result |
| --- | --- |
| Backend/service/exclusion non-Docker suite | 209 passed; 1 Docker-marked test deselected; 64 warnings |
| Remaining non-Docker suite | 978 passed; 5 skipped; 118,451 warnings |
| Combined non-overlapping Python result | **1,187 passed, 5 skipped, 1 deselected** |
| Focused final baseline/service/rehearsal rerun | 23 passed |
| Frontend | 75 passed in 7 suites |
| TypeScript check / production Next.js build | Both passed |
| Official npm advisory audit, production + development | 0 known vulnerabilities |
| Locked local and Linux Docker npm installation | Passed |
| Compose production build / startup | Both API and web passed on ports 18010/13010 |
| Real HTTP smoke | Web, CORS and all six service operations passed |
| Real full browser E2E | 1 passed in 20.0s; no HTTP mocks; no page errors |
| Live two-scenario/reference rehearsal | Technical PASS; final BLOCKED (exit 2), solely for merge order and client sign-off |

The suite warnings are retained, not counted as successes. Five existing
optional tests were skipped. The separate Docker pytest test was not called a
pass; independent production Compose build/start, HTTP smoke and real browser
E2E supplied runtime evidence.

Python was 3.13.5 with pytest 8.3.4 locally. CI installs pytest 9.1.1 on Python
3.13. Local Node is 24.13.0; Docker uses Node 24. GitHub Actions results must be
checked separately after upload; local success alone is not a remote CI claim.

## Frozen input and runtime

Input SHA-256:
`499403e0310dc8b7983b9a57156ce4204a1ea8e7b6d6fa18fa43e1b6e33bbe77`.

47,311 retained rows; 23,266 eligible; 24,045 excluded. Integration 44/44,
exclusions 6/6, input 28/28, scoring 9/9 and explanation 10/10 checks passed.
All eligible centroids pass the repaired ABS NSW boundary test.

Local image IDs (not published registry artefacts):

- API: `sha256:74938bb4e019091f1d14954f75179bd3d90c05e86b6f97c8db92c83d18a582ad`.
- Web: `sha256:a4b8c3cd54905dd82826f55ec20dbe4c22ef5dc692bc59a03ca0d79939d45de4`.

## Browser and reference observations

The real E2E covers the frozen input → engine → API → browser path, actual
canvas drawing, numeric weights, explanation phrases, filter invariance,
map/table selection, excluded null score/rank, comparison, both presets and
top_n=0 returning 422. Chrome independently displayed matching Grid-led run
`e43fd84cddd53cb5`, rank 1 `S32.436_E149.086`, and comparison 5→1 (+4).

[Browser JSON](browser-e2e.json), [E2E image](final-demo.png),
[Chrome image](chrome-final-demo.png) and [HTTP/reference report](rehearsal.json)
retain evidence. The report records its source commit and working-tree state
so an uncommitted rehearsal is not presented as a clean-commit verification.

13/16 GA operational wind-classified records fall in the upper quartile.
The reused majority expectation passes. Boco Rock remains below quartile,
Taralga/Rye Park remain excluded, and source duplication/classification caveats
are disclosed. This is plausibility evidence, not accuracy or site approval.
No weight tuning, fabricated human feedback or client sign-off is claimed.
