# Documentation Index

Use this index when presenting or operating the Product Evidence Harness.

## Start here

| Document | Purpose |
|---|---|
| `../README.md` | Main project overview, usage, outputs, and production handoff policy. |
| `TEAM_SHOWCASE_GUIDE.md` | Team-facing demo script and business explanation. |
| `PRODUCTION_GRADE_PRODUCT_URL.md` | Exact handoff rules for browser/scraping/product-coding teams. |
| `STRICT_PRODUCT_URL_POLICY.md` | Explains why `product_url` is non-empty when candidates exist, but may be review-only. |
| `ELITE_EVIDENCE_ENGINE.md` | Evidence graph, quality tiers, coding readiness, metrics, and review artifacts. |
| `LATENCY_OPTIMIZATION.md` | Static-first and concurrent scrape speedup controls. |
| `IMPORT_PATH_FIX.md` | Notebook/import path guidance. |

## Active notebooks

```text
notebooks/01_single_product_harness.ipynb
notebooks/02_batch_product_harness.ipynb
```

Both notebooks now surface:

```text
production_url_ready
production_url_status
browser_openable
highly_scrapable
exact_product_url_match
production_url_score
production_url_reasons
```

## Production handoff rule

For browser-opening, downstream scraping, and product-coding teams, use only rows where:

```text
production_url_ready = true
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
needs_review = false
```

Rows outside this filter can still contain `product_url`, but they are review-only.
