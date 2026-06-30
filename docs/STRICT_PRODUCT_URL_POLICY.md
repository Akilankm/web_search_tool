# Strict Product URL Policy

## Business rule

`product_url` must be populated with the best discovered URL whenever the harness has found any URL candidate from search, scrape evidence, requested retailer, same-country alternative retailer, or global fallback.

The harness must not suppress the URL merely because exactness or scrapability is weak. Instead, risk is exposed through explicit metadata.

## Production handoff rule

The strict non-empty rule does **not** mean every `product_url` is safe for production handoff.

For the browser-opening team, scraping team, and downstream product-coding team, use only rows/artifacts where:

```text
production_url_ready = true
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
champion_confirmation.passed = true
champion_confirmation.success_count = champion_confirmation.required_successes
needs_review = false
```

Rows that fail this combined production + confirmation gate can still have a `product_url`, but they are review-only.

## Selection priority

The final operational field follows this priority:

```text
1. confirmed production-grade exact/scrapable/browser-openable URL
2. production-grade exact URL that still needs confirmation review
3. verified exact requested-retailer URL
4. verified exact same-country alternative retailer URL
5. verified exact global fallback URL
6. best available scrape-usable product URL
7. best available non-scrapable product-like URL
8. best discovered candidate URL from search/reference
```

## Interpretation

| Field / artifact | Meaning |
|---|---|
| `product_url` | Always the best discovered URL when any URL exists. It may require review. |
| `production_url_ready` | True only when the selected URL is browser-openable, highly scrapable, and exact-product verified. |
| `production_url_status` | Handoff readiness status for the selected `product_url`. |
| `champion_confirmation.json` | Repeated champion confirmation details for tournament runs. |
| `champion_confirmation.passed` | True only when confirmation passed. |
| `browser_openable` | Whether the URL is expected to open normally in a browser. |
| `highly_scrapable` | Whether the URL has scrape-usable product-page evidence. |
| `exact_product_url_match` | Whether the URL is verified as the exact product, not a sibling/variant. |
| `verified_exact_url` | Strict exact URL. Filled only when exact product proof passes final gates. |
| `is_scrapable` | Whether the selected `product_url` was scrape-usable/product-page evidence. |
| `needs_review` | True when exactness/scrapability/coding-readiness is not production-safe. |
| `url_decision_status` | Explains why the selected URL was emitted and what risk applies. |
| `quality_tier` | Enterprise quality tier A/B/C/D/E. |
| `failure_taxonomy` | Machine-readable reasons for weak/review outcomes. |

## Important distinction

This policy does **not** pretend weak evidence is correct.

A non-scrapable, unverified, or unconfirmed URL can still be emitted as `product_url`, but it must carry review/non-production metadata such as:

```text
PRODUCT_URL_NOT_BROWSER_OPENABLE_NEEDS_REVIEW
PRODUCT_URL_NOT_HIGHLY_SCRAPABLE_NEEDS_REVIEW
PRODUCT_URL_NOT_EXACT_MATCH_NEEDS_REVIEW
CHAMPION_CONFIRMATION_FAILED
BEST_AVAILABLE_PRODUCT_URL_NOT_SCRAPABLE_NEEDS_REVIEW
DISCOVERED_CANDIDATE_URL_UNSCRAPED_NEEDS_REVIEW
REFERENCE_URL_FROM_SEARCH_NEEDS_REVIEW
```

## Zero-candidate edge case

The harness cannot invent a real product URL if all providers return zero URL candidates. In that exceptional case, the row is marked:

```text
STRICT_PRODUCT_URL_REQUIRED_BUT_NO_URL_CANDIDATE_AVAILABLE
```

This should be treated as a run/search failure requiring expanded search strategy or manual escalation, not as an acceptable blank product URL outcome.

## Notebook references

Both notebooks now surface the production gate and champion confirmation artifacts:

```text
notebooks/01_single_product_harness.ipynb
notebooks/02_batch_product_harness.ipynb
```

Use them to demonstrate the difference between `product_url`, `production_url_ready`, and `champion_confirmation.passed`.
