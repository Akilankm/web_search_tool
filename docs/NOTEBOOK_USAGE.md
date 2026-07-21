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

For management and leadership calls, use `apps/leadership_demo.py`; it is a presentation surface over the same agent API, not a fourth notebook or alternate workflow.

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
belief-url-resolution-v8-leadership-demo
```

Required capabilities:

```text
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
structured_no_url_review_outcome=true
leadership_demo_runtime_options=true
```

The single and batch notebooks verify readiness before paid search. The diagnostic notebook works offline.

---

# 1. Single product notebook

```text
notebooks/01_single_product.ipynb
```

Input:

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

`main_text` and `country_code` are mandatory. Preserve EAN/GTIN as text and use a unique `row_id`.

Processing route:

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

The first review view contains `final_decision_df`, `business_judgement_steps_df` and `visual_evidence_summary_df` before detailed engineering tables.

Workbook:

```text
data/artifacts/<row_id>/single_product_diagnostics.xlsx
```

A no-safe-URL result remains `REVIEW_REQUIRED`, shows `NO_SAFE_DIRECT_PRODUCT_URL_FOUND`, and continues into diagnostics without a traceback.

---

# 2. Parallel CSV batch notebook

```text
notebooks/02_batch_products.ipynb
```

Required CSV columns:

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

The loader rejects missing/blank mandatory fields, duplicate row IDs and empty files before paid search. Product parallelism is bounded by agent workers and browser contexts.

Outputs:

```text
data/batch_runs/<run_id>/
├── batch_input_normalized.csv
├── batch_results.csv
├── batch_failures.csv
├── batch_artifact_index.csv
└── batch_run_summary.json
```

`batch_run_summary.json` includes status counts, throughput, mean latency, p50, p95 and total SerpAPI credits. Each row preserves its own product artifact. Structured no-safe-URL rows remain `REVIEW_REQUIRED`; genuine technical errors alone appear in `batch_failures.csv`.

---

# 3. Interactive artifact diagnostics notebook

```text
notebooks/03_artifact_diagnostics.ipynb
```

Set `ARTIFACT_PATH` to a product directory or any file inside it:

```python
ARTIFACT_PATH = PROJECT_ROOT / "data" / "artifacts" / "ROW-001"
RUN_DIAGNOSTICS = True
```

It reconstructs:

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

Interactive workspace:

```text
Decision Map
Judgment Timeline
Candidates
Evidence
Artifacts
```

Outputs:

```text
artifact_diagnostics_interactive.html
artifact_diagnostic_report.md
artifact_diagnostic_workbook.xlsx
```

The notebook displays recorded evidence, actions, rules, judgments and conclusions. It does not expose hidden chain-of-thought.

---

# Shared artifact and result contract

Every terminal business result contains `business_judgement_review` and writes:

```text
data/artifacts/<row_id>/business_judgement_review.md
data/artifacts/<row_id>/run_configuration.json
```

Vision-derived feature evidence is identified by:

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

Terminal outcomes:

| Outcome | Meaning |
|---|---|
| `COMPLETED` | Strict URL gates passed |
| `REVIEW_REQUIRED` with URL | Real direct reference delivered; human confirmation remains |
| `REVIEW_REQUIRED` without URL | No safe direct page found within the bounded policy; trace preserved and no URL fabricated |
| `FAILED` | Genuine runtime, configuration, dependency or result-contract failure |

The first divergent human judgment becomes a precise development requirement.
