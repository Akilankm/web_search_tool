# Product Evidence Platform

A production-oriented product identification and URL-resolution workflow for vendor product text.

The business outcome is explicit:

> Given `MAIN_TEXT`, `COUNTRY_CODE`, and optional `RETAILER_NAME` / `EAN`, return the strongest real product-detail URL that a reviewer can open in a normal browser and inspect.

The URL is the final deliverable. Product understanding, hypotheses, search decisions, scrapes, browser checks, and belief updates exist to make that URL defensible.

## Market decision contract

```text
1. Requested retailer in the requested country, when retailer_name is provided
2. Alternative retailer within the requested country
3. Global fallback
```

Without a retailer, the search starts in the requested-country market and then moves to global fallback. Each selected URL records its scope; a global result never silently substitutes for a country result.

## Product-identification trajectory

The workflow does not pass raw vendor text directly into search.

```text
MAIN_TEXT + COUNTRY_CODE
→ deterministic offline parsing
→ structured LLM interpretation without internet evidence
→ competing product hypotheses and uncertainty metrics
→ targeted SerpAPI action for the current market
→ bounded candidate scraping and browser validation
→ atomic evidence ledger
→ posterior belief update and path correction
→ production URL gate
→ final browser-openable information-rich URL
```

The LLM may generate hypotheses from pretrained knowledge, but those claims remain priors until page evidence supports them. Search results are candidates, not facts.

## Production URL contract

A promoted URL must be:

- real and external, never fabricated;
- directly browser-openable;
- reachable without resolving to a homepage, listing, search page, consent wall, or soft 404;
- an individual product-detail page;
- text-scrapable and information-rich;
- related to the intended exact product and variant;
- free of blocking EAN, model, size, pack, product-form, or variant conflicts;
- durable enough for team review rather than a signed intermediary URL.

The rendered page and raw scrape are both validated. A production page must expose a product name and useful evidence such as description, specifications, brand/manufacturer, images, GTIN, price, or availability.

| Outcome | Meaning |
|---|---|
| `COMPLETED` | Exact product URL passed strict browser, identity, richness, scrapability, and durability gates |
| `REVIEW_REQUIRED` | A real direct product URL was delivered, but one or more gates need a reviewer |
| `FAILED` | No safe direct product-page URL could be delivered or execution failed |

The workflow never substitutes a Google page, SerpAPI URL, category page, social page, PDF, image, or known-wrong sibling product. If no direct product URL exists after the bounded search, the run ends with `MANDATORY_PRODUCT_URL_NOT_FOUND` rather than an empty successful output.

## Search and scrape budget

```env
PRODUCT_HARNESS_MAX_SERPAPI_CREDITS=3
PRODUCT_HARNESS_MAX_FULL_SCRAPES=6
PRODUCT_HARNESS_MAX_SCRAPES_PER_DOMAIN=2
PRODUCT_HARNESS_SCRAPE_TOP_K_PER_STAGE=2
PRODUCT_HARNESS_EARLY_STOP_ON_WORKING_URL=true
```

The workflow stops early as soon as a production-ready URL passes the gate. Business planning should expect approximately one to two SerpAPI calls and four to seven scrape attempts per product; the maximum is a safety limit, not a target.

## Input

```python
product = {
    'row_id': 'ROW-001',
    'main_text': 'Vendor product main text',
    'country_code': 'CZ',
    'retailer_name': None,
    'ean': None,
    'language_code': None,
}
```

`main_text` and `country_code` are mandatory. EAN/GTIN must remain text.

## Belief-state artifacts

Before search, the runtime creates deterministic claims, two to five product hypotheses, assumptions, negative constraints, unknowns, ambiguity entropy, assumption burden, identity completeness, search readiness, and the next evidence objective.

After every scraped page, it records atomic evidence and updates hypothesis probabilities. Observable summaries are written instead of hidden chain-of-thought.

```text
data/artifacts/<row_id>/
├── product_belief.json
├── product_understanding.md
├── market_decision_path.md
├── belief_updates.md
├── evidence_ledger.jsonl
├── adaptive_search_trace.json
├── serp_credit_<n>_<engine>_raw.json
├── candidate_url_records.json
├── candidates.csv
├── primary_url_acceptance.json
├── mandatory_url_delivery.json
├── orchestrated_result.json
├── review.md
└── single_product_diagnostics.xlsx
```

## Azure ML setup

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool
cp .env.example .env
# Add real SerpAPI and enterprise LLM credentials.
./scripts/azureml_startup.sh
```

Open only:

```text
notebooks/01_run_product_evidence.ipynb
```

The committed default feature schema is `inputs/private/toy_features.json`.

## Required credentials

```env
SERPAPI_API_KEY=<organization-provided-value>
LLM_API_KEY=<organization-provided-value>
LLM_API_VERSION=<organization-provided-value>
LLM_ENDPOINT=<organization-provided-value>
LLM_DEPLOYMENT=<organization-provided-value>
```

Equivalent `AZURE_OPENAI_*` names are accepted.

## Important controls

```env
PRODUCT_HARNESS_ENABLE_BELIEF_LLM=true
PRODUCT_HARNESS_COUNTRY_FIRST=true
PRODUCT_HARNESS_ALLOW_GLOBAL_FALLBACK=true
PRODUCT_HARNESS_MAX_SERPAPI_CREDITS=3
PRODUCT_HARNESS_MAX_FULL_SCRAPES=6
PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_REQUIRE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_ALLOW_EAN_CONFLICT=false
PRODUCT_HARNESS_REJECT_EXPIRING_URLS=true
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

- [Belief-driven product resolution](docs/BELIEF_DRIVEN_PRODUCT_RESOLUTION.md)
- [Market decision hierarchy](docs/SOURCE_AUTHORITY_HIERARCHY.md)
- [Adaptive SerpAPI search](docs/ADAPTIVE_SERPAPI_SEARCH.md)
- [Mandatory product URL delivery](docs/MANDATORY_PRODUCT_URL.md)
- [Candidate precision and context control](docs/CANDIDATE_PRECISION_AND_CONTEXT.md)
- [Notebook usage](docs/NOTEBOOK_USAGE.md)
- [Agentic browser](docs/AGENTIC_BROWSER.md)
- [Azure ML operations](docs/AZUREML_OPERATIONS.md)
- [Enterprise LLM configuration](docs/ENTERPRISE_LLM_CONFIGURATION.md)
- [Security contract](docs/SECURITY.md)
