# Strict Product URL Policy

## Business rule

`product_url` must be populated with the best discovered URL whenever the harness has found any URL candidate from search, AI reference, scrape evidence, requested retailer, same-country alternative retailer, or global fallback.

The harness must not suppress the URL merely because exactness or scrapability is weak. Instead, risk is exposed through explicit metadata.

## Selection priority

The final operational field follows this priority:

```text
1. verified exact requested-retailer URL
2. verified exact same-country alternative retailer URL
3. verified exact global fallback URL
4. best available scrape-usable product URL
5. best available non-scrapable product-like URL
6. best discovered candidate URL from search/AI reference
```

## Interpretation

| Field | Meaning |
|---|---|
| `product_url` | Always the best discovered URL when any URL exists. It may require review. |
| `verified_exact_url` | Strict exact URL. Filled only when exact product proof passes final gates. |
| `is_scrapable` | Whether the selected `product_url` was scrape-usable/product-page evidence. |
| `needs_review` | True when exactness/scrapability/coding-readiness is not production-safe. |
| `url_decision_status` | Explains why the selected URL was emitted and what risk applies. |
| `quality_tier` | Enterprise quality tier A/B/C/D/E. |
| `failure_taxonomy` | Machine-readable reasons for weak/review outcomes. |

## Important distinction

This policy does **not** pretend weak evidence is correct.

A non-scrapable or unverified URL can still be emitted as `product_url`, but it must carry a review status such as:

```text
BEST_AVAILABLE_PRODUCT_URL_NOT_SCRAPABLE_NEEDS_REVIEW
DISCOVERED_CANDIDATE_URL_UNSCRAPED_NEEDS_REVIEW
REFERENCE_URL_FROM_SEARCH_NEEDS_REVIEW
```

## Zero-candidate edge case

The harness cannot invent a real product URL if all providers return zero URL candidates. In that exceptional case, the row is marked:

```text
STRICT_PRODUCT_URL_REQUIRED_BUT_NO_URL_CANDIDATE_AVAILABLE
```

This should be treated as a run/search failure requiring expanded search budget or manual escalation, not as an acceptable blank product URL outcome.
