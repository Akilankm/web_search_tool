# Tournament Architecture

## Status

Tournament architecture is the **primary/default** product URL discovery path.

The legacy iterative loop is retained only as an explicit fallback for debugging or A/B comparison:

```env
PRODUCT_HARNESS_ENABLE_TOURNAMENT_MODE=false
```

Normal runs should leave tournament enabled.

## Purpose

The core requirement is high-stakes product URL discovery:

```text
Given product text, country, optional retailer, and optional EAN,
find the exact product URL that can be opened in a browser,
shows the intended product to the user,
and can be scraped for complete product information.
```

Tournament architecture treats this as a comparative decision problem. A URL is not judged only in isolation; it is compared against other candidates until a champion candidate is found and confirmed.

## Architecture

```text
Input product identity
  → search fan-out within 4 SerpAPI credits
  → candidate pool
  → cheap preflight ranking
  → enforced top-k preflight candidate cut
  → concurrent batch scraping with max-batch bound
  → evidence extraction
  → deterministic identity / EAN / title / variant / country / retailer checks
  → rendered page relevance check
  → batch winner selection
  → champion-vs-challenger comparison
  → champion confirmation gate, default 3 checks
  → final production URL gate
  → product_url + evidence artifacts when production-ready
  → review queue / safe review evidence when not production-ready
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

## Enforced preflight and batch limits

The tournament engine enforces the same limits that the docs expose:

```text
ranked_candidates = all scored candidates sorted by preflight score
preflight_candidates = ranked_candidates[:PRODUCT_HARNESS_TOURNAMENT_PREFLIGHT_TOP_K]
batches = chunk(preflight_candidates, PRODUCT_HARNESS_TOURNAMENT_BATCH_SIZE)
executed_batches = batches[:PRODUCT_HARNESS_TOURNAMENT_MAX_BATCHES]
```

With defaults, the tournament batch phase can scrape at most:

```text
min(60, available scrape budget, available preflight candidates)
```

because:

```text
PRODUCT_HARNESS_TOURNAMENT_BATCH_SIZE=20
PRODUCT_HARNESS_TOURNAMENT_MAX_BATCHES=3
```

Champion confirmation is separate from this batch phase. It uses the selected champion candidate and writes `champion_confirmation.json` / `champion_confirmation.md` when deep tournament artifacts are enabled.

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

Each executed batch produces a winner. Winners are then compared until a production-ready champion candidate is selected.

The champion candidate is ranked by:

```text
production readiness
browser-openability
rendered product-content relevance
scrapability
critical product evidence completeness
exact product match
country fit
retailer fit
confidence
richness
```

The candidate still must pass the champion confirmation gate before it is accepted for team handoff.

## Rendered-page relevance gate

A candidate can open in a browser and still fail if the visible page is not the intended product page.

The rendered gate checks:

```text
rendered_page_check_passed
rendered_page_type
rendered_product_visible
rendered_content_related
rendered_match_confidence
rendered_verdict
rendered_mismatch_reasons
```

Examples of rendered failures:

```text
PRODUCT_URL_RENDERED_CONTENT_MISMATCH_NEEDS_REVIEW
PRODUCT_URL_RENDERED_HOMEPAGE_NEEDS_REVIEW
PRODUCT_URL_RENDERED_LISTING_OR_SEARCH_NEEDS_REVIEW
PRODUCT_URL_RENDERED_INTERSTITIAL_NEEDS_REVIEW
```

A candidate with `browser_openable=true` but `rendered_page_check_passed=false` cannot be champion.

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

Confirmation artifacts, when enabled:

```text
champion_confirmation.json
champion_confirmation.md
```

If confirmation fails, the candidate is not accepted as a confirmed champion. It remains evidence for review and comparison.

## Production handoff rule

A row is handoff-ready only when:

```text
product_url is not blank
production_url_ready = true
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
browser_openable = true
rendered_page_check_passed = true
highly_scrapable = true
exact_product_url_match = true
champion_confirmation.passed = true
champion_confirmation.success_count = champion_confirmation.required_successes
needs_review = false
```

If no confirmed production-ready champion exists, `product_url` is blank. The harness may keep a safe review candidate in `best_available_url`, but hard-rejected candidates remain only in candidate/rejection evidence.

## Row artifacts

The default row packet is concise:

```text
output/<row_id>/
├── final_row.csv
├── review_summary.md
├── review_decision.json
├── candidate_decisions.csv
└── product_coding_input.json
```

Optional deep/tournament artifacts can include:

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
rendered page verdict
champion confirmation status
champion confirmation attempts and successes
```

## Why this is the primary architecture

Product URL discovery is a relative ranking problem. A candidate that looks acceptable alone may lose against another candidate with stronger EAN, title, variant, country, browser-openability, rendered-product-content, and scrapability evidence.

Tournament architecture improves the system by using:

```text
broad discovery
parallel evidence collection
side-by-side candidate comparison
rendered page relevance protection
production gate enforcement
safe review fallback protection
repeated champion confirmation
artifact-backed decisions
```

## Operational checklist

For every run, inspect:

```text
product_url
best_available_url
production_url_ready
production_url_status
browser_openable
rendered_page_check_passed
rendered_page_type
rendered_verdict
highly_scrapable
exact_product_url_match
needs_review
review_summary.md
candidate_decisions.csv
```

For downstream browser/scraping/product-coding teams, hand off only rows where `product_url` is non-blank, `production_url_ready=true`, `rendered_page_check_passed=true`, `champion_confirmation.passed=true`, and `needs_review=false`.
