# Notebook Usage and Diagnostic Contract

Use only `notebooks/01_run_product_evidence.ipynb`.

The notebook is both the supported single-product runner and the complete search, candidate, browser and final-selection EDA/RCA report.

## Fresh setup

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool
cp .env.example .env
# Edit only the real SerpAPI and LLM values.
./scripts/azureml_startup.sh
```

The repository includes `inputs/private/toy_features.json`. The first notebook cell installs only missing analytical packages into the active kernel.

## Run one product

```python
FEATURE_SET = "toy_features"
RUN_SINGLE_PRODUCT = True

product = {
    "row_id": "TEST-001",
    "main_text": "Exact product identity text",
    "country_code": "CO",
    "retailer_name": "Requested retailer or None",
    "ean": None,
    "language_code": None,
}
```

`main_text` and `country_code` are required. Keep EAN/GTIN as text. `RUN_SINGLE_PRODUCT` defaults to `False` to prevent accidental paid requests.

## Readiness contract

The notebook fails before submission unless `/health` confirms:

- adaptive three-credit search is enforced;
- SerpAPI request limit is exactly three;
- LLM search planning is enabled;
- LLM search feedback is enabled;
- the allowed search-engine list is present;
- LLM configuration is present;
- browser agentic tools are healthy.

## Adaptive credit flow

```text
LLM selects one engine/query
→ execute one paid SerpAPI request
→ normalize URLs, product tokens, IDs and images
→ precision admission and bounded scraping
→ validate current best URL
→ stop when working, otherwise replan with remaining credits
```

The planner may use:

- Google Search;
- Google Shopping;
- Google AI Mode;
- Google Immersive Product;
- Google Lens;
- requested-retailer native Amazon, eBay, Walmart or Home Depot search.

The notebook reports the actual engine sequence. It does not assume a fixed retailer/country/global sequence.

## Adaptive search tables

| DataFrame | Purpose |
|---|---|
| `search_actions_df` | One row per paid credit: engine, purpose, planner source, query, yield and current best URL |
| `search_engine_summary_df` | Engine-level credits, URL yield, handle yield, qualification and scrape conversion |
| `search_handles_df` | Product tokens, IDs and image URLs available for follow-up |
| `search_decision_rca_df` | Policy, credit usage, planner calls/fallbacks, engine sequence and stop reason |

A `planner_source` of `llm` means the enterprise LLM selected the action. `deterministic_fallback` means the guarded fallback policy selected a non-duplicate action after a planner failure.

## Candidate and evidence tables

| DataFrame | Purpose |
|---|---|
| `overview_df` | Executive metrics and final state |
| `search_stages_df` | Per-credit adaptive trace, retained for compatibility |
| `serp_results_df` | Raw result occurrences across engines and credits |
| `results_df` | Authoritative one-row-per-canonical-URL decision ledger |
| `agentic_df` | Browser turns, actions, termination and errors |
| `feature_evidence_df` | URL-feature evidence records |
| `feature_matrix_df` | URL by requested-feature support matrix |
| `funnel_df` | Result-to-selection conversion |
| `domain_summary_df` | Domain quality and conversion |
| `stage_quality_df` | Per-credit yield ratios |
| `rejection_reasons_df` | Normalized rejection and blocker counts |
| `selection_rca_df` | Final `primary_url` root-cause analysis |

## Two intentional URL grains

### `serp_results_df`

One row per result occurrence. The same canonical URL may occur in multiple engines, credits or positions. Columns include engine, purpose and source section.

### `results_df`

Exactly one row per canonical URL. The notebook asserts URL uniqueness. Tracking, campaign, referral, session and fragment noise are removed while product-defining parameters remain.

The same authoritative grain is persisted to:

```text
data/artifacts/<row_id>/candidate_url_records.json
data/artifacts/<row_id>/candidates.csv
```

## `results_df` field groups

| Group | Important fields |
|---|---|
| URL identity | `canonical_url`, `requested_url`, `final_url`, `domain` |
| Search support | engine/credit markers, appearance count, best position and title |
| Admission | `url_type`, `preflight_score`, `admitted_for_scrape`, `admission_reason` |
| Acquisition | `full_scrape_attempted`, `fetch_success`, `content_extracted`, `technical_scrapable` |
| Evidence quality | `product_page_likelihood`, `content_utility_score`, `scrape_accepted` |
| Identity | EAN, title, variant and page-type decisions |
| Features | coverage, missing features and conflicts |
| Browser | admission, turns, actions and outcome |
| Final RCA | terminal status, rejection category and selection |

Feature-specific scalar columns are created dynamically:

```text
feature_<feature_id>_value
feature_<feature_id>_status
feature_<feature_id>_confidence
```

## Scrape semantics

The stable notebook field `scrape_success` means **evidence-quality accepted**, not merely HTTP success.

| Field | Meaning |
|---|---|
| `fetch_success` | Acquisition operation succeeded |
| `content_extracted` | Readable content was obtained |
| `technical_scrapable` | Technical scrape checks passed |
| `product_page_likelihood` | Evidence for an individual product detail page |
| `content_utility_score` | Usefulness for product identity and feature evidence |
| `scrape_accepted` | Accepted for downstream reasoning |

## Graphical EDA

Separate charts show:

- SerpAPI credit allocation by engine;
- engine result, candidate, qualification and scrape yield;
- best candidate confidence after each credit;
- overall conversion funnel;
- per-credit yield;
- candidate outcome distribution;
- confidence and feature coverage;
- domain contribution;
- rejection reasons;
- URL-feature support heatmap.

## Search and candidate RCA

The notebook makes these questions directly answerable:

1. Which engine did the LLM choose for each credit, and why?
2. Did the result produce direct URLs, a product token, an image or only weak candidates?
3. How many new canonical URLs were produced?
4. How many passed pre-scrape admission?
5. How many were scraped and evidence-quality accepted?
6. Did the current best URL become a validated working URL?
7. Why was another credit spent or why did the search stop early?
8. Why was each candidate selected or rejected?

## Export

The export cell writes:

```text
data/artifacts/<row_id>/single_product_diagnostics.xlsx
```

The workbook includes the original candidate/browser/feature sheets and these adaptive search sheets:

```text
adaptive_actions
engine_summary
search_handles
search_rca
```

The run also writes:

```text
adaptive_search_trace.json
serp_credit_01_<engine>_raw.json
serp_credit_02_<engine>_raw.json
serp_credit_03_<engine>_raw.json
```

Only raw files for credits actually used are created.

`COMPLETED` and `REVIEW_REQUIRED` are successful terminal states. `REVIEW_REQUIRED` means no URL passed every mandatory gate. Only `FAILED` is an execution failure.

See:

- `docs/ADAPTIVE_SERPAPI_SEARCH.md`
- `docs/CANDIDATE_PRECISION_AND_CONTEXT.md`
- `docs/SINGLE_PRODUCT_DIAGNOSTICS.md`
