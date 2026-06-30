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

Tournament architecture treats this as a comparative decision problem. A URL is not judged only in isolation; it is compared against other candidates until a champion candidate is found and confirmed.

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
  → champion confirmation gate, default 3 checks
  → final production URL gate
  → product_url + evidence artifacts
```

## Hard SerpAPI budget

The search budget is fixed:

```text
PRODUCT_HARNESS_TOURNAMENT_MAX_SERP_CREDITS=4
```

The config clamps this value to a maximum of `4`, even if a higher value is supplied.

Tournament uses Google organic SerpAPI calls for candidate-pool discovery. Champion confirmation checks happen after candidate selection and do not add SerpAPI search calls.

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

Champion confirmation is currently fixed in the tournament implementation:

```text
champion_confirmation.required_attempts = 3
champion_confirmation.required_successes = 3
```

## Search strategy

The search fan-out can include:

```text
requested retailer search
EAN / country exact search when valid
same-country alternative retailer search
secondary language country search, when available
global fallback challenger search
```

Only the first unique queries within the four-credit cap are executed.

## Champion selection

Each batch produces a winner. Winners are then compared until a production-ready champion candidate is selected.

The champion candidate is ranked by:

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

The candidate still must pass the champion confirmation gate before it is accepted for team handoff.

## Champion confirmation gate

After candidate selection, the same candidate URL is confirmed repeatedly.

Default requirement:

```text
attempted_count = 3
success_count = 3
final_url_stable = true
evidence_stable = true
passed = true
```

Confirmation artifacts:

```text
champion_confirmation.json
champion_confirmation.md
```

If confirmation fails, the candidate is not accepted as a confirmed champion. It remains evidence for review and comparison.

## Production handoff rule

A row is handoff-ready only when:

```text
production_url_ready = true
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
champion_confirmation.passed = true
champion_confirmation.success_count = champion_confirmation.required_successes
needs_review = false
```

If no confirmed production-ready champion exists, the harness keeps the strongest available review candidate but does not treat it as production handoff-ready.

## Row artifacts

Each row includes tournament artifacts:

```text
tournament_bracket.json
tournament_bracket.md
champion_confirmation.json
champion_confirmation.md
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
champion confirmation status
champion confirmation attempts and successes
```

## Why this is the primary architecture

Product URL discovery is a relative ranking problem. A candidate that looks acceptable alone may lose against another candidate with stronger EAN, title, variant, country, browser-openability, and scrapability evidence.

Tournament architecture improves the system by using:

```text
broad discovery
parallel evidence collection
side-by-side candidate comparison
production gate enforcement
repeated champion confirmation
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
champion_confirmation.md
batch_winners.csv
```

For downstream browser/scraping/product-coding teams, hand off only rows where `production_url_ready=true`, `champion_confirmation.passed=true`, and `needs_review=false`.
