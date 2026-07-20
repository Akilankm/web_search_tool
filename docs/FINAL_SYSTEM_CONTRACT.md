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

Both outcomes must include a shareable `business_judgement_review.md` and complete artifacts. The system must never fabricate a URL or convert search exhaustion into an unhandled software exception.

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

Manufacturer authority is conditional. A retailer becomes primary when no manufacturer page passes every mandatory gate.

## Search policy

```text
manufacturer_primary
→ requested_retailer_country or country_alternative
→ global_fallback
```

A retailer found during `manufacturer_primary` is retained but cannot stop the search before the official manufacturer opportunity is evaluated.

The standard bounded policy uses three SerpAPI credits. Exhaustion of this bounded route without a safe direct page produces the structured no-safe-URL review outcome.

## Multimodal evidence policy

The system may use submitted text and identifiers, static/rendered page text, browser screenshots, product/package images, structured page data, vision-derived feature evidence, source authority and URL durability.

Vision evidence is explicit:

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

Images may materially complete the selected URL's feature gate. The system reports `UNKNOWN_NOT_COUNTERFACTUALLY_TESTED` for whether text alone would have passed unless a real text-only counterfactual is executed.

## Business judgment artifact

Every terminal business result writes:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

Each step records:

```text
business question
observable evidence considered
evidence sources
visual evidence use and impact
agent judgment and status
alternatives considered and rejected
rejection reason
business rule applied
effect on next action
confidence
final outcome
```

Each step follows:

```text
observable evidence
→ explicit business rule
→ business judgment
→ resulting action
```

It does not expose hidden chain-of-thought.

For no-safe-URL results, the artifact explicitly states that the bounded search did not produce a safe direct page, no URL was fabricated, the status is `REVIEW_REQUIRED`, and the human should review identifiers, search stages and rejected evidence.

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
```

A structured no-safe-URL result additionally contains:

```text
resolution_outcome.code=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
resolution_outcome.category=CONTROLLED_BUSINESS_NO_MATCH
url_delivery.status=NO_SAFE_DIRECT_PRODUCT_URL_FOUND_AFTER_BOUNDED_SEARCH
url_delivery.delivered=false
```

`manufacturer_url` and `retailer_url` are stable keys and may be null.

## Runtime contract

```text
belief-url-resolution-v7-structured-no-url-review
```

Required capabilities:

```text
belief_driven_product_resolution=true
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
structured_no_url_review_outcome=true
mandatory_review_url_delivery=true
deterministic_browser_fallback_on_llm_error=true
notebook_self_healing_runtime=true
compatibility_patches_applied=true
```

## Result validation boundary

The notebook result validator accepts:

- a direct URL when `url_delivery.delivered=true`; or
- a blank URL only when the complete structured no-safe-URL review contract is present.

Any other blank/contradictory result is a hard `INCONSISTENT_URL_DELIVERY_RESULT` error. A response claiming `COMPLETED` without a delivered direct URL is always invalid.

## Three-notebook contract

Exactly these notebooks are supported:

```text
notebooks/01_single_product.ipynb
notebooks/02_batch_products.ipynb
notebooks/03_artifact_diagnostics.ipynb
```

### Single product

`01_single_product.ipynb` must:

- verify v7 readiness before paid search;
- accept one product input;
- expose URL/source fields or the explicit no-safe-URL outcome;
- expose `business_judgement_steps_df` and `visual_evidence_summary_df`;
- continue into diagnostics for no-safe-URL results rather than raising a traceback;
- link to `business_judgement_review.md` and `no_url_resolution.json` when applicable;
- export `single_product_diagnostics.xlsx`.

### Parallel batch

`02_batch_products.ipynb` must:

- accept mandatory `main_text` and `country_code`;
- preserve EAN/GTIN as text;
- generate or validate unique row IDs;
- execute with bounded parallelism;
- isolate genuine technical failures;
- classify structured no-safe-URL rows as `REVIEW_REQUIRED`, not `FAILED`;
- preserve one complete artifact per product;
- expose throughput, p50 and p95 latency;
- write outputs under `data/batch_runs/<run_id>/`.

Batch outputs:

```text
batch_input_normalized.csv
batch_results.csv
batch_failures.csv
batch_artifact_index.csv
batch_run_summary.json
```

### Interactive artifact diagnostics

`03_artifact_diagnostics.ipynb` must:

- accept an artifact directory or any file inside it;
- operate offline;
- reconstruct input, identity, uncertainty, search, candidates, visual evidence, gates, source choice and final outcome;
- render one interactive workspace with `Decision Map`, `Judgment Timeline`, `Candidates`, `Evidence` and `Artifacts`;
- write `artifact_diagnostics_interactive.html`;
- optionally write `artifact_diagnostic_report.md` and `artifact_diagnostic_workbook.xlsx`;
- never claim access to hidden chain-of-thought.

## Product artifact contract

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
└── single_product_diagnostics.xlsx
```

No-safe-URL outcomes additionally require:

```text
no_url_resolution.json
```

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

`NO_SAFE_DIRECT_PRODUCT_URL_FOUND` means no safe page was found within the configured bounded policy. It does not claim that no URL exists anywhere on the internet.

## Operational acceptance

A release is acceptable only when CI validates on Python 3.10 and 3.11:

- source compilation;
- all three notebook JSON files and every code cell;
- Docker Compose and Azure ML bootstrap;
- v7 runtime capability and result schema;
- manufacturer-primary and retailer-fallback behavior;
- structured no-safe-URL service and notebook behavior;
- unstructured no-URL hard-failure behavior;
- multimodal evidence reporting;
- business judgment Markdown generation;
- bounded batch normalization, concurrency and failure isolation;
- interactive artifact diagnostics;
- complete historical suite.

## Leadership communication

See:

- [Management and leadership demo guide](MANAGEMENT_DEMO_GUIDE.md)
- [Structured no-safe-URL outcome](STRUCTURED_NO_URL_OUTCOME.md)
- [Interactive artifact diagnostics](INTERACTIVE_ARTIFACT_DIAGNOSTICS.md)
- [Business judgment review](BUSINESS_JUDGEMENT_REVIEW.md)
- [Notebook usage](NOTEBOOK_USAGE.md)
- [Azure ML operations](AZUREML_OPERATIONS.md)
