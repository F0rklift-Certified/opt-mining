"""
Shared helpers for Global Wind Atlas (GWA) retrieval.

The GWA publishes per-country GeoTIFFs behind a redirecting API endpoint:

    https://globalwindatlas.info/api/gis/country/<ISO3>/<variable>[/<height>]
        -> 302 -> https://gwa.cdn.nazkamapps.com/country_tifs_v4/<ISO3>_<variable>[_<height>m].tif

The CDN advertises ``accept-ranges: bytes`` and the rasters are tiled and
overviewed, so GDAL can read a window through ``/vsicurl/`` without
transferring the whole file. Australia rasters are ~600 MB each; a windowed
read of a 2° × 2° study area transfers a few MB.

Source:  https://globalwindatlas.info/
Licence: see DATA/wind-resource/DATA_PROVENANCE.md
"""

from __future__ import annotations

import os

import requests

from . import config


def apply_vsicurl_env() -> None:
    """Set GDAL environment variables for efficient remote reads."""
    for key, value in config.VSICURL_ENV.items():
        os.environ.setdefault(key, value)


def api_url(
    variable: str, height: int | None = None, country: str = config.GWA_COUNTRY
) -> str:
    """Build the GWA API URL for a variable, optionally at a given height."""
    url = f"{config.GWA_API_BASE}/{country}/{variable}"
    if height is not None:
        url = f"{url}/{height}"
    return url


def resolve_source(
    variable: str, height: int | None = None, country: str = config.GWA_COUNTRY
) -> dict:
    """
    Resolve the API endpoint to the underlying CDN GeoTIFF and report its size.

    Returns a provenance dict with keys: variable, height_m, api_endpoint,
    source_url, signed_url, remote_bytes, last_modified.

    Raises RuntimeError if the variable is not published as a country GeoTIFF
    (the CDN returns 403 for those).
    """
    endpoint = api_url(variable, height, country)
    head = requests.head(endpoint, allow_redirects=False, timeout=config.GWA_TIMEOUT)
    location = head.headers.get("Location")
    if head.status_code != 302 or not location:
        raise RuntimeError(
            f"{endpoint} did not redirect to a GeoTIFF (HTTP {head.status_code})"
        )

    cdn = requests.head(location, timeout=config.GWA_TIMEOUT)
    if cdn.status_code != 200:
        raise RuntimeError(
            f"{variable}"
            + (f" at {height}m" if height is not None else "")
            + f" is not available as a country GeoTIFF (CDN returned HTTP {cdn.status_code}). "
            "It may only be obtainable via the Global Wind Atlas custom-area download form."
        )

    return {
        "variable": variable,
        "height_m": height,
        "api_endpoint": endpoint,
        "source_url": location.split("?")[0],
        "signed_url": location,
        "remote_bytes": int(cdn.headers.get("Content-Length", 0)),
        "last_modified": cdn.headers.get("Last-Modified", ""),
    }


def human_bytes(n: int) -> str:
    """
    Format a byte count for logs and provenance tables.

    Decimal (1 MB = 10**6 bytes), matching the sizes quoted in the download
    manifest and the task documents.
    """
    step = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if step < 1000 or unit == "GB":
            return f"{step:.1f} {unit}"
        step /= 1000
    return f"{step:.1f} GB"
