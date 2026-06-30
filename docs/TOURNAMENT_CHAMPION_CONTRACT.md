# Tournament Champion Contract

## Purpose

The target outcome is always a usable product champion URL.

A champion is the URL that the browser, scraping, and product-coding teams can rely on.

```text
product_url = champion URL when the champion gate passes
best_review_candidate_url = strongest non-champion candidate for debugging/review
runner_up_url = comparison evidence
```

## Search budget

Tournament search uses a maximum of four SerpAPI search batches per product.

```text
max SerpAPI search batches = 4
```

Each search batch may return many candidate URLs. Repeated appearance across batches is a strong relevance signal, but it is not enough to become champion.

## Champion eligibility

A URL can become champion only when it is:

```text
browser-openable
highly scrapable
exact-product matched
rich enough for product coding
critical product details extracted
country acceptable or valid global fallback
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

## Champion confirmation gate

After a candidate passes the normal champion gate, the same candidate must pass repeated confirmation checks before final production handoff.

Default requirement:

```text
champion_confirmation_attempts = 3
champion_confirmation_required_successes = 3
```

Each confirmation attempt re-checks the same candidate URL against the production evidence gate. The confirmation must show:

```text
all required attempts pass
final URL is stable
product evidence label is stable
critical product details remain extractable
richness and word-count do not collapse
```

If confirmation fails, the candidate is not accepted as champion.

## Search objective

The harness should keep the target in working memory:

```text
Find the real product URL matching the input request.
Scrape enough critical product evidence.
Promote only a usable exact product page as champion.
Confirm the champion repeatedly before production handoff.
Record every search, scrape, decision, rejection, confirmation attempt, and runner-up.
```

## Review candidate

A review candidate is not the desired outcome. It is only diagnostic evidence showing the strongest candidate seen so far.

```text
best_review_candidate_url = strongest candidate that did not pass champion gates
```

The system should be improved until real runs produce a champion for valid product inputs.

## Invalid EAN behavior

Invalid EAN/GTIN values are not used in search queries or LLM prompts. They remain visible as input evidence and diagnostics, but they are not treated as exact identity anchors.

## Coding readiness rule

A row cannot be `CODING_READY` unless a production-ready exact champion exists and champion confirmation passed.

## Requested retailer metrics

Tournament search actions are recorded with scope metadata so requested-retailer status is accurate.

Expected values after a requested-retailer tournament query:

```text
requested_retailer_attempted = true
requested_retailer_scrapability_status != NOT_ATTEMPTED
```
