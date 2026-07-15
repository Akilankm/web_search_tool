# Notebook Usage and Diagnostic Contract

Use only:

```text
notebooks/01_run_product_evidence.ipynb
```

The notebook is the supported single-product runner and the complete adaptive-search, source-authority, mandatory-URL, candidate, browser, feature, and final-selection EDA/RCA report.

## Fresh setup

```bash
git checkout master
git pull origin master
cp .env.example .env
# Edit the real SerpAPI and enterprise LLM values.
./scripts/azureml_startup.sh
```

After pulling new code, restart the notebook kernel before running any cell.

The first notebook cell now:

1. locates the repository root;
2. places the repository root and `src/` first on `sys.path`;
3. evicts stale `product_evidence_harness` modules from `sys.modules`;
4. verifies that the package was loaded from the current checkout rather than `site-packages`;
5. confirms that `notebook_runtime.py` exists;
6. checks the live agent health contract.

This prevents an older installed package from shadowing the current repository.

## Run one product

```python
FEATURE_SET = "toy_features"
RUN_SINGLE_PRODUCT = True

product = {
    "row_id": "TEST-001",
    "main_text": "Exact product identity text",
    "country_code": "CO",
    "retailer_name": None,
    "ean": None,
    "language_code": None,
}
```

`main_text` and `country_code` are mandatory. Keep EAN/GTIN as text.

`RUN_SINGLE_PRODUCT` defaults to `False` to prevent accidental paid calls.

## Mandatory product URL contract

Every `COMPLETED` or `REVIEW_REQUIRED` run must contain:

```text
primary_url
product_match.product_url
product_match.best_available_url
evidence_set.primary_url
url_delivery.delivered = true
```

Strict verification and URL delivery are separate:

| Field | Meaning |
|---|---|
| `primary_url_acceptance.accepted` | Every strict browser, identity, feature, scrapability, and durability gate passed |
| `url_delivery.delivered` | A real direct external product-page URL was returned |
| `url_delivery.strictly_verified` | The delivered URL also passed strict acceptance |
| `url_delivery.status` | `STRICT_VERIFIED_PRODUCT_URL` or `BEST_AVAILABLE_REVIEW_URL` |
| `job_status` | `COMPLETED`, `REVIEW_REQUIRED`, or `FAILED` |

A review-required run still returns the strongest real product URL.

A run with no direct external product-page candidate after all three credits fails with:

```text
MANDATORY_PRODUCT_URL_NOT_FOUND
```

The notebook asserts this contract immediately after the run. It cannot continue diagnostics with an empty URL.

See `docs/MANDATORY_PRODUCT_URL.md`.

## Standardized source hierarchy

When `retailer_name` is supplied, that retailer is preferred first. Otherwise:

```text
Local/regional manufacturer
→ Global manufacturer
→ Major retailer in requested country
→ Other local website
→ Other global website
→ Amazon/eBay last resort
```

Amazon or eBay receive first priority only when explicitly supplied as `retailer_name`.

## Three-credit adaptive flow

```text
identify highest unresolved source tier
→ LLM selects one suitable engine/query
→ execute one paid SerpAPI request
→ normalize URLs, product tokens, IDs and images
→ classify source authority
→ precision admission and bounded scraping
→ validate current best URL
→ stop only for a strong high-priority exact URL
→ otherwise use the remaining credits
```

If the final credit starts without any direct external candidate, the planner enters mandatory recovery. It first expands a real immersive-product token when available; otherwise it uses AI Mode, Shopping, or Google Search to maximize exact product-page URL recall.

## Main notebook tables

| DataFrame | Purpose |
|---|---|
| `url_delivery_df` | Mandatory URL, strict-verification state, and job status |
| `source_hierarchy_df` | Target source tier and engine per credit |
| `search_actions_df` | Complete paid-credit decision trace |
| `search_engine_summary_df` | Engine-level URL and candidate yield |
| `search_handles_df` | Product tokens, IDs, and image handles |
| `search_decision_rca_df` | Budget, planner, fallback, and stop RCA |
| `serp_results_df` | Raw result occurrences across engines and credits |
| `results_df` | One authoritative row per canonical URL |
| `source_tier_summary_df` | Candidate conversion by source-authority tier |
| `agentic_df` | Browser turns, actions, termination, and errors |
| `feature_evidence_df` | URL-feature evidence records |
| `funnel_df` | Result-to-selection conversion |
| `rejection_reasons_df` | Normalized rejection and review reasons |
| `selection_rca_df` | Final URL decision RCA |

## Two intentional URL grains

`serp_results_df` has one row per raw result occurrence. A URL may appear more than once across engines and credits.

`results_df` has exactly one row per canonical URL and is persisted to:

```text
data/artifacts/<row_id>/candidate_url_records.json
data/artifacts/<row_id>/candidates.csv
```

## Selection interpretation

A stronger source does not rescue the wrong product. Selection order is:

```text
identity and variant evidence
→ strict failure severity
→ source authority
→ product-page likelihood
→ scrapability and reachability
→ richness and confidence
```

When no URL passes every strict gate, the same ordering chooses the strongest direct review URL rather than returning an empty field.

## Export

The workbook is written to:

```text
data/artifacts/<row_id>/single_product_diagnostics.xlsx
```

It includes the normal diagnostic tables plus:

```text
url_delivery
source_hierarchy
source_tier_summary
adaptive_actions
engine_summary
search_handles
search_rca
```

The run also writes:

```text
data/artifacts/<row_id>/mandatory_url_delivery.json
data/artifacts/<row_id>/adaptive_search_trace.json
data/artifacts/<row_id>/serp_credit_<n>_<engine>_raw.json
```

## Terminal interpretation

- `COMPLETED`: a strictly verified URL was delivered.
- `REVIEW_REQUIRED`: a real product URL was delivered but one or more strict gates require confirmation.
- `FAILED`: execution failed, including the non-negotiable case where no direct product URL was produced.
