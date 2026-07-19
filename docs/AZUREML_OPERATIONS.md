# Azure ML Operations Runbook

## Supported fresh-clone flow

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool
cp .env.example .env
# Edit only the real SerpAPI and enterprise LLM credential values.
./scripts/azureml_startup.sh
```

After the script reports `Product evidence platform is ready`, open only:

```text
notebooks/01_run_product_evidence.ipynb
```

The committed default feature schema is:

```text
inputs/private/toy_features.json
```

## Runtime topology

```text
Azure ML Compute Instance
├── Docker Compose
│   ├── agent:8000   -> host 127.0.0.1:8788
│   └── browser:9000 -> internal Compose network only
├── inputs/private/toy_features.json
├── data/runtime/stack_health.json
├── data/artifacts/<row_id>/
└── notebooks/01_run_product_evidence.ipynb
```

The notebook is a thin API client. Search, scraping, browser evidence, belief updates, feature assessment, source selection, and artifact writing execute inside the local agent/browser stack.

The agent starts through:

```text
src.product_evidence_harness.agent_service.app:app
```

The entrypoint applies the complete compatibility patch stack before creating the orchestrator and emits the runtime contract directly from `/health`.

## Final runtime contract

The supported notebook and agent version is:

```text
belief-url-resolution-v5-manufacturer-primary
```

The health response must include:

```text
status=healthy
runtime_contract_version=belief-url-resolution-v5-manufacturer-primary
manufacturer_first_primary_url=true
belief_driven_product_resolution=true
mandatory_review_url_delivery=true
deterministic_browser_fallback_on_llm_error=true
notebook_self_healing_runtime=true
compatibility_patches_applied=true
agent_entrypoint=src.product_evidence_harness.agent_service.app:app
three_stage_contract_enforced=true
serpapi_request_limit=3
agentic_browser_contract_enforced=true
llm_configured=true
browser_service.agentic_tools=true
```

The notebook rejects an agent that is healthy-looking but does not expose the exact version and capabilities.

## Startup modes

### Standard build and restart

```bash
./scripts/azureml_startup.sh
```

Use after a normal pull or `.env` change when Docker images are not known to be stale.

### Clean build and stale-image recovery

```bash
./scripts/azureml_startup.sh --clean-build
```

This mode:

1. validates credentials and production controls;
2. removes stale containers from the fixed Compose project;
3. verifies that the agent port is free;
4. runs `docker compose build --no-cache agent browser`;
5. recreates both services;
6. waits for SerpAPI, LLM, browser, and agent health;
7. verifies the exact runtime version and manufacturer-first capability;
8. writes `data/runtime/stack_health.json`.

Use this mode for:

- `STALE_AGENT_IMAGE`;
- a missing or legacy runtime contract;
- a notebook/agent mismatch;
- a missing `manufacturer_first_primary_url` capability;
- a Docker agent built from another repository checkout.

### Reuse known-current images

```bash
./scripts/azureml_startup.sh --no-build
```

Do not use `--no-build` for stale-image recovery. It is valid only when local images are known to match the current checkout.

## Self-healing notebook behavior

The notebook defaults to:

```python
AUTO_RECOVER_PLATFORM = True
CLEAN_BUILD_ON_RECOVERY = True
```

The readiness cell calls `ensure_platform_ready`. When port `8788` is unavailable, unhealthy, stale, or missing required capabilities, it invokes the startup script from the same repository checkout with `--clean-build`, streams startup logs, and rechecks health.

This occurs before `submit_product`, so recovery consumes no paid SerpAPI request.

Disable automatic recovery only for intentional manual operations:

```python
AUTO_RECOVER_PLATFORM = False
```

or:

```env
PRODUCT_HARNESS_NOTEBOOK_AUTO_RECOVER_PLATFORM=false
```

## What startup validates

- `.env` existence and permission policy;
- real SerpAPI and enterprise LLM values;
- committed feature schemas;
- Docker and Compose availability;
- non-root container UID/GID;
- host-port availability;
- exact three-credit adaptive search controls;
- belief-driven product resolution;
- manufacturer-first primary URL selection;
- mandatory review URL delivery;
- deterministic browser fallback after planning LLM failure;
- explicit compatibility-patch bootstrap;
- browser-service agentic tools;
- exact runtime-contract version.

## Manual readiness verification

```bash
docker compose ps
cat data/runtime/stack_health.json
curl -sS http://127.0.0.1:8788/health | python -m json.tool
```

The health payload is the authoritative runtime check.

## Required configuration

At minimum, replace:

```env
SERPAPI_API_KEY=<real-key>
LLM_API_KEY=<real-key>
LLM_API_VERSION=<supported-version>
LLM_ENDPOINT=<approved-https-endpoint>
LLM_DEPLOYMENT=<vision-capable-deployment>
```

Equivalent `AZURE_OPENAI_*` variables are accepted.

Recommended production controls:

```env
PRODUCT_HARNESS_NOTEBOOK_AUTO_RECOVER_PLATFORM=true
PRODUCT_HARNESS_NOTEBOOK_CLEAN_BUILD_ON_RECOVERY=true
PRODUCT_HARNESS_ALLOW_DETERMINISTIC_BROWSER_FALLBACK_ON_LLM_ERROR=true
PRODUCT_HARNESS_MAX_SERPAPI_CREDITS=3
PRODUCT_HARNESS_MAX_FULL_SCRAPES=6
PRODUCT_HARNESS_MAX_SCRAPES_PER_DOMAIN=2
PRODUCT_HARNESS_REJECT_EXPIRING_URLS=true
```

## Final product workflow

```text
MAIN_TEXT + COUNTRY_CODE
→ offline product interpretation
→ competing hypotheses and uncertainty metrics
→ Credit 1: manufacturer_primary — official manufacturer/brand product page
→ Credit 2: requested_retailer_country when retailer_name exists, otherwise country_alternative
→ Credit 3: global_fallback — global manufacturer-or-retailer fallback
→ bounded scrape and browser evidence
→ belief update
→ strict identity, feature, openability, scrapability, and durability gates
→ manufacturer-first authority ranking
→ primary_url + manufacturer_url + retailer_url
```

A manufacturer page becomes primary only after every mandatory gate passes. A retailer becomes primary when the manufacturer page is absent, inaccessible, incomplete, non-product, transient, or the wrong product/variant.

A browser-planning LLM error, including `403 Forbidden`, falls back to deterministic rendered-page acquisition. Strict gates remain authoritative.

## Stable output fields

```text
primary_url
primary_url_role
manufacturer_url
retailer_url
source_selection
primary_url_acceptance
url_delivery
```

The authority decision is written to:

```text
data/artifacts/<row_id>/source_selection.json
```

## Failure behavior

| Failure | Behavior |
|---|---|
| `.env` missing | Creates it from `.env.example`, stops, and asks for credentials |
| Placeholder credential | Fails before Docker build with the exact field |
| Feature schema missing or malformed | Fails before Docker build |
| Stale Compose containers | Removes and recreates them |
| Agent image built from older code | Notebook or startup performs a no-cache rebuild |
| Runtime contract mismatch | Startup/readiness fails before product submission |
| Manufacturer-first capability missing | Readiness fails before product submission |
| Compatibility bootstrap missing | Agent `/health` returns 503 |
| Agentic browser LLM returns 403 | Deterministic browser acquisition continues; strict gates still decide URL status |
| No safe direct product URL | Run fails with `MANDATORY_PRODUCT_URL_NOT_FOUND` |
| Browser/agent never becomes healthy | Startup prints Compose state and recent logs |

## Notebook workflow

1. open `notebooks/01_run_product_evidence.ipynb`;
2. run the readiness cell;
3. allow self-healing recovery when required;
4. verify `platform_readiness_df` and `manufacturer_first_primary_url=true`;
5. replace the product input;
6. set `RUN_SINGLE_PRODUCT = True`;
7. run the product cell;
8. inspect `primary_url`, `primary_url_role`, `manufacturer_url`, and `retailer_url`;
9. inspect `source_selection_df` and `source_selection.json`;
10. open the final URLs in a browser;
11. inspect the workbook when the result is `REVIEW_REQUIRED`.

Kernel restart is normally unnecessary after container-only recovery because the readiness cell evicts stale repository modules. Restart only when Azure ML itself retains an older notebook state.

## Logs and shutdown

```bash
docker compose logs -f --tail=200 agent browser
docker compose down
```

Stopping containers does not delete `data/artifacts` or `data/runtime`.

## Development validation

```bash
bash -n scripts/azureml_startup.sh
python scripts/wait_for_stack.py --help
python -m compileall -q src scripts
python -m json.tool inputs/private/toy_features.json >/dev/null
python -m json.tool notebooks/01_run_product_evidence.ipynb >/dev/null
PYTHONPATH=src pytest -q
docker compose config --quiet
```
