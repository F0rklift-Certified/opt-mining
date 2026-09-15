# Backend_App (FastAPI) image — S3-01a Application Shell Scaffold.
#
# Slim Python base. Installs the decision engine (repo `pipeline/` package) plus
# the API's own dependencies, copies the API source, and runs uvicorn.
#
# IMPORTANT — build context is the REPO ROOT, not app/api/.
# The API imports `pipeline.service`, so the engine package (`pipeline/`) and the
# engine's dependency manifest (`requirements.txt`) — both of which live at the
# repository root — must be inside the build context. The Dockerfile therefore
# expects paths relative to the repo root:
#     docker build -f app/api/Dockerfile -t optmining-api .
# The Compose service (task 7.3) sets:
#     build:
#       context: ..            # repo root (app/ is one level down)
#       dockerfile: app/api/Dockerfile
#
# Python is pinned to 3.13: the engine explicitly does NOT support 3.14 (the
# S1-02 grid builder emits degenerate zero-area cells on CPython 3.14.x — see
# pyproject.toml `requires-python = ">=3.13,<3.14"` and requirements.txt). Keep
# this base image on the 3.13 line to match what CI verifies.
FROM python:3.13-slim

# Fail fast, no stale bytecode, unbuffered logs for container-friendly output.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# --- Dependencies -----------------------------------------------------------
# Install the engine's runtime dependencies first (from the repo-root manifest),
# then the API's own dependencies (fastapi, uvicorn[standard], ...). Copying the
# manifests before the source keeps this layer cached across source-only edits.
COPY requirements.txt ./engine-requirements.txt
RUN pip install -r engine-requirements.txt

COPY app/api/requirements.txt ./api-requirements.txt
RUN pip install -r api-requirements.txt

# --- Application source -----------------------------------------------------
# The decision engine package. Making it importable as `pipeline.service` is the
# whole point: the API delegates every operation to it and adds no decision
# logic of its own (combined-sprint AC4 / CONTRACT.md §1). It is placed on the
# working directory (which is on PYTHONPATH via WORKDIR below) rather than
# pip-installed because the repo pyproject.toml declares no build-system.
COPY pipeline ./pipeline

# The FastAPI application itself.
COPY app/api ./app/api

# `app.py` lives in app/api; uvicorn is run from there so `app:app` resolves.
WORKDIR /srv/app/api

# Put the engine root on the import path so `import pipeline.service` works
# regardless of the current working directory.
ENV PYTHONPATH=/srv

EXPOSE 8000

# Bind to all interfaces so the published host port / Compose network can reach
# it. Host port mapping and env-driven URLs are handled by Compose (task 7.3).
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
