"""The committed frontend contract snapshot must equal the live FastAPI schema."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "app" / "api"
SNAPSHOT = REPO_ROOT / "app" / "web" / "openapi" / "decision-service.openapi.json"


# Generating the live schema in a FRESH interpreter makes this test hermetic.
# The in-process `importlib.reload(app)` approach is sensitive to test ordering:
# OpenAPI/JSON-Schema generation depends on process-global Pydantic model-registry
# and FastAPI schema-ref state that earlier tests (which import
# `pipeline.service.models` — CellCollection, CellProperties, CellFeature, ...)
# leave behind, so a reloaded app can emit a partial/degraded schema even though
# the committed snapshot is the correct, complete contract. A clean subprocess
# reproduces a true clean-boot schema regardless of prior import state.
_LIVE_SCHEMA_SOURCE = """
import json
import sys
from pathlib import Path

api_dir = Path(sys.argv[1])
sys.path.insert(0, str(api_dir))

import app as api_app

sys.stdout.write(json.dumps(api_app.app.openapi()))
"""


def _load_live_schema() -> dict:
    """Return the live FastAPI OpenAPI schema produced by a clean interpreter."""

    completed = subprocess.run(
        [sys.executable, "-c", _LIVE_SCHEMA_SOURCE, str(API_DIR)],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(REPO_ROOT),
    )
    return json.loads(completed.stdout)


def test_frontend_openapi_snapshot_matches_live_fastapi_app():
    """A backend contract change must force regeneration before merge."""

    committed = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert committed == _load_live_schema()
