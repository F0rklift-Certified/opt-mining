# Backend snapshot review for S3-10

The S3-10 preflight on 5 October 2026 found two stale S2-09 assertions on
integration commit `e6fa3bb`. Commit `1b499c2` had already replaced the integrated
GeoPackage and frozen manifest after expanding geographic coverage. The test
still pinned the preceding input and explanation digest.

## Input comparison

The preceding GeoPackage was read directly from `1b499c2^` and compared by
`cell_id` with the current file. Neither input was modified.

| Observation | Result |
| --- | --- |
| Rows and cell IDs | Same 47,311 cells |
| Eligibility and exclusion codes/text | Unchanged: 1,233 eligible, 46,078 excluded |
| Wind, demand, infrastructure, coordinates | Unchanged |
| Changed geographic fields across all cells | Elevation 39,223; slope 45,790; land use 38,685; geographic confidence 38,945 |
| Geographic differences among eligible cells | Elevation and slope each changed for 45 cells; the other features did not change |
| Baseline scores recomputed with the unchanged engine and weights | 45 changed; maximum absolute change 0.011649898676540288 |
| Baseline rank differences | 281 positions changed as those 45 scores moved |
| Baseline and scenario top-five snapshots | Existing assertions still pass; retained unchanged |

The confidence/context fields also changed where geographic data became
available. The explanation digest therefore changes, including explanations
for excluded cells. This is a source-data refresh, not a new scoring method.

## Updated pins

| Pin | Previous | Current |
| --- | --- | --- |
| Integrated input SHA-256 | `b7cd3d261abfdedd613301e0e2fdd07e3381178deb8ce8aff506a066117a1e61` | `8b300ca520ff42028fbb7b09024916580c105967c92fa8ade575c4e006c196fd` |
| Recomputed explanation SHA-256 | `36b82695ba4ec1c78e260399891d4050034d8077650cc5fe4de2d71152bdba4b` | `dabe4f4c74d927dbabc3ede1cd2a5b930c72fcf3a40322f962045228330a05a9` |

Only these two test pins were refreshed. Row counts, arithmetic fixtures, rank
ordering, exclusion assertions, top-five values and scenario-change assertions
remain enforced. In particular, the input hash is still a fixed literal and
is not copied dynamically from the file being tested.

The preflight also found two scored-artefact integration failures: confidence
did not match the current input, and the saved CSV differed from deterministic
regeneration. The existing scoring and explanation stages were therefore run
against the current frozen input. Their derived files, manifests, validation
reports and provenance were refreshed together; no weights, source inputs,
exclusion rules or eligibility values were changed.

This repair does not approve the input refresh on behalf of the client. The
final release still needs exclusion-source coverage reconciled with current
integrated features, scenario-appropriate explanations and the missing web
views. See the S3-10 release-preparation package when that stacked PR is added.
