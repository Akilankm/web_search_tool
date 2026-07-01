# Strict Product URL Policy

## Current business rule

`product_url` is reserved for a production-ready champion URL.

The harness must not promote hard-rejected or unsafe candidates into `product_url`, `best_available_url`, or selected reviewer evidence merely because a URL was discovered.

This is the corrected policy after the safe-review gate:

```text
product_url = confirmed production-ready champion only
best_available_url = safe review-only fallback only
candidate_decisions.csv = full candidate evidence, including rejected/unsafe URLs
```

## Why the policy changed

Earlier fallback behavior could retain the highest-ranked discovered URL even when it was a hard product mismatch. That created a dangerous artifact pattern:

```text
wrong candidate URL
  → best_available_url
  → selected evidence in review packet
```

That is no longer acceptable.

Hard mismatches remain visible for audit in candidate tables, but they must not be treated as selected evidence.

## Production handoff rule

For browser-opening, scraping, and downstream product-coding teams, use only rows/artifacts where:

```text
product_url is not blank
production_url_ready = true
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
browser_openable = true
rendered_page_check_passed = true
highly_scrapable = true
exact_product_url_match = true
champion_confirmation.passed = true
champion_confirmation.success_count = champion_confirmation.required_successes
needs_review = false
```

Rows that fail this combined production + confirmation gate are review-only.

## Selection priority

The final URL fields follow this priority:

```text
1. confirmed production-grade exact/scrapable/browser-openable/rendered-product URL
2. safe review candidate in best_available_url / best_reference_url
3. rejected candidates only in candidate_decisions.csv / audit evidence
4. no URL promoted when no safe review candidate exists
```

## Interpretation

| Field / artifact | Meaning |
|---|---|
| `product_url` | Production-ready champion URL only. Empty when no production-ready champion exists. |
| `best_available_url` | Safe review candidate only. Empty when all candidates are unsafe/hard-rejected. |
| `best_reference_url` | Supporting safe-reference URL only; not automated handoff. |
| `candidate_decisions.csv` | Full candidate table, including rejected candidates and reject reasons. |
| `production_url_ready` | True only when selected URL passes browser-openable, rendered-content, scrapability, critical evidence, exact identity, and country policy gates. |
| `production_url_status` | Handoff readiness status for the selected `product_url`. |
| `champion_confirmation.json` | Repeated champion confirmation details for tournament runs when deep artifacts are enabled. |
| `champion_confirmation.passed` | True only when confirmation passed. |
| `browser_openable` | Whether the URL opens technically. Not enough by itself. |
| `rendered_page_check_passed` | Whether the visible rendered page is truly the intended product content. |
| `rendered_page_type` | Visible page type, such as product detail, category, search, homepage, or interstitial. |
| `rendered_verdict` | Rendered-content pass/fail classification. |
| `highly_scrapable` | Whether the URL has scrape-usable product-page evidence. |
| `exact_product_url_match` | Whether the URL is verified as the exact product, not a sibling/variant. |
| `verified_exact_url` | Strict exact URL. Filled only when exact product proof passes final gates. |
| `is_scrapable` | Whether the selected/review URL was scrape-usable/product-page evidence. |
| `needs_review` | True when exactness/scrapability/rendered relevance/coding-readiness is not production-safe. |
| `url_decision_status` | Explains why the selected URL was emitted or why no URL was promoted. |
| `quality_tier` | Enterprise quality tier A/B/C/D/E. |
| `failure_taxonomy` | Machine-readable reasons for weak/review outcomes. |

## Important distinction

This policy does **not** hide weak or rejected evidence.

It separates evidence from selection:

```text
safe/production candidate -> product_url
safe review candidate -> best_available_url
hard rejected candidate -> candidate_decisions.csv only
```

A non-production candidate can still be valuable for audit, but it must carry review/non-production metadata such as:

```text
PRODUCT_URL_NOT_BROWSER_OPENABLE_NEEDS_REVIEW
PRODUCT_URL_RENDERED_CONTENT_MISMATCH_NEEDS_REVIEW
PRODUCT_URL_RENDERED_HOMEPAGE_NEEDS_REVIEW
PRODUCT_URL_RENDERED_LISTING_OR_SEARCH_NEEDS_REVIEW
PRODUCT_URL_RENDERED_INTERSTITIAL_NEEDS_REVIEW
PRODUCT_URL_NOT_HIGHLY_SCRAPABLE_NEEDS_REVIEW
PRODUCT_URL_NOT_EXACT_MATCH_NEEDS_REVIEW
CHAMPION_CONFIRMATION_FAILED
NO_SAFE_REVIEW_CANDIDATE
```

## Zero-safe-candidate edge case

When providers return URL candidates but every candidate is unsafe, hard-rejected, or below review confidence, the row is marked:

```text
NO_SAFE_REVIEW_CANDIDATE
```

This means:

```text
product_url = blank
best_available_url = blank
candidate_decisions.csv still records discovered/rejected URLs
manual escalation or expanded search is required
```

When no URL candidate is discovered at all, the row remains unresolved and should be treated as a run/search failure requiring expanded search strategy or manual escalation.

## Notebook references

Both notebooks surface the production gate, rendered-page fields, review queue, and concise row artifacts:

```text
notebooks/01_single_product_harness.ipynb
notebooks/02_batch_product_harness.ipynb
```

Use them to demonstrate the difference between:

```text
candidate URL
safe review URL
production product_url
rendered_page_check_passed
champion_confirmation.passed
```
