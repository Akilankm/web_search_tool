# Product Evidence Platform

A production-oriented product-identification and URL-resolution system for vendor product text.

> Given `MAIN_TEXT`, `COUNTRY_CODE`, and optional `RETAILER_NAME` / `EAN`, return the strongest real product-detail URL that a reviewer can open in a normal browser and inspect.

The platform separates **product truth** from **commercial reference**:

- the official manufacturer or brand page is preferred for identity, specifications, warnings, compatibility, dimensions, and official feature definitions;
- a retailer page is retained for price, availability, local assortment, language, market, and purchase context;
- a retailer becomes primary whenever the manufacturer page fails any mandatory production gate.

The URL is the final deliverable. Product understanding, hypotheses, search decisions, scrapes, browser checks, feature evidence, and belief updates exist to make that URL defensible.

## Final decision contract

```text
exact product, model, form, variant, size, quantity and pack
→ browser-openable rendered individual product page
→ text scrapability and information richness
→ requested feature completeness
→ durable non-expiring URL
→ official manufacturer authority
→ requested retailer / requested-country retailer
→ global retailer or other exact product source
→ marketplace last resort
```

Source authority is applied only after identity and evidence safety.

A manufacturer page never wins merely because it is official. It must be the exact product, pass rendered-page and scrape validation, contain the requested feature evidence, and expose a durable URL.

## Three-credit search route

```text
Credit 1: manufacturer_primary
Credit 2: requested_retailer_country when retailer_name is supplied
          otherwise country_alternative
Credit 3: global_fallback
```

A retailer discovered during credit 1 is retained, but it cannot stop the search before the manufacturer opportunity has been evaluated.

Credit 2 may expand a real Shopping immersive-product token because this is a direct merchant-resolution action and is more precise than repeating a generic retailer query.

Credit 3 removes the country restriction while retaining exact-product requirements.

## Product-identification trajectory

```text
MAIN_TEXT + COUNTRY_CODE
→ deterministic offline parsing
→ structured no-web LLM interpretation
→ competing hypotheses and uncertainty metrics
→ manufacturer-first paid search
→ bounded candidate scraping and browser validation
→ atomic evidence ledger
→ posterior belief update and path correction
→ strict feature and URL gates
→ authority-ranked primary URL
→ manufacturer and retailer reference URLs
```

Model knowledge remains a prior until page evidence supports it. Search results are candidates, not facts.

## Stable result schema

Every `COMPLETED` or `REVIEW_REQUIRED` response contains:

```text
primary_url
primary_url_role
manufacturer_url
retailer_url
source_selection
primary_url_acceptance
url_delivery
product_identification
search.market_decision_path
```

### URL roles

| Field | Purpose |
|---|---|
| `primary_url` | Strongest product-truth page after strict gates and authority ranking |
| `primary_url_role` | `OFFICIAL_MANUFACTURER`, `RETAILER`, `MARKETPLACE`, or `OTHER_PRODUCT_SOURCE` |
| `manufacturer_url` | Strongest strictly qualified official manufacturer page, when available |
| `retailer_url` | Strongest strictly qualified commercial reference page, when available |
| `source_selection` | Explicit manufacturer-versus-retailer decision and reason |

## Manufacturer fallback rule

A retailer becomes `primary_url` when the manufacturer page is:

- missing;
- inaccessible or blocked;
- not text-scrapable;
- a homepage, category, family, collection, campaign, or search page;
- the wrong model, product form, variant, edition, size, quantity, or pack;
- missing requested feature evidence;
- transient or expiring.

Retailer fallback is a controlled production decision, not a lower-quality failure.

## Terminal outcomes

| Outcome | Meaning |
|---|---|
| `COMPLETED` | `primary_url` passed strict browser, identity, feature, scrapability, durability, and authority selection |
| `REVIEW_REQUIRED` | A real direct product URL was delivered, but one or more gates need human confirmation |
| `FAILED` | No safe direct product-page URL could be delivered, or execution failed |

The system never reports success with an empty URL.

If no direct product URL exists after the bounded search, the run ends with:

```text
MANDATORY_PRODUCT_URL_NOT_FOUND
```

## Search and scrape budget

```env
PRODUCT_HARNESS_MAX_SERPAPI_CREDITS=3
PRODUCT_HARNESS_MAX_FULL_SCRAPES=6
PRODUCT_HARNESS_MAX_SCRAPES_PER_DOMAIN=2
PRODUCT_HARNESS_SCRAPE_TOP_K_PER_STAGE=2
PRODUCT_HARNESS_EARLY_STOP_ON_WORKING_URL=true
```

Maximums are safety limits, not targets. The runtime preserves unused scrape capacity for later credits.

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

The committed default schema is:

```text
inputs/private/toy_features.json
```

## Self-healing notebook runtime

The first notebook cell verifies that its code and the local Docker agent expose the same runtime contract before any paid search.

The final compatibility version is:

```text
belief-url-resolution-v5-manufacturer-primary
```

The health response must include:

```text
manufacturer_first_primary_url=true
```

Default notebook behavior:

```python
AUTO_RECOVER_PLATFORM = True
CLEAN_BUILD_ON_RECOVERY = True
```

When the agent is missing, stale, or incompatible, the notebook runs the equivalent of:

```bash
./scripts/azureml_startup.sh --clean-build
```

This removes stale Compose containers, rebuilds agent and browser images without cache, recreates both services, and validates the complete runtime contract before product submission.

For manual recovery:

```bash
git checkout master
git pull origin master
./scripts/azureml_startup.sh --clean-build
```

Use `--no-build` only when the local images are already known to match the checkout.

## Browser LLM failure handling

When the agentic browser planner fails, including `403 Forbidden`, the system falls back to deterministic rendered-page acquisition:

```env
PRODUCT_HARNESS_ALLOW_DETERMINISTIC_BROWSER_FALLBACK_ON_LLM_ERROR=true
```

The fallback does not bypass exact-product, requested-feature, openability, scrapability, or durability gates. It only preserves usable browser evidence when planning LLM access fails.

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

## Artifact contract

```text
data/artifacts/<row_id>/
├── product_belief.json
├── product_understanding.md
├── market_decision_path.md
├── belief_updates.md
├── evidence_ledger.jsonl
├── adaptive_search_trace.json
├── candidate_url_records.json
├── candidates.csv
├── primary_url_acceptance.json
├── mandatory_url_delivery.json
├── source_selection.json
├── orchestrated_result.json
├── review.md
└── single_product_diagnostics.xlsx
```

`source_selection.json` is the authoritative audit record for the manufacturer-versus-retailer decision.

Observable summaries are written instead of hidden chain-of-thought.

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
PRODUCT_HARNESS_NOTEBOOK_AUTO_RECOVER_PLATFORM=true
PRODUCT_HARNESS_NOTEBOOK_CLEAN_BUILD_ON_RECOVERY=true
PRODUCT_HARNESS_ENABLE_BELIEF_LLM=true
PRODUCT_HARNESS_MAX_SERPAPI_CREDITS=3
PRODUCT_HARNESS_MAX_FULL_SCRAPES=6
PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_REQUIRE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_ALLOW_DETERMINISTIC_BROWSER_FALLBACK_ON_LLM_ERROR=true
PRODUCT_HARNESS_ALLOW_EAN_CONFLICT=false
PRODUCT_HARNESS_REJECT_EXPIRING_URLS=true
```

## Validation

```bash
bash -n scripts/azureml_startup.sh
python scripts/wait_for_stack.py --help
python -m compileall -q src scripts
python -m json.tool inputs/private/toy_features.json >/dev/null
python -m json.tool notebooks/01_run_product_evidence.ipynb >/dev/null
PYTHONPATH=src pytest -q
docker compose config --quiet
```

## Documentation

- [Final system contract](docs/FINAL_SYSTEM_CONTRACT.md)
- [Manufacturer-first source authority](docs/SOURCE_AUTHORITY_HIERARCHY.md)
- [Belief-driven product resolution](docs/BELIEF_DRIVEN_PRODUCT_RESOLUTION.md)
- [Adaptive SerpAPI search](docs/ADAPTIVE_SERPAPI_SEARCH.md)
- [Candidate precision and context control](docs/CANDIDATE_PRECISION_AND_CONTEXT.md)
- [Mandatory product URL delivery](docs/MANDATORY_PRODUCT_URL.md)
- [Notebook usage](docs/NOTEBOOK_USAGE.md)
- [Agentic browser](docs/AGENTIC_BROWSER.md)
- [Azure ML operations](docs/AZUREML_OPERATIONS.md)
- [Enterprise LLM configuration](docs/ENTERPRISE_LLM_CONFIGURATION.md)
- [Security contract](docs/SECURITY.md)
