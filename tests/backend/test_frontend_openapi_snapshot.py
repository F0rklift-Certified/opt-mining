"""The committed frontend contract snapshot must equal the live FastAPI schema."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "app" / "api"
SNAPSHOT = REPO_ROOT / "app" / "web" / "openapi" / "decision-service.openapi.json"


def _load_api_module():
    api_dir = str(API_DIR)
    if api_dir not in sys.path:
        sys.path.insert(0, api_dir)
    if "app" in sys.modules:
        return importlib.reload(sys.modules["app"])
    return importlib.import_module("app")


def test_frontend_openapi_snapshot_matches_live_fastapi_app():
    """A backend contract change must force regeneration before merge."""

    committed = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert committed == _load_api_module().app.openapi()
