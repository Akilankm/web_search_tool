# Documentation Index

Use this index when presenting or operating the Product Evidence Harness.

This folder now keeps only current operating documentation. One-off PR notes, retrospective patch summaries, and stale implementation-history documents have been removed from the active docs tree.

## Start here

| Document | Purpose |
|---|---|
| `../README.md` | Main project overview for the tournament-first architecture and champion confirmation gate. |
| `END_TO_END_OPERATIONS.md` | Operational runbook for inputs, env, batch run, artifacts, champion confirmation, enforced preflight/batch limits, and handoff. |
| `TOURNAMENT_MODE.md` | Primary architecture, four-credit SerpAPI cap, enforced top-k/batch limits, champion selection, confirmation, and artifacts. |
| `TOURNAMENT_CHAMPION_CONTRACT.md` | Exact champion contract, including repeated confirmation requirements. |
| `CHAMPION.md` | Short champion definition and confirmation requirement. |
| `TEAM_SHOWCASE_GUIDE.md` | Team-facing demo script and business explanation. |
| `PRODUCTION_GRADE_PRODUCT_URL.md` | Exact handoff rules for browser/scraping/product-coding teams. |
| `STRICT_PRODUCT_URL_POLICY.md` | Explains the distinction between emitted URLs, confirmed champions, and review-only candidates. |
| `ELITE_EVIDENCE_ENGINE.md` | Evidence graph, quality tiers, coding readiness, metrics, and review artifacts. |
| `LATENCY_OPTIMIZATION.md` | Static-first and concurrent scrape speedup controls. |
| `IMPORT_PATH_FIX.md` | Notebook/import path guidance. |

## Primary architecture

Tournament is the default operating path:

```text
search fan-out within 4 SerpAPI credits
  → candidate pool
  → top-k preflight candidate cut
  → bounded batch scrape
  → batch winners
  → production-ready champion candidate
  → champion confirmation gate, default 3 checks
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
preflight top-k
max tournament batches
champion URL
runner-up URL
champion margin
champion confirmation attempts
champion confirmation successes
champion_confirmation.json
champion_confirmation.md
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
champion_confirmation.passed = true
champion_confirmation.success_count = champion_confirmation.required_successes
needs_review = false
```

Rows outside this filter can still contain `product_url`, but they are review-only.
