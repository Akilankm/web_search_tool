# Product Evidence Harness

A cost-bounded product evidence workflow for exact product URL discovery and feature-aware product coding.

## Core contract

```text
Product identity inputs
  -> exactly one SerpAPI search
  -> harvest every useful URL from that response
  -> normalize and rank the candidate pool
  -> scrape selected candidates locally
  -> verify exact product identity
  -> extract evidence for the known feature schema
  -> select one primary URL plus only useful supplementary URLs
  -> coding-ready or review-required decision
```

| Stage | Uses feature list? | Objective |
|---|:---:|---|
| SerpAPI search | No | Discover exact-product candidate URLs from identity inputs |
| Candidate preflight | No | Prioritize likely exact product pages |
| Scraping | Yes | Retain evidence relevant to required features |
| Evidence evaluation | Yes | Map page evidence to features and detect gaps/conflicts |
| Coding handoff | Yes | Produce feature values with URL-level provenance |

The production workflow enforces **one successful SerpAPI request per product**. It does not paginate, retry with another query, invoke AI Mode, or call a second search provider.

## Secure environment setup

```bash
cp .env.example .env
chmod 600 .env
```

Store SerpAPI and optional LLM credentials only in `.env` or in process-level secret injection. Never place keys in notebooks, YAML files, source code, command-line arguments, reports, or logs.

Before any paid request, both production runners call `validate_runtime_environment()`. It fails closed when it detects:

- missing, placeholder, malformed, or whitespace-containing secrets;
- duplicate `.env` keys;
- symlinked or group/world-readable local `.env` files;
- conflicting `AZURE_OPENAI_*` and `LLM_*` aliases;
- non-HTTPS, credential-bearing, or loopback LLM endpoints;
- invalid timeout, retry, token, temperature, or call-budget values;
- tournament mode, AI Mode, LLM search planning, or more than one organic search;
- configuration that violates the `one_credit_feature_aware` workflow identity.

The validation report contains only booleans and check names. Secret values are never returned.

### Optional LLM boundary

`PRODUCT_HARNESS_ENABLE_LLM_FEATURE_REASONING=false` by default. When enabled:

1. the product URL must already pass deterministic identity acceptance;
2. the page must already be scraped locally;
3. the LLM receives only bounded scraped-page evidence and missing feature definitions;
4. the LLM cannot search or follow URLs;
5. closed-set values must match the declared allowed values exactly;
6. every accepted LLM value must include a quote found in the scraped page text;
7. LLM confidence is capped below deterministic structured evidence;
8. calls are bounded by `PRODUCT_HARNESS_LLM_MAX_CALLS_PER_PRODUCT`.

This is defense-in-depth configuration hardening, not a claim of formal military or government security certification.

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

### Feature schema

```json
{
  "schema_id": "toy-board-game-v1",
  "pg_name": "BOARD_GAMES",
  "required_coverage_threshold": 0.8,
  "features": [
    {
      "feature_id": "MIN_AGE",
      "feature_name": "Minimum recommended age",
      "value_type": "integer",
      "criticality": "critical",
      "aliases": ["recommended age", "age from"]
    },
    {
      "feature_id": "MATERIAL",
      "feature_name": "Material",
      "value_type": "text",
      "criticality": "required"
    }
  ]
}
```

The feature list is intentionally **not added to the SerpAPI query**. It is introduced after candidate discovery and drives scraping, evidence extraction, coverage measurement, and supplementary-source selection.

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

schema = load_feature_schema("examples/toy_feature_schema.json")
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
result = harness.run(product, feature_schema=schema, return_trace=True)

print(result.best_match.product_url)
print(result.evidence_set.to_dict())
```

## Batch run

```bash
python batch_main.py \
  --input data/products.xlsx \
  --feature-schema examples/toy_feature_schema.json \
  --output outputs/final_submission.csv \
  --workers 4
```

Batch output includes:

- final product URL and review fallback;
- SerpAPI requests used;
- primary evidence URL;
- supplementary evidence URLs;
- required and critical feature coverage;
- missing and conflicting features;
- coding-ready status.

## Per-product artifacts

```text
output/<row_id>/
├── result.json
├── candidates.csv
├── feature_evidence.csv
└── review.md
```

`result.json` is the complete machine-readable decision. `review.md` is the first file for human review.

## Acceptance model

A candidate URL is evaluated in two independent stages:

1. **Identity acceptance:** exact product, correct variant, valid product page, accessible and scrapable.
2. **Feature utility:** explicit or structured evidence for one or more required features.

A rich page for the wrong product is always rejected. Multiple exact-product URLs may be retained only when they add feature evidence not covered by the primary source.

## Compatibility

`ProductEvidenceHarness` remains as the legacy-compatible review workflow for existing consumers. `LegacyTournamentProductEvidenceHarness` exposes the previous tournament implementation explicitly. New development should use `FeatureAwareProductEvidenceHarness`.

## Documentation and validation

The complete operating reference is in [`docs/README.md`](docs/README.md).

```bash
PYTHONPATH=src python -m compileall -q src main.py batch_main.py
PYTHONPATH=src pytest -q tests/test_environment_security.py
PYTHONPATH=src pytest -q tests/test_llm_feature_reasoner.py
PYTHONPATH=src pytest -q tests/test_serp_harvester.py
PYTHONPATH=src pytest -q tests/test_one_credit_feature_workflow.py
PYTHONPATH=src pytest -q
```
