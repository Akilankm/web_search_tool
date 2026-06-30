# Product Evidence Harness

Local Python package for **LLM-guided exact product URL discovery, production URL validation, and product-coding evidence handoff**.

This is intentionally not an AzureML component yet. It is a local PDM/Python codebase with notebooks and CLI entrypoints.

## Core strategy

The current strategy is **retailer-scrapability-aware loop engineering**:

```text
LLM builds product identity and search campaign
  → SerpAPI performs high-yield search and returns many candidate URLs
  → crawl4ai/static scraping validates useful candidate pages
  → deterministic extractors and detectors score page type, richness, exactness, EAN, country fit, and variant conflicts
  → LLM adjudicates exact product or repairs the search when enabled
  → requested retailer is tried first
  → same-country alternative retailers are searched when requested retailer is weak/blocked/wrong
  → global fallback is used when country evidence fails
  → production-grade exact/scrapable/browser-openable URL is promoted when available
  → strict non-empty product_url fallback is used when any URL candidate exists
  → production_url_ready / browser_openable / highly_scrapable / exact_product_url_match explain team handoff safety
```

## High-stakes handoff policy

`product_url` has two business meanings that must not be confused:

```text
product_url = best discovered URL emitted by the harness
production_url_ready = whether product_url is safe for browser-opening and downstream scraping/coding
```

For the browser team, scraping team, and product-coding handoff, use only rows where:

```text
production_url_ready = true
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
needs_review = false
```

Rows that fail this gate can still have a `product_url`, but they are **review-only** and should not be treated as production-ready evidence.

## Input contract

| Field | Required | Role |
|---|---:|---|
| `main_text` | Yes | Primary product identity text. |
| `country_code` | Yes | Country-first search market. |
| `ean` / `gtin` | No | Strong user-provided anchor. Must remain a string. LLM must never invent it. |
| `retailer_name` | No | Preferred first evidence source only; not a hard final constraint. |
| `language_code` | No | Optional search language override; otherwise derived from country profile. |
| `region` | No | Optional market hint. |

EAN/GTIN identifiers are read as strings. If Excel has already converted an EAN into scientific notation, the system flags `EAN_SCIENTIFIC_NOTATION_LOSS_RISK` and avoids using the corrupted value as exact evidence.

## Active notebooks

```text
notebooks/01_single_product_harness.ipynb
notebooks/02_batch_product_harness.ipynb
```

Both notebooks expose the production URL handoff fields:

```text
production_url_ready
production_url_status
browser_openable
highly_scrapable
exact_product_url_match
production_url_score
production_url_reasons
```

## URL decision semantics

| Field | Meaning |
|---|---|
| `product_url` | Best discovered URL. Populated whenever any candidate/search/scrape URL exists. |
| `production_url_ready` | True only when `product_url` is browser-openable, highly scrapable, and exact-product verified. |
| `production_url_status` | Final handoff/readiness class for the selected `product_url`. |
| `browser_openable` | Whether the selected page is expected to open in a normal browser. |
| `highly_scrapable` | Whether the selected page is product-page-like, scrape-usable, and evidence-rich. |
| `exact_product_url_match` | Whether the selected URL is verified as the exact product, not a sibling/variant. |
| `verified_exact_url` | Strict exact URL. Filled only when exact product proof passes final gates. |
| `is_scrapable` | Whether selected `product_url` had scrape-usable product-page evidence. |
| `needs_review` | True when the final URL is not production-safe or not coding-ready. |
| `url_decision_status` | Exact/requested-retailer/country-alternative/global/review/failure status. |
| `quality_tier` | Enterprise quality tier A/B/C/D/E. |
| `failure_taxonomy` | Machine-readable reasons for weak/review outcomes. |

Important status values:

```text
PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
PRODUCT_URL_NOT_BROWSER_OPENABLE_NEEDS_REVIEW
PRODUCT_URL_NOT_HIGHLY_SCRAPABLE_NEEDS_REVIEW
PRODUCT_URL_NOT_EXACT_MATCH_NEEDS_REVIEW
PRODUCT_URL_GLOBAL_OR_COUNTRY_MISMATCH_NEEDS_REVIEW
STRICT_PRODUCT_URL_REQUIRED_BUT_NO_URL_CANDIDATE_AVAILABLE
```

## Output contract

```text
CSV = final operational answer
Markdown = readable evidence and decision trace
JSON = compact machine replay/debug trace and product-coding handoff
```

### Row-level artifact packet

Each product row writes:

```text
output/<row_id>/
├── final_row.csv
├── report.md
├── search_plan.md
├── candidate_review.md
├── scrape_evidence.md
├── retailer_scrapability.md
├── final_decision.md
├── decision_trace.md
├── trace.json
├── enterprise_assessment.json
├── evidence_graph.json
├── product_coding_input.json
├── review_feedback_template.json
└── quality_assessment.md
```

### Batch-level outputs

```text
outputs/
├── final_submission.csv
├── review_queue.csv
├── batch_summary.md
└── metrics.json
```

`final_submission.csv` is the main business/submission artifact. For production handoff, filter by `production_url_ready=true` and `needs_review=false`.

## Product-coding handoff

The most important downstream file is:

```text
output/<row_id>/product_coding_input.json
```

It includes:

```text
selected_url
verified_exact_url
supporting_urls
selected_page_evidence
brand/manufacturer/description/specs/images/EAN evidence
identity_verification
quality_tier
coding_readiness_status
review_flags
```

## Cost-aware operating model

Paid/controlled:

```text
SerpAPI calls
LLM calls
```

Free/open-source and used aggressively:

```text
crawl4ai/static scraping
deterministic extraction
detector scoring
candidate dedupe/ranking
```

Recommended defaults favor high-yield search and broad scraping:

```env
PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES=3
PRODUCT_HARNESS_SERP_RESULTS=100
PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES=1
PRODUCT_HARNESS_MAX_SCRAPES=180
PRODUCT_HARNESS_MAX_ITERATIONS=240
PRODUCT_HARNESS_LLM_MAX_CALLS_PER_PRODUCT=4
PRODUCT_HARNESS_SCRAPE_CONCURRENCY=6
PRODUCT_HARNESS_STATIC_FETCH_FIRST=true
PRODUCT_HARNESS_BROWSER_FALLBACK_ONLY=true
PRODUCT_HARNESS_CRAWL_PAGE_TIMEOUT_MS=20000
```

## Minimal single-product usage

```python
from product_evidence_harness import HarnessConfig, ProductEvidenceHarness, ProductQuery, SerpAPIConfig, ProductionURLGate

product = ProductQuery(
    row_id="CO-ML-0001",
    main_text="PUT PRODUCT TEXT HERE",
    country_code="CO",
    ean="",
    retailer_name="Mercado Libre",
)

config = HarnessConfig.from_env(".env")
serp_config = SerpAPIConfig.from_env(country_code=product.country_code, language_code="es")
harness = ProductEvidenceHarness(serp_config=serp_config, config=config)
trace = harness.run(product, return_trace=True)

match = trace.best_match
production = ProductionURLGate().assess_url_in_state(trace.state, match.product_url or "")

print(match.product_url)
print(production.to_dict() if production else "No production assessment")
```

## CLI usage

Single product:

```bash
python main.py \
  --row-id CO-ML-0001 \
  --main-text "PUT PRODUCT TEXT HERE" \
  --country-code CO \
  --retailer-name "Mercado Libre" \
  --ean "7701234567890"
```

Batch:

```bash
python batch_main.py \
  --input data/products.xlsx \
  --output outputs/final_submission.csv \
  --workers 4
```

## Validation

```bash
PYTHONPATH=src python -m compileall -q src main.py batch_main.py
PYTHONPATH=src pytest -q
```

## Related docs

```text
docs/PRODUCTION_GRADE_PRODUCT_URL.md
docs/STRICT_PRODUCT_URL_POLICY.md
docs/ELITE_EVIDENCE_ENGINE.md
docs/TEAM_SHOWCASE_GUIDE.md
docs/LATENCY_OPTIMIZATION.md
docs/IMPORT_PATH_FIX.md
```

## Import path note

This project uses a standard `src/` package layout. In notebooks, add `<repo>/src` to `sys.path`, then import with `product_evidence_harness`. Do not import with `src.product_evidence_harness`. See `docs/IMPORT_PATH_FIX.md`.
