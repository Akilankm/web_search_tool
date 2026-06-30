# Product Evidence Harness

Local Python package for **tournament-first exact product URL discovery, production URL validation, and product-coding evidence handoff**.

This is intentionally not an AzureML component. It is a local PDM/Python codebase with notebooks and CLI entrypoints.

## Primary architecture

The primary operating model is **candidate tournament selection**:

```text
Input product identity
  → SerpAPI search fan-out, hard-capped at 4 search credits per product
  → broad candidate URL pool
  → cheap preflight ranking
  → concurrent batch scraping
  → deterministic identity, EAN, title, variant, country, retailer, and page-quality checks
  → batch winners
  → champion URL
  → production URL gate
  → evidence artifacts and product-coding handoff
```

The older iterative loop is retained only as a legacy/debug fallback when tournament mode is explicitly disabled.

## High-stakes handoff policy

`product_url` and `production_url_ready` must not be confused:

```text
product_url = best discovered/champion URL emitted by the harness
production_url_ready = whether product_url is safe for browser-opening, downstream scraping, and product coding
```

For browser, scraping, and product-coding teams, use only rows where:

```text
production_url_ready = true
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
needs_review = false
```

Rows that fail this gate can still have `product_url`, but they are **review-only**.

## Tournament defaults

Tournament mode is the default.

```env
PRODUCT_HARNESS_ENABLE_TOURNAMENT_MODE=true
PRODUCT_HARNESS_TOURNAMENT_MAX_SERP_CREDITS=4
PRODUCT_HARNESS_TOURNAMENT_CANDIDATE_POOL=150
PRODUCT_HARNESS_TOURNAMENT_PREFLIGHT_TOP_K=60
PRODUCT_HARNESS_TOURNAMENT_BATCH_SIZE=20
PRODUCT_HARNESS_TOURNAMENT_MAX_BATCHES=3
```

The code clamps `PRODUCT_HARNESS_TOURNAMENT_MAX_SERP_CREDITS` to a maximum of `4`.

## Input contract

| Field | Required | Role |
|---|---:|---|
| `row_id` | Recommended | Stable product/row identifier. |
| `main_text` | Yes | Primary product identity text. |
| `country_code` | Yes | Country-first search market. |
| `ean` / `gtin` | No | Strong user-provided anchor. Must remain a string. |
| `retailer_name` | No | Preferred first evidence source only; not a hard final constraint. |
| `language_code` | No | Optional search language override. |
| `region` | No | Optional market hint. |

EAN/GTIN identifiers are read as strings. If Excel has already converted an EAN into scientific notation, the system flags `EAN_SCIENTIFIC_NOTATION_LOSS_RISK` and avoids using the corrupted value as exact evidence.

## URL decision semantics

| Field | Meaning |
|---|---|
| `product_url` | Best discovered/champion URL. Populated whenever any candidate/search/scrape URL exists. |
| `production_url_ready` | True only when `product_url` is browser-openable, highly scrapable, and exact-product verified. |
| `production_url_status` | Final handoff/readiness class for the selected `product_url`. |
| `browser_openable` | Whether the selected page is expected to open in a normal browser. |
| `highly_scrapable` | Whether the selected page is product-page-like, scrape-usable, and evidence-rich. |
| `exact_product_url_match` | Whether the selected URL is verified as the exact product, not a sibling/variant. |
| `verified_exact_url` | Strict exact URL. Filled only when exact product proof passes final gates. |
| `needs_review` | True when the final URL is not production-safe or not coding-ready. |
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
├── quality_assessment.md
├── tournament_bracket.json
├── tournament_bracket.md
└── batch_winners.csv
```

### Batch-level outputs

```text
outputs/
├── final_submission.csv
├── review_queue.csv
├── batch_summary.md
└── metrics.json
```

`final_submission.csv` is the main business artifact. For production handoff, filter by `production_url_ready=true` and `needs_review=false`.

## Product-coding handoff

The main downstream file is:

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

## Active notebooks

```text
notebooks/01_single_product_harness.ipynb
notebooks/02_batch_product_harness.ipynb
```

Both notebooks now cover the complete end-to-end tournament workflow:

```text
tournament config
4-credit SerpAPI cap
champion URL
runner-up URL
champion margin
batch winners
production URL readiness
product-coding input artifact
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

## Batch usage

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
docs/END_TO_END_OPERATIONS.md
docs/TOURNAMENT_MODE.md
docs/PRODUCTION_GRADE_PRODUCT_URL.md
docs/STRICT_PRODUCT_URL_POLICY.md
docs/ELITE_EVIDENCE_ENGINE.md
docs/TEAM_SHOWCASE_GUIDE.md
docs/LATENCY_OPTIMIZATION.md
docs/IMPORT_PATH_FIX.md
```

## Import path note

This project uses a standard `src/` package layout. In notebooks, add `<repo>/src` to `sys.path`, then import with `product_evidence_harness`. Do not import with `src.product_evidence_harness`. See `docs/IMPORT_PATH_FIX.md`.
