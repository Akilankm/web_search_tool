# Adaptive Belief-Driven SerpAPI Search

## Objective

Use at most three paid SerpAPI credits to deliver a direct, browser-openable, information-rich exact-product URL.

The search is governed by a product belief state and an immutable market path:

```text
requested retailer, when supplied
→ alternative retailer in requested country
→ global fallback
```

## Before the first credit

No paid search occurs until the system has created deterministic identity claims, a structured no-web LLM interpretation, competing hypotheses, negative constraints, critical unknowns, uncertainty metrics, and a leading product hypothesis.

## Credit allocation

| Credit | Retailer supplied | Retailer absent |
|---:|---|---|
| 1 | Requested retailer in country | Requested-country retailers |
| 2 | Alternative retailer in country | Corrective requested-country search |
| 3 | Global fallback | Global fallback |

Credit 2 is diagnostic and may include the highest-impact unresolved distinction. Credit 3 removes the country restriction but never relaxes exact-product requirements.

## Engine routing

The planner may use Google Search, Shopping, AI Mode, Immersive Product, Lens, or a supported retailer-native engine. Engine choice is technical; market stage is the business decision.

Deterministic controls enforce one action per paid credit, duplicate prevention, response-derived tokens/images only, no invented EAN/GTIN, canonical direct URLs, bounded scraping, and production URL validation.

## Candidate lifecycle

```text
SerpAPI result
→ canonical URL
→ market classification
→ identity-aware preflight
→ bounded scrape
→ exact-product verification
→ belief update
→ browser/rendered-page gate
→ selected, review, rejected, or next market
```

Search snippets are weak discovery evidence. A candidate becomes eligible only after direct-page validation.

## Evidence-driven replanning

After each scrape, the system updates hypothesis probabilities, posterior margin, ambiguity entropy, hard conflicts, unresolved fields, and current market status. The next query uses the leading hypothesis and highest-impact unresolved field, such as product form, pack configuration, exact model, edition, or sibling variant.

## Early stopping

A working URL must be direct, external, browser-openable, an individual product-detail page, highly scrapable, information-rich, exact-product verified, variant/pack/model consistent, durable, and suitable for manual review.

## Budgets

```env
PRODUCT_HARNESS_MAX_SERPAPI_CREDITS=3
PRODUCT_HARNESS_MAX_FULL_SCRAPES=6
PRODUCT_HARNESS_MAX_SCRAPES_PER_DOMAIN=2
PRODUCT_HARNESS_SCRAPE_TOP_K_PER_STAGE=2
PRODUCT_HARNESS_EARLY_STOP_ON_WORKING_URL=true
```

The expected business average is one to two paid searches and four to seven scrape attempts. Maximum budgets are safety limits, not targets.

## Trace contract

Every credit records the market stage, engine, purpose, query, expected signals, result/candidate/scrape counts, belief status, leading hypothesis, posterior probability, margin, and working-URL outcome.

The notebook exposes `search_actions_df`, `results_df`, `url_delivery_df`, belief tables, and final URL RCA.

## Artifacts

```text
adaptive_search_trace.json
serp_credit_<n>_<engine>_raw.json
product_belief.json
market_decision_path.md
belief_updates.md
evidence_ledger.jsonl
candidate_url_records.json
candidates.csv
mandatory_url_delivery.json
```
