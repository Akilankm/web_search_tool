# Product Evidence Platform — Management and Leadership Demo Guide

> Open this document during the demo. It is a speaker-ready explanation of the business objective, workflow, three notebook surfaces, decisions, artifacts, performance boundaries and change points.

## Executive opening

The platform converts incomplete vendor product text into a defensible direct product URL. It does not accept the first search result. It interprets the product, searches the official manufacturer first, validates exact identity and requested features using text and images, applies deterministic acceptance gates, and writes a human-reviewable business judgment sequence.

The operating model has three notebooks:

```text
notebooks/01_single_product.ipynb
notebooks/02_batch_products.ipynb
notebooks/03_artifact_diagnostics.ipynb
```

## Business problem

Input such as `PKM ME04 WACHSENDES CHAOS BOOSTER` may omit the exact product form, edition, pack, EAN, retailer and language. A plausible URL may still be a category page, sibling variant, wrong pack, blocked page, expiring link or page missing the features required for coding.

The system converts ambiguity into a bounded evidence process rather than a search guess.

## Management value

| Need | Capability | Value |
|---|---|---|
| Exact product identification | Belief-driven interpretation and identity gates | Reduces silent miscoding |
| Product truth | Manufacturer-first source authority | Improves specification quality |
| Local context | Retailer/country fallback | Preserves pack, market and availability context |
| Packaging evidence | Screenshots and image reasoning | Recovers facts absent from text |
| Governance | `business_judgement_review.md` | Enables human sequence comparison |
| Throughput | Bounded parallel CSV notebook | Scales without removing per-product controls |
| Comprehension | Artifact mindmap notebook | Makes complex artifacts reviewable |

## Input and feature contract

Single input:

```python
product = {
    "row_id": "ROW-001",
    "main_text": "Vendor product text",
    "country_code": "CH",
    "retailer_name": None,
    "ean": None,
    "language_code": None,
}
```

Batch CSV requires `main_text` and `country_code`; `row_id`, `ean`, `retailer_name` and `language_code` are optional. The requested features come from `inputs/private/toy_features.json`.

## End-to-end architecture

```text
Azure ML notebook
→ Product Evidence Agent API
→ belief and search planner
→ SerpAPI candidate discovery
→ scraper and rendered browser
→ screenshot / image evidence
→ deterministic strict selector
→ product artifacts and human review
```

Current runtime:

```text
belief-url-resolution-v6-business-judgement-review
```

## Three notebook workflows

### `notebooks/01_single_product.ipynb`

Use for one product. It shows `final_decision_df`, `business_judgement_steps_df`, `visual_evidence_summary_df`, the chronological decision timeline, candidates, feature evidence and `single_product_diagnostics.xlsx`.

### `notebooks/02_batch_products.ipynb`

Use for CSV execution. It validates columns, preserves EAN as text, generates or validates unique row IDs, processes products with bounded parallelism, isolates row failures and writes:

```text
data/batch_runs/<run_id>/
├── batch_input_normalized.csv
├── batch_results.csv
├── batch_failures.csv
├── batch_artifact_index.csv
└── batch_run_summary.json
```

### `notebooks/03_artifact_diagnostics.ipynb`

Provide an artifact directory or any file inside it. It works offline and reconstructs input, identity, uncertainty, search, candidates, browser actions, text/image evidence, acceptance rules, source selection and final URL. It produces a mindmap, chronological trace, `artifact_diagnostic_report.md` and `artifact_diagnostic_workbook.xlsx`.

It exposes observable evidence, actions, rules, judgments and conclusions—not hidden chain-of-thought.

## Processing workflow and business judgments

```text
1. Validate mandatory input
2. Interpret likely product and unresolved distinctions
3. Credit 1: manufacturer_primary
4. Credit 2: requested_retailer_country or country_alternative
5. Credit 3: global_fallback
6. Deduplicate and preflight candidates
7. Scrape and open promising individual product pages
8. Use rendered text, structured data, screenshots and images
9. Apply exact identity, feature, browser, scrapability and durability gates
10. Select manufacturer or controlled retailer fallback
11. Write the result and human-comparable judgment artifact
```

## URL selection and acceptance

The final URL must be:

```text
exact product/model/form/variant/size/quantity/pack
+ browser-openable individual product page
+ text-scrapable and information-rich
+ complete for requested features
+ free from disqualifying conflicts
+ durable and non-expiring
```

Authority is applied only after these gates:

```text
official manufacturer
→ requested retailer / country retailer
→ global exact-product source
→ marketplace last resort
```

Outputs include `primary_url`, `primary_url_role`, `manufacturer_url`, `retailer_url` and `source_selection`. When no safe direct page exists, the system returns `MANDATORY_PRODUCT_URL_NOT_FOUND`.

## Multimodal evidence

The decision is not text-only. The browser can use rendered screenshots and product/package images. Vision evidence is recorded as:

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

`visual_evidence_summary_df` distinguishes whether images materially supported the selected URL, were used but not decisive, or were not recorded.

## Human-comparable decision artifact

Every `COMPLETED` or `REVIEW_REQUIRED` product writes:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

Each step records:

```text
business question
observable evidence
business rule
agent judgment
alternatives and rejection reason
next action
confidence and outcome
visual-evidence use
```

The reviewer marks `IDENTICAL`, `PARTIALLY IDENTICAL` or `NOT IDENTICAL` and identifies the first divergent step.

## Artifacts

Product artifacts include:

```text
business_judgement_review.md
product_belief.json
product_understanding.md
market_decision_path.md
belief_updates.md
evidence_ledger.jsonl
adaptive_search_trace.json
candidate_url_records.json
candidates.csv
primary_url_acceptance.json
mandatory_url_delivery.json
source_selection.json
orchestrated_result.json
single_product_diagnostics.xlsx
```

Diagnostic outputs add `artifact_diagnostic_report.md` and `artifact_diagnostic_workbook.xlsx`.

## Performance, latency, tokens and cost

Configured controls include three SerpAPI credits, bounded scrape/browser candidates, bounded LLM calls, `AGENT_WORKERS` and `BROWSER_MAX_CONTEXTS`.

**These are limits, not actual usage.** Early stopping may consume less.

The batch summary records `elapsed_seconds`, `throughput_products_per_minute`, mean, p50 and p95 per-product latency, status counts and total SerpAPI credits used.

`LLM_MAX_TOKENS` is a response ceiling, not actual usage. Per-call token logs exist, but one canonical per-product summary is not yet persisted. A fixed SLA must not be claimed until representative runs establish p50 and p95 values.

Recommended future artifacts:

```text
execution_metrics.json
llm_usage.json
```

Cost per product is the combination of search credits, input/output tokens, browser/compute time, storage and human review.

## Recommended KPIs

- final URL agreement rate;
- human judgment-sequence equivalence rate;
- first-divergent-step distribution;
- completion, review-required and failure rates;
- manufacturer-primary and retailer-fallback rates;
- image-evidence correctness;
- products/minute;
- p50 and p95 product latency;
- search credits, LLM calls and tokens per product;
- cost per completed product;
- artifact completeness.

## Assumptions

- each row represents one intended product;
- a direct public product page may exist;
- requested features are defined before execution;
- manufacturer authority is conditional on exactness and completeness;
- row IDs uniquely identify artifact directories;
- human feedback is available for behavioral validation.

## Constraints and non-goals

- pages may change, block automation or disappear;
- some products have no durable public URL;
- image availability does not prove image causality;
- bounded budgets do not test every possible source;
- the current job store is not an unbounded distributed queue;
- increasing concurrency without capacity changes can reduce reliability;
- the platform does not expose hidden chain-of-thought;
- configured limits are not measured SLA values.

## Failure handling

| Failure | Response |
|---|---|
| Missing input | Reject before paid search |
| Stale runtime | Clean rebuild when enabled |
| Browser-planner LLM failure | Deterministic rendered-page fallback where allowed |
| Manufacturer incomplete | Controlled retailer fallback |
| One batch row fails | Record failure and continue remaining rows |
| No safe URL | `FAILED` / `MANDATORY_PRODUCT_URL_NOT_FOUND` |
| Missing artifact evidence | Report absence; do not invent it |

## Change-impact map

| Requirement | Modification area |
|---|---|
| Change source priority | Source authority and final selector |
| Change requested features | Feature schema |
| Add search engine/credit | Adaptive search and environment validation |
| Change acceptance rules | Identity and strict URL gate modules |
| Increase batch throughput | Agent workers, browser contexts, queue architecture and load tests |
| Add batch columns | `batch_notebook_runtime.py` |
| Change mindmap/report | `artifact_diagnostics.py` and diagnostic notebook |
| Persist cost/latency | `execution_metrics.json` and `llm_usage.json` instrumentation |
| Change human review form | Business judgment artifact builder |

## Demo script

1. Open `notebooks/01_single_product.ipynb`; show the input and final URL fields.
2. Show the judgment sequence and `visual_evidence_summary_df`.
3. Explain manufacturer-first selection and retailer fallback.
4. Open `notebooks/02_batch_products.ipynb`; show CSV validation, bounded parallel execution and batch throughput.
5. Open `notebooks/03_artifact_diagnostics.ipynb`; pass an artifact path and show the mindmap and chronological trace.
6. End with the human review question: “What is the first judgment step where your process differs?”

## Pre-demo checklist and metric card

```text
[ ] latest master pulled
[ ] runtime v6 health is green
[ ] single product row_id is unique
[ ] batch CSV validated
[ ] diagnostic artifact path exists
[ ] business_judgement_review.md exists
[ ] no unsupported SLA or cost claim is shown
```

Record actual products submitted, completed/review/failed counts, elapsed time, products/minute, p50, p95, credits used, manufacturer/retailer selections, image-supported decisions and human-equivalent sequences.

## Leadership questions

**Is it a search wrapper?** No. Search discovers candidates; browser, evidence and deterministic gates decide the URL.

**Does it always prefer the manufacturer?** Only when the exact official page passes every mandatory gate.

**Does it use images?** Yes, and it records whether visual evidence was decisive.

**Can it process CSVs?** Yes, with bounded parallelism, row-level failure isolation and one full artifact per product.

**Can people understand the artifacts?** Yes. The diagnostic notebook reconstructs a mindmap and chronological observable decision trace.

## Leadership decisions for scale

Leadership should define the acceptable human-equivalence threshold, review/failure rates, batch volumes, concurrency and p95 targets, cost-per-product ceiling, artifact retention policy, governance owner and whether a persistent distributed queue is required.
