# Final Product Evidence System Contract

This is the canonical end-to-end production contract.

## Business objective

Given:

```text
MAIN_TEXT
COUNTRY_CODE
optional RETAILER_NAME
optional EAN/GTIN
optional LANGUAGE_CODE
```

return one of two valid business outcomes:

1. a defensible direct product-detail URL with manufacturer/retailer references and source decision; or
2. an explicit structured no-safe-URL `REVIEW_REQUIRED` result when bounded search cannot safely deliver a direct product page.

Both outcomes must include a shareable `business_judgement_review.md`, a recorded run configuration and complete artifacts. The system must never fabricate a URL or convert search exhaustion into an unhandled software exception.

## URL decision policy

```text
exact product, model, form, variant, size, quantity and pack
→ browser-openable rendered individual product page
→ text scrapability and information richness
→ requested-feature completeness
→ durable non-expiring URL
→ official manufacturer authority
→ requested retailer / requested-country retailer
→ global exact-product source
→ marketplace last resort
```

Manufacturer authority is conditional. A retailer or qualified global source becomes primary only when no manufacturer page passes every mandatory gate.

## Search and evidence policy

```text
manufacturer_primary
→ requested_retailer_country or country_alternative
→ global_fallback
```

The standard policy is bounded to three SerpAPI credits. Search exhaustion without a safe direct page produces the structured no-safe-URL review outcome.

Evidence may include submitted identifiers, static/rendered page text, structured page data, browser screenshots, product/package images, source authority and URL durability.

Vision-derived evidence is explicit:

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
belief-url-resolution-v8-leadership-demo
```

Required capabilities:

```text
belief_driven_product_resolution=true
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
structured_no_url_review_outcome=true
leadership_demo_runtime_options=true
mandatory_review_url_delivery=true
deterministic_browser_fallback_on_llm_error=true
notebook_self_healing_runtime=true
compatibility_patches_applied=true
```

## Leadership Streamlit contract

The leadership surface is:

```text
apps/leadership_demo.py
```

It must call the Product Evidence Agent API and must not implement independent search, browser, selection or artifact logic.

It must expose:

- runtime health and v8 contract;
- product input and feature set;
- live job stage;
- final URL/source decision or structured no-safe-URL result;
- strict gates;
- requested and actual budget usage;
- multimodal evidence impact;
- candidate rejection evidence;
- chronological business judgments;
- artifact inventory and downloads.

### Safe per-job budget boundary

Only these bounded values may be overridden per job:

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
- a blank URL only when the complete structured no-safe-URL review contract is present.

Any other blank or contradictory result is a hard `INCONSISTENT_URL_DELIVERY_RESULT` error. `COMPLETED` without a delivered direct URL is always invalid.

## Supported notebook contract

Exactly these notebooks are supported:

```text
notebooks/01_single_product.ipynb
notebooks/02_batch_products.ipynb
notebooks/03_artifact_diagnostics.ipynb
```

The first two use the running agent. The diagnostic notebook operates offline from persisted artifacts. Streamlit is an additional presentation surface, not a fourth notebook or alternate runtime.

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
| `COMPLETED` | A direct product URL passed every strict gate and artifacts were written |
| `REVIEW_REQUIRED` with URL | A real direct review URL was delivered but human confirmation remains |
| `REVIEW_REQUIRED` without URL | Bounded search found no safe direct page; trace and actions were preserved and no URL was fabricated |
| `FAILED` | Genuine software, configuration, dependency or response-contract failure |

`NO_SAFE_DIRECT_PRODUCT_URL_FOUND` states that no safe page was found within the configured bounded policy; it does not claim that no page exists anywhere on the internet.

## Operational acceptance

A release is acceptable only when CI validates on Python 3.10 and 3.11:

- source and Streamlit compilation;
- shell launchers;
- all three notebook JSON files and code cells;
- Docker Compose and Azure ML bootstrap;
- runtime capabilities and result schema;
- per-job option validation and concurrent isolation;
- manufacturer-primary and controlled fallback behavior;
- structured no-safe-URL service, notebook and UI behavior;
- unstructured no-URL hard-failure behavior;
- multimodal evidence reporting;
- business judgment generation;
- batch failure isolation;
- interactive artifact diagnostics;
- complete historical suite.

## Leadership communication

See:

- [Management and leadership demo guide](MANAGEMENT_DEMO_GUIDE.md)
- [Leadership Streamlit demo](STREAMLIT_LEADERSHIP_DEMO.md)
- [Structured no-safe-URL outcome](STRUCTURED_NO_URL_OUTCOME.md)
- [Interactive artifact diagnostics](INTERACTIVE_ARTIFACT_DIAGNOSTICS.md)
- [Business judgment review](BUSINESS_JUDGEMENT_REVIEW.md)
- [Notebook usage](NOTEBOOK_USAGE.md)
- [Azure ML operations](AZUREML_OPERATIONS.md)
