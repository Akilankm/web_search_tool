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
  → Enforced top-k candidate cut
  → Concurrent batch scraping with max-batch bound
  → Batch winner selection
  → Production-ready champion candidate selection
  → Champion confirmation gate, default 3 checks
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

The code also enforces `PRODUCT_HARNESS_TOURNAMENT_PREFLIGHT_TOP_K` and `PRODUCT_HARNESS_TOURNAMENT_MAX_BATCHES`. With defaults, the tournament batch phase considers the top `60` ranked candidates and executes at most `3` batches of `20`, subject to remaining scrape budget.

Champion confirmation is currently a fixed post-selection gate:

```text
champion_confirmation.required_attempts = 3
champion_confirmation.required_successes = 3
```

These confirmation checks are not extra SerpAPI searches. They are row-level quality confirmations recorded in `champion_confirmation.json` and `champion_confirmation.md`.

## Champion rule

A tournament champion exists only when a URL passes all production evidence gates:

```text
browser-openable
highly scrapable
exact-product matched
critical product details extracted
country acceptable or valid global fallback
not a conflicting variant
```

Scrapable means product details can actually be extracted for downstream coding. It does not mean only HTTP reachability.

After the production evidence gate, champion confirmation must also pass:

```text
champion_confirmation.passed = true
champion_confirmation.attempted_count = 3
champion_confirmation.success_count = 3
champion_confirmation.final_url_stable = true
champion_confirmation.evidence_stable = true
```

If no URL passes these gates:

```text
champion_url = empty
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
output/<row_id>/champion_confirmation.md
output/<row_id>/champion_confirmation.json
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
champion_confirmation.passed = true
champion_confirmation.success_count = champion_confirmation.required_successes
needs_review = false
product_url is not empty
```

Rows outside this filter may have a review candidate, but they are not production handoff rows.

## Key final_submission.csv columns and row artifacts

| Field / artifact | Meaning |
|---|---|
| `product_url` | Best discovered/champion URL. Can be review-only unless all handoff gates pass. |
| `best_available_url` | Best review candidate when no confirmed champion exists. |
| `production_url_ready` | True only when URL is handoff-ready by the production URL gate. |
| `production_url_status` | Production-readiness class. |
| `browser_openable` | Whether URL is expected to open in browser. |
| `highly_scrapable` | Whether the page is rich and scrape-usable. |
| `exact_product_url_match` | Whether URL is exact product, not a variant/sibling. |
| `verified_exact_url` | Strict exact URL when proven. |
| `needs_review` | True when not safe for automated handoff. |
| `champion_confirmation.json` | Repeated champion confirmation details. |
| `champion_confirmation.passed` | True only when the repeated confirmation gate passed. |
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
preflight candidate count after top-k cut
scraped candidate count after batch-limit enforcement
champion URL, only when production-ready and confirmation passed
best review candidate URL when no confirmed champion exists
runner-up URL
champion production-readiness status
champion confirmation status
champion confirmation attempts/successes
queries used
batch winners
```

`champion_confirmation.json` / `champion_confirmation.md` explain:

```text
URL being confirmed
required attempts
required successes
attempted count
success count
final URL stability
product evidence stability
minimum richness
minimum word count
per-attempt status and reasons
```

`batch_winners.csv` gives a compact table of every executed batch winner and runner-up.

## Notebooks

Use the notebooks for demonstration and manual inspection:

```text
notebooks/01_single_product_harness.ipynb
notebooks/02_batch_product_harness.ipynb
```

Both notebooks now surface champion confirmation status and the new confirmation artifact.

## Review workflow

1. Run the batch.
2. Filter production-ready rows.
3. Confirm the row artifact has `champion_confirmation.passed=true`.
4. Hand off only confirmed production-ready URLs.
5. Use `review_queue.csv` for non-production rows.
6. Inspect `tournament_bracket.md`, `champion_confirmation.md`, and `batch_winners.csv` for why a candidate won or failed confirmation.
7. Use `product_coding_input.json` only as production coding input when the row is production-ready and confirmation passed; otherwise use it for review only.

## Do not use

Do not treat a review candidate as production-ready.

Do not treat a production URL gate pass as sufficient if champion confirmation failed.

Do not manually edit EAN values in Excel as numbers. They must remain strings.

Do not increase tournament SerpAPI credits above 4; the code will clamp it and the business rule expects the 4-credit cap.
