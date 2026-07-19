# Azure ML Operations Runbook

## Supported fresh-clone flow

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool
cp .env.example .env
# Edit only the real SerpAPI and LLM credential values.
./scripts/azureml_startup.sh
```

After the script reports `Product evidence platform is ready`, open:

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

The notebook is an API client. Search, scraping, browser evidence, belief updates, URL selection, and artifact writing run inside the local agent/browser stack.

## Startup modes

### Standard build and restart

```bash
./scripts/azureml_startup.sh
```

Use after pulling normal code changes or modifying `.env`.

### Clean stale-image recovery

```bash
./scripts/azureml_startup.sh --clean-build
```

This mode:

1. validates credentials and production controls;
2. removes stale containers from the Compose project;
3. verifies that the agent port is free;
4. runs `docker compose build --no-cache agent browser`;
5. recreates both services;
6. waits for healthy SerpAPI, LLM, browser, and agent configuration;
7. verifies the exact notebook/agent runtime contract;
8. writes `data/runtime/stack_health.json`.

Use this mode for `STALE_AGENT_IMAGE`, a missing runtime contract, or when the notebook was updated but Docker still serves older code.

### Reuse known-current images

```bash
./scripts/azureml_startup.sh --no-build
```

Do not use `--no-build` for stale-image recovery. `--clean-build` and `--no-build` are mutually exclusive.

## Self-healing notebook behavior

The notebook defaults to:

```python
AUTO_RECOVER_PLATFORM = True
CLEAN_BUILD_ON_RECOVERY = True
```

The first cell calls `ensure_platform_ready`. When port `8788` is unavailable, unhealthy, legacy, or missing required browser capabilities, the cell invokes the startup script from the same repository checkout with `--clean-build`, streams startup logs, and rechecks health.

This happens before `submit_product`, so no paid SerpAPI request is consumed during recovery.

Disable automatic recovery only for manual operations:

```python
AUTO_RECOVER_PLATFORM = False
```

or:

```env
PRODUCT_HARNESS_NOTEBOOK_AUTO_RECOVER_PLATFORM=false
```

## What startup validates

The startup contract covers:

- `.env` existence and permission policy;
- real SerpAPI and enterprise LLM values;
- committed feature schemas;
- Docker and Compose availability;
- non-root container UID/GID;
- host-port availability;
- three-credit adaptive search controls;
- belief-driven product resolution;
- mandatory review URL delivery;
- deterministic browser fallback when the agentic LLM fails;
- browser service agentic tools;
- exact runtime-contract version.

The current health response must include:

```text
status=healthy
runtime_contract_version=belief-url-resolution-v3-self-healing
belief_driven_product_resolution=true
mandatory_review_url_delivery=true
deterministic_browser_fallback_on_llm_error=true
notebook_self_healing_runtime=true
three_stage_contract_enforced=true
serpapi_request_limit=3
agentic_browser_contract_enforced=true
llm_configured=true
browser_service.agentic_tools=true
```

## Manual readiness verification

```bash
docker compose ps
cat data/runtime/stack_health.json
curl -sS http://127.0.0.1:8788/health | python -m json.tool
```

The startup waiter rejects a healthy-looking but stale agent immediately instead of allowing the notebook to submit against an incompatible runtime.

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

Recommended production controls are already supplied in `.env.example`:

```env
PRODUCT_HARNESS_NOTEBOOK_AUTO_RECOVER_PLATFORM=true
PRODUCT_HARNESS_NOTEBOOK_CLEAN_BUILD_ON_RECOVERY=true
PRODUCT_HARNESS_ALLOW_DETERMINISTIC_BROWSER_FALLBACK_ON_LLM_ERROR=true
PRODUCT_HARNESS_MAX_SERPAPI_CREDITS=3
PRODUCT_HARNESS_MAX_FULL_SCRAPES=6
```

## Product workflow

```text
MAIN_TEXT + COUNTRY_CODE
→ offline product interpretation
→ competing hypotheses
→ requested retailer, when provided
→ alternative retailer within requested country
→ global fallback
→ bounded scraping and browser evidence
→ belief update
→ mandatory browser-openable product URL
```

A browser-planning LLM error, including `403 Forbidden`, falls back to deterministic rendered-page acquisition. The strict identity, feature, openability, scrapability, and durability gates remain authoritative.

## Failure behavior

| Failure | Behavior |
|---|---|
| `.env` missing | Creates it from `.env.example`, stops, and asks for credentials |
| Placeholder credential | Fails before Docker build with the exact field |
| Feature schema missing or malformed | Fails before Docker build |
| Stale Compose containers | Removes and recreates them |
| Stale agent image | Notebook or startup performs a no-cache rebuild |
| Runtime contract mismatch after startup | Startup fails immediately with expected/running versions |
| Agentic browser LLM returns 403 | Deterministic browser acquisition continues; strict gates still decide URL status |
| No safe direct product URL | Run fails with `MANDATORY_PRODUCT_URL_NOT_FOUND` |
| Browser/agent never becomes healthy | Prints Compose state and the final 200 log lines |

## Notebook workflow

1. open `notebooks/01_run_product_evidence.ipynb`;
2. run the readiness cell;
3. allow self-healing recovery when required;
4. verify `platform_readiness_df`;
5. replace the product input;
6. set `RUN_SINGLE_PRODUCT = True`;
7. run the product cell;
8. open `result['primary_url']` in a browser;
9. inspect the workbook and artifacts when the result is `REVIEW_REQUIRED`.

Kernel restart is not normally required after a container-only recovery because the readiness cell already evicts stale repository modules. Restart the kernel only when Azure ML itself retains an older notebook state.

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
