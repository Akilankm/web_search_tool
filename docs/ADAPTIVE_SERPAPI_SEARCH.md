# Adaptive Belief-Driven SerpAPI Search

## Objective

Use at most three paid SerpAPI credits to deliver a direct, browser-openable, information-rich exact-product URL while preserving both official product truth and commercial market context.

The search is governed by the product belief state and the final source route:

```text
manufacturer_primary
→ requested_retailer_country or country_alternative
→ global_fallback
```

## Before the first credit

No paid search occurs until the system has created:

- deterministic identity claims;
- a structured no-web LLM interpretation;
- competing product hypotheses;
- negative constraints;
- decision-critical unknowns;
- uncertainty metrics;
- a leading product hypothesis.

Model memory is a prior, not web evidence.

## Credit allocation

| Credit | Purpose | Required behavior |
|---:|---|---|
| 1 | `manufacturer_primary` | Search for the exact official manufacturer or brand product-detail page |
| 2 | `requested_retailer_country` or `country_alternative` | Preserve the requested commercial market after the manufacturer opportunity is evaluated |
| 3 | `global_fallback` | Relax country restrictions while preserving exact product identity |

A retailer page discovered during credit 1 is retained as a commercial reference but cannot trigger early stopping before manufacturer authority is evaluated.

When a real Google Shopping immersive-product token exists, credit 2 may expand it into direct merchant URLs. This is considered a retailer-resolution action and is preferred over issuing a weaker duplicate query.

## Engine routing

The planner may use:

- Google Search;
- Google Shopping;
- Google AI Mode;
- Google Immersive Product;
- Google Lens;
- supported retailer-native engines.

Engine choice is technical. The source stage is the business decision.

The final planner hardening ensures that credit number, engine, query, purpose, and expected source-tier signals agree. A manufacturer label cannot carry a retailer query, and a retailer stage cannot be silently rewritten into another source route.

## Candidate lifecycle

```text
SerpAPI occurrence
→ canonical direct URL
→ deterministic URL-type admission
→ source-role and authority classification
→ identity-aware preflight
→ bounded full scrape
→ exact-product and variant verification
→ requested-feature assessment
→ belief update
→ browser/rendered-page verification
→ durability gate
→ authority-ranked primary selection
```

Search snippets are weak discovery evidence. A candidate becomes eligible only after direct-page validation.

## Source roles

Qualified candidates are classified into authority tiers:

```text
LOCAL_MANUFACTURER
→ GLOBAL_MANUFACTURER
→ REQUESTED_RETAILER_LOCAL
→ REQUESTED_RETAILER_GLOBAL
→ MAJOR_COUNTRY_RETAILER
→ OTHER_LOCAL_WEBSITE
→ OTHER_GLOBAL_WEBSITE
→ MARKETPLACE_LAST_RESORT
```

Authority is applied only after identity, browser, feature, scrapability, and durability gates pass.

## Evidence-driven replanning

After each scrape, the system updates:

- hypothesis probabilities;
- posterior margin;
- ambiguity entropy;
- hard conflicts;
- unresolved fields;
- current source-stage status.

The next action uses the leading hypothesis and highest-impact unresolved distinction, such as product form, pack configuration, exact model, edition, size, quantity, or sibling variant.

## Early stopping

A manufacturer-targeted stage may stop early only when a strictly qualified manufacturer page is available.

A retailer discovered during the manufacturer stage does not stop the search.

A later stage may stop when the best current page is:

- direct and external;
- browser-openable;
- an individual product-detail page;
- text-scrapable and information-rich;
- exact-product and variant verified;
- complete for requested features;
- durable;
- eligible under the current authority policy.

## Budgets

```env
PRODUCT_HARNESS_MAX_SERPAPI_CREDITS=3
PRODUCT_HARNESS_MAX_FULL_SCRAPES=6
PRODUCT_HARNESS_MAX_SCRAPES_PER_DOMAIN=2
PRODUCT_HARNESS_SCRAPE_TOP_K_PER_STAGE=2
PRODUCT_HARNESS_EARLY_STOP_ON_WORKING_URL=true
```

Maximum budgets are safety ceilings. Unused scrape capacity rolls forward to later credits.

## Stable outputs

```text
primary_url
primary_url_role
manufacturer_url
retailer_url
source_selection
```

- `primary_url` is the strongest product-truth URL.
- `manufacturer_url` retains the strongest qualified official source.
- `retailer_url` retains the strongest qualified commercial source.
- `source_selection` explains the authority decision.

## Trace contract

Every paid credit records:

- source stage and target tier;
- engine;
- purpose;
- query;
- expected signals;
- response, candidate, qualification, and scrape counts;
- belief status;
- leading hypothesis and probability;
- posterior margin;
- working-URL outcome;
- early-stop decision and reason.

The notebook exposes:

```text
search_actions_df
search_engine_summary_df
search_handles_df
search_decision_rca_df
source_hierarchy_df
source_selection_df
results_df
url_delivery_df
```

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
source_selection.json
```
