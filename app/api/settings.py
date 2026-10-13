"""
Backend_App — env-driven configuration (S3-01a scaffold).

This module reads cross-service configuration from the environment ONLY — it
hard-codes NO origin or host-address literal (Requirement 4.2, 6.5). The single
piece of config it owns today is the CORS allowed-origins list:

    CORS_ALLOW_ORIGINS  — comma-separated list of allowed CORS origins for the
                          Frontend_App, exposed via `get_cors_allow_origins()`
                          and consumed by `app.py`'s CORSMiddleware.

The env var is the single source of truth: an unset or empty value yields an
empty list, and every origin is parsed out of the string rather than baked into
source (Property 3: cross-service URLs and origins are env-driven, never
hard-coded).
"""

import os

# Name of the environment variable holding the comma-separated CORS origins.
# This is a variable *name*, not an origin/host literal — no allowed origin is
# baked into source anywhere in this module (Requirement 4.2, 6.5).
CORS_ALLOW_ORIGINS_ENV = "CORS_ALLOW_ORIGINS"


def parse_origins(raw: str | None) -> list[str]:
    """Parse a comma-separated origins string into a clean list.

    Splits on commas, strips surrounding whitespace from each entry, and drops
    empty entries. A ``None`` or empty/whitespace-only input yields an empty
    list. Order is preserved as written in the env var.
    """
    if not raw:
        return []
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def get_cors_allow_origins() -> list[str]:
    """Resolve the allowed CORS origins from the environment.

    Reads ``CORS_ALLOW_ORIGINS`` (a comma-separated string) and returns the
    resolved allowed-origins list. An unset or empty variable yields an empty
    list. No origin literal is hard-coded — the returned list equals exactly the
    parsed contents of the environment variable (Requirement 4.2, 6.5).
    """
    return parse_origins(os.environ.get(CORS_ALLOW_ORIGINS_ENV))
