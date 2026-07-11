# Product Evidence Harness — Operating Reference

This is the canonical operating reference for the one-credit, feature-aware workflow.

## 1. Design objective

The workflow answers two separate questions:

1. Which URLs represent the exact requested product?
2. Which accepted URLs contain evidence for the requested features?

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
| AI Mode search | Disabled |
| Second provider search | Disabled |
| Feature names in search query | Prohibited |
| Feature-aware scraping | Enabled after candidate discovery |
| Exact identity before feature use | Required |
| Wrong product with rich details | Rejected |
| Missing feature evidence | Reported, never invented |

A technical HTTP retry can consume another paid request, so the production workflow forces `SerpAPIConfig.max_retries=1`.

## 3. Responsibility boundaries

| Component | Inputs | Responsibility |
|---|---|---|
| Query builder | Product identity only | Construct one high-information search query |
| SerpAPI client | Query + market localization | Return one complete Google SERP response |
| SERP harvester | Raw response | Extract every useful external URL already present |
| Candidate store | URL occurrences | Normalize, deduplicate, retain cross-module support |
| Preflight ranker | Product identity + SERP metadata | Choose candidates worth scraping |
| Scraper | Candidate URL + product identity | Extract product-page evidence |
| Identity verifier | Product identity + scraped page | Accept or reject exact product and variant |
| Feature extractor | Accepted page + requested features | Map explicit evidence to requested features |
| Optional LLM reasoner | Scraped evidence + requested features | Resolve semantic ambiguity after scraping |
| Evidence-set selector | URL-level feature evidence | Choose one primary and minimum supplementary sources |

## 4. Product input

| Field | Required | Notes |
|---|:---:|---|
| `row_id` | Recommended | Used for output folder and audit trail |
| `main_text` | Yes | Primary product identity |
| `country_code` | Yes | Target market |
| `ean` / `gtin` | No | Exact identity anchor |
| `retailer_name` | No | Preferred retailer signal |
| `language_code` | No | Search and extraction language override |
| `region` | No | Optional market context |

The search query uses identity anchors only:

```text
EAN + product text + retailer signal + market localization
```

Feature names, feature descriptions, coding rules, and requested output fields are never added to the search query.

## 5. Feature input

### Required external format

```json
{
  "features_to_code": [
    "brand",
    "manufacturer",
    "product type",
    "minimum recommended age",
    {
      "name": "material",
      "description": "Primary material used to manufacture the toy"
    },
    "battery required"
  ]
}
```

The top-level JSON object supports exactly one key:

```text
features_to_code
```

Each feature entry must be either:

```json
"brand"
```

or:

```json
{
  "name": "material",
  "description": "Primary material used to manufacture the toy"
}
```

Feature objects support only:

| Field | Required | Meaning |
|---|:---:|---|
| `name` | Yes | Feature to extract and code |
| `description` | No | Additional semantic guidance for extraction |

No other user configuration is required. The following are derived internally:

| Internal field | Derivation |
|---|---|
| Feature ID | Uppercase normalized name, e.g. `play duration` -> `PLAY_DURATION` |
| Feature name | Exact supplied name |
| Value type | `text` |
| Criticality | `required` |
| Alias | Exact supplied name |
| Schema ID | Feature-file name |
| Coding-ready threshold | `100%` requested-feature coverage |

The optional description does not affect SerpAPI search. It is used only by post-search extraction and optional LLM reasoning.

### Adding features later

Append another string:

```json
{
  "features_to_code": [
    "brand",
    "manufacturer",
    "material",
    "country of origin"
  ]
}
```

Or add an optional description:

```json
{
  "features_to_code": [
    "brand",
    {
      "name": "country of origin",
      "description": "Country where the toy was manufactured, not the seller location"
    }
  ]
}
```

No source-code or schema-configuration change is required when a feature is added.

### Validation rules

The loader rejects:

- an empty `features_to_code` list;
- empty feature names;
- unsupported top-level keys;
- feature-object fields other than `name` and `description`;
- duplicate feature names after normalization;
- non-string and non-object feature entries.

The richer legacy schema remains readable only for backward compatibility with earlier integrations. New input files must use `features_to_code`.

## 6. One-response URL harvesting

The single paid Google response is harvested across useful URL-bearing sections:

- organic results and sitelinks;
- shopping and inline-shopping results;
- product results and product sites;
- knowledge graph links;
- local-result websites;
- selected question and image source pages.

The harvester never follows:

- pagination;
- related-search queries;
- SerpAPI detail links;
- Google search URLs;
- cached-page links;
- video and social URLs that do not represent product evidence.

The same normalized URL may appear in several modules. This increases preflight priority but never replaces scraped identity validation.

## 7. Candidate funnel

| Stage | Purpose |
|---|---|
| Harvest all response URLs | Maximize value from one paid request |
| Normalize and deduplicate | Collapse tracking variants and repeated links |
| Keep bounded candidate pool | Control local processing |
| Scrape top candidates | Retrieve evidence without another search |
| Use browser fallback where required | Handle dynamic product pages |
| Validate identity | Reject wrong product, variant, listing, or homepage |
| Extract requested features | Build URL-by-feature evidence matrix |
| Select evidence set | Retain only sources that add feature coverage |

Search-result rank is a prioritization signal, not a correctness decision.

## 8. Identity acceptance

A URL may support feature coding only after exact-product acceptance.

Common rejection conditions:

- EAN conflict;
- sibling variant or pack-size conflict;
- weak title or product-form match;
- category, search, homepage, login, consent, anti-bot, or soft-404 page;
- inaccessible or non-scrapable page;
- rendered content unrelated to the input product.

A rich page for the wrong product is always rejected.

## 9. Feature-aware evidence extraction

The extractor checks:

- product title and normalized product name;
- JSON-LD and product metadata;
- specification tables;
- normalized label-value attributes;
- descriptions and bullets;
- exact feature names;
- optional feature descriptions through the post-scrape semantic reasoner.

Deterministic extraction runs first. The optional LLM reasoner receives only already-scraped text and only features still missing deterministic evidence. It cannot search, follow URLs, or override identity rejection.

## 10. Primary and supplementary URLs

The system does not require one URL to contain every requested feature.

| Role | Meaning |
|---|---|
| Primary URL | Best exact-product identity source |
| Supplementary URL | Exact-product source adding an uncovered requested feature |
| Identity-only URL | Exact product but no additional feature gain |
| Rejected URL | Identity failed or page unusable |

The selector starts with the primary URL and adds only the exact-product source with the largest uncovered-feature gain. It stops when no source adds a requested feature or the supplementary limit is reached.

## 11. Coding readiness

All entries in `features_to_code` are treated as required.

```text
coding_ready =
    every requested feature is supported
    AND no selected feature has conflicting evidence
```

Possible statuses:

| Status | Meaning |
|---|---|
| `CODING_READY` | Exact product and all requested features accepted |
| `CODING_READY_WITH_FEATURE_REVIEW` | Useful evidence exists but gaps or conflicts remain |
| `IDENTITY_READY_EVIDENCE_INCOMPLETE` | Exact product found but evidence is insufficient |
| `NO_IDENTITY_ACCEPTED_SOURCE` | No candidate can be used for product coding |

## 12. Secure environment

```bash
cp .env.example .env
chmod 600 .env
python scripts/validate_environment.py --env-file .env
```

The validator runs before any paid request and rejects placeholder secrets, duplicate or malformed assignments, unsafe POSIX permissions, conflicting credential aliases, unsafe endpoints, and settings that could violate the one-credit contract.

See [`SECURE_ENVIRONMENT.md`](SECURE_ENVIRONMENT.md) for full handling and incident-response procedures.

## 13. Running

Single product:

```bash
python main.py \
  --row-id CH-TOY-0001 \
  --main-text "Hitster Original Musik-Partyspiel" \
  --country-code CH \
  --retailer-name "Orell Füssli" \
  --ean 8710126198872 \
  --feature-schema examples/toy_feature_schema.json
```

Batch:

```bash
python batch_main.py \
  --input data/products.xlsx \
  --feature-schema examples/toy_feature_schema.json \
  --output outputs/final_submission.csv \
  --workers 4
```

## 14. Outputs

Per product:

```text
output/<row_id>/
├── result.json
├── candidates.csv
├── feature_evidence.csv
└── review.md
```

Batch:

```text
outputs/
├── final_submission.csv
├── review_queue.csv
├── metrics.json
└── batch_summary.md
```

## 15. Validation

```bash
PYTHONPATH=src python -m compileall -q src scripts main.py batch_main.py
PYTHONPATH=src pytest -q tests/test_simple_feature_schema.py
PYTHONPATH=src pytest -q tests/test_serp_harvester.py
PYTHONPATH=src pytest -q tests/test_one_credit_feature_workflow.py
PYTHONPATH=src pytest -q
```
