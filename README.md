# Product Evidence Platform

A production-oriented, LLM-agentic product URL and feature-evidence workflow for Azure ML Compute Instances.

## Production contract

For every product, the platform uses exactly three bounded SerpAPI organic-search credits:

1. **Requested retailer + requested country** — when `retailer_name` is supplied. When absent, this is the primary requested-country search.
2. **Requested-country alternatives** — removes the retailer constraint and searches other retailers in the mandatory country.
3. **Global fallback** — removes retailer and country restrictions and searches globally for the exact product.

Search is identity-driven and does not receive the private feature list. Requested features are evaluated after candidate discovery.

## True agentic browser investigation

Every eligible deduplicated candidate admitted to the bounded investigation pool receives an isolated LLM-controlled browser session:

```text
Observe rendered page and screenshot
  -> LLM plans one safe evidence-seeking action
  -> Browser executes the action
  -> LLM receives the changed page state
  -> repeat until resolved or budget exhausted
```

The LLM can click only observed elements, scroll, inspect an observed image, capture a screenshot, or finish. It cannot invent URLs, type, upload, log in, purchase, execute code, or bypass access controls.

The LLM controls investigation strategy. Deterministic code still validates evidence and selects the final URL.

See [LLM-controlled agentic browser](docs/AGENTIC_BROWSER.md).

## Final URL acceptance

A top-level `primary_url` is returned only when one LLM-investigated URL passes every deterministic gate:

| Gate | Requirement |
|---|---|
| Product identity | Same exact product and variant; EAN is supporting evidence only |
| Browser access | Dedicated browser service opens the rendered final page |
| Access policy | No CAPTCHA, login wall, forbidden page, or access-control bypass |
| Page type | Rendered page is verified as the intended product detail page |
| Scrapability | Product text is extractable and usable |
| Feature completeness | The same primary URL contains every requested feature |
| Conflicts | No requested feature has conflicting evidence |
| URL durability | No signed, tokenized, session-bound, expiry, or TTL parameters |

The system never returns a weak or rejected reference as `primary_url`. When no URL passes all gates, the workflow completes as `REVIEW_REQUIRED`, sets `primary_url` to `null`, and writes candidate evidence and rejection reasons.

## Input contract

| Field | Required | Meaning |
|---|:---:|---|
| `main_text` | Yes | Exact product identity text |
| `country_code` | Yes | Requested market; ISO-like country code |
| `row_id` | Recommended | Stable input identifier |
| `retailer_name` | No | Preferred retailer for search stage 1 |
| `ean` | No | Optional EAN/GTIN identity evidence; supply as text |
| `language_code` | No | Optional language override |

`retailer_name` is a preference, not a hard constraint. `ean` does not override contradictory product or variant evidence.

## Fresh Azure ML setup

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool

cp .env.example .env
chmod 600 .env
# Replace every placeholder, including SerpAPI and LLM credentials.

mkdir -p inputs/private
cp /secure/location/toy_features.json inputs/private/toy_features.json

./scripts/azureml_startup.sh
```

For an Azure ML `cloudfiles` mount that cannot preserve mode `600`:

```bash
./scripts/azureml_startup.sh --allow-insecure-env-permissions
```

The startup command creates runtime folders, validates the three-stage and agentic-browser contract, builds both containers, and waits for health.

Open:

```text
notebooks/01_run_product_evidence.ipynb
```

Set `FEATURE_SET` to the private feature filename without `.json`.

## Required `.env` controls

```env
PRODUCT_HARNESS_WORKFLOW=three_stage_feature_aware
PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES=3
PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES=0

PRODUCT_HARNESS_COUNTRY_FIRST=true
PRODUCT_HARNESS_ALLOW_GLOBAL_FALLBACK=true
PRODUCT_HARNESS_ENABLE_BROWSER_SERVICE=true
PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_REQUIRE_AGENTIC_BROWSER=true

PRODUCT_HARNESS_MAX_AGENTIC_CANDIDATES=18
PRODUCT_HARNESS_AGENTIC_MAX_TURNS_PER_CANDIDATE=10
PRODUCT_HARNESS_AGENTIC_MAX_ACTIONS_PER_CANDIDATE=20

PRODUCT_HARNESS_REQUIRE_ALL_FEATURES_ON_PRIMARY=true
PRODUCT_HARNESS_REJECT_EXPIRING_URLS=true
```

Startup fails when these controls are weakened. Agentic browser investigation requires a valid LLM endpoint and deployment even when optional post-scrape text reasoning is disabled.

## Candidate admission and cost control

The raw SerpAPI result set is not sent blindly to the LLM. URLs are merged, deduplicated, preflighted, statically scraped, identity-scored, and admitted to a bounded investigation pool.

The default pool is 18 candidates: six per search stage under the standard configuration. Every admitted candidate receives an agentic investigation. Raising candidate or turn limits increases LLM and browser cost.

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
└── CAND-###/agentic/
    ├── investigation.json
    ├── latest_observation.json
    ├── rendered_text.md
    ├── final_page.html
    ├── browser_actions.json
    ├── browser_result.json
    ├── visual_manifest.json
    ├── observations/
    ├── images/
    └── screenshots/
```

`investigation.json` records the LLM plans and termination decision. `browser_actions.json` records what was actually executed. `primary_url_acceptance.json` is the authoritative final acceptance decision.

## Result contract

Important fields returned by `GET /v1/jobs/{job_id}/result`:

| Path | Meaning |
|---|---|
| `product.row_id` | Original row identifier |
| `job_status` | `COMPLETED` or `REVIEW_REQUIRED` |
| `coding_ready` | True only when strict final acceptance passed |
| `primary_url` | Strictly accepted URL, otherwise `null` |
| `supplementary_urls` | Review references only when acceptance fails |
| `search.stages` | Three-stage search trace |
| `search.serpapi_requests_used` | Must be `3` |
| `agentic_browser` | Investigation policy, budgets, and completion counts |
| `candidate_investigations` | Per-candidate LLM plans, actions, conclusions, and errors |
| `product_match` | Product identity and scope decision |
| `primary_url_acceptance` | Browser, identity, feature, scrapability, and durability gates |
| `evidence_set` | Feature coverage and conflicts |
| `feature_assessments` | Per-URL requested-feature evidence |
| `browser_evidence` | Rendered and visual evidence |
| `artifact_dir` | Container artifact path |

`REVIEW_REQUIRED` is a completed workflow, not an execution failure. It means no investigated URL passed every final gate.

## Service responsibilities

| Service | Responsibility |
|---|---|
| Agent | Three searches, candidate admission, LLM planning loop, evidence validation, strict URL selection, outputs |
| Browser | Isolated Chromium sessions, page observations, safe action execution, text/images/screenshots |
| Notebook | Submit inputs, poll candidate-level progress, inspect results, optional CSV batching |

The browser never receives SerpAPI or LLM credentials. The agent never exposes unrestricted Playwright access to the LLM.

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
find data/artifacts -maxdepth 7 -type f | sort
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

- [LLM-controlled agentic browser](docs/AGENTIC_BROWSER.md)
- [Azure ML operations runbook](docs/AZUREML_OPERATIONS.md)
- [Notebook usage and result contract](docs/NOTEBOOK_USAGE.md)
- [Security contract](docs/SECURITY.md)
