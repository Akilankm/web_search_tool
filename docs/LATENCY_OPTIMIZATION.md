# Latency Optimization

This branch adds speedups that preserve the existing product identity and verification semantics.

## What changed

### 1. Static-first scraping

The scraper now tries a fast `requests` fetch first. If the static HTML already exposes enough product evidence through title/meta/JSON-LD/specs/price/images, the harness avoids browser automation.

If static evidence is thin, blocked, or not product-like, the scraper escalates to crawl4ai.

### 2. Concurrent scrape batches

The planner now emits scrape batches for candidate phases instead of scraping only one URL per loop iteration:

- requested-retailer candidates
- same-country candidates
- global fallback candidates

The executor records every scrape result, extracts evidence, verifies identity, and refreshes scorecards after the batch.

### 3. Configurable knobs

```env
PRODUCT_HARNESS_SCRAPE_CONCURRENCY=6
PRODUCT_HARNESS_STATIC_FETCH_FIRST=true
PRODUCT_HARNESS_BROWSER_FALLBACK_ONLY=true
PRODUCT_HARNESS_STATIC_TIMEOUT_SECONDS=8
PRODUCT_HARNESS_CRAWL_PAGE_TIMEOUT_MS=20000
PRODUCT_HARNESS_MAX_REQUESTED_RETAILER_SCRAPES=6
PRODUCT_HARNESS_MAX_COUNTRY_SCRAPES=30
PRODUCT_HARNESS_MAX_GLOBAL_SCRAPES=12
```

## Expected impact

The largest wall-clock reduction comes from replacing sequential scrape actions with concurrent scrape batches. Static-first fetches also avoid expensive browser runs for product pages where JSON-LD/meta evidence is already available.

## Correctness boundary

This change does not relax final URL gates. Every scraped URL still goes through the same evidence extraction, identity verification, score refresh, and final selector logic.
