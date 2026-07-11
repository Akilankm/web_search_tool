# Operating Reference

## Runtime topology

```text
Azure ML Compute Instance
├── Docker Compose network
│   ├── agent:8000 (published to host as 8788)
│   └── browser:9000 (internal only)
├── inputs/private (mounted read-only into agent)
├── artifacts (mounted into both containers)
└── Azure ML notebook (thin client)
```

## Agent API

### `GET /health`
Returns agent status and browser-service health.

### `POST /v1/jobs`
Creates an asynchronous product evidence job.

### `GET /v1/jobs/{job_id}`
Returns stage and status.

### `GET /v1/jobs/{job_id}/result`
Returns the final dossier after `COMPLETED` or `REVIEW_REQUIRED`.

## Browser API

The browser API is internal to Compose and bearer-token protected.

### `GET /health`
Returns Chromium worker health.

### `POST /v1/evidence/acquire`
Accepts one already-discovered URL, product identity, and a bounded evidence plan. It returns rendered text, validated image/screenshot assets, browser-openability, multimodal scrapability, blockers, and an action trace.

## Evidence acceptance

A source is useful only when:

```text
browser/opening succeeds
AND rendered content is product-like
AND identity remains related to the requested product
AND text or visual evidence is extractable
```

Vision evidence supplements explicit structured/text evidence. It does not override stronger conflicting manufacturer or retailer specifications.

## Security boundary

- Agent owns SerpAPI and LLM credentials.
- Browser owns no SerpAPI or LLM credentials.
- Private feature files are mounted only into the agent.
- Browser navigation is limited to supplied candidate URLs and their asset requests.
- No Docker socket is mounted into either container.
- Both services run as non-root users with `no-new-privileges`.
- Browser action and asset limits are bounded.
- Access blockers become review states instead of bypass attempts.

## Azure ML prerequisites

The Compute Instance must permit:

```bash
docker info
docker compose version
docker ps
```

Outbound access is required for SerpAPI, the approved LLM endpoint, retailer/manufacturer pages, image CDNs, and container-image pulls.

## Job stages

```text
VALIDATING_INPUT
SEARCHING
REQUESTING_BROWSER_EVIDENCE
RUNNING_MULTIMODAL_REASONING
WRITING_OUTPUTS
COMPLETED | REVIEW_REQUIRED | FAILED
```

## Artifacts

```text
artifacts/<row_id>/
├── orchestrated_result.json
├── result.json
├── candidates.csv
├── feature_evidence.csv
├── review.md
└── CAND-*/browser/
    ├── browser_result.json
    ├── rendered_text.md
    ├── final_page.html
    ├── browser_actions.json
    ├── visual_manifest.json
    ├── images/
    └── screenshots/
```
