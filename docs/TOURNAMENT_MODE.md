# Tournament Architecture

## Status

Tournament architecture is now the **primary/default** product URL discovery path.

The legacy iterative loop is retained only as an explicit fallback for debugging or A/B comparison:

```env
PRODUCT_HARNESS_ENABLE_TOURNAMENT_MODE=false
```

Normal runs should leave tournament enabled.

## Purpose

The core requirement is high-stakes product URL discovery:

```text
Given product text, country, optional retailer, and optional EAN,
find the exact product URL that can be opened in a browser and scraped for complete product information.
```

Tournament architecture treats this as a comparative decision problem. A URL is not judged only in isolation; it is compared against other candidates until a champion URL is selected.

## Architecture

```text
Input product identity
  → search fan-out within 4 SerpAPI credits
  → candidate pool
  → cheap preflight ranking
  → concurrent batch scraping
  → evidence extraction
  → deterministic identity / EAN / title / variant / country / retailer checks
  → batch winner selection
  → champion-vs-challenger comparison
  → final production URL gate
  → product_url + evidence artifacts
```

## Hard SerpAPI budget

The search budget is fixed:

```text
PRODUCT_HARNESS_TOURNAMENT_MAX_SERP_CREDITS=4
```

The config clamps this value to a maximum of `4`, even if a higher value is supplied.

Tournament uses Google organic SerpAPI calls for candidate-pool discovery. AI Mode SerpAPI calls are not used inside the tournament discovery path, so the search-credit budget stays bounded.

## Default configuration

```env
PRODUCT_HARNESS_ENABLE_TOURNAMENT_MODE=true
PRODUCT_HARNESS_TOURNAMENT_MAX_SERP_CREDITS=4
PRODUCT_HARNESS_TOURNAMENT_CANDIDATE_POOL=150
PRODUCT_HARNESS_TOURNAMENT_PREFLIGHT_TOP_K=60
PRODUCT_HARNESS_TOURNAMENT_BATCH_SIZE=20
PRODUCT_HARNESS_TOURNAMENT_MAX_BATCHES=3
PRODUCT_HARNESS_TOURNAMENT_FINALIST_COUNT=5
PRODUCT_HARNESS_TOURNAMENT_EARLY_STOP=true
PRODUCT_HARNESS_TOURNAMENT_EARLY_STOP_MARGIN=0.15
PRODUCT_HARNESS_TOURNAMENT_REQUIRE_PRODUCTION_READY=true
```

## Search strategy

The search fan-out can include:

```text
requested retailer search
EAN / country exact search
same-country alternative retailer search
secondary language country search, when available
global fallback challenger search
```

Only the first unique queries within the four-credit cap are executed.

## Champion selection

Each batch produces a winner. Winners are then compared until a champion URL is selected.

The champion is ranked by:

```text
production readiness
exact product match
scrapability
browser-openability
country fit
retailer fit
confidence
richness
```

The champion still must pass the production URL gate before it is accepted for team handoff.

## Production handoff rule

A row is handoff-ready only when:

```text
production_url_ready = true
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
needs_review = false
```

If no production-ready champion exists, the harness still follows the strict non-empty `product_url` policy and emits the best discovered fallback URL as review-only.

## Row artifacts

Each row includes tournament artifacts:

```text
tournament_bracket.json
tournament_bracket.md
batch_winners.csv
```

These explain:

```text
search credits used
queries executed
candidate pool size
preflight size
scraped count
batch winners
champion URL
runner-up URL
champion margin
production readiness status
```

## Why this is the primary architecture

Product URL discovery is a relative ranking problem. A candidate that looks acceptable alone may lose against another candidate with stronger EAN, title, variant, country, browser-openability, and scrapability evidence.

Tournament architecture improves the system by using:

```text
broad discovery
parallel evidence collection
side-by-side candidate comparison
production gate enforcement
artifact-backed decisions
```

## Operational checklist

For every run, inspect:

```text
product_url
production_url_ready
production_url_status
browser_openable
highly_scrapable
exact_product_url_match
needs_review
tournament_bracket.md
batch_winners.csv
```

For downstream browser/scraping/product-coding teams, hand off only rows where `production_url_ready=true` and `needs_review=false`.
