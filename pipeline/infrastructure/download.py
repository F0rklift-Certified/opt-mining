"""
Infrastructure download stage — validate pre-downloaded file presence.

Infrastructure data is already pre-downloaded from the GA service.
This stage verifies all expected files are present and reports any gaps.

Importable entry point:
    from pipeline.infrastructure.download import run
    result = run(verbose=False)

Output:
    (no new files — presence check only)
"""

from __future__ import annotations

from . import config
from ..common.geo import human_bytes


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(verbose: bool = False) -> dict:
    """
    Validate that pre-downloaded infrastructure files are present.

    Returns a summary dict with present/missing counts.
    """
    present, missing = [], []
    for rel in config.EXPECTED_FILES:
        path = config.INFRA_DIR / rel
        if path.exists():
            present.append(rel)
            if verbose:
                print(f"      [ok] {rel} ({human_bytes(path.stat().st_size)})")
        else:
            missing.append(rel)
            print(f"      [MISSING] {rel}")

    if missing:
        print(f"    WARNING: {len(missing)} file(s) missing")
    else:
        print(f"    All {len(present)} files present")

    return {"present": len(present), "missing": missing}
