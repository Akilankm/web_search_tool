# Product Evidence Platform

A production-oriented, LLM-agentic product URL and feature-evidence workflow for Azure ML Compute Instances.

## Production contract

Every product uses exactly three bounded SerpAPI organic searches:

1. requested retailer in the requested country, or the primary country search;
2. alternative retailers in the requested country;
3. unrestricted global fallback.

Every deduplicated URL retained by the bounded candidate pool receives an isolated LLM-controlled browser investigation. The LLM observes the rendered page and screenshot, plans one safe action, receives the changed page state, and repeats. Deterministic code still enforces product identity, accessibility, scrapability, feature evidence, conflicts, scope priority, and durable `primary_url` acceptance.

See [docs/AGENTIC_BROWSER.md](docs/AGENTIC_BROWSER.md).

## One-command Azure ML bootstrap

The supported fresh-clone workflow is intentionally short:

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool

cp .env.example .env
# Edit .env and replace the SerpAPI and LLM placeholders.

./scripts/azureml_startup.sh
```

Then open:

```text
notebooks/01_run_product_evidence.ipynb
```

The startup script performs the complete machine setup:

- creates repository-local runtime, artifact, private-input, and secret directories;
- creates the internal browser API token when absent;
- detects the invoking Azure ML user UID/GID and runs containers as that user;
- attempts `chmod 600 .env` automatically;
- detects Azure ML `cloudfiles` mounts that cannot preserve mode `0600` and switches automatically to a documented trusted-workspace permission fallback;
- validates all credentials, strict three-search controls, agentic-browser controls, feature schemas, Docker, Compose, and the configured port;
- removes stale containers from this Compose project;
- builds and recreates the browser and agent containers;
- waits for browser, LLM, SerpAPI, and strict agent health;
- writes `data/runtime/stack_health.json`;
- prints the API URL, notebook path, artifact path, and available `FEATURE_SET` names.

No manual `--allow-insecure-env-permissions` flag is required on Azure ML. The legacy flag remains available only as an explicit compatibility override.

If `.env` is missing, the script creates it from `.env.example`, stops before Docker startup, and tells you to fill the real values and rerun the same command.

## Required `.env` values

```env
SERPAPI_API_KEY=<real-key>

LLM_API_KEY=<real-key>
LLM_API_VERSION=<supported-version>
LLM_ENDPOINT=<approved-https-endpoint>
LLM_DEPLOYMENT=<vision-capable-deployment>
```

Equivalent `AZURE_OPENAI_*` names are also accepted. Placeholder values are rejected before Docker build.

The production controls must remain enabled:

```env
PRODUCT_HARNESS_WORKFLOW=three_stage_feature_aware
PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES=3
PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES=0
PRODUCT_HARNESS_COUNTRY_FIRST=true
PRODUCT_HARNESS_ALLOW_GLOBAL_FALLBACK=true
PRODUCT_HARNESS_ENABLE_BROWSER_SERVICE=true
PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_REQUIRE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_MAX_CANDIDATE_POOL=90
PRODUCT_HARNESS_MAX_AGENTIC_CANDIDATES=90
PRODUCT_HARNESS_AGENTIC_MAX_TURNS_PER_CANDIDATE=10
PRODUCT_HARNESS_AGENTIC_MAX_ACTIONS_PER_CANDIDATE=20
PRODUCT_HARNESS_REQUIRE_ALL_FEATURES_ON_PRIMARY=true
PRODUCT_HARNESS_REJECT_EXPIRING_URLS=true
```

## Feature schema

Place private feature schemas in:

```text
inputs/private/<feature_set>.json
```

When none exists, preflight creates `inputs/private/example_features.json` from the generic repository example so the notebook can still open and demonstrate the contract. In the notebook, use the filename without `.json`:

```python
FEATURE_SET = "toy_features"
```

## Final URL acceptance

A top-level `primary_url` is returned only when one LLM-investigated URL is:

- browser-openable and not blocked;
- the rendered exact product and variant;
- text-scrapable;
- complete for every requested feature on the same URL;
- free of feature conflicts;
- durable and non-expiring.

Otherwise the workflow completes as `REVIEW_REQUIRED`, keeps `primary_url=null`, and retains the candidate investigations and diagnostic multi-URL evidence coverage.

## Result contract

Important fields returned by `GET /v1/jobs/{job_id}/result`:

| Path | Meaning |
|---|---|
| `product.row_id` | Original row identifier |
| `job_status` | `COMPLETED` or `REVIEW_REQUIRED` |
| `coding_ready` | Strict deterministic final acceptance result |
| `primary_url` | Accepted durable URL or `null` |
| `search.stages` | Three-stage search trace |
| `search.serpapi_requests_used` | Must be `3` |
| `agentic_browser` | Investigation policy and budgets |
| `candidate_investigations` | Per-candidate LLM plans and actions |
| `feature_assessments` | Per-URL requested-feature evidence and coverage |
| `evidence_set` | Diagnostic selected-source coverage |
| `primary_url_acceptance` | Authoritative final gate decision |
| `browser_evidence` | Rendered text, screenshots, blockers, and assets |

## Operations

```bash
# Idempotent rebuild/restart after editing .env or pulling code
./scripts/azureml_startup.sh

# Status and logs
docker compose ps
docker compose logs -f --tail=200 agent browser

# Stop without deleting evidence
docker compose down
```

Generated evidence is written under:

```text
data/artifacts/<row_id>/
```

## Validation

```bash
python scripts/validate_environment.py --env-file .env
python -m compileall -q src scripts
python -m json.tool notebooks/01_run_product_evidence.ipynb >/dev/null
python -m pytest -q
docker compose config --quiet
```

## Documentation

- [Automated Azure ML operations](docs/AZUREML_OPERATIONS.md)
- [Notebook usage and result contract](docs/NOTEBOOK_USAGE.md)
- [LLM-controlled agentic browser](docs/AGENTIC_BROWSER.md)
- [Security contract](docs/SECURITY.md)
