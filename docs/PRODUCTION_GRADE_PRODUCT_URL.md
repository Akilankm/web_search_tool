# Production-Grade Product URL Gate

## Requirement

The URL emitted in `product_url` is intended for two downstream teams:

1. a team that opens the URL manually in a browser
2. a team that scrapes the URL to collect complete product information

Because of that, the harness now prefers a **production-grade product URL** over a merely discovered URL.

## Production-grade definition

A URL is production-grade only when it passes all of these gates:

```text
browser_openable = true
highly_scrapable = true
exact_product_url_match = true
country match is acceptable
no hard variant/EAN/product identity conflict
```

### Browser-openable

The page must be reachable and not look like a homepage, soft-404, or blocked/thin placeholder.

### Highly scrapable

The page must be scrape-usable, product-page-like, and rich enough for the downstream scraper/coding team. Evidence can include title, product name, JSON-LD/GTIN, specs, attributes, description, images, price, availability, or other structured product evidence.

### Exact product URL match

The page must be verified as the exact product, not just a sibling variant or related product. The gate requires deterministic verification and rejects hard conflicts such as variant conflict or blocking EAN conflict.

## Final selection behavior

The harness now applies two layers:

```text
Layer 1: production-grade URL promotion
Layer 2: strict non-empty fallback URL policy
```

If any candidate URL is production-grade, it is promoted into `product_url` even if an earlier weak URL was initially selected.

If no candidate is production-grade, the harness still preserves the strict non-empty business rule by emitting the best discovered fallback URL, but marks it clearly as non-production/review-only.

## New batch columns

`final_submission.csv` now includes:

```text
production_url_ready
production_url_status
browser_openable
highly_scrapable
exact_product_url_match
production_url_score
production_url_reasons
```

## Status values

Production-ready status:

```text
PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
```

Review / non-production statuses:

```text
PRODUCT_URL_NOT_BROWSER_OPENABLE_NEEDS_REVIEW
PRODUCT_URL_NOT_HIGHLY_SCRAPABLE_NEEDS_REVIEW
PRODUCT_URL_NOT_EXACT_MATCH_NEEDS_REVIEW
PRODUCT_URL_GLOBAL_OR_COUNTRY_MISMATCH_NEEDS_REVIEW
PRODUCT_URL_NOT_PRODUCTION_READY_NEEDS_REVIEW
```

Strict no-candidate status:

```text
STRICT_PRODUCT_URL_REQUIRED_BUT_NO_URL_CANDIDATE_AVAILABLE
```

## Operational interpretation

| Column | How to use it |
|---|---|
| `product_url` | Best URL emitted by the harness. |
| `production_url_ready=true` | Safe for manual browser opening and downstream scraping/coding. |
| `browser_openable=true` | Page is expected to open in a browser. |
| `highly_scrapable=true` | Page has scrape-usable product evidence. |
| `exact_product_url_match=true` | Page represents the exact product. |
| `production_url_status` | Final product URL readiness class. |
| `production_url_reasons` | Why a URL is not production-grade. |

## High-stakes usage policy

For high-stakes production coding, treat rows as auto-usable only when:

```text
production_url_ready = true
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
needs_review = false
```

Rows that fail this gate still have a `product_url`, but they are review-only and should not be handed to the scraping/coding team as production-ready evidence.
