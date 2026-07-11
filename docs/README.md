# Product Evidence Harness — Operating Reference

This is the canonical operating documentation for the one-credit, feature-aware workflow.

## 1. Design objective

The workflow answers two separate questions:

1. **Which URLs represent the exact requested product?**
2. **Which accepted URLs contain enough evidence to code the known feature schema?**

These concerns must remain separated.

```text
Product identity
  -> one SerpAPI search
  -> candidate URL pool
  -> local scraping and identity validation
  -> feature-aware evidence extraction
  -> primary + supplementary evidence set
  -> coding-ready / review-required decision
```

## 2. Non-negotiable invariants

| Invariant | Enforcement |
|---|---|
| Maximum SerpAPI requests per product | `1` |
| Search pagination | Disabled |
| Alternate query retries | Disabled |
| AI Mode search | Disabled in the new workflow |
| Second provider search | Disabled |
| Feature names in search query | Prohibited |
| Feature-aware scraping | Enabled after candidate discovery |
| Exact identity before feature use | Required |
| Wrong product with rich details | Rejected |
| Missing feature evidence | Reported, never invented |

A technical HTTP retry can consume another paid request. Therefore the new workflow forces `SerpAPIConfig.max_retries=1` at runtime.

## 3. Responsibility boundaries

| Component | Inputs | Responsibility |
|---|---|---|
| Query builder | Product identity only | Construct one high-information search query |
| SerpAPI client | Query + market localization | Return one complete Google SERP response |
| SERP harvester | Raw response | Extract every useful external URL already present |
| Candidate store | Harvested URL occurrences | Normalize, deduplicate, retain cross-module support |
| Preflight ranker | Product identity + SERP metadata | Choose which candidates are worth scraping |
| Scraper | Candidate URL + product identity | Extract product page evidence |
| Identity verifier | Product identity + scraped page | Accept/reject exact product and variant |
| Feature extractor | Accepted page + feature schema | Map explicit evidence to required features |
| Optional LLM reasoner | Scraped evidence + feature schema | Resolve semantic ambiguity only after scraping |
| Evidence-set selector | URL-level feature evidence | Choose one primary and minimum supplementary sources |

## 4. Product input contract

| Field | Required | Notes |
|---|:---:|---|
| `row_id` | Recommended | Used for output folder and audit trail |
| `main_text` | Yes | Primary product identity |
| `country_code` | Yes | ISO-style market code |
| `ean` / `gtin` | No | Preserved as text; scientific notation is rejected as unsafe |
| `retailer_name` | No | Search/ranking preference, not a hardcoded domain map |
| `language_code` | No | Derived from country profile when omitted |
| `region` | No | Optional market context |

### Canonical search query

The query is built from identity anchors only:

```text
EAN + main product text + retailer signal + localized market terms
```

The following are deliberately excluded:

- feature names;
- allowed feature values;
- coding rules;
- feature criticality;
- prompts such as material, colour, age, dimensions, or battery.

Adding feature names to the search query can bias retrieval toward manuals, blogs, category pages, and generic informational documents instead of exact product pages.

## 5. Feature schema contract

The feature schema is introduced after search.

```json
{
  "schema_id": "toy-v1",
  "pg_name": "TOYS",
  "required_coverage_threshold": 0.8,
  "features": [
    {
      "feature_id": "BRAND",
      "feature_name": "Brand",
      "value_type": "text",
      "criticality": "critical",
      "aliases": ["brand", "manufacturer"]
    },
    {
      "feature_id": "BATTERY_REQUIRED",
      "feature_name": "Battery required",
      "value_type": "boolean",
      "criticality": "required",
      "allowed_values": ["YES", "NO"],
      "aliases": ["battery required", "batteries required"]
    }
  ]
}
```

### Supported criticality levels

| Value | Meaning |
|---|---|
| `critical` | Must be covered before automatic coding handoff |
| `required` | Included in the required-coverage threshold |
| `optional` | Useful but not required for readiness |
| `conditional` | Evaluated when applicable |

### Feature evidence statuses

| Status | Meaning |
|---|---|
| `STRUCTURED_FOUND` | Found in specifications, attributes, JSON-LD, or normalized fields |
| `EXPLICITLY_FOUND` | Found explicitly in visible page text |
| `LLM_FOUND` | Optional post-scrape semantic extraction |
| `NOT_FOUND` | No supporting evidence |
| `CONFLICTING_EVIDENCE` | More than one incompatible value was found |
| `NOT_APPLICABLE` | Feature does not apply |
| `NEEDS_REVIEW` | Evidence is present but ambiguous |

## 6. One-response URL harvesting

`GoogleSERPHarvester` inspects useful URL-bearing sections in the one paid response:

- `organic_results`;
- organic sitelinks;
- `shopping_results`;
- `inline_shopping_results`;
- `product_results`;
- `product_sites`;
- `knowledge_graph`;
- `local_results`;
- related-question source links;
- selected image source pages.

The harvester does not follow:

- Google pagination;
- related-search query links;
- SerpAPI detail links;
- Google search URLs;
- cached-page links;
- YouTube/video URLs.

### Within-response consensus

The same normalized URL may appear in multiple SERP modules. The candidate store retains all module labels:

```text
serp_organic_results
serp_shopping_results
serp_product_sites
```

Cross-module repetition increases preflight priority, but it does not prove correctness. Scraped identity evidence remains authoritative.

## 7. Candidate funnel

| Stage | Default purpose |
|---|---|
| Harvest all response URLs | Maximize value from the single paid request |
| Normalize and deduplicate | Collapse tracking variants and repeated links |
| Keep up to 30 candidates | Bound local processing |
| Scrape top 8 | Retrieve evidence without another search |
| Browser fallback where required | Handle dynamic pages |
| Validate every scraped candidate | Reject wrong product, variant, listing, or homepage |
| Select production URL | Exact, rendered, scrapable product page only |

Search-result rank is a prioritization signal. It is not the final decision.

## 8. Identity acceptance

A URL may support feature coding only after identity acceptance.

Typical rejection conditions:

- EAN conflict without independently strong exact identity;
- sibling variant or pack-size conflict;
- weak title/product-form match;
- category, search, homepage, login, consent, anti-bot, or soft-404 page;
- inaccessible or non-scrapable page;
- rendered content unrelated to the input product.

The existing deterministic identity verifier, rendered-page verifier, and production URL gate remain in use.

## 9. Feature-aware scraping and evidence extraction

The extractor prioritizes:

- product title and structured product name;
- JSON-LD and product metadata;
- specification tables;
- normalized label/value attributes;
- description and bullet text;
- feature aliases and multilingual labels;
- images and manuals through future feature-specific adapters.

The deterministic extractor runs first. An optional `FeatureReasoner` can be supplied for semantic extraction, but it is called only after search and scraping. The LLM cannot initiate another search and cannot override hard identity rejection.

## 10. Primary and supplementary URL selection

The system does not require one URL to contain every feature.

| URL role | Definition |
|---|---|
| Primary URL | Best exact-product identity source |
| Supplementary URL | Another exact-product source that adds uncovered feature evidence |
| Identity-only URL | Exact product but no material feature gain |
| Rejected URL | Identity failed or page unusable |

`EvidenceSetSelector` uses a bounded greedy set-cover strategy:

1. Start with the preferred production/review identity URL.
2. Measure covered feature IDs.
3. Add the exact-product source with the largest uncovered-feature gain.
4. Stop when there is no gain or the supplementary-source limit is reached.

The default maximum is three supplementary URLs.

## 11. Coding readiness

```text
coding_ready =
    all critical features covered
    AND required coverage >= schema threshold
    AND no feature conflicts
```

Possible statuses:

| Status | Meaning |
|---|---|
| `CODING_READY` | Identity and feature acceptance passed |
| `CODING_READY_WITH_FEATURE_REVIEW` | Useful evidence exists, but gaps or conflicts remain |
| `IDENTITY_READY_EVIDENCE_INCOMPLETE` | Exact product found, insufficient coding evidence |
| `NO_IDENTITY_ACCEPTED_SOURCE` | No candidate can be used for product coding |

## 12. Outputs

### Per-product packet

```text
output/<row_id>/
├── result.json
├── candidates.csv
├── feature_evidence.csv
└── review.md
```

| File | Purpose |
|---|---|
| `result.json` | Full product, URL, feature schema, evidence, and evidence-set decision |
| `candidates.csv` | Candidate-level identity and scrape audit |
| `feature_evidence.csv` | One row per URL × feature evidence item |
| `review.md` | Concise human-readable decision |

### Batch packet

```text
outputs/
├── final_submission.csv
├── review_queue.csv
├── metrics.json
└── batch_summary.md
```

Important batch fields include:

- `product_url`;
- `best_available_url`;
- `serpapi_requests_used`;
- `primary_evidence_url`;
- `supplementary_urls`;
- `selected_evidence_urls`;
- `required_feature_coverage`;
- `critical_feature_coverage`;
- `missing_features`;
- `conflicting_features`;
- `coding_status`;
- `coding_ready`.

## 13. Running the workflow

### Environment

```env
SERPAPI_API_KEY=...
PRODUCT_HARNESS_OUTPUT_DIR=output
PRODUCT_HARNESS_SCRAPE_CONCURRENCY=6
PRODUCT_HARNESS_STATIC_FETCH_FIRST=true
PRODUCT_HARNESS_BROWSER_FALLBACK_ONLY=true
```

### Single product

```bash
python main.py \
  --row-id CH-TOY-0001 \
  --main-text "Hitster Original Musik-Partyspiel" \
  --country-code CH \
  --retailer-name "Orell Füssli" \
  --ean 8710126198872 \
  --feature-schema examples/toy_feature_schema.json
```

### Batch

```bash
python batch_main.py \
  --input data/products.xlsx \
  --feature-schema examples/toy_feature_schema.json \
  --output outputs/final_submission.csv \
  --workers 4
```

### Python

```python
from product_evidence_harness import (
    FeatureAwareProductEvidenceHarness,
    HarnessConfig,
    ProductQuery,
    SerpAPIConfig,
    load_feature_schema,
)

schema = load_feature_schema("examples/toy_feature_schema.json")
product = ProductQuery(
    row_id="CH-TOY-0001",
    main_text="Hitster Original Musik-Partyspiel",
    country_code="CH",
    retailer_name="Orell Füssli",
    ean="8710126198872",
)

result = FeatureAwareProductEvidenceHarness(
    serp_config=SerpAPIConfig.from_env(country_code="CH", language_code="de"),
    config=HarnessConfig.from_env(".env"),
).run(product, feature_schema=schema, return_trace=True)
```

## 14. LLM boundary

The feature schema may be passed to an LLM only for post-scrape reasoning.

The LLM may:

- map retailer terminology to known features;
- interpret ambiguous descriptive language;
- identify evidence location;
- explain why a source is primary or supplementary;
- report conflicts and uncertainty.

The LLM may not:

- add feature names to the SerpAPI query;
- initiate additional searches;
- accept a URL that failed deterministic identity validation;
- invent a feature value when evidence is absent;
- hide source conflicts.

## 15. Compatibility and migration

The previous tournament workflow remains exported as `ProductEvidenceHarness` so existing notebooks and integrations do not break silently.

Use the new class for all new development:

```python
FeatureAwareProductEvidenceHarness
```

Migration strategy:

1. Add a feature-schema file.
2. Replace the harness import in the calling application.
3. Pass `feature_schema=` to `run`.
4. Read `result.evidence_set` and the new compact artifacts.
5. Retire tournament-only configuration after downstream consumers migrate.

The legacy implementation can be removed in a future major version after migration tests confirm no remaining consumers.

## 16. Validation

```bash
PYTHONPATH=src python -m compileall -q src main.py batch_main.py
PYTHONPATH=src pytest -q tests/test_serp_harvester.py
PYTHONPATH=src pytest -q tests/test_one_credit_feature_workflow.py
PYTHONPATH=src pytest -q
```

The critical regression properties are:

- maximum one SerpAPI call;
- no AI Mode search in the new workflow;
- multiple SERP modules harvested from one response;
- exact identity required before feature acceptance;
- supplementary URL selected only when it adds feature coverage;
- coding readiness calculated from critical coverage, required coverage, and conflicts.
