"""Export the live FastAPI schema used to generate the frontend client.

Run from ``app/web`` through ``npm run generate:api-schema`` after installing
the repository and ``app/api`` Python requirements.  Importing the actual
``app/api/app.py`` object means the committed snapshot cannot silently become a
hand-maintained approximation of the transport contract.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


WEB_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = WEB_DIR.parents[1]
API_DIR = REPO_ROOT / "app" / "api"
OUTPUT_PATH = WEB_DIR / "openapi" / "decision-service.openapi.json"


def main() -> None:
    """Write a deterministic OpenAPI snapshot from the live FastAPI app."""

    # app/api/app.py is intentionally launched as top-level module ``app`` and
    # imports sibling modules ``models`` and ``settings``.  Match that runtime
    # layout while also exposing the repository's ``pipeline`` package.
    sys.path[:0] = [str(API_DIR), str(REPO_ROOT)]
    from app import app as fastapi_app  # noqa: PLC0415

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(fastapi_app.openapi(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Exported {OUTPUT_PATH.relative_to(WEB_DIR)}")


if __name__ == "__main__":
    main()
