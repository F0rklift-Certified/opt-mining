"""Exercise the running web/API stack, including CORS and materialised data.

Run from the repository root: python app/smoke_test.py
Set NEXT_PUBLIC_API_BASE_URL and CORS_ALLOW_ORIGINS for non-default ports.
Uses only Python's standard library; failures exit nonzero in CI.
"""

import json
import os
import time
import urllib.error
import urllib.request


def main():
    api = os.environ.get("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000").rstrip("/")
    web = os.environ.get("CORS_ALLOW_ORIGINS", "http://localhost:3000").split(",")[0].strip()

    for url in (api + "/openapi.json", web):
        deadline = time.monotonic() + 90
        while True:
            try:
                with urllib.request.urlopen(url, timeout=5) as response:
                    assert response.status == 200
                break
            except (OSError, urllib.error.URLError):
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"Service did not become ready: {url}")
                time.sleep(1)

    preflight = urllib.request.Request(
        api + "/runs", method="OPTIONS", headers={
            "Origin": web,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    with urllib.request.urlopen(preflight, timeout=10) as response:
        assert response.headers.get("Access-Control-Allow-Origin") == web

    def request(path, payload=None):
        req = urllib.request.Request(
            api + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Origin": web, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=90) as response:
            assert response.status == 200
            assert response.headers.get("Access-Control-Allow-Origin") == web
            return json.load(response)

    quality = request("/data-quality")
    assert quality["checks"], "Validation metadata must be available"
    # A flagged quality result is valid data and must not be hidden as a failure.
    run = request("/runs", {"scenario": "wind_led"})
    prefix = "/runs/" + run["run_id"]
    rows = request(prefix + "/results?top_n=5")
    assert rows, "Packaged scenario must return ranked cells"
    detail = request(prefix + "/sites/" + rows[0]["cell_id"])
    assert detail["cell_id"] == rows[0]["cell_id"]
    assert detail["features"] and detail["explanation"]
    exclusions = request(prefix + "/exclusions")
    assert exclusions, "Packaged exclusions must be readable"
    comparison = request("/scenario-comparison", {
        "scenario_a": "wind_led", "scenario_b": "grid_led",
    })
    assert comparison["rows"]
    print(f"PASS: web, CORS and all six operations; run={run['run_id']}; "
          f"quality_checks={len(quality['checks'])}; returned_ranks={len(rows)}")


if __name__ == "__main__":
    main()
