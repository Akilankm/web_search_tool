# Tournament Champion Contract

## Purpose

The tournament champion is the production-usable business URL.

```text
product_url = tournament champion URL only when a true champion exists
runner_up_url = supporting/debug evidence only
best_review_candidate_url = best weak candidate when no champion exists
```

A true champion is not just the highest-scoring candidate. It must pass the production evidence gate.

## Champion eligibility

A URL can become `tournament_champion_url` only when it is:

```text
browser-openable
highly scrapable
exact-product matched
rich enough for product coding
critical product details extracted
country acceptable
not a homepage/search/listing/soft-404 page
not a conflicting variant
```

In this project, scrapable means the page exposes actual product evidence, not just reachable HTML.

Critical product evidence includes product name plus multiple useful details such as:

```text
brand or manufacturer
description
specs or attributes
images
GTIN/EAN when present
price or availability signal
```

## Handoff rule

A champion is production-ready only when:

```text
production_url_ready = true
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
needs_review = false
```

## No-champion behavior

If no URL passes the champion gates, the system must not pretend that a champion exists.

Expected output:

```text
tournament_champion_url = empty
product_url = empty
best_review_candidate_url = populated when a review candidate exists
needs_review = true
verified_exact_url = empty
production_url_ready = false
```

This keeps the main URL field clean for downstream browser, scraper, and coding teams.

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

## Coding readiness rule

A row cannot be `CODING_READY` unless a production-ready exact champion exists.

If only a review candidate exists, the coding status must be downgraded to:

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
