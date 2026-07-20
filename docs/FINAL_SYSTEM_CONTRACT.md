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

return:

1. a real direct product-detail `primary_url`;
2. qualified `manufacturer_url` and `retailer_url` references;
3. an explicit manufacturer-versus-retailer `source_selection`;
4. a shareable `business_judgement_review.md` recording the observable sequence of business judgments;
5. notebook surfaces for single execution, bounded parallel batch execution and offline artifact diagnostics.

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

## Multimodal evidence policy

The system uses:

- submitted text and identifiers;
- static and rendered page text;
- browser screenshots;
- product and package images;
- structured page data;
- vision-derived requested-feature evidence;
- source authority and URL durability.

Vision evidence is explicit and auditable:

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

Images may materially complete the selected URL's feature gate. The system reports `UNKNOWN_NOT_COUNTERFACTUALLY_TESTED` for whether text alone would have passed unless a real text-only counterfactual is executed.

## Business judgment artifact contract

Every `COMPLETED` or `REVIEW_REQUIRED` product run writes:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

Each judgment step contains:

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

## Human validation policy

The human coder receives the original input and `business_judgement_review.md`, reviews independently, and classifies:

- `IDENTICAL`;
- `PARTIALLY IDENTICAL`; or
- `NOT IDENTICAL`.

The reviewer records the first divergent step, their own judgment, missed or overweighted evidence, image interpretation and proposed system change. Behavioral validation requires sequence equivalence, not merely the same final URL.

## Stable product result schema

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

## Runtime contract

Current:

```text
belief-url-resolution-v6-business-judgement-review
```

Required capabilities:

```text
belief_driven_product_resolution=true
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
mandatory_review_url_delivery=true
deterministic_browser_fallback_on_llm_error=true
notebook_self_healing_runtime=true
compatibility_patches_applied=true
```

## Three-notebook contract

Exactly these notebooks are supported:

```text
notebooks/01_single_product.ipynb
notebooks/02_batch_products.ipynb
notebooks/03_artifact_diagnostics.ipynb
```

### Single product

`01_single_product.ipynb` must:

- verify the runtime before paid search;
- accept one product input;
- expose `final_decision_df` with `primary_url`, `primary_url_role`, `manufacturer_url`, `retailer_url` and `source_selection`;
- expose `business_judgement_steps_df` and `visual_evidence_summary_df` before engineering diagnostics;
- link to `business_judgement_review.md`;
- export `single_product_diagnostics.xlsx`.

### Parallel batch

`02_batch_products.ipynb` must:

- accept a CSV with mandatory `main_text` and `country_code`;
- preserve EAN/GTIN as text;
- generate or validate unique `row_id` values;
- execute products with bounded parallelism;
- isolate row failures;
- preserve one complete artifact per product;
- expose throughput, p50 and p95 product latency;
- write consolidated batch outputs under `data/batch_runs/<run_id>/`.

Batch outputs:

```text
batch_input_normalized.csv
batch_results.csv
batch_failures.csv
batch_artifact_index.csv
batch_run_summary.json
```

Product-level parallelism is bounded by the safe capacity of agent workers and browser contexts. Configured concurrency is not a throughput guarantee and must be load-tested.

### Artifact diagnostics

`03_artifact_diagnostics.ipynb` must:

- accept an artifact directory or any file inside it;
- operate offline without the running agent;
- reconstruct input, identity, uncertainty, search, candidate investigation, visual evidence, acceptance, source choice and final URL;
- render a high-level decision mindmap;
- render a chronological observable business-judgment timeline;
- expose search, candidate, feature, belief and evidence tables;
- inventory artifact files;
- write `artifact_diagnostic_report.md` and `artifact_diagnostic_workbook.xlsx`.

The diagnostic surface displays recorded evidence, actions, rules, judgments and conclusions. It must never claim access to hidden chain-of-thought.

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

Optional diagnostic outputs:

```text
artifact_diagnostic_report.md
artifact_diagnostic_workbook.xlsx
```

## Batch artifact contract

```text
data/batch_runs/<run_id>/
├── batch_input_normalized.csv
├── batch_results.csv
├── batch_failures.csv
├── batch_artifact_index.csv
└── batch_run_summary.json
```

The batch summary must distinguish configured parallelism from observed throughput and latency.

## Terminal outcomes

| Outcome | Contract |
|---|---|
| `COMPLETED` | Strict URL gates passed and the business judgment artifact was written |
| `REVIEW_REQUIRED` | A real direct review URL and business judgment artifact were delivered |
| `FAILED` | No safe direct product URL was found or execution failed |

The workflow never reports success with an empty product URL.

## Operational acceptance

A release is acceptable only when CI validates:

- Python source compilation;
- all three notebook JSON files and every code cell;
- Docker Compose and Azure ML bootstrap;
- runtime capabilities and result schema;
- manufacturer-primary and retailer-fallback behavior;
- multimodal evidence reporting;
- business judgment Markdown generation;
- bounded batch normalization, concurrency and failure isolation;
- artifact-path resolution, mindmap and report generation;
- full historical unit suite on Python 3.10 and 3.11.

## Leadership communication

The speaker-ready explanation of the business problem, workflow, assumptions, constraints, artifacts, selection policy, notebook choices, performance model, token/cost boundaries, KPI framework and change-impact areas is maintained in:

```text
docs/MANAGEMENT_DEMO_GUIDE.md
```

See [Management and leadership demo guide](MANAGEMENT_DEMO_GUIDE.md), [Business judgment review](BUSINESS_JUDGEMENT_REVIEW.md), [Notebook usage](NOTEBOOK_USAGE.md), and [Azure ML operations](AZUREML_OPERATIONS.md).
