# Product Evidence Platform

A production-oriented product URL and feature-evidence workflow for Azure ML Compute Instances.

## Production contract

For every product, the platform uses exactly three bounded SerpAPI organic-search credits:

1. **Requested retailer + requested country** — when `retailer_name` is supplied. When it is absent, this is the primary requested-country search.
2. **Requested-country alternatives** — removes the retailer constraint and searches other retailers in the mandatory country.
3. **Global fallback** — removes retailer and country restrictions and searches globally for the exact product.

Search is identity-driven and does not receive the private feature list. Requested features are evaluated only after candidate pages are scraped and browser-opened.

## Final URL acceptance

A top-level `primary_url` is returned only when one URL passes every gate:

| Gate | Requirement |
|---|---|
| Product identity | Same exact product and variant; EAN is supporting evidence only |
| Browser access | Dedicated browser service opens the final page |
| Page type | Rendered page is verified as the intended product detail page |
| Scrapability | Product text is extractable and usable |
| Feature completeness | The same primary URL contains every requested feature |
| URL durability | No signed, tokenized, session-bound, expiry, or TTL query parameters |

The system never returns a weak or rejected reference as `primary_url`. When no URL passes all gates, the workflow completes as `REVIEW_REQUIRED`, sets `primary_url` to `null`, and writes the candidate and rejection evidence to the artifact folder.

## Input contract

| Field | Required | Meaning |
|---|:---:|---|
| `main_text` | Yes | Exact product identity text |
| `country_code` | Yes | Requested market; ISO-like country code |
| `row_id` | Recommended | Stable input identifier |
| `retailer_name` | No | Preferred retailer for stage 1 |
| `ean` | No | Optional EAN/GTIN identity evidence; supply as text |
| `language_code` | No | Optional language override |

`retailer_name` is a preference, not a hard constraint. `ean` is optional and does not override contradictory product or variant evidence.

## Supported workflow

```text
Clone repository
  -> configure .env
  -> add private feature JSON
  -> run startup script
  -> open the supported notebook
  -> submit products
```

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool

cp .env.example .env
chmod 600 .env
# Replace every placeholder in .env.

mkdir -p inputs/private
cp /secure/location/toy_features.json inputs/private/toy_features.json

./scripts/azureml_startup.sh
```

For an Azure ML `cloudfiles` mount that cannot preserve mode `600`:

```bash
./scripts/azureml_startup.sh --allow-insecure-env-permissions
```

The startup command creates all missing repository-local runtime folders, validates the immutable three-stage and strict-acceptance configuration, builds both containers, and waits for health.

Open:

```text
notebooks/01_run_product_evidence.ipynb
```

Set `FEATURE_SET` to the private feature filename without `.json`.

## Required `.env` controls

The checked-in example enforces:

```env
PRODUCT_HARNESS_WORKFLOW=three_stage_feature_aware
PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES=3
PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES=0
PRODUCT_HARNESS_COUNTRY_FIRST=true
PRODUCT_HARNESS_ALLOW_GLOBAL_FALLBACK=true
PRODUCT_HARNESS_ENABLE_BROWSER_SERVICE=true
PRODUCT_HARNESS_REQUIRE_ALL_FEATURES_ON_PRIMARY=true
PRODUCT_HARNESS_REJECT_EXPIRING_URLS=true
```

Startup fails when these controls are weakened.

## Artifact contract

```text
Host repository: ./data/artifacts
Agent container: /data/artifacts
Browser container: /data/artifacts
Product output:  ./data/artifacts/<row_id>/
```

Typical output:

```text
data/artifacts/TEST-001/
├── candidates.csv
├── feature_evidence.csv
├── result.json
├── review.md
├── primary_url_acceptance.json
├── orchestrated_result.json
└── CAND-*/browser/
```

`result.json` records the complete search campaign. `orchestrated_result.json` is the final API result. `primary_url_acceptance.json` records every final acceptance gate and rejection reason.

Generated `data/artifacts/` and `data/runtime/` content is ignored by Git. Missing runtime directories are recreated on startup.

## Result contract

Important fields returned by `GET /v1/jobs/{job_id}/result`:

| Path | Meaning |
|---|---|
| `product.row_id` | Original row identifier |
| `job_status` | `COMPLETED` or `REVIEW_REQUIRED` |
| `coding_ready` | True only when strict primary URL acceptance passed |
| `primary_url` | Strictly accepted URL, otherwise `null` |
| `supplementary_urls` | Review references only when strict acceptance fails |
| `search.stages` | Three-stage search trace |
| `search.serpapi_requests_used` | Must be `3` |
| `product_match` | Product identity and scope decision |
| `primary_url_acceptance` | Browser, identity, feature, scrapability, and durability gates |
| `evidence_set` | Feature coverage and conflicts |
| `feature_assessments` | Per-URL requested-feature evidence |
| `browser_evidence` | Rendered and visual evidence |
| `artifact_dir` | Container artifact path |

`REVIEW_REQUIRED` is a completed workflow, not an execution failure. It means no URL passed every final gate.

## Service responsibilities

| Service | Responsibility |
|---|---|
| Agent | Three searches, static extraction, identity validation, feature assessment, strict URL selection, outputs |
| Browser | Open rendered pages, expand sections, verify product page, collect text/images/screenshots |
| Notebook | Submit inputs, poll progress, inspect results, optional CSV batching |

The browser never receives SerpAPI or LLM credentials.

## Operations

```bash
# Status
docker compose ps

# Logs
docker compose logs -f --tail=200 agent browser

# Stop without deleting artifacts
docker compose down

# Update and rebuild
git checkout master
git pull origin master
docker compose down
./scripts/azureml_startup.sh
```

Inspect outputs:

```bash
find data/artifacts -maxdepth 5 -type f | sort
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

- [Azure ML operations runbook](docs/AZUREML_OPERATIONS.md)
- [Notebook usage and result contract](docs/NOTEBOOK_USAGE.md)
- [Security contract](docs/SECURITY.md)
