# Notebook Usage Contract

The repository has exactly three supported notebooks. Each notebook owns one job and should remain focused.

```text
notebooks/01_single_product.ipynb
notebooks/02_batch_products.ipynb
notebooks/03_artifact_diagnostics.ipynb
```

## Notebook selection

| Need | Notebook | Runtime required |
|---|---|---:|
| Resolve and inspect one product | `01_single_product.ipynb` | Yes |
| Process a CSV with bounded parallel product execution | `02_batch_products.ipynb` | Yes |
| Understand an existing product artifact using mindmaps and decision diagnostics | `03_artifact_diagnostics.ipynb` | No |

## Azure ML setup

```bash
git checkout master
git pull origin master
cp .env.example .env
# Add real SerpAPI and enterprise LLM values.
./scripts/azureml_startup.sh --clean-build
```

Current runtime contract:

```text
belief-url-resolution-v6-business-judgement-review
```

Required health capabilities:

```text
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
```

The single and batch notebooks verify readiness before paid search and can rebuild a stale runtime. The diagnostic notebook works offline from files already produced.

---

# 1. Single product notebook

```text
notebooks/01_single_product.ipynb
```

## Input

```python
FEATURE_SET = DEFAULT_FEATURE_SET
RUN_SINGLE_PRODUCT = False
product = {
    "row_id": "ROW-001",
    "main_text": "Vendor product main text",
    "country_code": "CH",
    "retailer_name": None,
    "ean": None,
    "language_code": None,
}
```

`main_text` and `country_code` are mandatory. Keep EAN/GTIN as text and use a unique `row_id` for each execution.

## Processing route

```text
input interpretation
→ uncertainty definition
→ manufacturer_primary
→ requested_retailer_country or country_alternative
→ global_fallback
→ candidate scraping and rendered browser investigation
→ text and visual feature evidence
→ strict identity, browser, scrapability, feature and durability gates
→ manufacturer-first source authority
→ primary_url + manufacturer_url + retailer_url + source_selection
→ business_judgement_review.md
```

## First review view

The notebook displays these before technical diagnostics:

| Object | Purpose |
|---|---|
| `final_decision_df` | Final URL, role, manufacturer and retailer references, source-selection reason and acceptance status |
| `business_judgement_steps_df` | Ordered business questions, observable evidence, rule, judgment and next action |
| `visual_evidence_summary_df` | Whether images/screenshots were used and whether they supported the selected URL |
| `business_judgement_review.md` | Shareable human-comparison document |

The artifact is stored at:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

Ask the human coder to classify the sequence as `IDENTICAL`, `PARTIALLY IDENTICAL` or `NOT IDENTICAL` and record the first divergent judgment.

## Workbook

```text
data/artifacts/<row_id>/single_product_diagnostics.xlsx
```

Sheets include:

```text
final_decision
overview
product_input
business_judgments
visual_evidence_impact
search_route
candidates
feature_evidence
evidence_ledger
belief_updates
artifact_inventory
```

---

# 2. Parallel CSV batch notebook

```text
notebooks/02_batch_products.ipynb
```

## CSV contract

Required:

```text
main_text
country_code
```

Optional:

```text
row_id
ean
retailer_name
language_code
```

The loader accepts common aliases such as uppercase names, spaces, `GTIN`, `retailer`, `country` and `language`. EAN is loaded as text. Before paid search it rejects:

- missing mandatory columns;
- blank mandatory values;
- duplicate `row_id` values;
- an empty CSV.

Example:

```text
examples/batch_products.example.csv
```

## Bounded parallel execution

```python
MAX_PARALLEL_PRODUCTS = recommended_batch_parallelism()
```

Product-level concurrency is bounded by:

```text
min(AGENT_WORKERS, BROWSER_MAX_CONTEXTS, 8)
```

Each product still applies its own strict three-credit search, scrape, browser and LLM limits. One product failure is captured in its row and does not abort remaining products.

Parallelism should be increased only after measuring:

- browser memory and context saturation;
- enterprise LLM rate limits;
- SerpAPI limits;
- p50 and p95 per-product latency;
- throughput in products/minute;
- review-required and failed rates.

## Batch result fields

The consolidated result includes:

```text
row_id
main_text
ean
retailer_name
country_code
job_status
primary_url
primary_url_role
manufacturer_url
retailer_url
selection_reason
strictly_verified
search_credits_used
image_influenced_final_decision
elapsed_seconds
artifact_dir
business_judgement_review_path
error
```

## Batch outputs

```text
data/batch_runs/<run_id>/
├── batch_input_normalized.csv
├── batch_results.csv
├── batch_failures.csv
├── batch_artifact_index.csv
└── batch_run_summary.json
```

`batch_run_summary.json` reports:

```text
input_rows
max_parallel
status_counts
successful_or_review_rows
failed_rows
elapsed_seconds
throughput_products_per_minute
mean_product_elapsed_seconds
p50_product_elapsed_seconds
p95_product_elapsed_seconds
total_serpapi_credits_used
```

The batch notebook does not merge product evidence into one opaque trace. Each row preserves its own complete artifact under `data/artifacts/<row_id>/`.

---

# 3. Artifact diagnostics notebook

```text
notebooks/03_artifact_diagnostics.ipynb
```

## Input

Set `ARTIFACT_PATH` to either the product artifact directory or any file inside it:

```python
ARTIFACT_PATH = PROJECT_ROOT / "data" / "artifacts" / "ROW-001"
RUN_DIAGNOSTICS = False
```

Examples that resolve to the same artifact:

```text
data/artifacts/ROW-001/
data/artifacts/ROW-001/orchestrated_result.json
data/artifacts/ROW-001/candidates.csv
data/artifacts/ROW-001/business_judgement_review.md
```

## What it reconstructs

The notebook reads the artifact and rebuilds the observable workflow:

```text
submitted input
→ product identity and uncertainty
→ manufacturer, local and global search route
→ candidate discovery and rejection funnel
→ rendered browser actions
→ text and image evidence
→ requested-feature coverage
→ strict URL gates
→ manufacturer-versus-retailer choice
→ final result
```

It renders:

- an executive overview;
- a complete decision mindmap;
- a chronological business-judgment timeline;
- search route tables;
- candidate acceptance and rejection evidence;
- feature evidence and visual extraction method;
- belief updates and evidence ledger;
- artifact inventory.

This is an audit of recorded evidence, actions, rules, judgments and conclusions. It does not expose hidden chain-of-thought.

## Diagnostic outputs

The notebook writes into the same product artifact directory:

```text
artifact_diagnostic_report.md
artifact_diagnostic_workbook.xlsx
```

`artifact_diagnostic_report.md` includes a Mermaid decision flow and human review prompts. The workbook contains all reconstructed diagnostic tables, including mindmap nodes and edges.

## Reviewer questions

1. Is the interpreted product identical to the human interpretation?
2. Is the search sequence identical?
3. Were the same candidates accepted and rejected for the same reasons?
4. Was visual evidence interpreted correctly?
5. Is the manufacturer-versus-retailer choice identical?
6. What is the first divergent judgment?

The first divergence becomes a precise development requirement.

---

# Shared visual-evidence contract

Vision-derived feature evidence is identified by:

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

The result reports:

```text
image_influenced_final_decision
features_resolved_visually
selected_url_features_resolved_visually
text_alone_would_have_passed
```

`text_alone_would_have_passed` remains `UNKNOWN_NOT_COUNTERFACTUALLY_TESTED` unless a real text-only comparison is executed.

# Shared terminal outcomes

| Outcome | Meaning |
|---|---|
| `COMPLETED` | Strict URL gates passed |
| `REVIEW_REQUIRED` | A real direct URL was delivered but human confirmation remains |
| `FAILED` | No safe direct URL was delivered or execution failed |

When no safe direct URL exists, the system reports `MANDATORY_PRODUCT_URL_NOT_FOUND` rather than presenting an empty or weak URL as success.
