# Requested retailer scrapability strategy

## Requirement

When `retailer_name` is provided, it is a **preferred first evidence source**, not a hard constraint.

The harness must try the requested retailer first, but only accept a requested-retailer URL when the page is:

- reachable
- crawl4ai-scrapable
- product-detail-like
- rich enough for evidence
- exact product, not a sibling variant

If the requested retailer is non-scrapable, thin, blocked, wrong-variant, or insufficient for exact proof, the harness escapes to:

1. other retailers in the same country
2. global fallback
3. reference-only URL if no exact/usable URL can be proven

## Scope order

```text
REQUESTED_RETAILER_SCOPE
  SerpAPI search includes retailer name
  crawl4ai scrapes requested-retailer candidates
  detector/LLM decides whether retailer is evidence-usable

COUNTRY_ALTERNATIVE_SCOPE
  SerpAPI search removes requested retailer constraint
  finds other retailers in the same country
  crawl4ai scrapes broadly

GLOBAL_SCOPE
  SerpAPI query uses true global fallback
  scrape and validate exact product globally
```

## New statuses

`best_url.csv` includes:

```text
requested_retailer_name
requested_retailer_attempted
requested_retailer_domains_found
requested_retailer_candidates_found
requested_retailer_candidates_scraped
requested_retailer_scrape_success_count
requested_retailer_rich_pages_count
requested_retailer_exact_candidates_count
requested_retailer_scrapability_status
requested_retailer_escape_reason
selection_scope
selected_retailer_name
selected_domain
selected_from_requested_retailer
selected_from_other_country_retailer
selected_from_global_fallback
```

`requested_retailer_scrapability_status` values:

```text
NOT_PROVIDED
NOT_ATTEMPTED
CANDIDATES_FOUND_NOT_SCRAPED
SCRAPABILITY_CHECK_IN_PROGRESS
EXACT_SCRAPABLE_RICH_FOUND
SCRAPABLE_RICH_BUT_NOT_EXACT
UNUSABLE_FOR_EVIDENCE
WRONG_VARIANTS_ONLY
WEAK_OR_INSUFFICIENT_EVIDENCE
SEARCHED_NO_CANDIDATES
```

## Selection priority

```text
EXACT_REQUESTED_RETAILER_MATCH
  beats
EXACT_COUNTRY_ALTERNATIVE_RETAILER_MATCH
  beats
EXACT_GLOBAL_FALLBACK
  beats
BEST_AVAILABLE_COUNTRY_ALTERNATIVE_NEEDS_REVIEW
  beats
BEST_AVAILABLE_GLOBAL_NEEDS_REVIEW
  beats
best_reference_url only
```

A wrong/non-scrapable requested-retailer URL must not block a better exact country or global URL.
