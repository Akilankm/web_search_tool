# Production-Grade Product URL Gate

## Requirement

The URL emitted in `product_url` is intended for downstream browser-opening, scraping, and product-coding workflows. It must therefore represent the exact product page that a user actually sees, not merely a URL that returns HTTP 200 or opens in a browser.

The harness now separates three ideas:

```text
browser_openable = the URL opens technically
rendered_page_check_passed = the user-visible page is actually the intended product content
production_url_ready = the URL is safe for automated browser/scraping/product-coding handoff
```

## Production-grade definition

A URL is production-grade only when it passes all gates below:

```text
browser_openable = true
rendered_page_check_passed = true
highly_scrapable = true
critical_product_evidence_complete = true
exact_product_url_match = true
country_acceptable = true
needs_review = false
```

In plain English:

```text
Champion = browser-openable
        + rendered product page visible
        + exact product identity validated
        + rich enough product evidence
        + scrapable
        + country/retailer policy acceptable
```

## Rendered-page relevance gate

`browser_openable=true` is necessary but not sufficient. A URL can open and still be wrong if it renders a homepage, category page, search page, consent wall, login wall, anti-bot page, store selector, or unrelated product content.

The rendered gate blocks those cases before a candidate can become production-ready.

### Rendered fields

`final_submission.csv`, `final_row.csv`, and production assessment JSON/dicts can expose:

```text
rendered_page_check_passed
rendered_page_type
rendered_product_visible
rendered_content_related
rendered_match_confidence
rendered_verdict
rendered_mismatch_reasons
rendered_visible_title
rendered_visible_product_name
rendered_screenshot_path
rendered_screenshot_captured
rendered_llm_used
```

### Page types

The rendered-page verifier classifies the visible page as one of:

```text
PRODUCT_DETAIL_PAGE
PRODUCT_VARIANT_PAGE
CATEGORY_PAGE
SEARCH_RESULTS_PAGE
HOMEPAGE
CONSENT_OR_INTERSTITIAL
LOGIN_OR_ACCESS_WALL
STORE_SELECTOR
ERROR_PAGE
ANTI_BOT_PAGE
EMPTY_OR_BROKEN_RENDER
NON_PRODUCT_PAGE
```

Only product-detail-like page types can pass the rendered gate:

```text
PRODUCT_DETAIL_PAGE
PRODUCT_VARIANT_PAGE
```

Even then, the visible/product-facing title and content must be related to the input product.

## Highly scrapable

The page must be scrape-usable, product-page-like, and rich enough for the downstream scraper/coding team. Evidence can include product title, product name, JSON-LD/GTIN, specs, attributes, description, images, price, availability, brand, manufacturer, or other product evidence.

## Exact product URL match

The page must be verified as the exact product, not just a sibling variant, category page, search result, or related product. The gate rejects hard conflicts such as blocking EAN conflict, variant conflict, hard identity mismatch, or rendered content mismatch.

## Champion confirmation

In tournament mode, passing the production URL gate is necessary but not sufficient for handoff. The selected champion candidate must also pass repeated confirmation.

Default requirement:

```text
champion_confirmation.required_attempts = 3
champion_confirmation.required_successes = 3
champion_confirmation.passed = true
champion_confirmation.final_url_stable = true
champion_confirmation.evidence_stable = true
```

The details are written to optional/deep row artifacts when enabled:

```text
champion_confirmation.json
champion_confirmation.md
```

## Final selection behavior

The harness now applies four layers:

```text
Layer 1: production-grade URL promotion
Layer 2: rendered product-content gate
Layer 3: champion confirmation gate
Layer 4: safe-review fallback gate
```

If a candidate URL is production-grade and passes champion confirmation, it is promoted into `product_url` as the confirmed champion.

If no confirmed production-ready champion exists, `product_url` remains empty. A fallback URL is retained only in `best_available_url` / `best_reference_url` if it passes the safe-review gate. Hard rejected candidates remain visible in `candidate_decisions.csv` and review artifacts, but they are not promoted as selected evidence.

## Batch columns and row artifacts

`final_submission.csv` includes production URL fields such as:

```text
production_url_ready
production_url_status
browser_openable
rendered_page_check_passed
rendered_page_type
rendered_verdict
rendered_mismatch_reasons
highly_scrapable
exact_product_url_match
production_url_score
production_url_reasons
```

The concise row packet remains:

```text
output/<row_id>/
├── final_row.csv
├── review_summary.md
├── review_decision.json
├── candidate_decisions.csv
└── product_coding_input.json
```

## Status values

Production-ready status:

```text
PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
```

Rendered-page failure statuses:

```text
PRODUCT_URL_RENDERED_CONTENT_MISMATCH_NEEDS_REVIEW
PRODUCT_URL_RENDERED_HOMEPAGE_NEEDS_REVIEW
PRODUCT_URL_RENDERED_LISTING_OR_SEARCH_NEEDS_REVIEW
PRODUCT_URL_RENDERED_INTERSTITIAL_NEEDS_REVIEW
```

Other review / non-production statuses:

```text
PRODUCT_URL_NOT_BROWSER_OPENABLE_NEEDS_REVIEW
PRODUCT_URL_CRITICAL_DETAILS_NOT_EXTRACTED_NEEDS_REVIEW
PRODUCT_URL_NOT_HIGHLY_SCRAPABLE_NEEDS_REVIEW
PRODUCT_URL_NOT_EXACT_MATCH_NEEDS_REVIEW
PRODUCT_URL_GLOBAL_OR_COUNTRY_MISMATCH_NEEDS_REVIEW
PRODUCT_URL_NOT_PRODUCTION_READY_NEEDS_REVIEW
NO_SAFE_REVIEW_CANDIDATE
```

Champion confirmation statuses:

```text
CHAMPION_CONFIRMATION_PASSED
CHAMPION_CONFIRMATION_FAILED
NO_CHAMPION_CANDIDATE_TO_CONFIRM
```

## Operational interpretation

| Column / artifact | How to use it |
|---|---|
| `product_url` | Production champion URL. Empty when no production-ready champion exists. |
| `best_available_url` | Safe review-only URL. Empty when no safe review candidate exists. |
| `production_url_ready=true` | Candidate passed production URL gates. Still require champion confirmation for tournament handoff. |
| `browser_openable=true` | URL opens technically. Not enough by itself. |
| `rendered_page_check_passed=true` | The user-visible page appears to show the intended product content. |
| `rendered_page_type` | User-visible page class: product detail, category, search, homepage, interstitial, etc. |
| `rendered_verdict` | Pass/fail reason for rendered content. |
| `highly_scrapable=true` | Page has scrape-usable product evidence. |
| `exact_product_url_match=true` | Page represents the exact product. |
| `production_url_status` | Final product URL readiness class. |
| `production_url_reasons` | Why a URL is not production-grade. |
| `candidate_decisions.csv` | Shows rejected candidates without promoting them as selected evidence. |
| `product_coding_input_path` | Path to downstream product-coding handoff JSON. |

## High-stakes usage policy

For high-stakes production coding, treat rows as auto-usable only when:

```text
product_url is not blank
production_url_ready = true
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
rendered_page_check_passed = true
champion_confirmation.passed = true
champion_confirmation.success_count = champion_confirmation.required_successes
needs_review = false
```

Rows that fail this combined gate are review-only. Hard mismatches should remain in candidate/rejection evidence, not in selected or best-review URL fields.

## Notebook workflow

Use the notebooks for demonstration and verification:

```text
notebooks/01_single_product_harness.ipynb
notebooks/02_batch_product_harness.ipynb
```

The single-product notebook shows candidate-level production gate diagnostics. The batch notebook shows production-ready filters, review queue, metrics, and concise row packets.

## Recommended team demo filter

In `outputs/final_submission.csv`, first filter:

```python
ready = df[
    df["product_url"].astype(str).str.strip().ne("")
    & (df["production_url_ready"].astype(str).str.lower().isin(["true", "1", "yes"]))
    & (df["production_url_status"] == "PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL")
    & (df["rendered_page_check_passed"].astype(str).str.lower().isin(["true", "1", "yes"]))
    & (~df["needs_review"].astype(str).str.lower().isin(["true", "1", "yes"]))
]
```

Then, for tournament runs, verify each ready row's champion confirmation has:

```text
passed = true
success_count = required_successes
```
