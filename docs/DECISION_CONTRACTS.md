# Decision Contracts

This document defines the business meaning of the major output fields and status values. It is intended for managers, analysts, downstream scraping teams, and product-coding teams.

## Core principle

```text
A URL is not production-ready because it exists.
A URL is not production-ready because it opens.
A URL is production-ready only when it passes production, rendered-content, identity, scrapability, and champion confirmation gates.
```

## Main URL fields

| Field | Business meaning | Automation interpretation |
|---|---|---|
| `product_url` | Production-ready champion URL. | Use only when production gates pass. Blank when no champion exists. |
| `verified_exact_url` | Strict exact URL when exact product proof is strong and production gates pass. | Strongest URL evidence. |
| `best_available_url` | Safe review candidate when no confirmed champion exists. | Review-only, not automated handoff. Blank when no safe review candidate exists. |
| `best_reference_url` | Useful supporting/reference URL when safe enough to expose. | Evidence only. |
| `candidate_decisions.csv` | Candidate table, including rejected URLs and reasons. | Audit/review evidence; not all rows are selected candidates. |

## Handoff fields

| Field | Good value | Meaning |
|---|---|---|
| `production_url_ready` | `true` | URL is safe for browser/scraping/product-coding handoff. |
| `production_url_status` | `PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL` | Final production-readiness class. |
| `needs_review` | `false` | No manual review needed before automated handoff. |
| `browser_openable` | `true` | URL opens technically in a browser-like flow. |
| `rendered_page_check_passed` | `true` | User-visible page is actually the intended product content. |
| `rendered_page_type` | `PRODUCT_DETAIL_PAGE` or `PRODUCT_VARIANT_PAGE` | Visible page type is product-detail-like. |
| `rendered_product_visible` | `true` | Product content is visible. |
| `rendered_content_related` | `true` | Visible/product-facing content aligns with the input product. |
| `rendered_verdict` | `PASS_RENDERED_PRODUCT_CONTENT` | Rendered-content verdict. |
| `highly_scrapable` | `true` | Page has enough evidence and is scrape-usable. |
| `exact_product_url_match` | `true` | URL matches the intended product, not a sibling/variant. |
| `champion_confirmation.passed` | `true` | Repeated champion confirmation passed. |

## Production decision matrix

| Condition | Business decision |
|---|---|
| `product_url` non-blank + `production_url_ready=true` + `rendered_page_check_passed=true` + `needs_review=false` + `champion_confirmation.passed=true` | Automated handoff allowed. |
| `browser_openable=true` but `rendered_page_check_passed=false` | Review-only; rendered page is wrong, non-product, or blocked by an intermediate page. |
| `production_url_ready=false` | Review-only. |
| `needs_review=true` | Review-only. |
| `champion_confirmation.passed=false` | Review-only. |
| `best_available_url` exists but `product_url` is blank | Safe review candidate only; not automated handoff. |
| hard rejected candidate appears in `candidate_decisions.csv` only | Evidence/audit only; not selected or safe review URL. |

## Production gate contract

```text
Candidate URL
  -> browser openable?
  -> rendered product content?
  -> highly scrapable?
  -> critical product evidence complete?
  -> exact product?
  -> champion confirmation?
  -> production-ready handoff
```

Any failed step becomes review-only.

## Identity fields

| Field | Meaning |
|---|---|
| `identity_status` | Overall identity judgement for the selected candidate. |
| `ean_check` | Whether input EAN/GTIN matches page evidence. |
| `title_check` | Strength of product title match. |
| `quantity_check` | Whether pack count/quantity appears consistent. |
| `brand_check` | Whether brand evidence is aligned. |
| `variant_check` | Whether the page appears to be a conflicting variant. |
| `blocking_reasons` | Hard reasons preventing production handoff. |

## Rendered-page fields

| Field | Meaning |
|---|---|
| `rendered_page_check_passed` | True only when the user-visible page is product-detail-like and related to the input product. |
| `rendered_page_type` | Page class: product detail, category, search, homepage, intermediate page, etc. |
| `rendered_product_visible` | Whether product content is visible. |
| `rendered_content_related` | Whether visible/product-facing content aligns with the input. |
| `rendered_match_confidence` | Confidence of rendered-content relevance. |
| `rendered_verdict` | Rendered pass/fail class. |
| `rendered_mismatch_reasons` | Machine-readable rendered-content failure reasons. |
| `rendered_visible_title` | Best visible title captured from rendered/scraped evidence. |
| `rendered_visible_product_name` | Best visible product name captured from rendered/scraped evidence. |
| `rendered_screenshot_path` | Reserved path for screenshot evidence when the screenshot/VLM layer is enabled. |
| `rendered_screenshot_captured` | Whether screenshot evidence was captured. |
| `rendered_llm_used` | Whether a vision/model verdict contributed to rendered check. |

## Retailer and country fields

| Field | Meaning |
|---|---|
| `retailer_check` | Whether the URL aligns with requested retailer evidence. |
| `country_check` | Whether URL/page is acceptable for the requested country policy. |
| `selected_domain` | Domain selected by the final decision. |
| `selected_retailer_name` | Retailer inferred/selected from evidence. |
| `selected_from_requested_retailer` | Whether selected URL came from the requested retailer. |
| `selected_from_global_fallback` | Whether a fallback/global candidate was used. |

## Quality fields

| Field | Meaning |
|---|---|
| `confidence` | Overall confidence in selected decision. |
| `quality_tier` | Enterprise quality tier, usually A/B/C/D/E. |
| `failure_taxonomy` | Machine-readable reasons for weak or review outcomes. |
| `coding_readiness_status` | Whether downstream product coding can consume the evidence. |

## Important statuses

| Status | Business meaning |
|---|---|
| `PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL` | Strongest automated handoff class. |
| `CHAMPION_CONFIRMATION_PASSED` | Repeated champion checks passed. |
| `CHAMPION_CONFIRMATION_FAILED` | Candidate was not stable/strong enough after confirmation. |
| `PRODUCT_URL_NOT_BROWSER_OPENABLE_NEEDS_REVIEW` | URL may exist but is not browser-safe. |
| `PRODUCT_URL_RENDERED_CONTENT_MISMATCH_NEEDS_REVIEW` | URL opens, but rendered content does not match intended product. |
| `PRODUCT_URL_RENDERED_HOMEPAGE_NEEDS_REVIEW` | URL opens to homepage-like content. |
| `PRODUCT_URL_RENDERED_LISTING_OR_SEARCH_NEEDS_REVIEW` | URL opens to listing/search/category-like content. |
| `PRODUCT_URL_RENDERED_INTERSTITIAL_NEEDS_REVIEW` | URL opens to an intermediate or access page. |
| `PRODUCT_URL_NOT_HIGHLY_SCRAPABLE_NEEDS_REVIEW` | Page is not rich/scrape-ready enough. |
| `PRODUCT_URL_NOT_EXACT_MATCH_NEEDS_REVIEW` | URL likely wrong product, variant, or sibling. |
| `PRODUCT_URL_GLOBAL_OR_COUNTRY_MISMATCH_NEEDS_REVIEW` | Country/fallback policy concern. |
| `NO_SAFE_REVIEW_CANDIDATE` | No candidate was safe enough even for best review URL promotion. |
| `STRICT_PRODUCT_URL_REQUIRED_BUT_NO_URL_CANDIDATE_AVAILABLE` | No viable candidate was discovered. |

## Review queue philosophy

The review queue is a strength, not a weakness.

```text
All products
  -> enough production evidence?
  -> yes: automated handoff
  -> no: review queue with failure reason, safe review URL if available, and candidate decisions
```

A mature automation system must know when not to automate.
