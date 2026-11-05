#!/usr/bin/env python3
"""One-shot Nominatim (OSM place-geocoding) acquisition for the GA+Overpass-unmatched NSW substations.

This is the THIRD, lower-confidence coordinate tier behind the GA-primary +
OSM-Overpass-second zone-substation geocoder (``pipeline.demand.geocode_load``).
It geocodes ONLY the names the first two tiers missed (read from
``DATA/electricity-demand/load/unmatched_substations.csv``, ~87 names), one name
at a time, and writes a frozen snapshot
``DATA/infrastructure/substations/nominatim_substations_nsw.geojson`` (EPSG:4326)
plus a ``download_manifest`` entry. The pipeline then reads the frozen snapshot;
the public endpoint is NEVER hit at pipeline run time.

CRITICAL DIFFERENCE from the Overpass tier: Nominatim is a PLACE geocoder, so
``"<name> NSW"`` returns the SUBURB / LOCALITY CENTROID, not the substation
itself. That is acceptable ONLY because ``load_weighted`` uses a 15 km
distance-decay / 40 km search radius, so a centroid a few km off still lands in
the right neighbourhood. Every Nominatim match is therefore flagged as a
separately-tiered LOWER-confidence coordinate downstream
(``coord_source='nominatim'``, ``nominatim_low_confidence=True``) and is never
mixed with GA/Overpass precision. See
``.agents/tasks/nominatim-geocode-fallback/findings.md`` §3-§6 for the design.

NOMINATIM USAGE POLICY — READ BEFORE RUNNING
--------------------------------------------
This script uses the public Nominatim endpoint, which is governed by the
**Nominatim Usage Policy**: https://operations.osmfoundation.org/policies/nominatim/

The policy has an explicit clause for LLM/AI-generated code: such code MUST
adhere to the policy and MUST prominently point the user to it. Accordingly:

  * Absolute maximum 1 request/second (this script sleeps 1.1 s between calls,
    single-threaded, on one machine).
  * A descriptive User-Agent identifying this application is REQUIRED; stock
    HTTP-library User-Agents are rejected.
  * Results MUST be cached on our side — this is exactly why the snapshot is
    frozen and committed, and the pipeline never re-queries at run time.
  * Attribution: data is © OpenStreetMap contributors under ODbL 1.0.
  * A one-off geocode of ~87 names is a permissible "smaller one-time bulk
    task"; bulk/repeated/pipeline-time use is NOT acceptable. For scale, use a
    self-hosted Nominatim instance or a commercial geocoder.

Temporary helper — not part of the pipeline stages. Run once from the repo root::

    python scripts/_acquire_nominatim_substations_nsw.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import time
from pathlib import Path

import requests

from pipeline.demand import config as demand_config
from pipeline.common.geo import atomic_write_json, atomic_write_text, utc_now

# --- Nominatim usage policy (cited prominently per the LLM/vibe-coding clause) ---
NOMINATIM_USAGE_POLICY_URL = "https://operations.osmfoundation.org/policies/nominatim/"

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"

# Fixed query parameters applied to every request (findings §3/§4 safeguards).
# format=json, limit=1 (so no multi-result tie-break is normally needed),
# countrycodes=au keeps results in Australia.
QUERY_PARAMS = {"format": "json", "limit": "1", "countrycodes": "au"}

# Descriptive User-Agent in the project's style (the Overpass tier uses the same
# style). Stock library UAs are rejected by the Nominatim policy.
USER_AGENT = (
    "opt-mining-nsw/1.0 (NSW zone-substation place-geocoding; one-shot Nominatim "
    "acquisition; +https://www.openstreetmap.org/copyright)"
)

LICENCE = "ODbL 1.0 - (c) OpenStreetMap contributors"

# Polite spacing: strictly <= 1 request/second (policy maximum).
_REQUEST_INTERVAL_S = 1.1

# Transient-failure retries (shared, rate-limited service). Never fabricate.
_MAX_ATTEMPTS = 4
_RETRY_DELAY_S = 5

# Hard NSW bounding box (same extent as scripts/_acquire_ucl_nsw.NSW_BBOX):
# lat -37.51..-28.16, lon 141.0..153.7. Any result outside -> bbox_pass=false,
# not written as a usable coordinate.
NSW_LAT_MIN, NSW_LAT_MAX = -37.51125, -28.16125
NSW_LON_MIN, NSW_LON_MAX = 141.01125, 153.66125

# Class allow-list for auto-accept (clean suburb/locality centroids).
ACCEPT_CLASSES = frozenset({"boundary", "place"})
# Classes that are the street/POI failure mode -> reject.
REJECT_CLASSES = frozenset({"highway", "waterway", "railway", "tourism", "amenity"})

# Importance floor. The probe (findings §2-§3) separated good admin hits
# (importance >= 0.16) from street/POI junk (<= 0.053-0.107). 0.15 cleanly
# splits them; results at/below the floor are rejected, and results just above
# it are flagged needs_review. Recorded in the manifest.
IMPORTANCE_FLOOR = 0.15
# A result whose importance is within this margin above the floor is flagged
# needs_review (near-floor admin hit an analyst should audit).
IMPORTANCE_REVIEW_MARGIN = 0.05

# Trailing directional qualifiers / descriptors stripped for the ONE base-name
# fallback retry (findings §3). e.g. "Cessnock South" -> "Cessnock",
# "Finley Town" -> "Finley", "Lismore Uni" -> "Lismore".
_FALLBACK_TRAILING = re.compile(
    r"\s+(north|south|east|west|central|town|uni|hospital)\s*$", re.IGNORECASE
)

OUT_PATH = (
    demand_config.PROJECT_ROOT
    / "DATA"
    / "infrastructure"
    / "substations"
    / "nominatim_substations_nsw.geojson"
)
MANIFEST_PATH = (
    demand_config.PROJECT_ROOT
    / "DATA"
    / "infrastructure"
    / "metadata"
    / "download_manifest.json"
)
UNMATCHED_CSV = (
    demand_config.PROJECT_ROOT
    / "DATA"
    / "electricity-demand"
    / "load"
    / "unmatched_substations.csv"
)


def read_unmatched_names(path: Path) -> list[str]:
    """Return the GA+Overpass-unmatched ``substation_name`` values (~87).

    Reads the geocoder's unmatched list, NOT all 543 rows. Deterministic order
    (sorted, de-duplicated) so re-runs geocode the same names in the same order.
    """
    names: list[str] = []
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        if "substation_name" not in (reader.fieldnames or []):
            raise SystemExit(
                f"{path} has no 'substation_name' column; got {reader.fieldnames}"
            )
        for row in reader:
            name = (row.get("substation_name") or "").strip()
            if name:
                names.append(name)
    return sorted(dict.fromkeys(names))


def base_name_fallback(name: str) -> str | None:
    """Strip ONE trailing directional qualifier/descriptor for the fallback retry.

    Returns the stripped base name, or ``None`` if nothing was stripped (so the
    caller knows there is no distinct retry to attempt).

    >>> base_name_fallback("Cessnock South")
    'Cessnock'
    >>> base_name_fallback("Finley Town")
    'Finley'
    >>> base_name_fallback("Metford") is None
    True
    """
    stripped = _FALLBACK_TRAILING.sub("", name).strip()
    if stripped and stripped.casefold() != name.strip().casefold():
        return stripped
    return None


def classify_result(result: dict | None) -> dict:
    """Pure safeguard/parse helper (findings §3) — NO network.

    Takes a single Nominatim result dict (or ``None`` for a NONE response) and
    decides whether it is a usable NSW place centroid. Returns a dict:

      * ``accepted``     — bool, True iff it passes bbox AND class AND importance
      * ``bbox_pass``    — bool, inside the hard NSW bbox
      * ``needs_review`` — bool, flagged for human audit (near-floor importance,
                           border/ACT-enclave latitude, etc.)
      * ``reason``       — short string describing the verdict
      * ``latitude`` / ``longitude`` / ``osm_class`` / ``osm_type`` /
        ``importance`` / ``display_name`` — parsed fields (``None`` if absent)

    Kept pure so it can be unit-tested directly without hitting the API.
    """
    if not result:
        return {
            "accepted": False,
            "bbox_pass": False,
            "needs_review": False,
            "reason": "no result",
            "latitude": None,
            "longitude": None,
            "osm_class": None,
            "osm_type": None,
            "importance": None,
            "display_name": None,
        }

    try:
        lat = float(result.get("lat"))
        lon = float(result.get("lon"))
    except (TypeError, ValueError):
        return {
            "accepted": False,
            "bbox_pass": False,
            "needs_review": False,
            "reason": "unparseable coordinates",
            "latitude": None,
            "longitude": None,
            "osm_class": result.get("class"),
            "osm_type": result.get("type"),
            "importance": result.get("importance"),
            "display_name": result.get("display_name"),
        }

    osm_class = result.get("class")
    osm_type = result.get("type")
    display_name = result.get("display_name")
    try:
        importance = float(result.get("importance")) if result.get("importance") is not None else None
    except (TypeError, ValueError):
        importance = None

    bbox_pass = (NSW_LAT_MIN <= lat <= NSW_LAT_MAX) and (NSW_LON_MIN <= lon <= NSW_LON_MAX)

    parsed = {
        "latitude": lat,
        "longitude": lon,
        "osm_class": osm_class,
        "osm_type": osm_type,
        "importance": importance,
        "display_name": display_name,
    }

    if not bbox_pass:
        return {**parsed, "accepted": False, "bbox_pass": False, "needs_review": False, "reason": "outside NSW bbox"}

    if osm_class in REJECT_CLASSES:
        return {**parsed, "accepted": False, "bbox_pass": True, "needs_review": False, "reason": f"rejected class {osm_class}"}

    if osm_class not in ACCEPT_CLASSES:
        return {**parsed, "accepted": False, "bbox_pass": True, "needs_review": False, "reason": f"class {osm_class} not in allow-list"}

    if importance is None or importance <= IMPORTANCE_FLOOR:
        return {**parsed, "accepted": False, "bbox_pass": True, "needs_review": False, "reason": f"importance {importance} <= floor {IMPORTANCE_FLOOR}"}

    # Accepted. Flag near-floor importance for review.
    needs_review = importance < (IMPORTANCE_FLOOR + IMPORTANCE_REVIEW_MARGIN)
    reason = "accepted (near-floor importance, review)" if needs_review else "accepted"
    return {**parsed, "accepted": True, "bbox_pass": True, "needs_review": needs_review, "reason": reason}


def _query_once(query_string: str) -> dict | None:
    """One GET to Nominatim for ``query_string``; return the top result or None.

    Retries a few times on transient failure (never fabricates). Raises
    ``RuntimeError`` if the endpoint stays unavailable.
    """
    params = dict(QUERY_PARAMS)
    params["q"] = query_string
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resp = requests.get(
                NOMINATIM_SEARCH_URL,
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=30,
            )
            if resp.status_code == 429:
                raise RuntimeError("rate-limited (HTTP 429)")
            resp.raise_for_status()
            body = resp.json()
            return body[0] if body else None
        except Exception as exc:  # network / 429 / 5xx / malformed JSON
            last_exc = exc
            print(f"    attempt {attempt}/{_MAX_ATTEMPTS} failed: {exc}")
            if attempt < _MAX_ATTEMPTS:
                time.sleep(_RETRY_DELAY_S)
    raise RuntimeError(
        f"Nominatim unavailable after {_MAX_ATTEMPTS} attempts: {last_exc}"
    )


def geocode_name(name: str) -> dict | None:
    """Geocode ONE substation name with the deterministic base-name fallback.

    Tries ``"<name> NSW"`` first; if that yields NONE or a non-accepted result,
    strips a trailing directional/descriptor qualifier and retries ONCE
    (``"<base> NSW"``). Returns a resolved-feature dict (with the query string
    used and the classification) when accepted, else ``None``.

    Sleeps _REQUEST_INTERVAL_S before every network call so the whole run stays
    <= 1 req/sec.
    """
    attempts: list[tuple[str, str]] = [(name, f"{name} NSW")]
    base = base_name_fallback(name)
    if base is not None:
        attempts.append((base, f"{base} NSW"))

    first_classified: dict | None = None
    first_query: str | None = None
    used_fallback = False
    for idx, (queried, query_string) in enumerate(attempts):
        time.sleep(_REQUEST_INTERVAL_S)
        print(f"  querying: {query_string!r}")
        result = _query_once(query_string)
        classified = classify_result(result)
        if first_classified is None:
            first_classified = classified
            first_query = query_string
        if classified["accepted"]:
            if idx > 0:
                used_fallback = True
            return {
                "queried_name": name,
                "query_string_used": query_string,
                "used_fallback": used_fallback,
                **classified,
            }

    # Nothing accepted. Report the first verdict for the log.
    print(f"    -> not resolved ({first_classified['reason'] if first_classified else 'no result'})")
    return None


def build_feature(resolved: dict) -> dict:
    """Build one GeoJSON Point feature for a resolved name (EPSG:4326)."""
    # A fallback-resolved or near-floor hit is flagged needs_review so an analyst
    # can audit it; the classifier already sets needs_review for near-floor.
    needs_review = bool(resolved["needs_review"] or resolved["used_fallback"])
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [resolved["longitude"], resolved["latitude"]],
        },
        "properties": {
            "queried_name": resolved["queried_name"],
            "query_string_used": resolved["query_string_used"],
            "display_name": resolved["display_name"],
            "latitude": resolved["latitude"],
            "longitude": resolved["longitude"],
            "osm_class": resolved["osm_class"],
            "osm_type": resolved["osm_type"],
            "importance": resolved["importance"],
            "bbox_pass": resolved["bbox_pass"],
            "needs_review": needs_review,
        },
    }


def main() -> int:
    print("=" * 78)
    print("Nominatim one-shot acquisition (THIRD, lower-confidence PLACE-centroid tier)")
    print(f"USAGE POLICY (please read): {NOMINATIM_USAGE_POLICY_URL}")
    print("  <= 1 request/second, single-threaded, descriptive User-Agent,")
    print("  results cached as a frozen committed snapshot (never re-queried at run time).")
    print(f"Coordinates: {LICENCE}")
    print("=" * 78)

    names = read_unmatched_names(UNMATCHED_CSV)
    print(f"Read {len(names)} GA+Overpass-unmatched names from {UNMATCHED_CSV.name}")

    resolved: list[dict] = []
    for name in names:
        hit = geocode_name(name)
        if hit is not None:
            resolved.append(hit)
            flag = " [needs_review]" if (hit["needs_review"] or hit["used_fallback"]) else ""
            print(
                f"    OK {name!r} -> ({hit['latitude']:.5f}, {hit['longitude']:.5f}) "
                f"class={hit['osm_class']} importance={hit['importance']}{flag}"
            )

    if not resolved:
        raise SystemExit(
            "Nominatim resolved zero names; aborting (not fabricating a file)."
        )

    # Deterministic feature sort by queried_name so the snapshot bytes are stable.
    features = [build_feature(r) for r in resolved]
    features.sort(key=lambda f: f["properties"]["queried_name"])

    collection = {"type": "FeatureCollection", "features": features}
    text = json.dumps(collection, separators=(",", ":")) + "\n"
    atomic_write_text(OUT_PATH, text)
    nbytes = len(text.encode())
    sha = hashlib.sha256(OUT_PATH.read_bytes()).hexdigest()
    n_review = sum(1 for f in features if f["properties"]["needs_review"])
    print(f"  wrote {OUT_PATH} ({nbytes} bytes, {len(features)} features, {n_review} needs_review)")
    print(f"  sha256={sha}")

    manifest = json.loads(MANIFEST_PATH.read_text()) if MANIFEST_PATH.exists() else {}
    manifest["nominatim_substations_nsw.geojson"] = {
        "dataset": "Nominatim (OSM place-geocoding) centroids for GA+Overpass-unmatched NSW substations",
        "source": NOMINATIM_SEARCH_URL,
        "query_params": {**QUERY_PARAMS, "q": "<substation_name> NSW (one name at a time; base-name fallback retry)"},
        "usage_policy": NOMINATIM_USAGE_POLICY_URL,
        "usage_policy_note": (
            "Public Nominatim endpoint: <= 1 request/second, descriptive User-Agent "
            "required, results cached as this frozen snapshot (never re-queried at run "
            "time). One-off smaller bulk task per the policy."
        ),
        "retrieved_utc": utc_now(),
        "features": int(len(features)),
        "names_queried": int(len(names)),
        "needs_review": int(n_review),
        "local_bytes": int(nbytes),
        "sha256": sha,
        "crs": "EPSG:4326",
        "safeguards": {
            "nsw_bbox_epsg4326": [NSW_LON_MIN, NSW_LAT_MIN, NSW_LON_MAX, NSW_LAT_MAX],
            "accept_classes": sorted(ACCEPT_CLASSES),
            "reject_classes": sorted(REJECT_CLASSES),
            "importance_floor": IMPORTANCE_FLOOR,
            "importance_review_margin": IMPORTANCE_REVIEW_MARGIN,
        },
        "licence": LICENCE,
        "tier": "third (lower-confidence PLACE centroid; nominatim_low_confidence=True)",
        "generated_by": "scripts/_acquire_nominatim_substations_nsw.py",
    }
    atomic_write_json(MANIFEST_PATH, manifest)
    print(f"  manifest updated: {MANIFEST_PATH}")

    print(
        f"\nSummary: resolved {len(features)}/{len(names)} names "
        f"({n_review} flagged needs_review). Importance floor = {IMPORTANCE_FLOOR}."
    )
    print(f"Remember: coordinates are {LICENCE}; attribution required wherever surfaced.")
    print(f"Usage policy: {NOMINATIM_USAGE_POLICY_URL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
