# Documentation Index

Use this index when presenting or operating the Product Evidence Harness.

## Start here

| Document | Purpose |
|---|---|
| `../README.md` | Main project overview for the tournament-first architecture. |
| `END_TO_END_OPERATIONS.md` | Operational runbook for inputs, env, batch run, artifacts, and handoff. |
| `TOURNAMENT_MODE.md` | Primary architecture, four-credit SerpAPI cap, champion selection, and artifacts. |
| `TEAM_SHOWCASE_GUIDE.md` | Team-facing demo script and business explanation. |
| `PRODUCTION_GRADE_PRODUCT_URL.md` | Exact handoff rules for browser/scraping/product-coding teams. |
| `STRICT_PRODUCT_URL_POLICY.md` | Explains why `product_url` is non-empty when candidates exist, but may be review-only. |
| `ELITE_EVIDENCE_ENGINE.md` | Evidence graph, quality tiers, coding readiness, metrics, and review artifacts. |
| `LATENCY_OPTIMIZATION.md` | Static-first and concurrent scrape speedup controls. |
| `IMPORT_PATH_FIX.md` | Notebook/import path guidance. |

## Primary architecture

Tournament is the default operating path:

```text
search fan-out within 4 SerpAPI credits
  → candidate pool
  → batch scrape
  → batch winners
  → champion URL
  → production URL gate
```

The legacy iterative loop is fallback-only and should be used only for debugging/A-B comparison.

## Active notebooks

```text
notebooks/01_single_product_harness.ipynb
notebooks/02_batch_product_harness.ipynb
```

Both notebooks now surface the complete tournament workflow:

```text
tournament config
4-credit cap
champion URL
runner-up URL
champion margin
batch winners
production_url_ready
production_url_status
browser_openable
highly_scrapable
exact_product_url_match
production_url_score
production_url_reasons
product_coding_input.json
```

## Production handoff rule

For browser-opening, downstream scraping, and product-coding teams, use only rows where:

```text
production_url_ready = true
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
needs_review = false
```

Rows outside this filter can still contain `product_url`, but they are review-only.
