"""
S3-01a structural test for the Compose_Stack.

Docker Compose and the Dockerfiles are declarative infrastructure, so this is a
structural check (design §Testing Strategy → "Compose config (structural)"),
not a property test. It pins the invariants Requirement 6 places on
``app/docker-compose.yml`` and the two Dockerfiles so a drift — a dropped
service, a removed ``depends_on``, a hard-coded host address, a swapped base
image — fails in CI rather than silently at ``docker compose up``.

Every assertion is grounded in the committed files:

* ``app/docker-compose.yml`` — two services ``api`` and ``web``.
* ``app/api/Dockerfile``     — slim Python base, repo-root build context.
* ``app/web/Dockerfile``     — Node base.

Validates: Requirements 6.1, 6.2, 6.4, 6.5, 6.6.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

# --- Paths (repo-root relative; conftest.py puts the repo root on sys.path) ---
APP_DIR = Path(__file__).resolve().parents[2] / "app"
COMPOSE_PATH = APP_DIR / "docker-compose.yml"
API_DOCKERFILE = APP_DIR / "api" / "Dockerfile"
WEB_DOCKERFILE = APP_DIR / "web" / "Dockerfile"


@pytest.fixture(scope="module")
def compose() -> dict:
    """Parse the committed Compose file as YAML (Requirement 6.1)."""
    assert COMPOSE_PATH.is_file(), f"missing Compose file: {COMPOSE_PATH}"
    with COMPOSE_PATH.open(encoding="utf-8") as handle:
        parsed = yaml.safe_load(handle)
    assert isinstance(parsed, dict), "docker-compose.yml must parse to a mapping"
    return parsed


@pytest.fixture(scope="module")
def services(compose: dict) -> dict:
    services = compose.get("services")
    assert isinstance(services, dict), "docker-compose.yml must define a `services` mapping"
    return services


def _env_list(service: dict) -> list[str]:
    """Return a service's `environment` entries as a list of `KEY=value` strings.

    Compose accepts both the list form (`- KEY=value`) and the mapping form
    (`KEY: value`); normalise to the list form so assertions are uniform.
    """
    environment = service.get("environment", [])
    if isinstance(environment, dict):
        return [f"{key}={value}" for key, value in environment.items()]
    assert isinstance(environment, list), "`environment` must be a list or mapping"
    return [str(entry) for entry in environment]


def _ports(service: dict) -> list[str]:
    ports = service.get("ports", [])
    assert isinstance(ports, list), "`ports` must be a list"
    return [str(entry) for entry in ports]


# ---------------------------------------------------------------------------
# Requirement 6.1 — parses and defines both `web` and `api` services
# ---------------------------------------------------------------------------


def test_compose_parses_and_defines_web_and_api(services: dict):
    assert set(services) >= {"web", "api"}, (
        f"expected `web` and `api` services, found: {sorted(services)}"
    )


# ---------------------------------------------------------------------------
# Requirement 6.4 — web.depends_on includes api
# ---------------------------------------------------------------------------


def test_web_depends_on_includes_api(services: dict):
    depends_on = services["web"].get("depends_on")
    # Compose allows the short list form and the long mapping form.
    if isinstance(depends_on, dict):
        dependencies = set(depends_on)
    else:
        assert isinstance(depends_on, list), "web.depends_on must be a list or mapping"
        dependencies = set(depends_on)
    assert "api" in dependencies, (
        f"web must depend_on api (Requirement 6.4); got: {sorted(dependencies)}"
    )


# ---------------------------------------------------------------------------
# Requirement 6.6 — both services publish documented host ports via env
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "service_name, published_form",
    [
        ("api", "${API_HOST_PORT:-8000}:8000"),
        ("web", "${WEB_HOST_PORT:-3000}:3000"),
    ],
)
def test_services_publish_documented_host_ports_via_env(
    services: dict, service_name: str, published_form: str
):
    ports = _ports(services[service_name])
    assert published_form in ports, (
        f"{service_name} must publish its host port via env as "
        f"'{published_form}' (Requirement 6.6); got: {ports}"
    )


# ---------------------------------------------------------------------------
# Requirement 6.5 — all cross-service URLs are ${ENV...} references, not literals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "service_name, env_key, expected_default",
    [
        # Browser -> API base URL (frontend build/runtime).
        ("web", "NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000"),
        # In-network web-container -> api-container URL (Compose service DNS).
        ("web", "API_INTERNAL_URL", "http://api:8000"),
        # API's allowed CORS origins (the web app origin).
        ("api", "CORS_ALLOW_ORIGINS", "http://localhost:3000"),
    ],
)
def test_cross_service_urls_are_env_references_with_documented_defaults(
    services: dict, service_name: str, env_key: str, expected_default: str
):
    entries = _env_list(services[service_name])
    matching = [entry for entry in entries if entry.startswith(f"{env_key}=")]
    assert matching, (
        f"{service_name} must set {env_key} via environment (Requirement 6.5); "
        f"got env: {entries}"
    )
    value = matching[0].split("=", 1)[1]
    # The value must be a ${ENV:-default} reference, never a bare literal URL.
    expected = f"${{{env_key}:-{expected_default}}}"
    assert value == expected, (
        f"{service_name}.{env_key} must be the env reference '{expected}', "
        f"not a literal; got: '{value}'"
    )
    assert value.startswith("${") and value.endswith("}"), (
        f"{service_name}.{env_key} must be a ${{ENV...}} reference (Requirement 6.5)"
    )


def test_no_bare_host_url_literal_in_env_values(services: dict):
    """No cross-service URL value is a bare literal (all are ${ENV...} refs).

    Any http(s) URL that appears in an `environment` value must sit inside a
    ${...} substitution (as its documented default), never as a standalone
    literal assignment like `KEY=http://host:port` (Requirement 6.5).
    """
    bare_url = re.compile(r"=\s*https?://")
    offenders: list[str] = []
    for service_name in ("api", "web"):
        for entry in _env_list(services[service_name]):
            key, _, value = entry.partition("=")
            if bare_url.search(entry) and not value.strip().startswith("${"):
                offenders.append(f"{service_name}: {entry}")
    assert not offenders, (
        "cross-service URLs must be ${ENV...} references, not literals "
        f"(Requirement 6.5); offenders: {offenders}"
    )


# ---------------------------------------------------------------------------
# Requirement 6.5 — api uses the repo-root build context
# ---------------------------------------------------------------------------


def test_api_uses_repo_root_build_context(services: dict):
    build = services["api"].get("build")
    assert isinstance(build, dict), (
        "api.build must be the long form so the repo-root context is explicit"
    )
    assert build.get("context") == "..", (
        f"api build context must be the repo root ('..'); got: {build.get('context')!r}"
    )
    assert build.get("dockerfile") == "app/api/Dockerfile", (
        "api must build from app/api/Dockerfile; "
        f"got: {build.get('dockerfile')!r}"
    )


# ---------------------------------------------------------------------------
# Requirement 6.2 — api/Dockerfile slim Python base, web/Dockerfile Node base
# ---------------------------------------------------------------------------


def _from_images(dockerfile: Path) -> list[str]:
    assert dockerfile.is_file(), f"missing Dockerfile: {dockerfile}"
    images: list[str] = []
    for raw in dockerfile.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.upper().startswith("FROM "):
            # `FROM <image> [AS <stage>]` — take the image reference.
            images.append(line.split()[1])
    assert images, f"no FROM instruction found in {dockerfile}"
    return images


def test_api_dockerfile_uses_slim_python_base():
    images = _from_images(API_DOCKERFILE)
    assert all(image.startswith("python:") for image in images), (
        f"api/Dockerfile must use a Python base image (Requirement 6.2); got: {images}"
    )
    assert any("slim" in image for image in images), (
        f"api/Dockerfile must use a *slim* Python base (Requirement 6.2); got: {images}"
    )


def test_web_dockerfile_uses_node_base():
    images = _from_images(WEB_DOCKERFILE)
    assert all(image.startswith("node:") for image in images), (
        f"web/Dockerfile must use a Node base image (Requirement 6.2); got: {images}"
    )
