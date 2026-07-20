# Notebook Usage Contract

The repository has exactly three supported notebooks:

```text
notebooks/01_single_product.ipynb
notebooks/02_batch_products.ipynb
notebooks/03_artifact_diagnostics.ipynb
```

| Need | Notebook | Agent required |
|---|---|---:|
| Resolve and inspect one product | `01_single_product.ipynb` | Yes |
| Process a CSV with bounded parallel execution | `02_batch_products.ipynb` | Yes |
| Explore an existing product artifact interactively | `03_artifact_diagnostics.ipynb` | No |

## Runtime setup

```bash
git checkout master
git pull origin master
cp .env.example .env
# Add real SerpAPI and enterprise LLM values.
./scripts/azureml_startup.sh --clean-build
```

Current runtime:

```text
belief-url-resolution-v7-structured-no-url-review
```

Required capabilities:

```text
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
structured_no_url_review_outcome=true
```

The single and batch notebooks verify readiness before paid search. The diagnostic notebook works offline.

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

`main_text` and `country_code` are mandatory. Keep EAN/GTIN as text and use a unique `row_id`.

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
→ direct URL or structured no-safe-URL review outcome
→ business_judgement_review.md
```

## Result behavior

A URL-backed result displays:

```text
primary_url
primary_url_role
manufacturer_url
retailer_url
source_selection
primary_url_acceptance
url_delivery
```

When bounded search finds no safe direct product page, `run_product` returns rather than raising an internal exception:

```text
job_status=REVIEW_REQUIRED
primary_url=null
primary_url_role=NONE
resolution_outcome.code=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
url_delivery.delivered=false
url_delivery.status=NO_SAFE_DIRECT_PRODUCT_URL_FOUND_AFTER_BOUNDED_SEARCH
```

The notebook displays the outcome message, credits used, suggested next actions and artifact paths, then continues into diagnostics.

A blank URL in any other response shape remains a hard `INCONSISTENT_URL_DELIVERY_RESULT` contract error.

## First review view

| Object | Purpose |
|---|---|
| `final_decision_df` | Final URL or explicit no-safe-URL result, source decision and delivery status |
| `business_judgement_steps_df` | Ordered question, evidence, rule, judgment and next action |
| `visual_evidence_summary_df` | Screenshot/image use and recorded impact |
| `business_judgement_review.md` | Shareable human-comparison document |

Primary artifact:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

No-safe-URL runs additionally provide:

```text
data/artifacts/<row_id>/no_url_resolution.json
```

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

The loader accepts common aliases, preserves EAN as text, and rejects missing/blank mandatory fields, duplicate row IDs and empty CSV files before paid search.

Example:

```text
examples/batch_products.example.csv
```

## Bounded parallel execution

```python
MAX_PARALLEL_PRODUCTS = recommended_batch_parallelism()
```

Concurrency is bounded by:

```text
min(AGENT_WORKERS, BROWSER_MAX_CONTEXTS, 8)
```

Every product retains its own search/browser/LLM limits and artifact directory. A genuine technical row failure does not abort the remaining products.

A structured no-safe-URL row is **not** a technical failure:

- it remains `REVIEW_REQUIRED` in `batch_results.csv`;
- it is not written into `batch_failures.csv`;
- its product artifact and human-review files remain available.

## Batch result fields

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

Each row preserves its own complete artifact under `data/artifacts/<row_id>/`.

---

# 3. Interactive artifact diagnostics notebook

```text
notebooks/03_artifact_diagnostics.ipynb
```

## Input

Set `ARTIFACT_PATH` to a product artifact directory or any file inside it:

```python
ARTIFACT_PATH = PROJECT_ROOT / "data" / "artifacts" / "ROW-001"
RUN_DIAGNOSTICS = True
```

Examples:

```text
data/artifacts/ROW-001/
data/artifacts/ROW-001/orchestrated_result.json
data/artifacts/ROW-001/candidates.csv
data/artifacts/ROW-001/business_judgement_review.md
data/artifacts/ROW-001/no_url_resolution.json
```

## Interactive workspace

The notebook reconstructs:

```text
submitted input
→ product identity and uncertainty
→ manufacturer/local/global search route
→ candidate discovery and rejection
→ rendered browser actions
→ text and image evidence
→ requested-feature coverage
→ strict URL gates
→ manufacturer-versus-retailer selection
→ final URL or controlled no-safe-URL outcome
```

It presents one compact tabbed workspace:

```text
Decision Map
Judgment Timeline
Candidates
Evidence
Artifacts
```

Interactions include hover detail, pan/zoom, legend isolation, candidate outcome filters and click-to-zoom evidence/artifact hierarchies. Raw diagnostic DataFrames are not used as the main comprehension layer.

Primary output:

```text
data/artifacts/<row_id>/artifact_diagnostics_interactive.html
```

The HTML is self-contained and works offline.

Secondary exports:

```text
artifact_diagnostic_report.md
artifact_diagnostic_workbook.xlsx
```

The explorer displays recorded evidence, actions, rules, judgments and conclusions. It does not expose or reconstruct hidden chain-of-thought.

## Reviewer questions

1. Is the interpreted product identical to the human interpretation?
2. Is the search sequence identical?
3. Were the same candidates accepted or rejected for the same reasons?
4. Was visual evidence interpreted correctly?
5. Is the manufacturer-versus-retailer decision identical?
6. For no-safe-URL cases, would the human also stop under the configured bounded policy?
7. What is the first divergent judgment?

The first divergence becomes a precise development requirement.

---

# Shared visual-evidence contract

Vision-derived evidence is identified by:

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
| `COMPLETED` | A safe direct product URL passed all strict gates |
| `REVIEW_REQUIRED` with URL | A real direct review URL was delivered but human confirmation remains |
| `REVIEW_REQUIRED` without URL | Bounded search found no safe direct product page; trace is preserved and no URL is fabricated |
| `FAILED` | Genuine software, configuration, dependency or response-contract failure |

See [Structured No-Safe-URL Review Outcome](STRUCTURED_NO_URL_OUTCOME.md).
