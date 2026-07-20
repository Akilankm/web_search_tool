# Product Evidence Platform

A production-oriented, multimodal product-identification and URL-resolution system for incomplete vendor product text.

> Given `MAIN_TEXT`, `COUNTRY_CODE`, and optional `RETAILER_NAME`, `EAN/GTIN`, and `LANGUAGE_CODE`, identify the exact product, return the strongest defensible direct product URL, preserve manufacturer and retailer references, and expose the observable business judgments that produced the result.

## Core business contract

The system separates **product truth** from **commercial reference**:

- an exact, complete and durable official manufacturer page is preferred for product truth;
- a qualified retailer page is retained for local pack, language, price, availability and purchase context;
- a retailer becomes `primary_url` when no official manufacturer page passes every mandatory production gate.

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

Source authority never bypasses identity, browser, feature, scrapability or durability safety.

## Three-credit search route

```text
Credit 1: manufacturer_primary
Credit 2: requested_retailer_country when retailer_name is supplied
          otherwise country_alternative
Credit 3: global_fallback
```

A retailer found during credit 1 is retained but cannot stop the search before the official manufacturer opportunity is evaluated.

## Three supported notebooks

The notebook layer is intentionally separated by task.

| Notebook | Purpose | Requires running agent? |
|---|---|---:|
| `notebooks/01_single_product.ipynb` | Enter one product, execute the complete workflow, review the final URL, source choice, judgment sequence, visual evidence and engineering diagnostics | Yes |
| `notebooks/02_batch_products.ipynb` | Load a CSV, validate inputs, run products with bounded parallelism, isolate row failures, measure throughput and write consolidated outputs | Yes |
| `notebooks/03_artifact_diagnostics.ipynb` | Point to an existing product artifact or any file inside it and reconstruct the complete observable decision mindmap, chronological trace and diagnostic report | No |

### 1. Single product

```text
one product input
→ final_decision_df
→ business_judgement_steps_df
→ visual_evidence_summary_df
→ chronological decision timeline
→ candidate and feature evidence
→ single_product_diagnostics.xlsx
```

The primary file to share with a human coder remains:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

### 2. Parallel batch

Accepted CSV columns:

```text
required: main_text, country_code
optional: row_id, ean, retailer_name, language_code
```

An example is committed at:

```text
examples/batch_products.example.csv
```

Each row receives an isolated product artifact. Batch-level outputs are written under:

```text
data/batch_runs/<run_id>/
├── batch_input_normalized.csv
├── batch_results.csv
├── batch_failures.csv
├── batch_artifact_index.csv
└── batch_run_summary.json
```

Product-level concurrency defaults to the safe minimum of `AGENT_WORKERS` and `BROWSER_MAX_CONTEXTS`. The batch summary records elapsed time, products/minute, mean, p50 and p95 per-product latency, status counts and total SerpAPI credits used. Higher concurrency must be load-tested against browser memory, LLM and SerpAPI rate limits, and observed p95 latency.

### 3. Artifact diagnostics

The diagnostics notebook accepts either:

```text
data/artifacts/<row_id>/
```

or any file inside that directory. It reconstructs:

```text
submitted input
→ product interpretation
→ uncertainty
→ search route
→ candidate investigations
→ text and image evidence
→ acceptance and rejection rules
→ source authority choice
→ final URL
```

It writes:

```text
artifact_diagnostic_report.md
artifact_diagnostic_workbook.xlsx
```

and renders both a high-level decision mindmap and a chronological evidence-to-action timeline. It exposes recorded evidence, actions, rules, judgments and conclusions—not hidden chain-of-thought.

## Human-comparable business judgment artifact

Every `COMPLETED` or `REVIEW_REQUIRED` product run writes:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

It contains:

- submitted input;
- chronological business questions;
- observable identifier, text, rendered-page and visual evidence;
- explicit business rule applied;
- agent judgment and status;
- alternatives considered and rejected;
- rejection reason;
- effect on the next action;
- final `primary_url`, `manufacturer_url`, `retailer_url` and `source_selection`;
- a human form for `IDENTICAL`, `PARTIALLY IDENTICAL` or `NOT IDENTICAL`;
- the first divergent judgment and requested change.

Behavioral validation compares the sequence, not only whether the final URL happens to match.

## Multimodal evidence

The browser workflow can use:

- rendered screenshots;
- product galleries;
- package front/back images;
- visible specification and warning sections;
- structured page data;
- text extracted from the rendered product page.

Vision evidence is auditable:

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

The artifact distinguishes:

```text
YES_VISUAL_EVIDENCE_SUPPORTED_SELECTED_URL_FEATURE_GATE
VISUAL_EVIDENCE_USED_BUT_NOT_RECORDED_AS_DECISIVE_FOR_SELECTED_URL
NO_VISUAL_EVIDENCE_RECORDED
```

It does not claim that text alone would have failed unless a real text-only counterfactual was executed.

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

`manufacturer_url` and `retailer_url` are stable keys and may be `null` when no qualified source exists for that role.

## Outcomes

| Outcome | Meaning |
|---|---|
| `COMPLETED` | Strict identity, browser, feature, scrapability, durability and authority gates passed |
| `REVIEW_REQUIRED` | A real direct review URL was delivered but one or more judgments require human confirmation |
| `FAILED` | No safe direct product URL could be delivered or execution failed |

The system never reports success with an empty URL. When no safe direct page exists, the delivery contract reports `MANDATORY_PRODUCT_URL_NOT_FOUND`.

## Azure ML setup

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool
cp .env.example .env
# Add real SerpAPI and enterprise LLM values.
./scripts/azureml_startup.sh
```

The committed feature schema is:

```text
inputs/private/toy_features.json
```

A stale or incompatible runtime can be rebuilt with:

```bash
./scripts/azureml_startup.sh --clean-build
```

Current runtime contract:

```text
belief-url-resolution-v6-business-judgement-review
```

Required health capabilities include:

```text
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
```

The single and batch notebooks verify readiness before any paid search. The artifact diagnostics notebook works offline and does not require the Docker stack.

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
├── review.md
└── single_product_diagnostics.xlsx
```

The diagnostics notebook may add:

```text
artifact_diagnostic_report.md
artifact_diagnostic_workbook.xlsx
```

## Important controls

```env
PRODUCT_HARNESS_MAX_SERPAPI_CREDITS=3
PRODUCT_HARNESS_MAX_FULL_SCRAPES=6
PRODUCT_HARNESS_MAX_AGENTIC_CANDIDATES=3
PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_REQUIRE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_ENABLE_VISION_REASONING=true
PRODUCT_HARNESS_ALLOW_DETERMINISTIC_BROWSER_FALLBACK_ON_LLM_ERROR=true
PRODUCT_HARNESS_ALLOW_EAN_CONFLICT=false
PRODUCT_HARNESS_REJECT_EXPIRING_URLS=true
AGENT_WORKERS=2
BROWSER_MAX_CONTEXTS=3
```

Configured ceilings are safety controls, not guaranteed usage or a latency SLA.

## Validation

```bash
bash -n scripts/azureml_startup.sh
python -m compileall -q src scripts
python -m json.tool inputs/private/toy_features.json >/dev/null
PYTHONPATH=src pytest -q
docker compose config --quiet
```

CI validates all three notebook JSON documents and every code cell on Python 3.10 and 3.11.

## Documentation

- [Management and leadership demo guide](docs/MANAGEMENT_DEMO_GUIDE.md)
- [Final system contract](docs/FINAL_SYSTEM_CONTRACT.md)
- [Notebook usage](docs/NOTEBOOK_USAGE.md)
- [Business judgment review](docs/BUSINESS_JUDGEMENT_REVIEW.md)
- [Azure ML operations](docs/AZUREML_OPERATIONS.md)
- [Manufacturer-first source authority](docs/SOURCE_AUTHORITY_HIERARCHY.md)
- [Belief-driven product resolution](docs/BELIEF_DRIVEN_PRODUCT_RESOLUTION.md)
- [Adaptive SerpAPI search](docs/ADAPTIVE_SERPAPI_SEARCH.md)
- [Candidate precision and context control](docs/CANDIDATE_PRECISION_AND_CONTEXT.md)
- [Mandatory product URL delivery](docs/MANDATORY_PRODUCT_URL.md)
- [Agentic browser](docs/AGENTIC_BROWSER.md)
- [Enterprise LLM configuration](docs/ENTERPRISE_LLM_CONFIGURATION.md)
- [Security contract](docs/SECURITY.md)
