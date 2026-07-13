# Azure ML Operations Runbook

This is the definitive operating procedure for the Product Evidence Platform.

## Runtime topology

```text
Azure ML Compute Instance
├── Docker Compose
│   ├── agent:8000   -> host 127.0.0.1:8788
│   └── browser:9000 -> internal Compose network only
├── inputs/private/  -> read-only private feature schemas
├── data/
│   ├── artifacts/   -> shared agent/browser evidence
│   └── runtime/     -> repository-local transient state
└── notebooks/01_run_product_evidence.ipynb
```

The notebook is only an API client. Search, scraping, identity validation, browser verification, feature extraction, URL acceptance, and artifact writing happen inside the containers.

## Fresh-clone procedure

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool
cp .env.example .env
chmod 600 .env
# Replace all placeholders.
mkdir -p inputs/private
cp /secure/location/toy_features.json inputs/private/toy_features.json
./scripts/azureml_startup.sh
```

For Azure ML mounted filesystems that cannot preserve mode `600`:

```bash
./scripts/azureml_startup.sh --allow-insecure-env-permissions
```

Startup creates missing repository-local runtime folders, validates the strict production controls, builds both containers, and waits for health.

## Immutable search campaign

Every product consumes exactly three SerpAPI organic-search credits:

| Credit | Scope | Retailer behavior |
|---:|---|---|
| 1 | Requested country | Includes `retailer_name` when provided |
| 2 | Requested country | Removes retailer constraint and searches other country retailers |
| 3 | Global | Removes retailer and country restrictions |

When `retailer_name` is absent, credit 1 is the primary country search. EAN is optional throughout. `country_code` and `main_text` are mandatory. Private feature names are never placed in SerpAPI queries.

Required configuration:

```env
PRODUCT_HARNESS_WORKFLOW=three_stage_feature_aware
PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES=3
PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES=0
PRODUCT_HARNESS_COUNTRY_FIRST=true
PRODUCT_HARNESS_ALLOW_GLOBAL_FALLBACK=true
```

The runtime and preflight validators reject weaker or different values.

## Strict primary URL acceptance

After all search stages, candidates are statically scraped and opened by the browser service. `primary_url` is populated only when one URL satisfies all conditions:

1. Browser opens the final URL successfully.
2. Rendered content is the exact requested product and variant.
3. The rendered page is a product detail page.
4. Product text is scrapable.
5. The same URL contains all requested features with no conflicts.
6. The URL has no token, signature, expiry, TTL, session, or temporary credential parameter.

Required controls:

```env
PRODUCT_HARNESS_ENABLE_BROWSER_SERVICE=true
PRODUCT_HARNESS_REQUIRE_ALL_FEATURES_ON_PRIMARY=true
PRODUCT_HARNESS_REJECT_EXPIRING_URLS=true
PRODUCT_HARNESS_RETURN_REJECTED_REFERENCE_AS_PRODUCT_URL=false
```

When no URL passes, the workflow returns `REVIEW_REQUIRED`, `coding_ready=false`, and `primary_url=null`. Review references may remain in diagnostic fields, but they are never promoted to `primary_url`.

## Input contract

| Field | Required |
|---|:---:|
| `main_text` | Yes |
| `country_code` | Yes |
| `row_id` | Recommended |
| `retailer_name` | No |
| `ean` | No |
| `language_code` | No |

EAN/GTIN must be supplied as text to preserve leading zeroes.

## Running products

Open `notebooks/01_run_product_evidence.ipynb`, set `FEATURE_SET`, and call `run_product(product, FEATURE_SET)`.

Progress stages:

```text
VALIDATING_INPUT
SEARCHING
REQUESTING_BROWSER_EVIDENCE
VALIDATING_PRIMARY_URL
WRITING_OUTPUTS
COMPLETED or REVIEW_REQUIRED
```

## Result fields

| Path | Meaning |
|---|---|
| `product.row_id` | Original input row identifier |
| `job_status` | `COMPLETED` or `REVIEW_REQUIRED` |
| `coding_ready` | True only after strict acceptance |
| `search.queries` | Executed queries in order |
| `search.stages` | Stage name, scope, result count, and scrape count |
| `search.serpapi_requests_used` | Exactly `3` |
| `product_match.selection_scope` | Requested retailer, country alternative, or global |
| `primary_url_acceptance` | Browser, identity, feature, scrapability, and durability gates |
| `primary_url` | Strict accepted URL or `null` |
| `evidence_set` | Feature coverage and conflicts |
| `feature_assessments` | Per-URL requested-feature evidence |
| `browser_evidence` | Rendered evidence and blockers |

## Artifact contract

```text
Host repository: ./data/artifacts
Agent container: /data/artifacts
Browser container: /data/artifacts
Product output:  ./data/artifacts/<row_id>/
```

```text
data/artifacts/<row_id>/
├── result.json
├── candidates.csv
├── feature_evidence.csv
├── review.md
├── primary_url_acceptance.json
├── orchestrated_result.json
└── CAND-*/browser/
```

Use:

```bash
find data/artifacts -maxdepth 5 -type f | sort
```

## Health and logs

```bash
docker compose ps
python scripts/wait_for_stack.py
docker compose logs -f --tail=200 agent browser
```

The health response reports `three_stage_contract_enforced=true` and `serpapi_request_limit=3`.

## Restart and update

```bash
docker compose down
git checkout master
git pull origin master
./scripts/azureml_startup.sh
```

## Failure guide

| Symptom | Action |
|---|---|
| Docker socket permission denied | Request Docker permission from the Azure ML administrator |
| `.env` permissions remain broad | Use the explicit mounted-filesystem override |
| Organic searches must be 3 | Update `.env` from the current `.env.example` |
| A strict flag must be true | Restore the required production control |
| No feature set found | Copy a valid JSON file into `inputs/private/` |
| `REVIEW_REQUIRED` | Inspect `primary_url_acceptance.json`, search stages, browser evidence, and candidates |
| URL rejected for TTL/signature | Use a canonical product page instead of a temporary/signed link |
| CAPTCHA/login/access wall | Candidate remains rejected; access controls are not bypassed |

## Validation

```bash
python scripts/validate_environment.py --env-file .env
python -m compileall -q src scripts
python -m json.tool notebooks/01_run_product_evidence.ipynb >/dev/null
python -m pytest -q
docker compose config --quiet
```
