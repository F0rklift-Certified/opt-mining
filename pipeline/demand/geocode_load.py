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

Matched substations become a clean load-point layer
``DATA/electricity-demand/load/nsw_zone_substation_load_points.gpkg`` (EPSG:4326
storage, carrying ``max_demand`` in MVA, ``dnsp``, ``data_year`` and the matched
GA ``feature_name``/``locality``/``voltage_kv``). Unmatched substations are
**dropped** (coordinates are never invented) but written to
``DATA/electricity-demand/load/unmatched_substations.csv`` for review, and the
match rate is reported.

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


def normalise_substation_name(name: str | None) -> str:
    """Return a canonical form of a substation name for deterministic matching.

    Lower-cases, strips voltage suffixes (``110/66kV``, ``33/11kV``, ``11kV``,
    ``132kV`` …), removes punctuation, and collapses whitespace. A blank/None
    input returns the empty string (which never matches a real GA name).

    >>> normalise_substation_name("Terranora 110/66kV")
    'terranora'
    >>> normalise_substation_name("Lismore 132/66kV")
    'lismore'
    >>> normalise_substation_name("St. Mary's")
    'st marys'
    """
    if name is None:
        return ""
    s = str(name).lower().strip()
    s = _VOLTAGE_SUFFIX.sub(" ", s)
    # Drop apostrophes without inserting a space so possessives collapse
    # ("St Mary's" -> "st marys"), then map remaining punctuation to spaces.
    s = _APOSTROPHE.sub("", s)
    s = _NON_ALNUM.sub(" ", s)
    s = _WHITESPACE.sub(" ", s).strip()
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


def geocode(
    load_csv: Path,
    ga_geojson: Path,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame, dict]:
    """Match load rows to GA points. Returns (matched_layer, unmatched, stats).

    ``matched_layer`` is an EPSG:4326 GeoDataFrame (one point per matched
    substation); ``unmatched`` is a DataFrame of the dropped rows; ``stats``
    carries the match rate and collision count for reporting/provenance.
    """
    load_csv = Path(load_csv)
    ga_geojson = Path(ga_geojson)
    if not load_csv.exists():
        raise FileNotFoundError(f"Load CSV is missing: {load_csv}")
    if not ga_geojson.exists():
        raise FileNotFoundError(f"GA substation layer is missing: {ga_geojson}")

    load = pd.read_csv(load_csv)
    if config.LOAD_MVA_COLUMN not in load.columns:
        raise ValueError(
            f"Load CSV {load_csv} is missing the load column "
            f"{config.LOAD_MVA_COLUMN!r}; got {list(load.columns)}"
        )
    ga = gpd.read_file(ga_geojson)
    lookup = _build_ga_lookup(ga)

    matched_records: list[dict] = []
    unmatched_rows: list[dict] = []
    collisions_hit = 0
    # Deterministic order: by dnsp then substation_name so the output layer and
    # any floating-point downstream are reproducible.
    load = load.sort_values(["dnsp", "substation_name"], kind="mergesort").reset_index(drop=True)
    norm_bucket_sizes: dict[str, int] = {}
    for _, row in ga.iterrows():
        norm = normalise_substation_name(row.get("feature_name"))
        if norm:
            norm_bucket_sizes[norm] = norm_bucket_sizes.get(norm, 0) + 1

    for _, row in load.iterrows():
        norm = normalise_substation_name(row["substation_name"])
        hit = lookup.get(norm)
        if hit is None:
            unmatched_rows.append(
                {
                    "dnsp": row["dnsp"],
                    "substation_name": row["substation_name"],
                    "normalised_name": norm,
                    "max_demand": row[config.LOAD_MVA_COLUMN],
                    "max_demand_unit": row.get("max_demand_unit"),
                    "data_year": row.get("data_year"),
                    "reason": "no GA substation name match",
                }
            )
            continue
        if norm_bucket_sizes.get(norm, 0) > 1:
            collisions_hit += 1
        matched_records.append(
            {
                "dnsp": row["dnsp"],
                "substation_name": row["substation_name"],
                "normalised_name": norm,
                config.LOAD_MVA_COLUMN: float(row[config.LOAD_MVA_COLUMN]),
                "max_demand_unit": row.get("max_demand_unit"),
                "data_year": row.get("data_year"),
                "ga_feature_name": hit["feature_name"],
                "ga_locality": hit["locality"],
                "ga_voltage_kv": hit["voltage_kv"],
                "latitude": hit["latitude"],
                "longitude": hit["longitude"],
            }
        )

    matched_df = pd.DataFrame(matched_records)
    matched_layer = gpd.GeoDataFrame(
        matched_df,
        geometry=gpd.points_from_xy(matched_df["longitude"], matched_df["latitude"]),
        crs="EPSG:4326",
    )
    unmatched_df = pd.DataFrame(unmatched_rows)

    stats = {
        "load_rows": int(len(load)),
        "matched": int(len(matched_layer)),
        "unmatched": int(len(unmatched_df)),
        "match_rate": round(len(matched_layer) / len(load), 4) if len(load) else 0.0,
        "collisions_resolved": int(collisions_hit),
        "ga_points": int(len(ga)),
    }
    return matched_layer, unmatched_df, stats


def main() -> int:
    load_csv = config.OUTPUT_DIR / "load" / "nsw_zone_substation_max_demand.csv"
    ga_geojson = config.GA_SUBSTATIONS_PATH
    out_gpkg = config.LOAD_WEIGHTS_PATH
    unmatched_csv = config.OUTPUT_DIR / "load" / "unmatched_substations.csv"

    print(f"Geocoding {load_csv.name} against {ga_geojson.name} ...")
    matched_layer, unmatched_df, stats = geocode(load_csv, ga_geojson)
    print(
        f"  matched {stats['matched']}/{stats['load_rows']} "
        f"({stats['match_rate'] * 100:.1f}%); unmatched {stats['unmatched']}; "
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

    # Provenance: SHA + manifest entry for the geocoded layer.
    sha = hashlib.sha256(out_gpkg.read_bytes()).hexdigest()
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
        "unmatched": stats["unmatched"],
        "load_rows": stats["load_rows"],
    }
    atomic_write_json(manifest_path, manifest)
    print(f"  manifest updated: {manifest_path} (sha256={sha})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
