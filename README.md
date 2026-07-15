# Product Evidence Platform

A production-oriented product URL and feature-evidence workflow for Azure ML Compute Instances.

## Non-negotiable production objective

For every submitted product, the workflow must return a real direct product URL.

A `COMPLETED` or `REVIEW_REQUIRED` result may not contain an empty `primary_url` or `product_match.product_url`.

```text
product identity
→ determine highest unresolved source-authority tier
→ LLM selects one suitable SerpAPI engine and query
→ normalize direct URLs, product tokens, IDs and images
→ precision-gated scrape and browser validation
→ deliver a strictly verified URL when possible
→ otherwise deliver the strongest real review URL
```

The system never fabricates a URL and never substitutes a Google result page, SerpAPI URL, category page, social page, document, or media file.

If all three SerpAPI credits are exhausted without any direct external product-page candidate, the run fails with:

```text
MANDATORY_PRODUCT_URL_NOT_FOUND
```

It does not complete successfully with a blank URL.

See [Mandatory product URL delivery](docs/MANDATORY_PRODUCT_URL.md).

## Three adaptive SerpAPI credits

The credits are three adaptive decisions, not three fixed organic searches.

The planner may use:

| Engine | Role |
|---|---|
| `google` | Exact EAN/model, requested retailer, manufacturer, and direct-page recovery |
| `google_shopping` | Product identity, merchant discovery, product IDs, and immersive tokens |
| `google_immersive_product` | Expand a real product token into direct store URLs |
| `google_ai_mode` | Product/manufacturer disambiguation and cited URL recovery |
| `google_lens` | Visual matching when a real product image exists |
| `amazon`, `ebay`, `walmart`, `home_depot` | Requested-retailer native discovery |

Deterministic code enforces the three-credit ceiling, engine preconditions, duplicate-action prevention, URL normalization, source hierarchy, candidate admission, scraping, browser investigation, and final URL delivery.

If the final credit begins without any direct candidate, the planner enters mandatory recovery:

1. expand a real immersive-product token when available;
2. otherwise use AI Mode, Shopping, or Google Search;
3. preserve EAN, model, retailer, country, and product identity terms;
4. request direct manufacturer or retailer product pages;
5. reject intermediary and non-product URLs deterministically.

See [Adaptive three-credit SerpAPI search](docs/ADAPTIVE_SERPAPI_SEARCH.md).

## Standardized source hierarchy

When `retailer_name` is supplied, that retailer receives first priority. Otherwise:

```text
Local/regional manufacturer website
→ Global manufacturer website
→ Major retailer in the requested country
→ Other local website
→ Other global exact-product website
→ Amazon/eBay last resort
```

Amazon or eBay receive first priority only when explicitly supplied as `retailer_name`.

The hierarchy applies twice:

1. **Search routing:** each credit targets the highest unresolved source tier before choosing an engine.
2. **Final selection:** among usable candidates, source authority is applied before small richness or confidence differences.

A valid manufacturer URL therefore outranks a richer Amazon/eBay URL unless the marketplace was explicitly requested.

See [Standardized source-authority hierarchy](docs/SOURCE_AUTHORITY_HIERARCHY.md).

## Strict acceptance versus mandatory delivery

Strict acceptance and URL delivery are separate decisions.

| Output | Meaning |
|---|---|
| `primary_url_acceptance.accepted` | Every strict browser, identity, feature, scrapability, and durability gate passed |
| `url_delivery.delivered` | A real direct product URL was returned |
| `url_delivery.strictly_verified` | The delivered URL also passed strict acceptance |
| `url_delivery.status` | `STRICT_VERIFIED_PRODUCT_URL` or `BEST_AVAILABLE_REVIEW_URL` |
| `job_status` | `COMPLETED`, `REVIEW_REQUIRED`, or `FAILED` |

### `COMPLETED`

A strictly verified exact-product URL was delivered.

### `REVIEW_REQUIRED`

A real direct product URL was delivered, but one or more strict gates still require confirmation. The URL remains populated in:

```text
primary_url
product_match.product_url
product_match.best_available_url
evidence_set.primary_url
evidence_set.selected_urls
```

### `FAILED`

The workflow failed operationally, including the hard failure where no direct product URL was produced.

## Candidate precision and browser escalation

All engine responses enter one canonical candidate pool:

```text
raw result occurrence
→ canonical URL
→ source-authority classification
→ URL-type and identity admission
→ bounded full scrape
→ evidence-utility validation
→ bounded browser escalation
→ strict acceptance and mandatory delivery
```

Production defaults:

```env
PRODUCT_HARNESS_MAX_SERPAPI_CREDITS=3
PRODUCT_HARNESS_MAX_FULL_SCRAPES=6
PRODUCT_HARNESS_MAX_SCRAPES_PER_DOMAIN=2
PRODUCT_HARNESS_MIN_PREFLIGHT_SCORE=0.28
PRODUCT_HARNESS_MAX_AGENTIC_CANDIDATES=3
PRODUCT_HARNESS_AGENTIC_MAX_TURNS_PER_CANDIDATE=4
PRODUCT_HARNESS_AGENTIC_MAX_ACTIONS_PER_CANDIDATE=6
```

Homepages, search pages, category pages, collections, social pages, documents, media files, Google intermediary URLs, and SerpAPI URLs are never accepted as the delivered product URL.

See [Candidate precision and context control](docs/CANDIDATE_PRECISION_AND_CONTEXT.md) and [Agentic browser](docs/AGENTIC_BROWSER.md).

## One-command Azure ML bootstrap

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool
cp .env.example .env
# Edit the real SerpAPI and LLM credential values.
./scripts/azureml_startup.sh
```

Then open:

```text
notebooks/01_run_product_evidence.ipynb
```

The repository includes:

```text
inputs/private/toy_features.json
```

No feature-file copy, manual Docker command, or separate notebook dependency setup is required.

## Required credentials

```env
SERPAPI_API_KEY=<organization-provided-value>
LLM_API_KEY=<organization-provided-value>
LLM_API_VERSION=<organization-provided-value>
LLM_ENDPOINT=<organization-provided-value>
LLM_DEPLOYMENT=<organization-provided-value>
```

Equivalent `AZURE_OPENAI_*` names are accepted. Enterprise LLM values are treated as opaque; startup validates presence rather than provider-specific formatting.

## Notebook EDA and RCA

The supported notebook exposes:

| DataFrame | Purpose |
|---|---|
| `url_delivery_df` | Mandatory URL and strict-verification outcome |
| `search_actions_df` | One row per paid adaptive credit |
| `source_hierarchy_df` | Target source tier and engine per credit |
| `search_engine_summary_df` | Per-engine yield and conversion |
| `search_handles_df` | Product tokens, IDs, and image handles |
| `search_decision_rca_df` | Budget, planner fallback, and stop RCA |
| `serp_results_df` | Raw cross-engine result occurrences |
| `results_df` | One row per canonical candidate URL |
| `source_tier_summary_df` | Candidate conversion by source tier |
| `funnel_df` | Search-to-selection conversion |
| `rejection_reasons_df` | Candidate blockers and review reasons |
| `selection_rca_df` | Final URL decision |

The workbook is written to:

```text
data/artifacts/<row_id>/single_product_diagnostics.xlsx
```

## Artifacts

```text
data/artifacts/<row_id>/
├── adaptive_search_trace.json
├── serp_credit_01_<engine>_raw.json
├── serp_credit_02_<engine>_raw.json
├── serp_credit_03_<engine>_raw.json
├── candidate_state.json
├── candidate_url_records.json
├── candidates.csv
├── feature_evidence.csv
├── primary_url_acceptance.json
├── mandatory_url_delivery.json
├── orchestrated_result.json
├── review.md
└── single_product_diagnostics.xlsx
```

Only raw response files for credits actually used are created.

## Operations

```bash
./scripts/azureml_startup.sh

docker compose ps
docker compose logs -f --tail=200 agent browser

docker compose down
```

See [Automated Azure ML operations](docs/AZUREML_OPERATIONS.md).

## Validation

```bash
python scripts/validate_environment.py --env-file .env
python -m compileall -q src scripts
python -m json.tool inputs/private/toy_features.json >/dev/null
python -m json.tool notebooks/01_run_product_evidence.ipynb >/dev/null
PYTHONPATH=src pytest -q
docker compose config --quiet
```

## Documentation

- [Mandatory product URL delivery](docs/MANDATORY_PRODUCT_URL.md)
- [Adaptive three-credit SerpAPI search](docs/ADAPTIVE_SERPAPI_SEARCH.md)
- [Standardized source-authority hierarchy](docs/SOURCE_AUTHORITY_HIERARCHY.md)
- [Candidate precision and context control](docs/CANDIDATE_PRECISION_AND_CONTEXT.md)
- [Notebook usage and diagnostic contract](docs/NOTEBOOK_USAGE.md)
- [Single-product diagnostic interpretation](docs/SINGLE_PRODUCT_DIAGNOSTICS.md)
- [Agentic browser](docs/AGENTIC_BROWSER.md)
- [Automated Azure ML operations](docs/AZUREML_OPERATIONS.md)
- [Enterprise LLM configuration](docs/ENTERPRISE_LLM_CONFIGURATION.md)
- [Security contract](docs/SECURITY.md)
