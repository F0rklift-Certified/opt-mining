# S3-10 demo and release candidate

The full technical demonstration now passes on the repaired NSW baseline.
This is a **pre-review release candidate**, not client acceptance or a claim
that the demonstrated stack is already on `main`. Upstream PRs #19–#24 and
Checkpoint D remain explicit review gates.

## Review package

- [Demo script](demo-script.md): Guidance §10 walkthrough, real examples and weights.
- [Limitations](limitations.md): concise screening assumptions and remaining Should items.
- [Readiness](readiness.json): AC1–AC12 evidence and separate human review gates.
- [HTTP/reference rehearsal](rehearsal.json): input hash, scenarios, contributions,
  unscored exclusion, rank deltas and honest reference anomalies.
- [Verification](verification.md): exact local checks, Docker images and browser proof.
- [Baseline audit](baseline-change.json) and [fixed snapshot review](../../DATA/scoring/metadata/s3_10_snapshot_review.md):
  authorised coverage/boundary changes, unchanged formula/weights and new literal pins.
- [Security upgrade](security-upgrade.md): independent patched frontend migration.
- [Browser E2E record](browser-e2e.json), [E2E screenshot](final-demo.png) and
  [Chrome walkthrough](chrome-final-demo.png).

## Reproduce from this candidate branch

`main` does not yet contain all prerequisites. Check out the candidate branch.
Docker Desktop/Engine with Compose installs independent Python 3.13 and Node
24 images; the web image uses the committed npm lockfile.

```bash
docker compose -f app/docker-compose.yml up --build
```

Open <http://localhost:3000> and <http://localhost:8000/docs>. See
[app/README.md](../../app/README.md) for setup, CORS, source provenance, equations,
architecture, troubleshooting and manual/E2E verification.

For an independent local rehearsal, the tested command was:

```bash
API_HOST_PORT=18010 WEB_HOST_PORT=13010 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:18010 \
CORS_ALLOW_ORIGINS=http://localhost:13010 \
docker compose -p opt-mining-s3-10 -f app/docker-compose.yml up --build -d

NEXT_PUBLIC_API_BASE_URL=http://localhost:18010 \
CORS_ALLOW_ORIGINS=http://localhost:13010 python3 app/smoke_test.py

NEXT_PUBLIC_API_BASE_URL=http://localhost:18010 \
CORS_ALLOW_ORIGINS=http://localhost:13010 \
python3 app/rehearse_demo.py --external-sanity --require-final \
  --output outputs/s3-10-rehearsal.json
```

The reference comparison needs Python 3.13 with root `requirements.txt`
installed. HTTP-only checking uses the standard library. The report distinguishes
technical success from final acceptance: exit 1 is a technical failure; with
`--require-final`, exit 2 records unresolved merge/client gates. Do not clear
those gates merely because a test or GitHub check turns green.

In `app/web`, after `npm ci` and `npx playwright install chromium`:

```bash
E2E_WEB_URL=http://localhost:13010 E2E_API_URL=http://localhost:18010 npm run test:e2e
```

The browser test calls the real Compose API, without mocked HTTP responses.
It checks map drawing/selection, filtering without rerunning, excluded detail,
actual explanation phrases, scenario comparison and invalid top-N response.
CI builds/boots the stack and preserves its browser/report evidence.

## Review and release order

1. Maintain the existing upstream checkpoint/backend → web review sequence.
2. Review the separate S3-10 baseline and service consistency repairs first.
3. Review the map/detail/comparison UI, then the independent security upgrade.
   Scoped PRs: [baseline #25](https://github.com/F0rklift-Certified/opt-mining/pull/25),
   [service #26](https://github.com/F0rklift-Certified/opt-mining/pull/26),
   [web #27](https://github.com/F0rklift-Certified/opt-mining/pull/27),
   [security #28](https://github.com/F0rklift-Certified/opt-mining/pull/28).
4. Review the small final validation/docs package; rerun the recorded gates on
   the intended merged release commit. Do not merge the entire stack through
   one giant final PR.
5. The annotated `v0.1.0-rc.1` tag identifies the tested **pre-review
   candidate**, not an approved production release. Never move a published tag.
6. Present the live walkthrough to Iman Rahimi for Checkpoint D and record
   actual feedback/acceptance. Then close the named review gates.

Browser CSV export and a dedicated web sanity-check visualisation remain
Should items. Multi-worker deployment and commercial styling are not claimed.
The repaired data is still screening-level. See limitations before using ranks.
