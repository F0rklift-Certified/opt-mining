"""
Geographic probe stage — discover available geographic/environmental sources.

Probes every candidate geographic/environmental data source and builds the
Task 4 source register. Probes are metadata-only: ArcGIS layer JSON,
HTTP HEAD, or count queries — no feature or pixel data transferred.

Importable entry point:
    from pipeline.geographic.probe import run
    result = run(verbose=False)

Output:
    DATA/geographic/metadata/source_register.md
    DATA/geographic/metadata/source_register.csv
"""

from __future__ import annotations

import csv as csv_mod
import io
from pathlib import Path

import requests

from . import config
from ..common.geo import (
    atomic_write_text,
    banner,
    layer_count,
    layer_metadata,
    utc_now,
)
from ..common.geo import human_bytes


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CSV_COLUMNS = [
    "dataset_id", "category", "custodian", "endpoint", "access_method",
    "http_status", "format", "native_crs", "licence", "vintage",
    "size_or_count", "intended_use", "notes",
]

_UA = {"User-Agent": "opt-mining-sprint0-task4 (data investigation; contact: repo owner)"}


# ---------------------------------------------------------------------------
# Probe helpers
# ---------------------------------------------------------------------------


def _head_status(url: str, allow_redirects: bool = True) -> tuple[int, int]:
    """Return (status, content_length) from a HEAD request."""
    resp = requests.head(
        url, timeout=config.TIMEOUT, allow_redirects=allow_redirects, headers=_UA
    )
    return resp.status_code, int(resp.headers.get("Content-Length") or 0)


def _probe_arcgis_layer(
    dataset_id, category, custodian, layer_url, licence, vintage,
    intended_use, notes="", count_where="1=1",
):
    """Register row for an ArcGIS FeatureServer layer."""
    try:
        meta = layer_metadata(layer_url)
        count = layer_count(layer_url, where=count_where)
        sr = meta.get("sourceSpatialReference") or meta.get("extent", {}).get("spatialReference", {})
        wkid = sr.get("latestWkid") or sr.get("wkid")
        geom = meta.get("geometryType", "?").replace("esriGeometry", "")
        fields = len(meta.get("fields", []))
        return {
            "dataset_id": dataset_id, "category": category, "custodian": custodian,
            "endpoint": layer_url, "access_method": "ArcGIS REST FeatureServer (f=geojson)",
            "http_status": 200, "format": f"GeoJSON/EsriJSON, {geom}",
            "native_crs": f"EPSG:{wkid}" if wkid else "unreported",
            "licence": licence, "vintage": vintage,
            "size_or_count": f"{count} features, {fields} fields",
            "intended_use": intended_use, "notes": notes or meta.get("name", ""),
        }
    except Exception as exc:
        return {
            "dataset_id": dataset_id, "category": category, "custodian": custodian,
            "endpoint": layer_url, "access_method": "ArcGIS REST FeatureServer",
            "http_status": "error", "format": "", "native_crs": "", "licence": licence,
            "vintage": vintage, "size_or_count": "", "intended_use": intended_use,
            "notes": f"probe failed: {exc}",
        }


def _probe_http(
    dataset_id, category, custodian, url, access_method, fmt, crs, licence,
    vintage, intended_use, notes="", expect_bytes=True,
):
    """Register row for a plain HTTP(S) resource via HEAD."""
    try:
        status, length = _head_status(url)
        size = human_bytes(length) if (expect_bytes and length) else ""
        return {
            "dataset_id": dataset_id, "category": category, "custodian": custodian,
            "endpoint": url, "access_method": access_method, "http_status": status,
            "format": fmt, "native_crs": crs, "licence": licence, "vintage": vintage,
            "size_or_count": size, "intended_use": intended_use, "notes": notes,
        }
    except Exception as exc:
        return {
            "dataset_id": dataset_id, "category": category, "custodian": custodian,
            "endpoint": url, "access_method": access_method, "http_status": "error",
            "format": fmt, "native_crs": crs, "licence": licence, "vintage": vintage,
            "size_or_count": "", "intended_use": intended_use,
            "notes": f"probe failed: {exc}",
        }


# ---------------------------------------------------------------------------
# Source register
# ---------------------------------------------------------------------------


def _build_geo_register() -> list[dict]:
    """Probe all geographic/environmental sources and return register rows."""
    rows: list[dict] = []

    # --- Administrative boundaries (ABS ASGS 2021) ---
    for layer, dsid, use, note in [
        ("STE", "abs_asgs2021_ste",
         "Reference layer: state/territory polygons; basis for derived NEM regions",
         "10 features incl. Other Territories and 'Outside Australia' (null geometry rows to filter)"),
        ("AUS", "abs_asgs2021_aus",
         "National land outline; land-mask candidate", ""),
        ("LGA", "abs_asgs2021_lga",
         "Local Government Area boundaries (checklist item A)", ""),
        ("SA2", "abs_asgs2021_sa2",
         "Population/demand allocation join geometry (Task 2 cross-reference)", ""),
    ]:
        rows.append(_probe_arcgis_layer(
            dsid, "admin-boundaries", "ABS",
            f"{config.ABS_ASGS_BASE}/{layer}/FeatureServer/0",
            "CC BY 4.0", "ASGS Ed. 3 (2021)", use, note))

    rows.append(_probe_arcgis_layer(
        "abs_asgs2021_ucl", "urban", "ABS",
        f"{config.ABS_ASGS_BASE}/UCL/FeatureServer/0",
        "CC BY 4.0", "ASGS Ed. 3 (2021)",
        "Urban Centres and Localities: urban-extent exclusion evidence + demand proxy"))

    # --- Protected areas (CAPAD) ---
    rows.append(_probe_arcgis_layer(
        "capad2024_terrestrial", "protected-areas", "DCCEEW",
        f"{config.CAPAD_BASE}/0", "CC BY 4.0", "CAPAD 2024",
        "Hard exclusion: terrestrial protected areas with IUCN categories"))
    rows.append(_probe_arcgis_layer(
        "capad2024_marine", "protected-areas", "DCCEEW",
        f"{config.CAPAD_BASE}/1", "CC BY 4.0", "CAPAD 2024 (marine)",
        "Marine/terrestrial distinction (checklist C); not sampled — analysis grid is terrestrial"))

    # --- Land use (ABARES) ---
    nlum = "https://www.agriculture.gov.au/sites/default/files/documents"
    rows.append(_probe_http(
        "abares_nlum_2020_21", "land-use", "ABARES",
        f"{nlum}/NLUM_v7_1_250m_ALUMV8_2020_21_alb_20260814.zip",
        "HTTP zip download", "GeoTIFF (zipped), 250 m", "EPSG:3577 (expected)",
        "CC BY 4.0", "2020–21 (NLUM v7.1, ALUM v8)",
        "National land use at screening resolution; window clip sampled"))
    rows.append(_probe_http(
        "abares_nlum_2015_16", "land-use", "ABARES",
        f"{nlum}/NLUM_v7_1_250m_ALUMV8_2015_16_alb_20260814.zip",
        "HTTP zip download", "GeoTIFF (zipped), 250 m", "EPSG:3577 (expected)",
        "CC BY 4.0", "2015–16 (NLUM v7.1)", "Earlier vintage; register only"))
    rows.append(_probe_http(
        "abares_clum_50m", "land-use", "ABARES",
        "https://www.agriculture.gov.au/abares/aclump/land-use/data-download",
        "Portal page (manual download)", "GeoTIFF/Esri Grid, 50 m", "EPSG:3577",
        "CC BY 4.0", "CLUM Dec 2023 v2",
        "Catchment-scale 50 m product; register only — 250 m NLUM matches the ~5 km "
        "screening grid and is 1/25th the data volume", expect_bytes=False))

    # --- Elevation / DEM ---
    ot = "https://opentopography.s3.sdsc.edu/raster"
    rows.append(_probe_http(
        "srtm_gl1_30m", "elevation", "NASA/OpenTopography",
        f"{ot}/SRTM_GL1/SRTM_GL1_srtm.vrt",
        "GDAL /vsicurl/ windowed read", "VRT mosaic of GeoTIFF tiles, 1 arc-second (~30 m)",
        "EPSG:4326", "NASA public domain (attribution requested)", "SRTM (2000 mission)",
        "Working scripted route to 1-second elevation; windowed clip sampled"))
    rows.append(_probe_http(
        "srtm_gl3_90m", "elevation", "NASA/OpenTopography",
        f"{ot}/SRTM_GL3/SRTM_GL3_srtm.vrt",
        "GDAL /vsicurl/ windowed read", "VRT mosaic of GeoTIFF tiles, 3 arc-second (~90 m)",
        "EPSG:4326", "NASA public domain (attribution requested)", "SRTM (2000 mission)",
        "Coarser screening-friendly product; windowed clip sampled"))
    rows.append(_probe_http(
        "ga_dem_services", "elevation", "Geoscience Australia",
        "https://services.ga.gov.au/gis/rest/services/DEM_SRTM_1Second_Hydro_Enforced/MapServer",
        "ArcGIS REST (scripted)", "MapServer/ImageServer", "EPSG:4283 (documented)",
        "CC BY 4.0", "GA SRTM-derived 1s DEM suite (2011)",
        "Authoritative national DEM; expect 403 to scripted clients"))
    rows.append(_probe_http(
        "ga_elvis_portal", "elevation", "Geoscience Australia",
        "https://elevation.fsdf.org.au/",
        "Interactive portal only", "Various (tile downloads)", "EPSG:4283",
        "CC BY 4.0", "current", "Browser download route for GA DEM tiles",
        expect_bytes=False))
    rows.append(_probe_http(
        "csiro_slope_1s", "elevation", "CSIRO",
        "https://data.csiro.au/collection/csiro:5588",
        "Portal page (registration)", "Esri Grid, 1 arc-second", "EPSG:4283",
        "CC BY", "2011 (derived from GA DEM-S)",
        "Pre-computed national slope; register only", expect_bytes=False))

    # --- Coastline & water ---
    rows.append(_probe_http(
        "ne_land_50m", "coastline", "Natural Earth",
        "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
        "geojson/ne_50m_land.geojson",
        "HTTP GeoJSON download", "GeoJSON, 1:50m generalisation", "EPSG:4326",
        "Public domain", "NE master",
        "The prototype's land-mask source; sampled for the mask-adequacy assessment"))
    rows.append(_probe_http(
        "dea_coastlines", "coastline", "Geoscience Australia (DEA)",
        "https://data.dea.ga.gov.au/?prefix=derivative/dea_coastlines/",
        "S3 public bucket", "GeoPackage/Shapefile", "EPSG:3577",
        "CC BY 4.0", "annual shorelines 1988–",
        "Higher-fidelity coastline option; register only", expect_bytes=False))
    rows.append(_probe_http(
        "dea_waterbodies", "water", "Geoscience Australia (DEA)",
        "https://data.dea.ga.gov.au/?prefix=derivative/dea_waterbodies/",
        "S3 public bucket", "GeoPackage/Shapefile polygons", "EPSG:3577",
        "CC BY 4.0", "Landsat-derived, current",
        "Inland waterbody polygons; register only", expect_bytes=False))

    # --- Roads (secondary) ---
    rows.append(_probe_http(
        "osm_australia_pbf", "roads", "OpenStreetMap/Geofabrik",
        "https://download.geofabrik.de/australia-oceania/australia-latest.osm.pbf",
        "HTTP pbf download", "OSM PBF (roads via highway=* tags)", "EPSG:4326",
        "ODbL", "continuous",
        "Secondary priority per checklist F: size recorded, not sampled"))

    # --- Portals (discovery only) ---
    rows.append(_probe_http(
        "nationalmap", "portal", "Digital Atlas of Australia / TerriaJS",
        "https://nationalmap.gov.au/", "Interactive portal", "WMS/WFS/ArcGIS proxies",
        "various", "various", "current",
        "Aggregates the same custodial services probed above; discovery only",
        expect_bytes=False))
    rows.append(_probe_http(
        "data_gov_au", "portal", "data.gov.au (CKAN)",
        "https://data.gov.au/data/api/3/action/package_search?q=CAPAD&rows=1",
        "CKAN API", "catalogue JSON", "n/a", "various", "current",
        "Catalogue used for discovery; intermittently slow — never load-bearing",
        expect_bytes=False))

    return rows


def _render_geo_markdown(rows: list[dict]) -> str:
    """Render the source register as markdown grouped by category."""
    out = io.StringIO()
    out.write("# Task 4 source register\n\n")
    out.write(banner("geographic.probe"))
    out.write(
        "\nEvery candidate source probed for the geographic/environmental criterion, "
        "including routes that refuse scripted access (their status is the finding). "
        "Probes are metadata-only; no feature or pixel data was transferred.\n\n"
    )
    by_cat: dict[str, list[dict]] = {}
    for row in rows:
        by_cat.setdefault(row["category"], []).append(row)
    for cat, cat_rows in by_cat.items():
        out.write(f"## {cat}\n\n")
        out.write(
            "| Dataset | Custodian | Access | Status | Format | Native CRS "
            "| Licence | Vintage | Size/Count | Notes |\n"
        )
        out.write("|---|---|---|---|---|---|---|---|---|---|\n")
        for r in cat_rows:
            out.write(
                f"| `{r['dataset_id']}` | {r['custodian']} | {r['access_method']} "
                f"| {r['http_status']} | {r['format']} | {r['native_crs']} | {r['licence']} "
                f"| {r['vintage']} | {r['size_or_count']} | {r['notes']} |\n"
            )
        out.write("\n")
    out.write("Endpoints (full URLs) are in `source_register.csv`.\n")
    return out.getvalue()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(verbose: bool = False) -> dict:
    """
    Probe geographic/environmental sources and write source register.

    Returns a summary dict with output paths.
    """
    rows = _build_geo_register()

    if verbose:
        for row in rows:
            status = row["http_status"]
            flag = "" if status == 200 else "  <-- finding"
            print(f"    [{status}] {row['dataset_id']}: "
                  f"{row['size_or_count'] or row['notes'][:60]}{flag}")

    md_path = config.GEO_META_DIR / "source_register.md"
    atomic_write_text(md_path, _render_geo_markdown(rows))

    csv_buf = io.StringIO()
    writer = csv_mod.DictWriter(csv_buf, fieldnames=_CSV_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    csv_path = config.GEO_META_DIR / "source_register.csv"
    atomic_write_text(csv_path, csv_buf.getvalue())

    print(f"    → {md_path.relative_to(config.PROJECT_ROOT)}")
    print(f"    → {csv_path.relative_to(config.PROJECT_ROOT)}")
    return {"source_register_md": md_path, "source_register_csv": csv_path}
