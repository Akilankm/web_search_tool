# Product Evidence Platform

A production-oriented, LLM-agentic product URL and feature-evidence workflow for Azure ML Compute Instances.

## Production contract

Every product uses exactly three bounded SerpAPI organic searches:

1. requested retailer in the requested country, or the primary country search;
2. alternative retailers in the requested country;
3. unrestricted global fallback.

Every deduplicated URL retained by the bounded candidate pool may receive an isolated LLM-controlled browser investigation. The LLM observes the rendered page and screenshot, plans one safe action, receives the changed page state, and repeats. Deterministic code still enforces product identity, accessibility, scrapability, feature evidence, conflicts, scope priority, and durable `primary_url` acceptance.

See [docs/AGENTIC_BROWSER.md](docs/AGENTIC_BROWSER.md).

## One-command Azure ML bootstrap

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool
cp .env.example .env
# Edit only the SerpAPI and LLM values in .env.
./scripts/azureml_startup.sh
```

Then open:

```text
notebooks/01_run_product_evidence.ipynb
```

The repository already contains `inputs/private/toy_features.json`. No feature-file copy, manual Docker command, permission override, or separate notebook dependency setup is required.

The startup script:

- creates runtime, artifact, private-input, and secret directories;
- creates the internal browser API token when absent;
- runs containers as the Azure ML notebook user;
- adapts automatically to Azure ML managed-mount permission behavior;
- validates required fields, feature schema, Docker, Compose, and production controls;
- removes stale Compose resources;
- builds and recreates the browser and agent containers;
- waits for strict health;
- writes `data/runtime/stack_health.json`;
- prints the notebook and artifact locations.

## Required `.env` values

```env
SERPAPI_API_KEY=<organization-provided-value>
LLM_API_KEY=<organization-provided-value>
LLM_API_VERSION=<organization-provided-value>
LLM_ENDPOINT=<organization-provided-value>
LLM_DEPLOYMENT=<organization-provided-value>
```

Equivalent `AZURE_OPENAI_*` names are accepted. LLM values are treated as organization-provided opaque configuration; startup requires them to be present but does not impose key-length or endpoint-format assumptions.

The production controls in `.env.example` should remain unchanged:

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

## Included feature schema

A fresh clone includes:

```text
inputs/private/toy_features.json
```

It defines:

- brand;
- manufacturer;
- minimum recommended age.

The notebook uses:

```python
FEATURE_SET = "toy_features"
```

## Single-product EDA and RCA notebook

The notebook is not only a runner. After one product completes, it builds a complete diagnostic model with compact pandas tables, a Rich executive summary, Matplotlib charts, Seaborn charts, and an Excel export.

The principal table is `results_df`, containing one row per deduplicated retained candidate. It joins search scope, SERP position, scrape outcome, agentic-browser activity, deterministic identity acceptance, feature coverage, rejection reasons, and final `primary_url` selection.

Other diagnostic DataFrames include:

- `search_stages_df`;
- `serp_results_df`;
- `funnel_df`;
- `domain_summary_df`;
- `stage_quality_df`;
- `agentic_df`;
- `feature_evidence_df`;
- `feature_matrix_df`;
- `rejection_reasons_df`;
- `selection_rca_df`.

The funnel is reported explicitly:

```text
SERP rows returned
→ unique candidate URLs
→ scrape attempted
→ scrape successful
→ agentic investigated
→ browser openable
→ identity accepted
→ feature complete
→ selected
```

The final diagnostic workbook is written to:

```text
data/artifacts/<row_id>/single_product_diagnostics.xlsx
```

See [docs/SINGLE_PRODUCT_DIAGNOSTICS.md](docs/SINGLE_PRODUCT_DIAGNOSTICS.md).

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

Important API fields:

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
./scripts/azureml_startup.sh

docker compose ps
docker compose logs -f --tail=200 agent browser

docker compose down
```

Generated evidence is written under `data/artifacts/<row_id>/`.

## Validation

```bash
python scripts/validate_environment.py --env-file .env
python -m compileall -q src scripts
python -m json.tool inputs/private/toy_features.json >/dev/null
python -m json.tool notebooks/01_run_product_evidence.ipynb >/dev/null
python -m pytest -q
docker compose config --quiet
```

## Documentation

- [Automated Azure ML operations](docs/AZUREML_OPERATIONS.md)
- [Notebook usage and diagnostic contract](docs/NOTEBOOK_USAGE.md)
- [Single-product diagnostic interpretation](docs/SINGLE_PRODUCT_DIAGNOSTICS.md)
- [Enterprise LLM configuration](docs/ENTERPRISE_LLM_CONFIGURATION.md)
- [LLM-controlled agentic browser](docs/AGENTIC_BROWSER.md)
- [Security contract](docs/SECURITY.md)
