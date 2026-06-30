# Team Showcase Guide

## One-line positioning

```text
The Product Evidence Harness discovers product URLs, validates browser/scraping usability, verifies exact product identity, and produces an auditable product-coding evidence packet.
```

## What to demonstrate

Show that the system does not merely return a URL. It returns a URL with production-readiness evidence:

```text
product_url
production_url_ready
production_url_status
browser_openable
highly_scrapable
exact_product_url_match
needs_review
verified_exact_url
quality_tier
coding_readiness_status
failure_taxonomy
product_coding_input_path
```

## Demo script

### 1. Start with the business requirement

```text
The URL must be useful for two teams:
1. A team that opens the product page in a browser.
2. A team that scrapes the product page for complete coding evidence.
```

### 2. Explain the handoff rule

For high-stakes handoff, use only rows where:

```text
production_url_ready = true
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
needs_review = false
```

Rows that fail this gate can still have `product_url`, but they are review-only.

### 3. Show the batch command

```bash
python batch_main.py \
  --input data/products.xlsx \
  --output outputs/final_submission.csv \
  --workers 4
```

### 4. Show final_submission.csv

Highlight these columns:

| Column | Message to team |
|---|---|
| `product_url` | Best URL emitted by the harness. |
| `production_url_ready` | Whether the URL is safe for browser/scraper handoff. |
| `production_url_status` | Handoff readiness class. |
| `browser_openable` | Whether the page should open in browser. |
| `highly_scrapable` | Whether the page is scrape-usable and evidence-rich. |
| `exact_product_url_match` | Whether the page is the exact product. |
| `production_url_reasons` | Why a URL failed the gate, if it failed. |
| `product_coding_input_path` | Evidence bundle for downstream product coding. |

### 5. Show production-ready filter

```python
ready = df[
    (df["production_url_ready"].astype(str).str.lower().isin(["true", "1", "yes"]))
    & (df["production_url_status"] == "PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL")
    & (~df["needs_review"].astype(str).str.lower().isin(["true", "1", "yes"]))
]
```

This filtered dataset is the handoff set for browser and scraping teams.

### 6. Show review-only fallback set

Rows outside the ready set should be shown as governance, not failure:

```text
They still have best discovered product_url where possible,
but the system clearly marks them as not production-ready.
```

### 7. Open one row artifact folder

Show:

```text
output/<row_id>/quality_assessment.md
output/<row_id>/product_coding_input.json
output/<row_id>/evidence_graph.json
output/<row_id>/decision_trace.md
```

Explain that this is the audit trail: what was searched, scraped, verified, rejected, selected, and why.

## Suggested team wording

```text
This harness is not a naive link finder. It runs an iterative search-scrape-verify loop. It first attempts the requested retailer, then same-country alternatives, and then global fallback. The output always preserves the best discovered product_url when a candidate exists, but a separate production gate determines whether that URL is safe for browser opening, downstream scraping, and product coding.
```

```text
For operational handoff, we will use only rows where production_url_ready is true. That means the URL is browser-openable, highly scrapable, exact-product verified, and does not require review.
```

## Team takeaway

```text
The system gives us both coverage and governance:
- coverage: product_url is populated with the best discovered URL when candidates exist
- governance: only production_url_ready=true rows are handed to browser/scraping/product-coding teams
```
