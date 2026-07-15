# Product Evidence Platform

A production-oriented product URL and feature-evidence workflow for Azure ML Compute Instances.

## Production objective

The platform uses a maximum of three SerpAPI credits to obtain a direct, durable, exact-product URL that can pass live scrape and browser validation.

The credits are **three adaptive decisions**, not three predefined organic searches:

```text
product identity
→ determine highest unresolved source-authority tier
→ LLM selects one suitable SerpAPI engine and query
→ normalize direct URLs, product tokens, IDs and images
→ precision-gated scrape and exact-product validation
→ stop when a strong working URL is found, otherwise replan
```

The LLM may choose Google Search, Google Shopping, Google AI Mode, Google Immersive Product, Google Lens, or a supported retailer-native engine. Deterministic code enforces the budget, validates action parameters, prevents duplicate searches, rejects weak URLs before scraping, and remains authoritative for final URL acceptance.

See [Adaptive three-credit SerpAPI search](docs/ADAPTIVE_SERPAPI_SEARCH.md), [Standardized source-authority hierarchy](docs/SOURCE_AUTHORITY_HIERARCHY.md), [Candidate precision and context control](docs/CANDIDATE_PRECISION_AND_CONTEXT.md), and [Agentic browser](docs/AGENTIC_BROWSER.md).

## Standardized source hierarchy

When `retailer_name` is supplied, that retailer receives first priority. Otherwise the internal standard is:

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
2. **Final selection:** among exact working URLs, source tier outranks richness or confidence differences.

A valid manufacturer URL therefore outranks a richer Amazon/eBay URL unless the marketplace was explicitly requested.

## One-command Azure ML bootstrap

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool
cp .env.example .env
# Edit only the SerpAPI and LLM credential values.
./scripts/azureml_startup.sh
```

Then open:

```text
notebooks/01_run_product_evidence.ipynb
```

The repository includes `inputs/private/toy_features.json`. No feature-file copy, manual Docker command, permission override, or separate notebook dependency setup is required.

## Required credentials

```env
SERPAPI_API_KEY=<organization-provided-value>
LLM_API_KEY=<organization-provided-value>
LLM_API_VERSION=<organization-provided-value>
LLM_ENDPOINT=<organization-provided-value>
LLM_DEPLOYMENT=<organization-provided-value>
```

Equivalent `AZURE_OPENAI_*` names are accepted. Enterprise LLM values are treated as opaque: startup validates presence, not key length, endpoint shape or deployment naming.

## Adaptive search controls

Keep the production defaults in `.env.example`:

```env
PRODUCT_HARNESS_WORKFLOW=three_stage_feature_aware
PRODUCT_HARNESS_MAX_SERPAPI_CREDITS=3
PRODUCT_HARNESS_ALLOWED_SEARCH_ENGINES=google,google_shopping,google_ai_mode,google_immersive_product,google_lens,amazon,ebay,walmart,home_depot
PRODUCT_HARNESS_ENABLE_LLM_SEARCH_PLANNING=true
PRODUCT_HARNESS_ENABLE_LLM_SEARCH_FEEDBACK=true
PRODUCT_HARNESS_REQUIRE_LLM_SEARCH_PLANNING=true
PRODUCT_HARNESS_EARLY_STOP_ON_WORKING_URL=true
PRODUCT_HARNESS_SEARCH_PLANNER_MAX_CANDIDATES=8
```

`PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES` and `PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES` remain only for backward-compatible `.env` parsing. The unified three-credit limit is authoritative.

### Engine roles

| Engine | Role |
|---|---|
| `google` | Requested retailer, manufacturer, exact EAN/model and direct-page recovery |
| `google_shopping` | Major local retailer/product identity and merchant discovery |
| `google_immersive_product` | Expand a product token into direct store URLs |
| `google_ai_mode` | Resolve manufacturer/product ambiguity and collect cited URLs |
| `google_lens` | Visual matching when a real product image is available |
| `amazon`, `ebay`, `walmart`, `home_depot` | Requested-retailer native discovery only |

Immersive Product is available only after a real token is returned. Lens is available only after a real image URL is returned. Retailer-native engines are exposed only when the requested retailer matches.

## Precision-gated acquisition

All engine responses enter one canonical candidate pool:

```text
raw result occurrence
→ canonical URL
→ source-authority classification
→ URL-type and product-identity admission
→ bounded full scrape
→ evidence-utility validation
→ bounded browser escalation
→ strict product URL decision
```

```env
PRODUCT_HARNESS_MAX_FULL_SCRAPES=6
PRODUCT_HARNESS_MAX_SCRAPES_PER_DOMAIN=2
PRODUCT_HARNESS_MIN_PREFLIGHT_SCORE=0.28
```

Homepages, search pages, categories, collections, social pages, documents, media files and low-identity URLs remain visible in the audit ledger but do not consume a full scrape or LLM browser session.

A successful HTTP response is not automatically a useful scrape. The runtime separately records:

| Field | Meaning |
|---|---|
| `fetch_success` | Acquisition completed technically |
| `content_extracted` | Readable content was obtained |
| `technical_scrapable` | Technical scrape checks passed |
| `product_page_likelihood` | Evidence of an individual product page |
| `content_utility_score` | Product-identity/evidence usefulness |
| `scrape_accepted` | Suitable for downstream reasoning |

## Context-efficient browser escalation

The browser is an escalation tool after intelligent search, not the source of all search intelligence.

```env
PRODUCT_HARNESS_MAX_AGENTIC_CANDIDATES=3
PRODUCT_HARNESS_AGENTIC_MAX_TURNS_PER_CANDIDATE=4
PRODUCT_HARNESS_AGENTIC_MAX_ACTIONS_PER_CANDIDATE=6
PRODUCT_HARNESS_AGENTIC_OBSERVATION_CHARS=4000
PRODUCT_HARNESS_AGENTIC_MAX_ELEMENTS=15
PRODUCT_HARNESS_AGENTIC_MAX_IMAGES=8
```

The browser prompt uses unresolved features, delta text, relevance-ranked controls/images, and compact prior actions.

## Working URL contract

A top-level `primary_url` is returned only when the URL is:

- external and direct;
- an individual product-detail page;
- browser-openable and not blocked;
- technically and semantically scrapable;
- the exact product and variant;
- durable and non-expiring;
- complete for the configured final evidence policy.

Shopping intermediaries, SerpAPI links, search pages, category pages and derived URLs are never accepted without live validation.

No system can truthfully guarantee that every discontinued, private, app-only or unindexed product has a public page. The platform therefore guarantees **no fabricated or unvalidated URL**, while aggressively using the three-credit budget to maximize working-URL recovery.

## One URL, one authoritative row

Two table grains are preserved intentionally:

- `search.serp_results` / `serp_results_df`: one row per result occurrence from every engine and credit;
- `candidate_records` / `candidate_url_records.json` / `candidates.csv` / `results_df`: one row per canonical URL.

Every candidate row includes source authority fields such as:

```text
source_tier
source_tier_name
source_role
country_alignment
requested_retailer_match
manufacturer_match
major_country_retailer
marketplace
higher_priority_tier_exhausted
selected_within_tier
```

Every canonical URL ends with one explicit RCA status such as:

```text
SERP_REJECTED_URL_TYPE
SERP_REJECTED_LOW_IDENTITY
QUALIFIED_NOT_SCRAPED_BUDGET
SCRAPE_FAILED
SCRAPE_LOW_UTILITY
IDENTITY_REJECTED
BROWSER_BLOCKED
FEATURE_INCOMPLETE
ELIGIBLE_NOT_SELECTED
REVIEW_SELECTED
STRICT_SELECTED
```

## Notebook EDA and RCA

The supported notebook exposes:

| DataFrame | Purpose |
|---|---|
| `search_actions_df` | One row per paid adaptive credit and LLM decision |
| `source_hierarchy_df` | Target source tier, engine and outcome per credit |
| `search_engine_summary_df` | Per-engine yield and conversion |
| `search_handles_df` | Product tokens, IDs and image handles |
| `search_decision_rca_df` | Budget, hierarchy, planner fallback and stop RCA |
| `serp_results_df` | Raw cross-engine result occurrences |
| `results_df` | One row per canonical candidate URL with source authority |
| `source_tier_summary_df` | Candidate/scrape/identity/selection conversion by tier |
| `funnel_df` | Search-to-selection conversion |
| `rejection_reasons_df` | Normalized candidate blockers |
| `selection_rca_df` | Final primary-URL decision |

Charts show engine credit allocation, source-tier routing, engine candidate yield, best-candidate confidence after each credit, candidate funnel, source quality, rejection reasons and feature coverage.

The Excel workbook is written to:

```text
data/artifacts/<row_id>/single_product_diagnostics.xlsx
```

## Search artifacts

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
├── review.md
└── single_product_diagnostics.xlsx
```

Only the raw files for credits actually used are created.

## Operations

```bash
./scripts/azureml_startup.sh

docker compose ps
docker compose logs -f --tail=200 agent browser

docker compose down
```

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

- [Adaptive three-credit SerpAPI search](docs/ADAPTIVE_SERPAPI_SEARCH.md)
- [Standardized source-authority hierarchy](docs/SOURCE_AUTHORITY_HIERARCHY.md)
- [Candidate precision and context control](docs/CANDIDATE_PRECISION_AND_CONTEXT.md)
- [Notebook usage and diagnostic contract](docs/NOTEBOOK_USAGE.md)
- [Single-product diagnostic interpretation](docs/SINGLE_PRODUCT_DIAGNOSTICS.md)
- [Agentic browser](docs/AGENTIC_BROWSER.md)
- [Automated Azure ML operations](docs/AZUREML_OPERATIONS.md)
- [Enterprise LLM configuration](docs/ENTERPRISE_LLM_CONFIGURATION.md)
- [Security contract](docs/SECURITY.md)
