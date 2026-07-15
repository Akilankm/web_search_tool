# Notebook Usage and Diagnostic Contract

Use only `notebooks/01_run_product_evidence.ipynb`.

The notebook is the supported single-product runner and the complete **three-credit adaptive search**, source-authority, candidate, browser, and final-selection EDA/RCA report.

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

Amazon/eBay receive first priority only when explicitly supplied as `retailer_name`.

## Three-credit adaptive flow

```text
identify highest unresolved source tier
→ LLM selects one suitable engine/query
→ execute one paid SerpAPI request
→ normalize URLs, product tokens, IDs and images
→ classify source authority
→ precision admission and bounded scraping
→ validate current best URL
→ stop or target the next source tier
```

The notebook reports the actual source-tier and engine sequence. It does not assume a fixed retailer/country/global sequence.

## Search and hierarchy tables

| DataFrame | Purpose |
|---|---|
| `source_hierarchy_df` | One row per credit: target source tier, engine, yield, and continuation reason |
| `search_actions_df` | Complete paid-credit decision trace |
| `search_engine_summary_df` | Engine-level URL, handle, qualification, and scrape yield |
| `search_handles_df` | Product tokens, IDs, and images available for follow-up |
| `search_decision_rca_df` | Budget, hierarchy, planner calls/fallbacks, and stop reason |

A `planner_source` of `llm` means the enterprise LLM selected the route. `deterministic_fallback` means the guarded hierarchy policy selected a valid, non-duplicate route after planner failure.

## Candidate and evidence tables

| DataFrame | Purpose |
|---|---|
| `overview_df` | Executive metrics and final state |
| `search_stages_df` | Per-credit adaptive trace |
| `serp_results_df` | Raw result occurrences across engines and credits |
| `results_df` | Authoritative one-row-per-canonical-URL decision ledger |
| `source_tier_summary_df` | Candidate/scrape/identity/selection conversion by source tier |
| `agentic_df` | Browser turns, actions, termination, and errors |
| `feature_evidence_df` | URL-feature evidence records |
| `feature_matrix_df` | URL by requested-feature support matrix |
| `funnel_df` | Result-to-selection conversion |
| `domain_summary_df` | Domain quality and conversion |
| `stage_quality_df` | Per-credit yield ratios |
| `rejection_reasons_df` | Normalized rejection and blocker counts |
| `selection_rca_df` | Final `primary_url` root-cause analysis |

## Two intentional URL grains

### `serp_results_df`

One row per raw result occurrence. The same URL may appear in multiple engines, credits, or positions.

### `results_df`

Exactly one row per canonical URL. The same authoritative grain is persisted to:

```text
data/artifacts/<row_id>/candidate_url_records.json
data/artifacts/<row_id>/candidates.csv
```

## Source-authority fields in `results_df`

| Field | Meaning |
|---|---|
| `source_tier` | Numeric business priority; lower is stronger |
| `source_tier_name` | Requested retailer, manufacturer, major retailer, other, or marketplace |
| `source_role` | Functional source classification |
| `country_alignment` | Local/regional or global/unknown |
| `requested_retailer_match` | Candidate belongs to explicitly supplied retailer |
| `manufacturer_match` | Candidate domain matches manufacturer/brand evidence |
| `major_country_retailer` | Country-aligned merchant from a product-oriented surface |
| `marketplace` | Amazon/eBay marketplace marker |
| `source_priority_reason` | Reason for assigned tier |
| `higher_priority_tier_exhausted` | Whether a stronger viable source remained |
| `selected_within_tier` | Best candidate within its own tier |

## Remaining candidate fields

| Group | Important fields |
|---|---|
| URL identity | `canonical_url`, `requested_url`, `final_url`, `domain` |
| Search support | engine/credit markers, appearance count, and position |
| Admission | `url_type`, `preflight_score`, `admitted_for_scrape`, `admission_reason` |
| Acquisition | `full_scrape_attempted`, `fetch_success`, `content_extracted`, `technical_scrapable` |
| Evidence quality | `product_page_likelihood`, `content_utility_score`, `scrape_accepted` |
| Identity | EAN, title, variant, and page-type decisions |
| Features | coverage, missing features, and conflicts |
| Browser | admission, turns, actions, and outcome |
| Final RCA | terminal status, rejection category, and selection |

Feature-specific columns are created dynamically:

```text
feature_<feature_id>_value
feature_<feature_id>_status
feature_<feature_id>_confidence
```

## Selection interpretation

A stronger source does not rescue the wrong product. Selection order is:

```text
exact product identity
→ usable product-detail page
→ source authority
→ confidence/richness within the source tier
```

A lower-tier URL is selected only after higher tiers were absent or failed mandatory product/evidence gates.

## Scrape semantics

The notebook field `scrape_success` means **evidence-quality accepted**, not merely HTTP success.

| Field | Meaning |
|---|---|
| `fetch_success` | Acquisition operation succeeded |
| `content_extracted` | Readable content was obtained |
| `technical_scrapable` | Technical scrape checks passed |
| `product_page_likelihood` | Evidence for an individual product page |
| `content_utility_score` | Usefulness for identity and feature evidence |
| `scrape_accepted` | Accepted for downstream reasoning |

## Graphical EDA

Separate charts show:

- SerpAPI credit allocation by engine;
- source-authority tier targeted by each credit;
- engine result/candidate/qualification/scrape yield;
- best candidate confidence after each credit;
- overall conversion funnel;
- candidate outcomes, confidence, and feature coverage;
- domain contribution and rejection reasons;
- URL-feature support heatmap.

## RCA questions answered

1. Which source tier was targeted for each credit?
2. Why was that engine selected for the tier?
3. Were manufacturer or requested-retailer pages found?
4. Why did the workflow move to a lower tier?
5. How many candidates were scraped and evidence-quality accepted per tier?
6. Were Amazon/eBay considered only after stronger sources?
7. Why did the chosen URL outrank alternatives?
8. Why did each candidate fail identity, scrape, browser, or feature gates?

## Export

The workbook is written to:

```text
data/artifacts/<row_id>/single_product_diagnostics.xlsx
```

It includes:

```text
adaptive_actions
engine_summary
search_handles
search_rca
source_hierarchy
source_tier_summary
```

The run also writes `adaptive_search_trace.json` and raw response files for only the SerpAPI credits actually used.

`COMPLETED` and `REVIEW_REQUIRED` are successful terminal states. `REVIEW_REQUIRED` means no URL passed every mandatory gate. Only `FAILED` is an execution failure.

See:

- `docs/ADAPTIVE_SERPAPI_SEARCH.md`
- `docs/SOURCE_AUTHORITY_HIERARCHY.md`
- `docs/CANDIDATE_PRECISION_AND_CONTEXT.md`
- `docs/SINGLE_PRODUCT_DIAGNOSTICS.md`
