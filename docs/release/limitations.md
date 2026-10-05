# Limitations and assumptions for the final review

This MVP screens NSW wind-energy candidate cells under stated data and
preferences. A high rank is a reason to investigate an area, not a construction
recommendation, connection offer or planning approval.

- **Cell and boundary scale:** all 47,311 rectangular grid cells are retained.
  Cells are approximately 5 km, not surveyed parcels. Eligibility requires the
  stored centroid to be covered by the committed ABS NSW boundary, including
  its edge, in EPSG:3577. Invalid source geometries use buffer(0) repair before
  projection. A coastal/border cell can still straddle NSW; centroid membership
  does not establish usable land over its whole area.
- **Preferences and population:** six criteria represent the broad themes.
  Wind-led and Grid-led are preferences, not uncertainty probabilities.
  Min-max bounds use eligible cells. The coverage/boundary repair changes
  bounds, scores and ranks despite unchanged formulas and weights. The
  approved before/after audit records this.
- **Demand:** the regional allocation is a spatial proxy, not measured local
  demand or a local load forecast. It is constant across this eligible NSW
  population, so it adds no discrimination between these cells. Cells without
  a scored demand proxy are excluded, not imputed.
- **Infrastructure:** centroid distances to transmission/substations and REZ
  membership describe proximity and policy context. They do not establish
  spare capacity, an approved connection or an available route. Connection-
  point distance remains missing and is not a scored criterion.
- **Data quality:** canonical full-NSW wind/slope and statewide UCL replace the
  legacy New England exclusion inputs. CAPAD any-intersection and UCL overlap
  remain screening conventions. Missing context-only values stay null and
  flagged. Passing the 28 input checks is structural evidence, not parcel-level
  ground truth or engineering feasibility.
- **Explanations:** each service run now materialises actual S2-06 explanations
  using its resolved weights and input hash. These explain the model's output,
  not independent causal evidence.
- **Reference validation:** the operational GA wind-farm comparison is a
  plausibility check, not an accuracy estimate. Taralga and Rye Park remain
  excluded reference anomalies. Inspect their overlap/slope assumptions and
  coarse grid placement rather than fitting weights to existing farms.
  Full outcomes remain in `rehearsal.json`.
  Actual cell reasons are `protected_area: Tarlo River` for Taralga and
  `protected_area: Bango` for Rye Park. The frozen any-cell-intersection rule
  is stricter than checking the generator point, so inspect parcel geometry
  before proposing a change; do not override an exclusion because a farm exists.
  Counts are GA records, not unique farms: Gullen Range appears twice, and
  the source labels White Rock Solar Farm as wind/turbine technology. This
  classification ambiguity is retained for review, not silently filtered out.
- **Web/deployment scope:** map, exclusions, features, explanation and comparison
  are implemented. Browser CSV export and a dedicated sanity view remain Should
  items. First-run locking is process-local; the documented API is single-
  process. Multi-worker/host deployment needs additional coordination.
- **Release acceptance:** local tests do not imply GitHub CI success, merged
  prerequisites or client approval. Upstream review and Checkpoint D remain
  separate gates. The pre-review candidate is not an accepted release.
