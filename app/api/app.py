"""
Backend_App — FastAPI application entry point (S3-01a scaffold).

STUB: filled in by task 4 (Implement the FastAPI app: routes, delegation, CORS,
error mapping). This module will construct a single `FastAPI()` instance and
register exactly the six frozen S2-08 routes as thin delegating handlers:

    POST /runs
    GET  /runs/{run_id}/results
    GET  /runs/{run_id}/sites/{cell_id}
    GET  /runs/{run_id}/exclusions
    POST /scenario-comparison
    GET  /data-quality

It maps each route to the matching pure operation in `pipeline.service`,
serialises the returned dataclass, installs env-driven CORS
(`settings.get_cors_allow_origins()`), and centralises the exception -> HTTP
code mapping (CONTRACT.md §6). It holds NO decision logic — no weights, no
criteria list, no normalisation, ranking, or threshold arithmetic
(Requirement 2.4, combined-sprint AC4).

Run (dev):  uvicorn app:app --reload --port 8000   (from app/api/)
"""
