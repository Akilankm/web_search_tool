# Final Product Evidence System Contract

This document defines the canonical production contract.

## Objective

Given:

```text
MAIN_TEXT
COUNTRY_CODE
optional RETAILER_NAME
optional EAN/GTIN
optional LANGUAGE_CODE
```

return one of two valid business outcomes:

1. a defensible direct product-page URL with manufacturer and retailer references; or
2. a structured `REVIEW_REQUIRED` result when bounded search cannot safely deliver a direct product page.

Both outcomes must include `business_judgement_review.md`, `run_configuration.json` and the standard product artifacts. The system must never fabricate a URL or convert expected search exhaustion into an unhandled exception.

## URL acceptance policy

```text
exact product, model, form, variant, size, quantity and pack
→ browser-openable rendered individual product page
→ text scrapability and information richness
→ requested-feature completeness
→ durable non-expiring URL
→ source-authority selection
```

Source authority is evaluated only after identity, browser, feature, scrapability and durability gates pass.

## Source-authority order

```text
local official manufacturer
global official manufacturer
requested retailer in market
requested retailer global
major country retailer
global exact-product source
marketplace last resort
```

Manufacturer priority is conditional. An incomplete, inaccessible or mismatched official page cannot override a qualified retailer page.

## Search policy

```text
manufacturer_primary
→ requested_retailer_country or country_alternative
→ global_fallback
```

The standard policy is bounded to three paid search credits. Search exhaustion without a safe direct page produces the structured no-safe-URL result.

## Evidence policy

Accepted evidence may include:

```text
submitted identifiers
static page text
rendered page text
structured page data
browser screenshots
product and package images
source authority
URL durability
```

Vision-derived evidence must include:

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

## Business judgment artifact

Every terminal business result writes:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

Each step records observable evidence, evidence sources, visual use, explicit rule, agent judgment, alternatives, rejection reason, next action, confidence and outcome. It does not expose hidden chain-of-thought.

## Stable result schema

Every `COMPLETED` or `REVIEW_REQUIRED` result contains:

```text
product_identification
search.market_decision_path
primary_url
primary_url_role
manufacturer_url
retailer_url
source_selection
primary_url_acceptance
url_delivery
business_judgement_review
run_configuration
```

A structured no-safe-URL result additionally contains:

```text
resolution_outcome.code=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
resolution_outcome.category=CONTROLLED_BUSINESS_NO_MATCH
url_delivery.status=NO_SAFE_DIRECT_PRODUCT_URL_FOUND_AFTER_BOUNDED_SEARCH
url_delivery.delivered=false
```

## Runtime contract

```text
belief-url-resolution-v9-product-evidence-ui
```

Required capabilities:

```text
belief_driven_product_resolution=true
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
structured_no_url_review_outcome=true
per_job_runtime_controls=true
mandatory_review_url_delivery=true
deterministic_browser_fallback_on_llm_error=true
notebook_self_healing_runtime=true
compatibility_patches_applied=true
```

## Product Evidence Platform UI contract

The application is:

```text
apps/product_evidence_ui.py
```

It must call the Product Evidence Agent API and must not implement independent search, browser, selection or artifact logic.

It must expose:

```text
runtime health
product input and feature set
per-job runtime controls
live workflow stage
final URL or structured no-safe-URL result
strict acceptance gates
source-selection decision
multimodal evidence impact
candidate rejection evidence
chronological business judgments
artifact inventory and downloads
```

## Per-job runtime control boundary

Only these values may be overridden per job:

```text
serpapi_credits:                 1–3
full_scrapes:                    1–12
scrapes_per_domain:              1–4
planner_candidates:              3–20
agentic_candidates:              1–8
browser_turns_per_candidate:     1–12
browser_actions_per_candidate:   1–24
images_in_reasoning:             4–20
```

Overrides must be context-local, concurrency-safe, immutable during one run and persisted to:

```text
data/artifacts/<row_id>/run_configuration.json
```

The UI must not expose credentials, mutate `.env`, restart shared containers or change identity, requested-feature, EAN-conflict, URL-durability, source-authority or no-fabrication policies.

## Result validation boundary

The result validator accepts:

- a direct URL when `url_delivery.delivered=true`; or
- a blank URL only when the complete structured no-safe-URL contract is present.

Any other blank or contradictory result is a hard `INCONSISTENT_URL_DELIVERY_RESULT` error. `COMPLETED` without a delivered direct URL is always invalid.

## Supported notebooks

```text
notebooks/01_single_product.ipynb
notebooks/02_batch_products.ipynb
notebooks/03_artifact_diagnostics.ipynb
```

The first two use the running agent. The diagnostic notebook operates offline from persisted artifacts. The browser application is an additional execution surface, not an alternate runtime.

## Product artifact contract

```text
data/artifacts/<row_id>/
├── business_judgement_review.md
├── run_configuration.json
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
└── single_product_diagnostics.xlsx
```

No-safe-URL outcomes additionally require `no_url_resolution.json`.

Optional diagnostic outputs:

```text
artifact_diagnostics_interactive.html
artifact_diagnostic_report.md
artifact_diagnostic_workbook.xlsx
```

## Terminal outcomes

| Outcome | Contract |
|---|---|
| `COMPLETED` | A direct product page passed every strict gate and artifacts were written |
| `REVIEW_REQUIRED` with URL | A real direct reference was delivered but confirmation remains |
| `REVIEW_REQUIRED` without URL | No safe direct page was found within the bounded policy; trace preserved and no URL fabricated |
| `FAILED` | Software, configuration, dependency or response-contract failure |

`NO_SAFE_DIRECT_PRODUCT_URL_FOUND` means that no safe page was found within the configured bounded policy. It does not claim that no page exists anywhere on the internet.

## Release acceptance

A release is acceptable only when CI validates on Python 3.10 and 3.11:

```text
source and UI compilation
shell launchers
all notebook JSON and code cells
Docker Compose and Azure ML bootstrap
runtime capabilities and result schema
per-job control validation and concurrency isolation
manufacturer-primary and controlled fallback behavior
structured no-safe-URL behavior
multimodal evidence reporting
business judgment generation
batch failure isolation
interactive artifact diagnostics
complete regression suite
```

## Related documents

- [Feature reference](FEATURE_REFERENCE.md)
- [System workflow](SYSTEM_WORKFLOW.md)
- [Product Evidence Platform UI](PRODUCT_EVIDENCE_UI.md)
- [Structured no-safe-URL outcome](STRUCTURED_NO_URL_OUTCOME.md)
- [Business judgment review](BUSINESS_JUDGEMENT_REVIEW.md)
- [Notebook usage](NOTEBOOK_USAGE.md)
- [Azure ML operations](AZUREML_OPERATIONS.md)
