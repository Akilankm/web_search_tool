# Product Evidence Harness

A cost-bounded workflow for exact product URL discovery and feature-aware product coding.

## Core workflow

```text
Product identity inputs
  -> exactly one SerpAPI search
  -> harvest every useful URL from that response
  -> normalize and rank the candidate pool
  -> scrape selected candidates locally
  -> verify exact product identity
  -> extract evidence for the requested feature list
  -> select one primary URL plus only useful supplementary URLs
  -> coding-ready or review-required decision
```

| Stage | Uses feature list? | Objective |
|---|:---:|---|
| SerpAPI search | No | Discover exact-product candidate URLs from identity inputs |
| Candidate preflight | No | Prioritize likely exact product pages |
| Scraping | Yes | Retain evidence relevant to requested features |
| Evidence evaluation | Yes | Map page evidence to features and detect gaps/conflicts |
| Coding handoff | Yes | Produce feature values with URL-level provenance |

The production workflow permits one SerpAPI request per product. It does not paginate, retry with another query, invoke AI Mode, or call a second search provider.

## Secure environment setup

```bash
cp .env.example .env
chmod 600 .env
python scripts/validate_environment.py --env-file .env
```

Store SerpAPI and optional LLM credentials only in `.env` or managed process-level secret injection. The production runners validate configuration before any paid request.

## Inputs

### Product input

| Field | Required | Purpose |
|---|:---:|---|
| `row_id` | Recommended | Stable product identifier |
| `main_text` | Yes | Product identity text |
| `country_code` | Yes | Target market |
| `ean` / `gtin` | No | Exact identity anchor |
| `retailer_name` | No | Preferred retailer signal |
| `language_code` | No | Search and extraction language override |

### Feature input

The external feature file is intentionally minimal.

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

Each entry must be one of:

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

Only `name` and optional `description` are accepted for a feature object. No schema ID, feature ID, value type, criticality, aliases, thresholds, or allowed values are required from the user.

The loader derives the internal representation automatically:

- a stable normalized feature ID, such as `minimum recommended age` -> `MINIMUM_RECOMMENDED_AGE`;
- the feature name exactly as supplied;
- `text` as the default internal value type;
- `required` as the default internal criticality;
- the feature name as the initial extraction alias;
- `100%` requested-feature coverage as the coding-ready threshold.

The description is optional and is used only as extraction context. Adding a new feature requires adding another string or `{name, description}` object to `features_to_code`.

The feature list is never added to the SerpAPI query. It is introduced only after candidate discovery and drives scraping, evidence extraction, coverage measurement, and supplementary-source selection.

## Single-product run

```bash
python main.py \
  --row-id CH-TOY-0001 \
  --main-text "Hitster Original Musik-Partyspiel" \
  --country-code CH \
  --retailer-name "Orell Füssli" \
  --ean 8710126198872 \
  --feature-schema examples/toy_feature_schema.json
```

Python API:

```python
import os

from product_evidence_harness import (
    FeatureAwareProductEvidenceHarness,
    HarnessConfig,
    LLMFeatureReasoner,
    ProductQuery,
    SerpAPIConfig,
    load_feature_schema,
    validate_runtime_environment,
)

environment = validate_runtime_environment(".env")
product = ProductQuery(
    row_id="CH-TOY-0001",
    main_text="Hitster Original Musik-Partyspiel",
    country_code="CH",
    retailer_name="Orell Füssli",
    ean="8710126198872",
)

features = load_feature_schema("examples/toy_feature_schema.json")
reasoner = None
if environment.llm_feature_reasoning_enabled:
    reasoner = LLMFeatureReasoner.from_env(
        max_calls=int(os.getenv("PRODUCT_HARNESS_LLM_MAX_CALLS_PER_PRODUCT", "2"))
    )

harness = FeatureAwareProductEvidenceHarness(
    serp_config=SerpAPIConfig.from_env(country_code="CH", language_code="de"),
    config=HarnessConfig.from_env(".env"),
    feature_reasoner=reasoner,
)
result = harness.run(product, feature_schema=features, return_trace=True)
```

## Batch run

```bash
python batch_main.py \
  --input data/products.xlsx \
  --feature-schema examples/toy_feature_schema.json \
  --output outputs/final_submission.csv \
  --workers 4
```

## Outputs

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

A candidate URL must first pass exact-product identity acceptance. Multiple URLs are retained only when an additional exact-product source adds evidence for requested features not covered by the primary URL.

## Validation

```bash
PYTHONPATH=src python -m compileall -q src scripts main.py batch_main.py
PYTHONPATH=src pytest -q tests/test_simple_feature_schema.py
PYTHONPATH=src pytest -q
```

The canonical operating reference is in [`docs/README.md`](docs/README.md), and secret-handling procedures are in [`docs/SECURE_ENVIRONMENT.md`](docs/SECURE_ENVIRONMENT.md).
