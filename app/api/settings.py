"""
Backend_App — env-driven configuration (S3-01a scaffold).

STUB: filled in by task 2.2 (Implement env-driven settings). This module reads
cross-service configuration from the environment ONLY — it hard-codes no origin
or host-address literal (Requirement 4.2, 6.5). Planned:

    CORS_ALLOW_ORIGINS  — comma-separated list of allowed CORS origins for the
                          Frontend_App, exposed as the resolved allowed-origins
                          list consumed by app.py's CORSMiddleware.
"""
