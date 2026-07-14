# Azure ML Operations Runbook

## Runtime topology

```text
Azure ML Compute Instance
├── Docker Compose
│   ├── agent:8000   -> host 127.0.0.1:8788
│   └── browser:9000 -> internal Compose network only
├── inputs/private/  -> read-only feature schemas
├── data/artifacts/  -> shared evidence and traces
└── notebooks/01_run_product_evidence.ipynb
```

The notebook is an API client. The agent owns search, LLM planning, deterministic validation, final selection, and outputs. The browser owns isolated Chromium sessions and safe action execution.

## Fresh setup

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool
cp .env.example .env
chmod 600 .env
# Replace SerpAPI and LLM placeholders.
mkdir -p inputs/private
cp /secure/location/toy_features.json inputs/private/toy_features.json
./scripts/azureml_startup.sh
```

For mounted storage that cannot preserve mode `600`:

```bash
./scripts/azureml_startup.sh --allow-insecure-env-permissions
```

## Search campaign

Every product uses exactly three SerpAPI organic searches:

1. requested retailer in requested country, or primary country search;
2. other retailers in requested country;
3. global fallback.

Private feature names are not included in search queries.

## Agentic browser campaign

After static preflight and candidate admission, every eligible deduplicated URL in the bounded investigation pool receives a separate browser session.

```text
Start isolated session
  -> browser returns screenshot, text, elements and images
  -> LLM selects one safe action
  -> browser executes it
  -> browser returns updated state
  -> repeat
  -> finish evidence bundle
```

Default controls:

```env
PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_REQUIRE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_MAX_AGENTIC_CANDIDATES=18
PRODUCT_HARNESS_AGENTIC_MAX_TURNS_PER_CANDIDATE=10
PRODUCT_HARNESS_AGENTIC_MAX_ACTIONS_PER_CANDIDATE=20
```

Increasing these values increases browser runtime and LLM cost.

## Progress stages

```text
VALIDATING_INPUT
SEARCHING
AGENTIC_BROWSER_INVESTIGATION
VALIDATING_PRIMARY_URL
WRITING_OUTPUTS
COMPLETED or REVIEW_REQUIRED
```

Candidate progress includes turn number and selected action, for example:

```text
CAND-003 | turn 2/10 | CLICK | retailer.example
CAND-003 | turn 3/10 | INSPECT_IMAGE | retailer.example
CAND-003 | COMPLETED | turns=4 | actions=3 | openable=True | scrapable=True
```

## Final acceptance

`primary_url` is populated only when one investigated URL is:

- browser-openable and not access-blocked;
- a rendered product-detail page;
- the exact requested product and variant;
- text-scrapable;
- complete for every requested feature on the same URL;
- free of feature conflicts;
- durable and non-expiring.

The LLM investigation dossier is explanatory. `primary_url_acceptance.json` is authoritative.

## Result inspection

```python
result["search"]
result["agentic_browser"]
result["candidate_investigations"]
result["browser_evidence"]
result["feature_assessments"]
result["primary_url_acceptance"]
```

## Artifacts

```text
data/artifacts/<row_id>/
├── orchestrated_result.json
├── primary_url_acceptance.json
└── CAND-###/agentic/
    ├── investigation.json
    ├── latest_observation.json
    ├── browser_actions.json
    ├── browser_result.json
    ├── rendered_text.md
    ├── final_page.html
    ├── observations/
    ├── images/
    └── screenshots/
```

Inspect:

```bash
find data/artifacts -maxdepth 8 -type f | sort
```

## Health and logs

```bash
docker compose ps
python scripts/wait_for_stack.py
docker compose logs -f --tail=200 agent browser
```

The health response must report:

```text
three_stage_contract_enforced=true
serpapi_request_limit=3
agentic_browser_contract_enforced=true
llm_configured=true
```

## Restart after an update

```bash
docker compose down
git checkout master
git pull origin master
./scripts/azureml_startup.sh --allow-insecure-env-permissions
```

Restart the notebook kernel after rebuilding.

## Failure guide

| Symptom | Meaning / action |
|---|---|
| Agentic browser flag must be true | Refresh `.env` from `.env.example` |
| LLM configuration missing | Provide approved endpoint, deployment, version and key |
| Candidate investigation failed | Inspect `CAND-###/agentic/investigation.json` and service logs |
| CAPTCHA/login/access wall | Candidate is rejected; no bypass is attempted |
| `REVIEW_REQUIRED` | No investigated candidate passed all deterministic gates |
| URL rejected for signature/TTL | Use a canonical product page |

## Validation

```bash
python scripts/validate_environment.py --env-file .env
python scripts/preflight_azureml.py --skip-docker --skip-port
python -m compileall -q src scripts
python -m json.tool notebooks/01_run_product_evidence.ipynb >/dev/null
python -m pytest -q
docker compose config --quiet
```
