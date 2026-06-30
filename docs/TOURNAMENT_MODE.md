# Tournament Mode

## Purpose

Tournament mode is an optional candidate-selection architecture for faster and stronger exact product URL selection.

Instead of evaluating candidates one by one through a long repair loop, it:

```text
1. spends a bounded search budget up front
2. builds a broad candidate pool
3. preflights and ranks candidate URLs cheaply
4. scrapes top candidates in concurrent batches
5. selects a batch winner
6. compares winners until a champion URL is found
7. applies the production URL gate as final authority
```

## Hard SerpAPI budget

Tournament mode has a hard business cap:

```text
PRODUCT_HARNESS_TOURNAMENT_MAX_SERP_CREDITS=4
```

The config clamps this value to a maximum of `4`. Tournament mode uses Google organic SerpAPI calls for candidate-pool discovery and disables AI Mode SerpAPI calls inside the tournament path, so the per-product SerpAPI search budget remains bounded.

## Enablement

Tournament mode is opt-in:

```env
PRODUCT_HARNESS_ENABLE_TOURNAMENT_MODE=true
PRODUCT_HARNESS_TOURNAMENT_MAX_SERP_CREDITS=4
PRODUCT_HARNESS_TOURNAMENT_CANDIDATE_POOL=150
PRODUCT_HARNESS_TOURNAMENT_PREFLIGHT_TOP_K=60
PRODUCT_HARNESS_TOURNAMENT_BATCH_SIZE=20
PRODUCT_HARNESS_TOURNAMENT_MAX_BATCHES=3
PRODUCT_HARNESS_TOURNAMENT_EARLY_STOP=true
PRODUCT_HARNESS_TOURNAMENT_EARLY_STOP_MARGIN=0.15
```

## Search strategy

The tournament search fan-out can include up to four distinct queries:

```text
requested retailer search
EAN / country exact search
same-country alternative retailer search
secondary language country search, when available
global fallback challenger search
```

Only the first unique queries within the hard credit cap are executed.

## Selection behavior

Tournament mode does not bypass correctness gates.

The final URL is still accepted only through the production URL gate:

```text
production_url_ready = true
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
needs_review = false
```

If no production-ready champion exists, the harness still follows the strict non-empty product URL policy and emits the best discovered fallback URL as review-only.

## Row artifacts

When tournament mode runs, each row folder includes:

```text
tournament_bracket.json
tournament_bracket.md
batch_winners.csv
```

These explain:

```text
search credits used
queries executed
candidate count
preflight count
scraped count
batch winners
champion URL
runner-up URL
champion margin
production readiness status
```

## Why this can improve speed and quality

Tournament mode improves the architecture because product URL selection is comparative.

A URL may look acceptable in isolation but lose when compared with a candidate that has stronger EAN, title, variant, country, browser-openability, and scrapability evidence.

The model shifts from:

```text
sequential candidate investigation
```

to:

```text
batch evidence collection + champion selection
```

## Operational recommendation

For high-stakes runs, enable tournament mode and inspect the final CSV fields:

```text
product_url
production_url_ready
production_url_status
browser_openable
highly_scrapable
exact_product_url_match
needs_review
```

Handoff rows only when `production_url_ready=true` and `needs_review=false`.
