# Product Evidence Platform

A production-oriented, multimodal product-identification and URL-resolution system for vendor product text.

> Given `MAIN_TEXT`, `COUNTRY_CODE`, and optional `RETAILER_NAME` / `EAN`, return the strongest real product-detail URL and a human-comparable record of the business judgments that produced it.

## Core business contract

The platform separates **product truth** from **commercial reference**:

- an exact, complete and durable official manufacturer page is preferred for product truth;
- a qualified retailer page is preserved for price, availability, local assortment, language and purchasing context;
- a retailer becomes `primary_url` when no manufacturer page passes every mandatory gate.

```text
exact product, model, form, variant, size, quantity and pack
→ browser-openable rendered individual product page
→ text scrapability and information richness
→ requested feature completeness
→ durable non-expiring URL
→ official manufacturer authority
→ requested retailer / requested-country retailer
→ global exact-product source
→ marketplace last resort
```

Source authority never bypasses identity, browser, feature, scrapability or durability safety.

## Three-credit search route

```text
Credit 1: manufacturer_primary
Credit 2: requested_retailer_country when retailer_name is supplied
          otherwise country_alternative
Credit 3: global_fallback
```

A retailer discovered during credit 1 is retained but cannot stop the search before the manufacturer opportunity is evaluated.

## Human-comparable business judgment artifact

Every completed or review-required run writes:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

This is the primary artifact to share with a human coder. It contains:

- the submitted input;
- the chronological business questions considered;
- observable text, identifier, rendered-page and visual evidence;
- the agent judgment at each step;
- the explicit business rule applied;
- alternatives considered and rejected;
- the effect on the next action;
- the strict URL gates;
- the manufacturer-versus-retailer `source_selection`;
- the final `primary_url`, `manufacturer_url` and `retailer_url`;
- a human response form for `IDENTICAL`, `PARTIALLY IDENTICAL` or `NOT IDENTICAL`;
- the first divergent step and recommended system change.

The artifact records evidence and decisions, not hidden chain-of-thought.

See [Business judgment review](docs/BUSINESS_JUDGEMENT_REVIEW.md).

## Multimodal evidence

The agentic browser receives rendered screenshots, discovers product galleries, downloads product/package images and may explicitly inspect images. Vision-derived evidence is recorded as:

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

Images can materially complete the selected URL's requested-feature gate. The review artifact distinguishes whether images were decisive, merely used during investigation, or not recorded. It does not claim that text alone would have failed unless an explicit counterfactual was run.

## Stable result schema

Every `COMPLETED` or `REVIEW_REQUIRED` result contains:

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
business_judgement_review
```

`manufacturer_url` and `retailer_url` are stable keys and may be `null` only when no qualified page exists for that role.

## Outcomes

| Outcome | Meaning |
|---|---|
| `COMPLETED` | Primary URL passed strict browser, identity, feature, scrapability, durability and authority selection |
| `REVIEW_REQUIRED` | A real direct product URL was delivered but requires human confirmation |
| `FAILED` | No safe direct product URL could be delivered or execution failed |

The system never reports success with an empty product URL. When no safe direct page exists it returns `MANDATORY_PRODUCT_URL_NOT_FOUND`.

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

The committed feature schema is:

```text
inputs/private/toy_features.json
```

## Runtime compatibility

Current contract:

```text
belief-url-resolution-v6-business-judgement-review
```

Previous contract retained for migration documentation:

```text
belief-url-resolution-v5-manufacturer-primary
```

Required health capabilities include:

```text
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
```

The notebook validates these capabilities before product submission and before any paid SerpAPI request. A stale agent is rebuilt using:

```bash
./scripts/azureml_startup.sh --clean-build
```

## Supported notebook workflow

```text
run product
→ review business_judgement_steps_df
→ review visual_evidence_summary_df
→ share business_judgement_review.md with the human coder
→ classify IDENTICAL / PARTIALLY IDENTICAL / NOT IDENTICAL
→ inspect engineering diagnostics only after a divergence is identified
```

The review workbook adds:

```text
business_judgments
visual_evidence_impact
source_selection
```

## Artifact contract

```text
data/artifacts/<row_id>/
├── business_judgement_review.md
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

`business_judgement_review.md` is the human validation artifact. `source_selection.json` is the final manufacturer-versus-retailer authority record. The other files are supporting engineering evidence.

## Important controls

```env
PRODUCT_HARNESS_NOTEBOOK_AUTO_RECOVER_PLATFORM=true
PRODUCT_HARNESS_NOTEBOOK_CLEAN_BUILD_ON_RECOVERY=true
PRODUCT_HARNESS_ENABLE_BELIEF_LLM=true
PRODUCT_HARNESS_MAX_SERPAPI_CREDITS=3
PRODUCT_HARNESS_MAX_FULL_SCRAPES=6
PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_REQUIRE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_ENABLE_VISION_REASONING=true
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
- [Business judgment review](docs/BUSINESS_JUDGEMENT_REVIEW.md)
- [Notebook usage](docs/NOTEBOOK_USAGE.md)
- [Azure ML operations](docs/AZUREML_OPERATIONS.md)
- [Manufacturer-first source authority](docs/SOURCE_AUTHORITY_HIERARCHY.md)
- [Belief-driven product resolution](docs/BELIEF_DRIVEN_PRODUCT_RESOLUTION.md)
- [Adaptive SerpAPI search](docs/ADAPTIVE_SERPAPI_SEARCH.md)
- [Candidate precision and context control](docs/CANDIDATE_PRECISION_AND_CONTEXT.md)
- [Mandatory product URL delivery](docs/MANDATORY_PRODUCT_URL.md)
- [Agentic browser](docs/AGENTIC_BROWSER.md)
- [Enterprise LLM configuration](docs/ENTERPRISE_LLM_CONFIGURATION.md)
- [Security contract](docs/SECURITY.md)
