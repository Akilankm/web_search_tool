# End-to-End Tournament Operations Runbook

## Purpose

This runbook is the operational entry point for running the Product Evidence Harness end to end.

The system is tournament-first:

```text
Input CSV/XLSX
  → Product identity normalization
  → SerpAPI search fan-out, capped at 4 credits per product
  → Candidate URL pool
  → Cheap preflight ranking
  → Concurrent batch scraping
  → Batch winner selection
  → Production-ready champion selection
  → Production URL gate
  → Evidence artifacts and product-coding handoff
```

## Required input

| Column | Required | Notes |
|---|---:|---|
| `row_id` | Recommended | Stable row/product identifier. |
| `main_text` | Yes | Primary product identity text. |
| `country_code` | Yes | Target market/country. |
| `ean` / `gtin` | No | Keep as text. Invalid GTINs are ignored for search construction. |
| `retailer_name` | No | Preferred first source, not a hard final constraint. |
| `language_code` | No | Optional language override. |
| `region` | No | Optional region/market hint. |

## Required environment

```env
SERPAPI_API_KEY=your_serpapi_key
PRODUCT_HARNESS_ENABLE_TOURNAMENT_MODE=true
PRODUCT_HARNESS_TOURNAMENT_MAX_SERP_CREDITS=4
PRODUCT_HARNESS_TOURNAMENT_CANDIDATE_POOL=150
PRODUCT_HARNESS_TOURNAMENT_PREFLIGHT_TOP_K=60
PRODUCT_HARNESS_TOURNAMENT_BATCH_SIZE=20
PRODUCT_HARNESS_TOURNAMENT_MAX_BATCHES=3
PRODUCT_HARNESS_SCRAPE_CONCURRENCY=6
PRODUCT_HARNESS_STATIC_FETCH_FIRST=true
PRODUCT_HARNESS_BROWSER_FALLBACK_ONLY=true
PRODUCT_HARNESS_WRITE_OUTPUTS=true
```

The code clamps `PRODUCT_HARNESS_TOURNAMENT_MAX_SERP_CREDITS` to a maximum of `4`.

## Champion rule

A tournament champion exists only when a URL passes all production evidence gates:

```text
browser-openable
highly scrapable
exact-product matched
critical product details extracted
country acceptable
not a conflicting variant
```

Scrapable means product details can actually be extracted for downstream coding. It does not mean only HTTP reachability.

If no URL passes these gates:

```text
product_url = empty
tournament_champion_url = empty
best_review_candidate_url = populated when available
needs_review = true
production_url_ready = false
```

## Run validation

```bash
PYTHONPATH=src python -m compileall -q src main.py batch_main.py
PYTHONPATH=src pytest -q
```

## Run batch

```bash
python batch_main.py \
  --input data/products.xlsx \
  --output outputs/final_submission.csv \
  --workers 4
```

## Main batch outputs

```text
outputs/final_submission.csv
outputs/review_queue.csv
outputs/batch_summary.md
outputs/metrics.json
```

## Main row artifacts

```text
output/<row_id>/final_row.csv
output/<row_id>/tournament_bracket.md
output/<row_id>/tournament_bracket.json
output/<row_id>/batch_winners.csv
output/<row_id>/quality_assessment.md
output/<row_id>/product_coding_input.json
output/<row_id>/evidence_graph.json
output/<row_id>/decision_trace.md
```

## Production handoff rule

Only hand off URLs to browser/scraping/product-coding teams when:

```text
production_url_ready = true
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
needs_review = false
product_url is not empty
```

Rows outside this filter may have a review candidate, but they are not production handoff rows.

## Key final_submission.csv columns

| Column | Meaning |
|---|---|
| `product_url` | Production-ready tournament champion URL only. Empty when no champion exists. |
| `best_available_url` | Best review candidate when no champion exists. |
| `production_url_ready` | True only when URL is handoff-ready. |
| `production_url_status` | Production-readiness class. |
| `browser_openable` | Whether URL is expected to open in browser. |
| `highly_scrapable` | Whether the page is rich and scrape-usable. |
| `exact_product_url_match` | Whether URL is exact product, not a variant/sibling. |
| `verified_exact_url` | Strict exact URL when proven. |
| `needs_review` | True when not safe for automated handoff. |
| `quality_tier` | Enterprise quality tier A/B/C/D/E. |
| `coding_readiness_status` | Downstream product-coding readiness. |
| `failure_taxonomy` | Structured weak/review reasons. |
| `product_coding_input_path` | Downstream coding JSON payload. |

## Tournament artifact interpretation

`tournament_bracket.json` / `tournament_bracket.md` explain:

```text
search credits used
search credit limit
raw candidate count
preflight candidate count
scraped candidate count
champion URL, only when production-ready
best review candidate URL when no champion exists
runner-up URL
champion production-readiness status
queries used
batch winners
```

`batch_winners.csv` gives a compact table of every batch winner and runner-up.

## Notebooks

Use the notebooks for demonstration and manual inspection:

```text
notebooks/01_single_product_harness.ipynb
notebooks/02_batch_product_harness.ipynb
```

## Review workflow

1. Run the batch.
2. Filter production-ready rows.
3. Hand off only production-ready URLs.
4. Use `review_queue.csv` for non-production rows.
5. Inspect `tournament_bracket.md` and `batch_winners.csv` for why no champion was found or why a champion won.
6. Use `product_coding_input.json` only as production coding input when the row is production-ready; otherwise use it for review only.

## Do not use

Do not treat a review candidate as production-ready.

Do not manually edit EAN values in Excel as numbers. They must remain strings.

Do not increase tournament SerpAPI credits above 4; the code will clamp it and the business rule expects the 4-credit cap.
