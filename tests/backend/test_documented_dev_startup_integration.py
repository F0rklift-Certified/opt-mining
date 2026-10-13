"""
S3-01a documented dev-startup integration test (task 9.2).

Startup is an external, deterministic behaviour, so this is an *integration*
test (design §Testing Strategy → "Documented dev startup (integration)"), not a
property test and not the in-process ``TestClient`` smoke (that is task 9.1,
``test_backend_startup_smoke.py``). Where the smoke drives the app through
Starlette's in-process transport, this test proves the promise Requirement 5.3
actually makes to a contributor: **following the DOCUMENTED commands in a clean
environment starts the app and makes ``/docs`` + ``/openapi.json`` reachable.**

To honour "documented", the backend half launches the app *exactly* the way
``app/README.md`` documents it — the real command, from the real directory,
with the real import path — and asserts over a real socket:

    (from app/api/)   PYTHONPATH=../.. uvicorn app:app --port <free>

* it runs ``uvicorn app:app`` (the README's backend dev command), not an
  in-process client;
* it runs it with the working directory set to ``app/api/`` (so ``app.py``
  imports its ``models`` / ``settings`` siblings as top-level modules, exactly
  as the run command and the api Dockerfile launch it);
* it sets ``PYTHONPATH`` to the repository root (the README's ``PYTHONPATH=../..``
  from ``app/api/``) so ``app.py``'s ``import pipeline.service`` delegation
  resolves — the documented reason the engine is importable without a
  ``pip install -e``;
* it binds a real, free TCP port, polls that port over HTTP until the server is
  ready, and asserts ``GET /openapi.json`` and ``GET /docs`` each return HTTP
  200 over the wire;
* it tears the server down cleanly (terminate, then kill on timeout) in a
  ``finally`` so no stray uvicorn process is left bound to the port.

The frontend half follows the README's documented ``next dev`` command. Standing
up ``next dev`` needs Node plus an installed ``node_modules`` and is
expensive/flaky for a fast Python suite (and often unavailable in CI for the
Python job), so — per the task — that portion is **gated behind an availability
check and skipped with an explicit reason** when the toolchain or dependencies
are absent. When Node *and* the web ``node_modules`` are present, it launches the
documented dev server the README's way — ``npm run dev`` (→ ``next dev``) from
``app/web/`` on a free port — binds a real socket, polls it over HTTP until
ready, and asserts the app root answers 200, then tears the server down cleanly.
This mirrors the backend half's real-socket approach rather than mutating tracked
source with a full ``next build`` (which reformats ``tsconfig.json`` and drops
build artefacts). At minimum, and unconditionally, the backend is verified
end-to-end over a real socket.

If a required tool for a given half is unavailable (``uvicorn`` for the backend;
``node`` / ``npm`` / installed web deps for the frontend) the corresponding test
**skips with a clear reason** rather than failing spuriously — a clean
environment that has not yet installed that toolchain is a skip, not a
regression.

**Validates: Requirements 5.3**
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

# --- Paths ------------------------------------------------------------------
# The repo root carries the `pipeline/` engine; `app/api/` is the documented
# working directory for the backend dev command; `app/web/` the frontend one.
REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "app" / "api"
WEB_DIR = REPO_ROOT / "app" / "web"

# How long to wait for the documented server to bind + answer, and how often to
# poll. Generous enough for a cold import of the FastAPI app + engine package on
# a loaded CI box, still bounded so a genuinely broken startup fails fast.
STARTUP_TIMEOUT_S = 30.0
POLL_INTERVAL_S = 0.25
# `next dev` has to compile the first route on demand; give the frontend a
# larger readiness budget than the backend's cold import.
FRONTEND_STARTUP_TIMEOUT_S = 120.0


def _uvicorn_available() -> bool:
    """True when `uvicorn` is importable in the test interpreter.

    The documented command is ``uvicorn app:app``; we launch it as
    ``<this-python> -m uvicorn`` so it runs against the very interpreter (and
    virtualenv) pytest is using, rather than depending on a console-script shim
    being on PATH. So the availability check that matters is whether the
    ``uvicorn`` module can be imported here.
    """
    return importlib.util.find_spec("uvicorn") is not None


def _find_free_port() -> int:
    """Reserve a free TCP port on the loopback interface and return it.

    Binding to port 0 lets the OS pick an unused port; we read it back, then
    close the socket so uvicorn can bind it moments later. A short race window
    exists between close and re-bind, but on loopback in a test context it is
    negligible and the readiness poll would surface any collision as a failure
    to become ready rather than a false pass.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _wait_until_ready(
    probe_url: str,
    process: subprocess.Popen,
    *,
    label: str,
    timeout_s: float = STARTUP_TIMEOUT_S,
) -> None:
    """Poll `probe_url` until it answers 200, or fail with context.

    Fails fast (not after the full timeout) if the launched process exits early,
    surfacing its captured output so a documented-command breakage — a bad
    import path, a missing dependency — is diagnosable rather than a bare
    timeout. `label` names the app in failure messages (e.g. "backend").
    """
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            out = _drain(process)
            raise AssertionError(
                f"documented {label} command exited before becoming ready "
                f"(exit code {process.returncode}); output:\n{out}"
            )
        try:
            response = httpx.get(probe_url, timeout=2.0)
            if response.status_code == 200:
                return
            last_error = AssertionError(
                f"{probe_url} returned {response.status_code} during startup"
            )
        except httpx.HTTPError as exc:  # not yet bound / mid-startup
            last_error = exc
        time.sleep(POLL_INTERVAL_S)
    raise AssertionError(
        f"{label} did not become ready within {timeout_s:.0f}s "
        f"at {probe_url}; last error: {last_error!r}\n{_drain(process)}"
    )


def _drain(process: subprocess.Popen) -> str:
    """Best-effort capture of a (possibly still-running) process's output."""
    try:
        out, _ = process.communicate(timeout=1.0)
    except subprocess.TimeoutExpired:
        return "<process still running; output not yet flushed>"
    except Exception:  # pragma: no cover - defensive
        return "<output unavailable>"
    if out is None:
        return ""
    return out if isinstance(out, str) else out.decode("utf-8", "replace")


def _terminate(process: subprocess.Popen) -> None:
    """Tear the server down cleanly: terminate, then kill if it lingers.

    Servers launched with ``start_new_session=True`` (below) lead their own
    process group, so a wrapper (``npm run dev``) and its spawned child
    (``next dev``) are torn down together by signalling the whole group — a bare
    ``process.terminate()`` would kill only the wrapper and orphan the child
    still bound to the port. Falls back to signalling just the process when the
    platform has no process groups.
    """
    if process.poll() is not None:
        return

    def _signal_group(sig: int) -> None:
        try:
            os.killpg(os.getpgid(process.pid), sig)
        except (ProcessLookupError, PermissionError, AttributeError, OSError):
            # No group / already gone / non-POSIX: signal the process directly.
            if sig == signal.SIGKILL:
                process.kill()
            else:
                process.terminate()

    _signal_group(signal.SIGTERM)
    try:
        process.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        _signal_group(signal.SIGKILL)
        process.wait(timeout=10.0)


# ---------------------------------------------------------------------------
# Backend half — MANDATORY end-to-end over a real socket (skips only if the
# documented command's tool, uvicorn, is genuinely unavailable).
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _uvicorn_available(),
    reason=(
        "uvicorn is not installed in this environment; the documented backend "
        "command `uvicorn app:app` cannot be launched. Install it with "
        "`pip install -r app/api/requirements.txt` to run this integration test."
    ),
)
def test_documented_backend_startup_serves_docs_and_openapi_over_http():
    """Following the README's documented backend command serves /docs + /openapi.json.

    Runs `PYTHONPATH=<repo-root> <python> -m uvicorn app:app --port <free>` with
    the working directory set to `app/api/` — the exact documented dev command
    (`app/README.md` → "Backend (dev)") — binds a real socket, and asserts both
    documented OpenAPI endpoints answer 200 over HTTP (Requirement 5.3).
    """
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    # The documented run environment: repo root on PYTHONPATH so
    # `import pipeline.service` resolves (README `PYTHONPATH=../..` from app/api/).
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(REPO_ROOT) + (os.pathsep + existing if existing else "")
    )

    # `uvicorn app:app` launched against the test interpreter (== the README's
    # `uvicorn app:app`, just invoked module-style so it uses this venv). Working
    # directory is app/api/ so `app.py` finds its `models`/`settings` siblings.
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        command,
        cwd=str(API_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,  # own process group for clean group teardown
    )
    try:
        _wait_until_ready(f"{base_url}/openapi.json", process, label="backend")

        # Assert both documented OpenAPI surfaces are reachable over the socket.
        openapi = httpx.get(f"{base_url}/openapi.json", timeout=5.0)
        assert openapi.status_code == 200, (
            f"/openapi.json must return 200 over HTTP (Requirement 5.3); "
            f"got {openapi.status_code}"
        )
        schema = openapi.json()
        assert "openapi" in schema and schema.get("paths"), (
            "/openapi.json must serve the OpenAPI document (version + paths)"
        )

        docs = httpx.get(f"{base_url}/docs", timeout=5.0)
        assert docs.status_code == 200, (
            f"/docs must return 200 over HTTP (Requirement 5.3); "
            f"got {docs.status_code}"
        )
    finally:
        _terminate(process)


# ---------------------------------------------------------------------------
# Frontend half — gated behind toolchain + installed-deps availability; skips
# with a clear reason when a full documented `next` startup cannot run here.
# ---------------------------------------------------------------------------


def _frontend_toolchain_available() -> tuple[bool, str]:
    """Whether the documented `next` commands can actually run in this env.

    Requires Node + npm on PATH and an installed `app/web/node_modules` (the
    README's `npm install` step). Returns (available, reason-if-not) so the skip
    message names precisely what is missing rather than a generic "skipped".
    """
    if shutil.which("node") is None:
        return False, "node is not on PATH"
    if shutil.which("npm") is None:
        return False, "npm is not on PATH"
    if not (WEB_DIR / "package.json").is_file():
        return False, f"missing {WEB_DIR / 'package.json'}"
    if not (WEB_DIR / "node_modules").is_dir():
        return False, (
            "app/web/node_modules is not installed; run `npm install` in "
            "app/web/ (README → Frontend) to enable the frontend startup check"
        )
    return True, ""


_FRONTEND_OK, _FRONTEND_REASON = _frontend_toolchain_available()


@pytest.mark.skipif(
    not _FRONTEND_OK,
    reason=(
        "documented frontend `next dev` startup cannot run in this environment: "
        f"{_FRONTEND_REASON}. The backend half of this integration test still "
        "verifies documented startup end-to-end over a real socket."
    ),
)
def test_documented_frontend_dev_server_serves_app_over_http():
    """The documented frontend dev command (`npm run dev` → `next dev`) serves the app.

    Follows `app/README.md` → "Frontend (dev)": from `app/web/`, `npm run dev`
    runs `next dev`. Launches it on a free port, binds a real socket, polls the
    app root over HTTP until ready, and asserts it answers 200, then tears the
    server down cleanly. Mirrors the backend half's real-socket approach; the
    backend half remains the mandatory /docs + /openapi.json assertion
    Requirement 5.3 centres on (Requirement 5.2, 5.3).
    """
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    # `next dev` rewrites tracked `tsconfig.json` (reformats it and injects the
    # `.next/types` include) and drops `next-env.d.ts` on startup. Snapshot the
    # tracked config and restore it in `finally` so this test never leaves a
    # modified committed file; the untracked `.next/` and `next-env.d.ts` are
    # gitignored (app/web/.gitignore) and removed here too.
    tsconfig_path = WEB_DIR / "tsconfig.json"
    tsconfig_before = (
        tsconfig_path.read_text(encoding="utf-8") if tsconfig_path.is_file() else None
    )

    # `npm run dev` == `next dev`; pass the free port through the npm script with
    # `--` so it reaches next. `--hostname` pins it to loopback for the probe.
    command = ["npm", "run", "dev", "--", "--port", str(port), "--hostname", "127.0.0.1"]
    process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        command,
        cwd=str(WEB_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,  # own process group so `next dev` child dies too
    )
    try:
        # `next dev` compiles the root route on first request; probe `/` and give
        # it the larger frontend readiness budget.
        _wait_until_ready(
            f"{base_url}/",
            process,
            label="frontend",
            timeout_s=FRONTEND_STARTUP_TIMEOUT_S,
        )
        response = httpx.get(f"{base_url}/", timeout=30.0)
        assert response.status_code == 200, (
            "documented frontend dev server (`npm run dev` -> `next dev`) must "
            f"serve the app root with 200 over HTTP (Requirement 5.2, 5.3); "
            f"got {response.status_code}"
        )
    finally:
        _terminate(process)
        # Leave the workspace as we found it: restore the tracked tsconfig and
        # drop the dev-generated artefacts `next dev` created.
        if tsconfig_before is not None:
            tsconfig_path.write_text(tsconfig_before, encoding="utf-8")
        shutil.rmtree(WEB_DIR / ".next", ignore_errors=True)
        (WEB_DIR / "next-env.d.ts").unlink(missing_ok=True)
