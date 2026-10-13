#!/usr/bin/env python3
"""
AEMO connection-point geometry fetcher — honest, never-fabricated.

Background
----------
``dist_connection_km`` is null for 100% of NSW cells because the AEMO KCI source
workbook (``DATA/infrastructure/connection-points/aemo_kci_2026.xlsx``) carries
NO coordinates. Its columns are administrative (TNSP name, dates, organisation,
"Site Name", free-text "Site Location Description", region) — there is no
latitude/longitude. The infrastructure feature builder
(``pipeline.infrastructure.features._resolve_connection_points``) therefore reads
the workbook, finds no lat/lon columns, and correctly leaves the distance null
rather than inventing a location.

This script's job is to obtain *real* geometry for those connection points from a
source YOU confirm, and write a coordinates file the builder can consume. It will
NEVER invent, guess, geocode-from-thin-air, or centroid-fill coordinates. If no
real source is available, it writes nothing and says so — the column stays null,
which is the honest state.

Geometry sources, in priority order
------------------------------------
1. ``--coords-csv PATH`` — a user-supplied CSV you have obtained from an
   authoritative source (e.g. AEMO's GIS export, a TNSP connection register, or a
   manually-verified table). It must have columns that identify the connection
   point and carry ``latitude``/``longitude`` (or lat/lon/x/y). Rows without valid
   coordinates are dropped, not filled.

2. ``--aemo-gis-url URL`` — an ArcGIS/GeoJSON endpoint you confirm serves
   connection-point or committed-project geometry. Fetched via the same
   ``query_layer_geojson`` helper the rest of the pipeline uses. Only used when you
   pass the flag — this script does not hardcode or guess an endpoint.

3. ``--match-substations`` (coarse APPROXIMATION, opt-in) — associate each KCI
   record with a GA substation by locality/name string match and borrow the
   substation's real coordinates. This is a documented approximation (a connection
   point is near, not at, its substation) and every matched row is flagged
   ``geometry_source = "ga_substation_locality_match"`` with the matched substation
   name, so the approximation is never silently presented as a surveyed location.
   Unmatched KCI records get NO geometry (stay null).

Output
------
Writes ``DATA/infrastructure/connection-points/aemo_kci_2026_geocoded.csv`` with,
at minimum, ``latitude``, ``longitude`` columns (so the builder's lat/lon detection
picks it up) plus provenance columns (``site_name``, ``geometry_source``,
``geometry_source_detail``). To make the builder consume it, point
``CONNECTION_POINTS_PATH`` at this file (see --wire-config / the printed hint).

Nothing here mutates the frozen KCI workbook or the builder logic.

Usage
-----
    # Preferred: supply verified coordinates
    python -m scripts.fetch_connection_point_geometry --coords-csv path/to/coords.csv

    # Or confirm an AEMO GIS endpoint
    python -m scripts.fetch_connection_point_geometry --aemo-gis-url "https://.../FeatureServer/0"

    # Or opt into the coarse substation-locality approximation
    python -m scripts.fetch_connection_point_geometry --match-substations

    # Inspect the KCI workbook columns without writing anything
    python -m scripts.fetch_connection_point_geometry --inspect
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from pipeline.infrastructure import config as infra_config
from pipeline.infrastructure import helpers

KCI_PATH = infra_config.CONNECTION_POINTS_PATH
SUBSTATION_PATH = infra_config.SUBSTATION_PATH
OUTPUT_PATH = (
    infra_config.INFRA_DIR / "connection-points" / "aemo_kci_2026_geocoded.csv"
)

# KCI workbook layout (verified): the header row is the third row (index 2) and
# data begins at the fourth row (index 3) — the same offsets the builder uses.
KCI_HEADER_ROW = 2
KCI_DATA_START = 3


def _load_kci() -> pd.DataFrame:
    """Load the KCI workbook into a DataFrame with its real (row-2) headers."""
    if not KCI_PATH.exists():
        raise SystemExit(f"KCI workbook missing: {KCI_PATH}")
    raw = pd.read_excel(KCI_PATH, header=None)
    if len(raw) <= KCI_DATA_START:
        raise SystemExit(f"KCI workbook has too few rows: {KCI_PATH}")
    headers = [str(v).strip() for v in raw.iloc[KCI_HEADER_ROW].tolist()]
    data = raw.iloc[KCI_DATA_START:].copy()
    data.columns = headers
    data = data.reset_index(drop=True)
    return data


def _find_col(df: pd.DataFrame, *needles: str) -> str | None:
    """Return the first column whose lowercased name contains any needle."""
    for col in df.columns:
        low = str(col).lower()
        if any(n in low for n in needles):
            return col
    return None


def inspect_kci() -> int:
    """Print the KCI columns and confirm there is no coordinate column."""
    df = _load_kci()
    print(f"KCI workbook: {KCI_PATH}")
    print(f"  rows: {len(df)}")
    print("  columns:")
    for col in df.columns:
        print(f"    - {col}")
    lat = _find_col(df, "latitude", "lat", " y")
    lon = _find_col(df, "longitude", "lon", "long", " x")
    if lat and lon:
        print(f"\n  Coordinate columns present: {lat!r}, {lon!r} "
              f"— the builder can already use this workbook directly.")
    else:
        print("\n  No latitude/longitude column present. This is why "
              "dist_connection_km is null. Supply geometry via --coords-csv, "
              "--aemo-gis-url, or --match-substations.")
    return 0


def _validate_coords(df: pd.DataFrame, lat_col: str, lon_col: str) -> pd.DataFrame:
    """Keep only rows with in-range numeric coordinates; drop the rest."""
    lat = pd.to_numeric(df[lat_col], errors="coerce")
    lon = pd.to_numeric(df[lon_col], errors="coerce")
    ok = lat.between(-90, 90) & lon.between(-180, 180)
    out = df.loc[ok].copy()
    out["latitude"] = lat.loc[ok]
    out["longitude"] = lon.loc[ok]
    dropped = int((~ok).sum())
    if dropped:
        print(f"    dropped {dropped} row(s) with missing/out-of-range coordinates "
              f"(not fabricated).")
    return out


def from_coords_csv(path: Path) -> pd.DataFrame:
    """Load user-supplied, authoritative connection-point coordinates."""
    print(f"[coords-csv] reading verified coordinates from {path}")
    if not Path(path).exists():
        raise SystemExit(f"Coordinates CSV not found: {path}")
    df = pd.read_csv(path)
    lat_col = _find_col(df, "latitude", "lat", " y")
    lon_col = _find_col(df, "longitude", "lon", "long", " x")
    if not lat_col or not lon_col:
        raise SystemExit(
            f"Coordinates CSV {path} has no latitude/longitude columns "
            f"(found: {list(df.columns)}). Refusing to fabricate coordinates."
        )
    out = _validate_coords(df, lat_col, lon_col)
    name_col = _find_col(out, "site name", "name", "connection")
    out["site_name"] = out[name_col] if name_col else pd.NA
    out["geometry_source"] = "user_supplied_coords_csv"
    out["geometry_source_detail"] = str(path)
    return out[["site_name", "latitude", "longitude",
                "geometry_source", "geometry_source_detail"]]


def from_aemo_gis(url: str) -> pd.DataFrame:
    """Fetch connection-point geometry from a user-confirmed GIS endpoint."""
    print(f"[aemo-gis] querying confirmed endpoint {url}")
    from pipeline.common.geo import query_layer_geojson

    collection = query_layer_geojson(url)
    rows = []
    for feat in collection.get("features", []):
        geom = feat.get("geometry")
        if not geom or geom.get("type") != "Point" or not geom.get("coordinates"):
            continue  # only real point geometry is usable; never invented
        lon, lat = geom["coordinates"][0], geom["coordinates"][1]
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        props = feat.get("properties") or {}
        name = next((props[k] for k in props
                     if "name" in str(k).lower()), None)
        rows.append({"site_name": name, "latitude": lat, "longitude": lon,
                     "geometry_source": "aemo_gis_endpoint",
                     "geometry_source_detail": url})
    if not rows:
        raise SystemExit(
            f"Endpoint {url} returned no usable point geometry. Nothing written "
            f"(dist_connection_km stays null)."
        )
    print(f"    {len(rows)} connection point(s) with real point geometry.")
    return pd.DataFrame(rows)


def from_substation_match() -> pd.DataFrame:
    """
    COARSE APPROXIMATION: borrow GA substation coordinates by locality/name match.

    A connection point is near — not at — its substation, so this is explicitly a
    proxy location. Every matched row is flagged so the approximation is visible in
    provenance and can be surfaced as reduced confidence. Unmatched KCI records get
    no geometry (stay null); nothing is fabricated.
    """
    print("[match-substations] COARSE approximation via GA substation locality match")
    print("    NOTE: connection point != substation location; flagged as approximate.")
    kci = _load_kci()
    if not SUBSTATION_PATH.exists():
        raise SystemExit(f"GA substations layer missing: {SUBSTATION_PATH}")
    subs = helpers.load_geojson(SUBSTATION_PATH)
    sub_feats = [f for f in subs.get("features", [])
                 if f.get("geometry") and f["geometry"].get("coordinates")]

    # Index substations by lowercased locality and by name for a simple match.
    by_locality: dict[str, dict] = {}
    by_name: dict[str, dict] = {}
    for f in sub_feats:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"][:2]
        rec = {"lat": lat, "lon": lon,
               "sub_name": p.get("feature_name"), "locality": p.get("locality")}
        if p.get("locality"):
            by_locality.setdefault(str(p["locality"]).strip().lower(), rec)
        if p.get("feature_name"):
            by_name.setdefault(str(p["feature_name"]).strip().lower(), rec)

    loc_col = _find_col(kci, "site location description", "location", "locality")
    name_col = _find_col(kci, "site name", "name")
    rows = []
    for _, r in kci.iterrows():
        matched = None
        # Try a name match first, then a locality substring match.
        if name_col and pd.notna(r.get(name_col)):
            matched = by_name.get(str(r[name_col]).strip().lower())
        if matched is None and loc_col and pd.notna(r.get(loc_col)):
            loc = str(r[loc_col]).strip().lower()
            matched = by_locality.get(loc)
            if matched is None:
                # loose substring: locality token appears in the free-text desc
                for key, rec in by_locality.items():
                    if key and key in loc:
                        matched = rec
                        break
        if matched is None:
            continue  # no real coordinate to borrow -> leave null
        rows.append({
            "site_name": r.get(name_col) if name_col else None,
            "latitude": matched["lat"],
            "longitude": matched["lon"],
            "geometry_source": "ga_substation_locality_match",
            "geometry_source_detail": f"substation:{matched['sub_name']}",
        })
    n_total = len(kci)
    print(f"    matched {len(rows)} of {n_total} KCI records to a substation "
          f"({n_total - len(rows)} left null — no confident match).")
    if not rows:
        raise SystemExit(
            "No KCI record could be matched to a GA substation. Nothing written "
            "(dist_connection_km stays null). Prefer --coords-csv with real data."
        )
    return pd.DataFrame(rows)


def _write_output(df: pd.DataFrame) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_PATH.with_suffix(".csv.tmp")
    df.to_csv(tmp, index=False)
    tmp.replace(OUTPUT_PATH)
    print(f"\nWrote {len(df)} connection point(s) with real geometry to:\n  {OUTPUT_PATH}")
    sources = df["geometry_source"].value_counts().to_dict()
    print(f"  geometry_source breakdown: {sources}")
    print(
        "\nTo make the feature builder consume this file, point the builder's\n"
        "connection-points path at it, e.g. set in pipeline/infrastructure/config.py:\n"
        f"    CONNECTION_POINTS_PATH = INFRA_DIR / 'connection-points' / '{OUTPUT_PATH.name}'\n"
        "then rebuild infrastructure features:\n"
        "    python -m pipeline --only infrastructure.features\n"
        "Cells near a real connection point will get a real dist_connection_km;\n"
        "cells with no connection point remain null (never fabricated).\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--inspect", action="store_true",
                        help="print KCI columns and exit (no writes)")
    parser.add_argument("--coords-csv", type=Path,
                        help="authoritative coordinates CSV (preferred)")
    parser.add_argument("--aemo-gis-url", type=str,
                        help="confirmed GIS endpoint serving connection-point geometry")
    parser.add_argument("--match-substations", action="store_true",
                        help="COARSE opt-in: borrow GA substation coords by locality/name")
    args = parser.parse_args(argv)

    if args.inspect:
        return inspect_kci()

    chosen = [bool(args.coords_csv), bool(args.aemo_gis_url), args.match_substations]
    if sum(chosen) == 0:
        print(
            "No geometry source specified. The AEMO KCI workbook has no coordinates,\n"
            "so this script will not fabricate any. Choose a real source:\n"
            "  --coords-csv PATH        (verified coordinates — preferred)\n"
            "  --aemo-gis-url URL       (a GIS endpoint you confirm)\n"
            "  --match-substations      (coarse substation-locality approximation)\n"
            "Run with --inspect to see the workbook columns.",
            file=sys.stderr,
        )
        return 2
    if sum(chosen) > 1:
        print("Choose exactly one geometry source at a time.", file=sys.stderr)
        return 2

    if args.coords_csv:
        df = from_coords_csv(args.coords_csv)
    elif args.aemo_gis_url:
        df = from_aemo_gis(args.aemo_gis_url)
    else:
        df = from_substation_match()

    if df.empty:
        print("No real geometry produced; nothing written.", file=sys.stderr)
        return 1
    _write_output(df)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
