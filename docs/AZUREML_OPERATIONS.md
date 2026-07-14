# Azure ML Operations Runbook

## Supported fresh-clone flow

The supported setup requires only credential entry and one startup command:

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool
cp .env.example .env
# Edit only the real SerpAPI and LLM credential values.
./scripts/azureml_startup.sh
```

The repository already contains:

```text
inputs/private/toy_features.json
```

No feature-file copy or creation step is required. After the script reports `Product evidence platform is ready`, open:

```text
notebooks/01_run_product_evidence.ipynb
```

The notebook is an API client. It does not build containers or install browser dependencies itself.

## What the startup script automates

`./scripts/azureml_startup.sh` is the single bootstrap and restart entry point. It:

1. locates the repository root;
2. creates `data/artifacts`, `data/runtime`, `inputs/private`, and `secrets`;
3. validates the committed `inputs/private/toy_features.json` schema;
4. creates the internal browser API token when missing;
5. selects the invoking Azure ML user UID/GID for both non-root containers;
6. attempts to set `.env` to mode `0600`;
7. automatically detects Azure ML `cloudfiles` mounts that cannot preserve `0600` and continues with the trusted-workspace fallback;
8. validates credentials, strict search controls, agentic-browser controls, feature files, Docker, Compose, and the host port;
9. stops stale containers belonging to this Compose project;
10. builds and recreates both services;
11. waits for a healthy browser and strict agent configuration;
12. fails immediately with the actual agent `configuration_error` instead of polling a hidden 503 until timeout;
13. writes `data/runtime/stack_health.json`;
14. prints the agent URL, notebook path, artifact root, and available `FEATURE_SET` values.

The same command is safe to rerun after changing `.env` or pulling new code:

```bash
./scripts/azureml_startup.sh
```

Use `--no-build` only when intentionally reusing existing images.

## `.env` permission behavior

The default permission mode is `auto`:

- on normal Linux filesystems, the script enforces mode `0600`;
- on Azure ML paths under `/cloudfiles/`, it first attempts `chmod 600`;
- when the mount reports broader permissions despite that attempt, startup continues automatically with a warning because the mode cannot be represented by the mount;
- credential placeholders, malformed values, disabled safety controls, and invalid endpoints are still rejected;
- `.env` contents are never printed.

For an explicit stricter run:

```bash
./scripts/azureml_startup.sh --strict-env-permissions
```

The old `--allow-insecure-env-permissions` option remains only for compatibility and should not be needed on Azure ML.

## Runtime topology

```text
Azure ML Compute Instance
├── Docker Compose
│   ├── agent:8000   -> host 127.0.0.1:8788
│   └── browser:9000 -> internal Compose network only
├── inputs/private/toy_features.json -> committed default schema
├── data/runtime/    -> bootstrap health snapshot
├── data/artifacts/  -> shared evidence and traces
└── notebooks/01_run_product_evidence.ipynb
```

The agent owns all three SerpAPI searches, candidate admission, LLM planning, deterministic evidence validation, final selection, and outputs. The browser owns isolated Chromium sessions and safe action execution.

## Required configuration

At minimum, replace these `.env` values:

```env
SERPAPI_API_KEY=<real-key>
LLM_API_KEY=<real-key>
LLM_API_VERSION=<supported-version>
LLM_ENDPOINT=<approved-https-endpoint>
LLM_DEPLOYMENT=<vision-capable-deployment>
```

The equivalent `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_VERSION`, `AZURE_OPENAI_ENDPOINT`, and `AZURE_OPENAI_DEPLOYMENT` names are accepted. All other production controls are already supplied in `.env.example` and should remain unchanged.

## Included feature schema

The committed default schema is:

```text
inputs/private/toy_features.json
```

It requests:

- brand;
- manufacturer;
- minimum recommended age.

The corresponding notebook/API value is:

```python
FEATURE_SET = "toy_features"
```

Additional organization-specific schemas may be placed under `inputs/private/`. They are ignored by Git unless explicitly approved; the committed `toy_features.json` remains the default runnable schema.

## Readiness verification

The bootstrap performs this automatically. Manual verification is:

```bash
docker compose ps
cat data/runtime/stack_health.json
curl -sS http://127.0.0.1:8788/health | python -m json.tool
```

The health response must include:

```text
status=healthy
three_stage_contract_enforced=true
serpapi_request_limit=3
agentic_browser_contract_enforced=true
llm_configured=true
browser_service.agentic_tools=true
```

## Search and browser flow

Every product uses exactly three searches:

1. requested retailer in the requested country;
2. alternative retailers in the requested country;
3. global fallback.

Every retained deduplicated candidate then receives an isolated agentic browser session:

```text
observe page + screenshot
  -> LLM plans one safe action
  -> browser validates and executes it
  -> observe changed state
  -> repeat
```

The deterministic selector still controls `primary_url`.

## Failure behavior

| Failure | Bootstrap behavior |
|---|---|
| `.env` missing | Creates it from `.env.example`, stops, and instructs you to edit credentials and rerun |
| Placeholder SerpAPI/LLM value | Fails before Docker build with the exact missing field |
| Default toy schema missing or malformed | Fails before Docker build with the exact file error |
| `cloudfiles` cannot preserve `0600` | Automatically continues with a security notice |
| Invalid production control | Fails preflight before containers start |
| Stale project containers | Removes and recreates them automatically |
| Unrelated process owns the agent port | Stops with the occupied-port error |
| Agent returns configuration 503 | Health waiter prints the exact `configuration_error` and exits immediately |
| Browser/agent never becomes healthy | Prints Compose state and the final 200 log lines |

## Notebook workflow

After successful startup:

1. open `notebooks/01_run_product_evidence.ipynb`;
2. restart the kernel if the notebook was already open before rebuild;
3. run the setup/health cell;
4. the included `toy_features` schema is discovered automatically;
5. replace the product input;
6. set `RUN_SINGLE_PRODUCT = True`;
7. run the product cell.

The notebook reads `data/runtime/stack_health.json`, checks live `/health`, discovers feature sets, submits jobs, displays candidate-level progress, and inspects evidence artifacts.

## Logs and shutdown

```bash
docker compose logs -f --tail=200 agent browser
docker compose down
```

Stopping containers does not delete `data/artifacts` or `data/runtime`.

## Validation for development

```bash
python scripts/validate_environment.py --env-file .env
python scripts/preflight_azureml.py --skip-docker --skip-port
python -m compileall -q src scripts
python -m json.tool inputs/private/toy_features.json >/dev/null
python -m json.tool notebooks/01_run_product_evidence.ipynb >/dev/null
python -m pytest -q
docker compose config --quiet
```
