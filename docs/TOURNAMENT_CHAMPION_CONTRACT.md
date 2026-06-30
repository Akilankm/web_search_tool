# Tournament Champion Contract

## Purpose

The tournament champion is the business-selected URL.

```text
product_url = tournament champion URL
runner_up_url = supporting/debug evidence only
production_url_ready = whether the champion is safe for handoff
```

This means the system no longer replaces the tournament champion with a weaker runner-up simply because the runner-up is more scrapeable. The champion remains the URL everyone should inspect.

## Handoff rule

A champion is production-ready only when:

```text
production_url_ready = true
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
needs_review = false
```

If the champion is not production-ready, the row remains review-only:

```text
product_url = tournament champion
needs_review = true
verified_exact_url = empty
```

## Runner-up interpretation

Runner-ups help explain the decision. They are not the primary business URL.

Use runner-ups for:

```text
comparison
manual review
fallback investigation
source consensus
```

Do not use runner-ups as production handoff URLs unless a future review explicitly promotes one.

## Invalid EAN behavior

Invalid EAN/GTIN values are not used in search queries or LLM prompts. They remain visible as input evidence and diagnostics, but they are not treated as exact identity anchors.

Example:

```text
7800270000000
```

This fails GTIN checksum validation, so it is ignored for search construction and exact EAN matching.

## Coding readiness rule

A row cannot be `CODING_READY` unless the selected champion is production-ready and exact.

If the champion has useful scrape evidence but is not production-ready exact, the coding status is downgraded to:

```text
CODING_PARTIAL
```

or:

```text
URL_ONLY_NOT_CODING_READY
```

## Requested retailer metrics

Tournament search actions are recorded with scope metadata so requested-retailer status is accurate.

Expected values after a requested-retailer tournament query:

```text
requested_retailer_attempted = true
requested_retailer_scrapability_status != NOT_ATTEMPTED
```

## Operational interpretation

For a row like MercadoLibre requested, Colombia country, and a MercadoLibre Argentina champion:

```text
product_url = MercadoLibre tournament champion
needs_review = true if wrong country or not production-ready
runner_up_url = supporting comparison only
```

That is expected tournament behavior.
