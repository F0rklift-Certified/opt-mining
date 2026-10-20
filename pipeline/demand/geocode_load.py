#!/usr/bin/env python3
"""Deterministic geocoding of NSW zone-substation max-demand rows.

The real NSW DNSP DAPR extract
(``DATA/electricity-demand/load/nsw_zone_substation_max_demand.csv``) lists 543
zone substations by name only — ``latitude``/``longitude``/``locality`` are
blank for every row (see that directory's ``SOURCES.md``). To use the data as a
spatial weight it must be given coordinates. This module does that by matching
each substation name against the Geoscience Australia substation point layer
(``DATA/infrastructure/substations/ga_substations_2026_nsw.geojson``), which
carries ``feature_name``, ``locality``, ``latitude`` and ``longitude`` for 586
NSW points.

Matching is **deterministic** and name-only (load rows have no locality):

1. Normalise both sides with :func:`normalise_substation_name` — lower-case,
   strip voltage suffixes like ``110/66kV`` / ``33/11kV`` / ``11kV`` / ``132kV``,
   drop punctuation, collapse whitespace.
2. Join on the normalised name. Where several GA points share one normalised
   name, pick one deterministically by sorting candidates on
   ``(locality, latitude, longitude)`` and taking the first.

The Geoscience Australia layer is transmission-weighted and genuinely lacks the
urban *distribution* zone substations the DNSP load rows carry (Campsie, City
South, Chatswood, Mascot, Manly, Miranda, Lidcombe, Darling Harbour, …). Those
sites are in OpenStreetMap, so OSM is wired in as a deterministic **second**
coordinate source (``DATA/infrastructure/substations/osm_substations_nsw.geojson``,
built by ``scripts/_acquire_osm_substations_nsw.py``). Precedence per load row:

1. Try the GA layer first (unchanged logic/order) -> ``coord_source="ga"``.
2. On a GA miss, try the OSM layer. OSM names its sites ``Campsie Zone
   Substation`` / ``Boronia Street ZS`` etc., so OSM matching additionally
   strips those site suffixes and applies a conservative street-abbreviation
   expansion (``normalise_substation_name(..., strip_site_suffix=True)``). An OSM
   hit emits ``coord_source="osm"`` after an **operator-agreement gate** (where
   the OSM element carries an ``operator`` it must match the row's DNSP). The
   match is flagged ``osm_low_confidence`` where the operator is absent or the
   match required abbreviation expansion.
3. Unmatched by **both** sources -> dropped (coordinates are never invented) and
   written to ``unmatched_substations.csv`` for review.

OSM coordinates are **(c) OpenStreetMap contributors, licensed ODbL 1.0**;
attribution is recorded in the snapshot manifest and this directory's
``README``/``SOURCES``. Demand magnitudes remain under the restricted DNSP DAPR
terms (see ``SOURCES.md``) — the two provenances have different reuse rights.

Matched substations become a clean load-point layer
``DATA/electricity-demand/load/nsw_zone_substation_load_points.gpkg`` (EPSG:4326
storage, carrying ``max_demand`` in MVA, ``dnsp``, ``data_year``, the matched
source feature name/locality/voltage, plus ``coord_source`` ("ga"/"osm") and the
boolean ``osm_low_confidence``). The match rate is reported.

Run from the repository root::

    python -m pipeline.demand.geocode_load

This is a one-shot acquisition/derivation helper (like
``scripts/_acquire_ucl_nsw.py``), not one of the pipeline stages.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd

from ..common.geo import atomic_write_json, atomic_write_text, utc_now
from . import config


# Voltage suffixes that distinguish network records but not the physical site,
# e.g. "Terranora 110/66kV", "Cudgen 11kV", "Lismore 132/66kV". Stripped before
# matching so a voltage-split row still lands on its GA point.
_VOLTAGE_SUFFIX = re.compile(r"\b\d{1,3}(?:/\d{1,3})?\s*kv\b", re.IGNORECASE)
_APOSTROPHE = re.compile(r"['\u2019]")
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_WHITESPACE = re.compile(r"\s+")

# OSM names zone substations with a site suffix the DNSP rows do not carry, e.g.
# "Campsie Zone Substation", "Boronia Street ZS", "Mascot Substation". Stripped
# (OSM side only, behind strip_site_suffix) before matching so they collapse
# onto the bare DNSP name ("campsie", "boronia street"). Applied to the
# lower-cased string before punctuation handling.
_OSM_SITE_SUFFIX = re.compile(
    r"\b(?:zone\s+substation|sub\s*station|substation|zss|zs)\b", re.IGNORECASE
)
# Conservative street-abbreviation expansion (findings §2 pass 2). Applied after
# punctuation/whitespace collapse (tokens are bare words by then) and only when
# strip_site_suffix is set, so GA-mode normalisation stays byte-identical. Order
# is fixed and each is whole-token so "street" is never re-expanded.
_ABBREV_EXPANSIONS = (
    ("st", "street"),
    ("dr", "drive"),
    ("cr", "crescent"),
    ("rd", "road"),
    ("mt", "mount"),
)


def normalise_substation_name(name: str | None, strip_site_suffix: bool = False) -> str:
    """Return a canonical form of a substation name for deterministic matching.

    Lower-cases, strips voltage suffixes (``110/66kV``, ``33/11kV``, ``11kV``,
    ``132kV`` …), removes punctuation, and collapses whitespace. A blank/None
    input returns the empty string (which never matches a real GA name).

    When ``strip_site_suffix`` is set (used for the OSM side only), the OSM site
    suffixes ``zone substation`` / ``substation`` / ``ZS`` / ``ZSS`` are stripped
    and a conservative street-abbreviation expansion (``St``→``Street``,
    ``Dr``→``Drive``, ``Cr``→``Crescent``, ``Rd``→``Road``, ``Mt``→``Mount``) is
    applied. It defaults off so GA-mode normalisation is **byte-identical** to
    before.

    >>> normalise_substation_name("Terranora 110/66kV")
    'terranora'
    >>> normalise_substation_name("Lismore 132/66kV")
    'lismore'
    >>> normalise_substation_name("St. Mary's")
    'st marys'
    >>> normalise_substation_name("Campsie Zone Substation", strip_site_suffix=True)
    'campsie'
    >>> normalise_substation_name("Boronia Street ZS", strip_site_suffix=True)
    'boronia street'
    """
    if name is None:
        return ""
    s = str(name).lower().strip()
    s = _VOLTAGE_SUFFIX.sub(" ", s)
    if strip_site_suffix:
        s = _OSM_SITE_SUFFIX.sub(" ", s)
    # Drop apostrophes without inserting a space so possessives collapse
    # ("St Mary's" -> "st marys"), then map remaining punctuation to spaces.
    s = _APOSTROPHE.sub("", s)
    s = _NON_ALNUM.sub(" ", s)
    s = _WHITESPACE.sub(" ", s).strip()
    if strip_site_suffix and s:
        tokens = s.split(" ")
        expand = dict(_ABBREV_EXPANSIONS)
        s = " ".join(expand.get(tok, tok) for tok in tokens)
    return s


def _build_ga_lookup(ga: gpd.GeoDataFrame) -> dict[str, dict]:
    """Map normalised GA name -> chosen point (deterministic on collisions)."""
    buckets: dict[str, list[dict]] = {}
    for _, row in ga.iterrows():
        norm = normalise_substation_name(row.get("feature_name"))
        if not norm:
            continue
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        buckets.setdefault(norm, []).append(
            {
                "feature_name": row.get("feature_name"),
                "locality": row.get("locality"),
                "voltage_kv": row.get("voltage_kv"),
                "latitude": float(geom.y),
                "longitude": float(geom.x),
            }
        )
    lookup: dict[str, dict] = {}
    for norm, candidates in buckets.items():
        # Deterministic tie-break: load rows carry no locality, so choose the
        # candidate with the lexicographically/numerically smallest
        # (locality, latitude, longitude). Documented, reproducible.
        candidates.sort(
            key=lambda c: (
                str(c["locality"]) if c["locality"] is not None else "",
                c["latitude"],
                c["longitude"],
            )
        )
        lookup[norm] = candidates[0]
    return lookup


def _build_osm_lookup(osm: gpd.GeoDataFrame) -> dict[str, dict]:
    """Map suffix-stripped normalised OSM name -> chosen point.

    Mirrors :func:`_build_ga_lookup` but keys on the suffix-stripped normalised
    name (``strip_site_suffix=True``) and carries ``name``, ``operator``,
    ``substation``, ``lat``, ``lon``. Load rows carry no operator, so duplicate
    OSM names are resolved by the documented deterministic tie-break
    ``(operator, latitude, longitude)`` (operator in place of GA's locality).
    """
    buckets: dict[str, list[dict]] = {}
    for _, row in osm.iterrows():
        norm = normalise_substation_name(row.get("name"), strip_site_suffix=True)
        if not norm:
            continue
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        buckets.setdefault(norm, []).append(
            {
                "name": row.get("name"),
                "operator": row.get("operator"),
                "substation": row.get("substation"),
                "latitude": float(geom.y),
                "longitude": float(geom.x),
            }
        )
    lookup: dict[str, dict] = {}
    for norm, candidates in buckets.items():
        candidates.sort(
            key=lambda c: (
                str(c["operator"]) if c["operator"] is not None else "",
                c["latitude"],
                c["longitude"],
            )
        )
        lookup[norm] = candidates[0]
    return lookup


# DNSP code (load-row ``dnsp``) -> the OSM ``operator`` string it must match
# where the OSM element carries an operator tag (findings §4 gate).
_DNSP_TO_OSM_OPERATOR = {
    "ausgrid": "Ausgrid",
    "essential": "Essential Energy",
    "endeavour": "Endeavour Energy",
}


def _operator_agrees(dnsp: str | None, osm_operator: str | None) -> bool:
    """True if the OSM operator agrees with (or is absent for) the DNSP.

    Where the OSM element has no operator tag the gate passes (accept, but the
    caller flags it ``osm_low_confidence``). Where it has one, it must equal the
    expected operator string for the row's DNSP; a disagreement rejects the
    match. Comparison is case-insensitive/trimmed.
    """
    if osm_operator is None or str(osm_operator).strip() == "":
        return True
    expected = _DNSP_TO_OSM_OPERATOR.get(str(dnsp).strip().lower())
    if expected is None:
        # Unknown DNSP code: cannot confirm, so do not trust an operator-tagged
        # OSM element for it.
        return False
    return str(osm_operator).strip().casefold() == expected.casefold()


def _match_needed_abbrev(load_name: str | None) -> bool:
    """True if the street-abbreviation expansion changed the normalised name.

    Compares the full OSM-mode normalisation (suffix strip + abbrev expansion)
    against a suffix-strip-only form; a difference means an abbreviation token
    (``st``→``street`` …) was expanded, which the caller flags as
    ``osm_low_confidence``.
    """
    with_abbrev = normalise_substation_name(load_name, strip_site_suffix=True)
    # Reproduce suffix-strip-only normalisation (no abbreviation expansion).
    if load_name is None:
        return False
    s = str(load_name).lower().strip()
    s = _VOLTAGE_SUFFIX.sub(" ", s)
    s = _OSM_SITE_SUFFIX.sub(" ", s)
    s = _APOSTROPHE.sub("", s)
    s = _NON_ALNUM.sub(" ", s)
    without_abbrev = _WHITESPACE.sub(" ", s).strip()
    return with_abbrev != without_abbrev


def geocode(
    load_csv: Path,
    ga_geojson: Path,
    osm_geojson: Path,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame, dict]:
    """Match load rows to GA (primary) then OSM (second). Returns
    ``(matched_layer, unmatched, stats)``.

    Precedence per load row: try the GA layer first (unchanged logic/order); on a
    GA miss, try the OSM layer (suffix-stripped names + operator-agreement gate).
    A row unmatched by **both** is dropped and listed in ``unmatched``.

    ``matched_layer`` is an EPSG:4326 GeoDataFrame (one point per matched
    substation) carrying ``coord_source`` ("ga"/"osm") and the boolean
    ``osm_low_confidence``; ``unmatched`` is a DataFrame of the dropped rows;
    ``stats`` carries the per-source match counts, the combined match rate and
    collision count for reporting/provenance.

    All three sources are required: a missing GA, OSM or load file raises
    ``FileNotFoundError`` (no silent single-source fallback).
    """
    load_csv = Path(load_csv)
    ga_geojson = Path(ga_geojson)
    osm_geojson = Path(osm_geojson)
    if not load_csv.exists():
        raise FileNotFoundError(f"Load CSV is missing: {load_csv}")
    if not ga_geojson.exists():
        raise FileNotFoundError(f"GA substation layer is missing: {ga_geojson}")
    if not osm_geojson.exists():
        raise FileNotFoundError(f"OSM substation layer is missing: {osm_geojson}")

    load = pd.read_csv(load_csv)
    if config.LOAD_MVA_COLUMN not in load.columns:
        raise ValueError(
            f"Load CSV {load_csv} is missing the load column "
            f"{config.LOAD_MVA_COLUMN!r}; got {list(load.columns)}"
        )
    ga = gpd.read_file(ga_geojson)
    osm = gpd.read_file(osm_geojson)
    ga_lookup = _build_ga_lookup(ga)
    osm_lookup = _build_osm_lookup(osm)

    matched_records: list[dict] = []
    unmatched_rows: list[dict] = []
    collisions_hit = 0
    matched_ga = 0
    matched_osm = 0
    osm_low_confidence_count = 0
    # Deterministic order: by dnsp then substation_name so the output layer and
    # any floating-point downstream are reproducible.
    load = load.sort_values(["dnsp", "substation_name"], kind="mergesort").reset_index(drop=True)
    norm_bucket_sizes: dict[str, int] = {}
    for _, row in ga.iterrows():
        norm = normalise_substation_name(row.get("feature_name"))
        if norm:
            norm_bucket_sizes[norm] = norm_bucket_sizes.get(norm, 0) + 1

    for _, row in load.iterrows():
        # --- GA first (unchanged logic/order) ---
        ga_norm = normalise_substation_name(row["substation_name"])
        ga_hit = ga_lookup.get(ga_norm)
        if ga_hit is not None:
            if norm_bucket_sizes.get(ga_norm, 0) > 1:
                collisions_hit += 1
            matched_ga += 1
            matched_records.append(
                {
                    "dnsp": row["dnsp"],
                    "substation_name": row["substation_name"],
                    "normalised_name": ga_norm,
                    config.LOAD_MVA_COLUMN: float(row[config.LOAD_MVA_COLUMN]),
                    "max_demand_unit": row.get("max_demand_unit"),
                    "data_year": row.get("data_year"),
                    "ga_feature_name": ga_hit["feature_name"],
                    "ga_locality": ga_hit["locality"],
                    "ga_voltage_kv": ga_hit["voltage_kv"],
                    "latitude": ga_hit["latitude"],
                    "longitude": ga_hit["longitude"],
                    "coord_source": "ga",
                    "osm_low_confidence": False,
                }
            )
            continue

        # --- OSM second (suffix-stripped name + operator gate) ---
        osm_norm = normalise_substation_name(
            row["substation_name"], strip_site_suffix=True
        )
        osm_hit = osm_lookup.get(osm_norm)
        if osm_hit is not None and _operator_agrees(
            row["dnsp"], osm_hit.get("operator")
        ):
            matched_osm += 1
            operator = osm_hit.get("operator")
            operator_absent = operator is None or str(operator).strip() == ""
            # A match that only exists because a street abbreviation was expanded
            # (findings §2 pass 2) is lower confidence than an exact-name match.
            abbrev_expanded = _match_needed_abbrev(row["substation_name"])
            low_conf = bool(operator_absent or abbrev_expanded)
            if low_conf:
                osm_low_confidence_count += 1
            matched_records.append(
                {
                    "dnsp": row["dnsp"],
                    "substation_name": row["substation_name"],
                    "normalised_name": osm_norm,
                    config.LOAD_MVA_COLUMN: float(row[config.LOAD_MVA_COLUMN]),
                    "max_demand_unit": row.get("max_demand_unit"),
                    "data_year": row.get("data_year"),
                    "ga_feature_name": osm_hit["name"],
                    "ga_locality": None,
                    "ga_voltage_kv": None,
                    "latitude": osm_hit["latitude"],
                    "longitude": osm_hit["longitude"],
                    "coord_source": "osm",
                    "osm_low_confidence": low_conf,
                }
            )
            continue

        # --- unmatched by both -> dropped ---
        reason = "no GA or OSM substation name match"
        if osm_hit is not None:
            # Present in OSM but rejected by the operator gate.
            reason = "OSM operator disagrees with DNSP (rejected)"
        unmatched_rows.append(
            {
                "dnsp": row["dnsp"],
                "substation_name": row["substation_name"],
                "normalised_name": ga_norm,
                "max_demand": row[config.LOAD_MVA_COLUMN],
                "max_demand_unit": row.get("max_demand_unit"),
                "data_year": row.get("data_year"),
                "reason": reason,
            }
        )

    # Explicit column order so an all-dropped run still yields a well-formed
    # (empty) layer rather than a schema-less frame.
    matched_columns = [
        "dnsp",
        "substation_name",
        "normalised_name",
        config.LOAD_MVA_COLUMN,
        "max_demand_unit",
        "data_year",
        "ga_feature_name",
        "ga_locality",
        "ga_voltage_kv",
        "latitude",
        "longitude",
        "coord_source",
        "osm_low_confidence",
    ]
    matched_df = pd.DataFrame(matched_records, columns=matched_columns)
    matched_layer = gpd.GeoDataFrame(
        matched_df,
        geometry=gpd.points_from_xy(matched_df["longitude"], matched_df["latitude"]),
        crs="EPSG:4326",
    )
    unmatched_df = pd.DataFrame(unmatched_rows)

    stats = {
        "load_rows": int(len(load)),
        "matched": int(len(matched_layer)),
        "matched_ga": int(matched_ga),
        "matched_osm": int(matched_osm),
        "osm_low_confidence": int(osm_low_confidence_count),
        "unmatched": int(len(unmatched_df)),
        "match_rate": round(len(matched_layer) / len(load), 4) if len(load) else 0.0,
        "collisions_resolved": int(collisions_hit),
        "ga_points": int(len(ga)),
        "osm_points": int(len(osm)),
    }
    return matched_layer, unmatched_df, stats


def main() -> int:
    load_csv = config.OUTPUT_DIR / "load" / "nsw_zone_substation_max_demand.csv"
    ga_geojson = config.GA_SUBSTATIONS_PATH
    osm_geojson = config.OSM_SUBSTATIONS_PATH
    out_gpkg = config.LOAD_WEIGHTS_PATH
    unmatched_csv = config.OUTPUT_DIR / "load" / "unmatched_substations.csv"

    print(
        f"Geocoding {load_csv.name} against {ga_geojson.name} (primary) "
        f"+ {osm_geojson.name} (second) ..."
    )
    matched_layer, unmatched_df, stats = geocode(load_csv, ga_geojson, osm_geojson)
    print(
        f"  matched {stats['matched']}/{stats['load_rows']} "
        f"({stats['match_rate'] * 100:.1f}%) "
        f"(GA {stats['matched_ga']} + OSM {stats['matched_osm']}); "
        f"OSM low-confidence {stats['osm_low_confidence']}; "
        f"unmatched {stats['unmatched']}; "
        f"collisions resolved {stats['collisions_resolved']}"
    )

    out_gpkg.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_gpkg.with_name(out_gpkg.stem + ".tmp" + out_gpkg.suffix)
    try:
        matched_layer.to_file(tmp, layer=config.LOAD_POINTS_LAYER, driver="GPKG", index=False)
        tmp.replace(out_gpkg)
    finally:
        tmp.unlink(missing_ok=True)
    print(f"  wrote {out_gpkg} ({len(matched_layer)} load points)")

    # Always (re)write the unmatched list so a 100% match clears a stale file.
    unmatched_cols = [
        "dnsp",
        "substation_name",
        "normalised_name",
        "max_demand",
        "max_demand_unit",
        "data_year",
        "reason",
    ]
    with open(unmatched_csv, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=unmatched_cols)
        writer.writeheader()
        for _, row in unmatched_df.iterrows():
            writer.writerow({c: row.get(c, "") for c in unmatched_cols})
    print(f"  wrote {unmatched_csv} ({len(unmatched_df)} unmatched rows)")

    # Provenance: SHA + manifest entry for the geocoded layer, recording both
    # source SHAs (GA primary, OSM second) and the ODbL credit for the OSM half.
    sha = hashlib.sha256(out_gpkg.read_bytes()).hexdigest()
    ga_sha = hashlib.sha256(ga_geojson.read_bytes()).hexdigest()
    osm_sha = hashlib.sha256(osm_geojson.read_bytes()).hexdigest()
    manifest_path = config.OUTPUT_DIR / "metadata" / config.FEATURE_MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest[out_gpkg.name] = {
        "sha256": sha,
        "bytes": out_gpkg.stat().st_size,
        "utc": utc_now(),
        "derived_proxy": True,
        "generated_by": "pipeline.demand.geocode_load",
        "match_rate": stats["match_rate"],
        "matched": stats["matched"],
        "matched_ga": stats["matched_ga"],
        "matched_osm": stats["matched_osm"],
        "osm_low_confidence": stats["osm_low_confidence"],
        "unmatched": stats["unmatched"],
        "load_rows": stats["load_rows"],
        "sources": {
            "ga_substations_2026_nsw.geojson": {
                "sha256": ga_sha,
                "role": "primary",
            },
            "osm_substations_nsw.geojson": {
                "sha256": osm_sha,
                "role": "second",
                "licence": "ODbL 1.0 - (c) OpenStreetMap contributors",
            },
        },
    }
    atomic_write_json(manifest_path, manifest)
    print(f"  manifest updated: {manifest_path} (sha256={sha})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
