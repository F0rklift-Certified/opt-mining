"""
S3-01a one-command Compose stack integration test (CI tier).

This is the executable form of Requirement 6.3 and the design's
§Testing Strategy → "One-command stack (integration, CI)": bring the whole MVP
web stack up with the single documented command

    docker compose up --build        # run from app/

in a clean environment, health-check that **both** ``web`` and ``api`` come up,
and confirm the **browser-facing API host port** is reachable (a GET to
``/openapi.json`` returns 200). The stack is always torn down with
``docker compose down`` in cleanup, even on failure.

Why this test is gated (not a fast unit test)
---------------------------------------------
Standing up two containers with ``--build`` is expensive and deterministic, so
the design places it in CI rather than the fast unit suite. It is therefore:

* marked ``@pytest.mark.integration`` (registered in ``pytest.ini``) so the fast
  suite can exclude it with ``pytest -m "not integration"``; and
* **skipped with a clear reason** when its runtime is unavailable — Docker CLI
  missing, Compose v2 plugin missing, or the Docker daemon not running — so a
  developer without Docker sees a SKIP, never a failure. In CI where Docker is
  present it runs for real.

How to run / exclude
--------------------
* Run only this CI tier:      ``pytest -m integration``
* Exclude it (fast suite):    ``pytest -m "not integration"``
* Run this file directly:     ``pytest tests/backend/test_compose_stack_integration.py``

**Validates: Requirement 6.3**
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

# --- Paths (repo-root relative; conftest.py puts the repo root on sys.path) ---
REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = REPO_ROOT / "app"
COMPOSE_PATH = APP_DIR / "docker-compose.yml"

# The documented default host ports (docker-compose.yml ${API_HOST_PORT:-8000} /
# ${WEB_HOST_PORT:-3000}). We pin explicit, non-default host ports below to
# avoid colliding with anything a dev already has bound on 8000/3000, driving
# them through the same documented env vars the Compose file reads.
API_HOST_PORT = 18000
WEB_HOST_PORT = 13000

# Health-check budget. `--build` (a Python image install + a Next.js build) can
# take a while on a cold cache, so give startup a generous ceiling; we poll and
# return as soon as it is healthy, so a fast machine is not slowed down.
BUILD_AND_START_TIMEOUT_S = 600
POLL_INTERVAL_S = 3


# ---------------------------------------------------------------------------
# Runtime availability gate — SKIP (never fail) when Docker/Compose is absent
# ---------------------------------------------------------------------------


def _docker_stack_unavailable_reason() -> str | None:
    """Return a human-readable skip reason if the stack cannot run, else None.

    Checks, in order: the ``docker`` CLI is on PATH, the Compose v2 plugin is
    present (``docker compose version``), and the Docker daemon is actually
    reachable (``docker info``). Any failure yields a clear reason so the test
    SKIPs rather than fails in an environment without Docker.
    """
    if shutil.which("docker") is None:
        return "Docker CLI not found on PATH; skipping CI-tier Compose stack test"

    # Compose v2 is the documented tool (`docker compose`, not `docker-compose`).
    try:
        compose = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - env-specific
        return f"`docker compose version` could not run ({exc}); skipping"
    if compose.returncode != 0:
        return "Docker Compose v2 plugin not available (`docker compose`); skipping"

    # The daemon must be running for `up --build` to do anything.
    try:
        info = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - env-specific
        return f"`docker info` could not run ({exc}); skipping"
    if info.returncode != 0:
        return "Docker daemon is not running/reachable (`docker info` failed); skipping"

    return None


def _is_port_free(port: int) -> bool:
    """True if `port` on localhost is not already bound (best-effort)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


# ---------------------------------------------------------------------------
# Compose lifecycle helpers
# ---------------------------------------------------------------------------


def _compose_env() -> dict[str, str]:
    """Environment for the Compose invocation: pin the documented host-port env
    vars to our non-default test ports (still driven through the same
    ``API_HOST_PORT`` / ``WEB_HOST_PORT`` the compose file reads), and keep the
    browser-facing / CORS URLs pointed at those ports."""
    env = os.environ.copy()
    env.update(
        {
            "API_HOST_PORT": str(API_HOST_PORT),
            "WEB_HOST_PORT": str(WEB_HOST_PORT),
            "NEXT_PUBLIC_API_BASE_URL": f"http://localhost:{API_HOST_PORT}",
            "CORS_ALLOW_ORIGINS": f"http://localhost:{WEB_HOST_PORT}",
        }
    )
    return env


def _compose(*args: str, env: dict[str, str], timeout: int) -> subprocess.CompletedProcess:
    """Run `docker compose <args>` with the app/ dir as the project directory."""
    return subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_PATH), *args],
        cwd=str(APP_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _service_running(service: str, env: dict[str, str]) -> bool:
    """True if `docker compose ps` reports `service` in a running state."""
    result = _compose("ps", "--status", "running", "--services", env=env, timeout=60)
    if result.returncode != 0:
        return False
    running = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return service in running


def _http_ok(url: str) -> bool:
    """True if a GET to `url` returns HTTP 200 (any connection error → False)."""
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 - localhost
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return False


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_compose_up_build_brings_up_web_and_api_and_api_port_reachable():
    """`docker compose up --build` brings up web + api; the API host port is
    reachable (GET /openapi.json → 200). Torn down in cleanup even on failure.

    Validates: Requirement 6.3.
    """
    reason = _docker_stack_unavailable_reason()
    if reason is not None:
        pytest.skip(reason)

    assert COMPOSE_PATH.is_file(), f"missing Compose file: {COMPOSE_PATH}"

    # Guard against colliding with an already-bound port so a failure here is a
    # clear environment problem, not a mysterious health-check timeout.
    for port in (API_HOST_PORT, WEB_HOST_PORT):
        if not _is_port_free(port):
            pytest.skip(
                f"host port {port} is already in use; skipping CI-tier Compose "
                "stack test to avoid a spurious failure"
            )

    env = _compose_env()
    api_openapi_url = f"http://localhost:{API_HOST_PORT}/openapi.json"

    try:
        # Single documented command, detached so we can poll for readiness.
        up = _compose(
            "up", "--build", "-d",
            env=env,
            timeout=BUILD_AND_START_TIMEOUT_S,
        )
        assert up.returncode == 0, (
            "`docker compose up --build -d` failed (Requirement 6.3).\n"
            f"stdout:\n{up.stdout}\nstderr:\n{up.stderr}"
        )

        # Poll until BOTH services are running AND the browser-facing API host
        # port answers /openapi.json with 200, or the budget expires.
        deadline = time.monotonic() + BUILD_AND_START_TIMEOUT_S
        api_reachable = False
        web_up = False
        while time.monotonic() < deadline:
            web_up = _service_running("web", env)
            api_up = _service_running("api", env)
            api_reachable = api_up and _http_ok(api_openapi_url)
            if web_up and api_reachable:
                break
            time.sleep(POLL_INTERVAL_S)

        # Confirm the web service came up (Requirement 6.1/6.3 — both services).
        assert web_up, (
            "web service did not reach a running state within "
            f"{BUILD_AND_START_TIMEOUT_S}s (Requirement 6.3).\n"
            f"{_compose('ps', env=env, timeout=60).stdout}"
        )
        # Confirm the browser-facing API host port is reachable (Requirement 6.6
        # / 6.3): GET /openapi.json returns 200 on the published host port.
        assert api_reachable, (
            f"API host port not reachable at {api_openapi_url} within "
            f"{BUILD_AND_START_TIMEOUT_S}s — /openapi.json did not return 200 "
            f"(Requirement 6.3).\n{_compose('ps', env=env, timeout=60).stdout}"
        )
    finally:
        # Always tear the stack down, even on failure (remove volumes/orphans so
        # a re-run starts clean). Best-effort: never mask the real assertion.
        try:
            _compose(
                "down", "--volumes", "--remove-orphans",
                env=env,
                timeout=180,
            )
        except (OSError, subprocess.SubprocessError):  # pragma: no cover - cleanup
            pass
