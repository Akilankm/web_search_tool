# Candidate Precision, Progressive Acquisition, and Context Control

## Purpose

This document defines how a single product run moves from high-recall SERP results to one defensible product URL without spending scrape or LLM context on obviously weak candidates.

The search contract remains exactly three organic SerpAPI requests:

1. requested retailer and country, or the primary country search;
2. alternative sources within the requested country;
3. global fallback.

The downstream contract is now precision-gated:

```text
raw SERP occurrence
→ canonical URL identity
→ deterministic URL-type and identity admission
→ bounded full scrape
→ evidence-utility validation
→ bounded agentic-browser escalation
→ strict primary URL decision
```

## Two table grains

### Raw SERP occurrence grain

`search.serp_results` and `serp_results_df` retain one row for every search result occurrence. The same canonical URL can occur in several queries and positions. Repetition is expected and useful for search-stage analysis.

### Canonical candidate grain

`candidate_records`, `candidate_url_records.json`, `candidates.csv`, and notebook `results_df` use exactly one row per canonical URL.

The canonicalization contract:

- removes URL fragments;
- removes tracking, campaign, referral, and session parameters;
- normalizes the hostname and path;
- preserves product-defining parameters such as `sku`, `productid`, `ean`, `gtin`, and `variant`;
- rejects duplicate canonical URLs from the final candidate ledger.

The runtime asserts that `canonical_url` is unique. A duplicate is treated as a contract failure rather than being silently displayed twice.

## Pre-scrape admission

Every candidate is classified before a full scrape.

Rejected URL classes include:

- homepage;
- internal search result;
- category or collection page;
- social or community page;
- PDF, image, video, or archive;
- malformed or non-HTTP URL.

A remaining candidate receives a deterministic preflight score from:

- requested-product identity overlap;
- exact EAN or GTIN signal, when supplied;
- retailer signal, when supplied;
- probable product-detail path structure;
- independent SERP support;
- best SERP position.

The admission decision is recorded for every canonical URL:

```text
url_type
preflight_score
identity_overlap
admitted_for_scrape
admission_reason
```

Rejected candidates remain in the audit ledger. They do not consume a full scrape.

## Progressive acquisition budget

All three searches share one full-scrape budget.

Default and hard production controls:

```env
PRODUCT_HARNESS_MAX_FULL_SCRAPES=6
PRODUCT_HARNESS_MAX_SCRAPES_PER_DOMAIN=2
PRODUCT_HARNESS_MIN_PREFLIGHT_SCORE=0.28
```

Unused capacity rolls forward to later search stages. The final global stage can use remaining capacity, but only for qualified candidates.

The per-domain limit is cumulative across stages. One retailer cannot consume the complete scrape budget simply by returning many similar URLs.

## Acquisition semantics

A technical fetch is not treated as useful product evidence.

| Field | Meaning |
|---|---|
| `full_scrape_attempted` | The candidate consumed a full scrape slot |
| `fetch_success` | HTTP or browser acquisition succeeded |
| `content_extracted` | A usable amount of readable content was obtained |
| `product_page_likelihood` | Evidence that the page is an individual product detail page |
| `identity_status` | Product and variant identity decision |
| `feature_evidence_count` | Requested features with grounded support |
| `content_utility_score` | Combined usefulness for the requested product task |
| `scrape_accepted` | The acquisition is suitable for downstream evidence reasoning |

This prevents a page with a successful HTTP response, a price, or one image from being reported as a quality scrape when it lacks relevant product evidence.

## Agentic-browser admission

The LLM-controlled browser is an escalation path, not a second crawler for every SERP URL.

A candidate is eligible only when it:

- was fully scraped;
- has no deterministic hard failure;
- is a probable product-detail page;
- has sufficient content utility;
- is not an identity mismatch;
- can plausibly resolve missing evidence or verify a high-quality static candidate.

Default and hard effective ceilings:

```env
PRODUCT_HARNESS_MAX_AGENTIC_CANDIDATES=3
PRODUCT_HARNESS_AGENTIC_MAX_TURNS_PER_CANDIDATE=4
PRODUCT_HARNESS_AGENTIC_MAX_ACTIONS_PER_CANDIDATE=6
PRODUCT_HARNESS_AGENTIC_OBSERVATION_CHARS=4000
PRODUCT_HARNESS_AGENTIC_MAX_ELEMENTS=15
PRODUCT_HARNESS_AGENTIC_MAX_IMAGES=8
```

An older `.env` with larger legacy values remains startup-compatible, but runtime execution and health reporting clamp to the effective production ceilings.

The browser first selects different domains, then fills remaining capacity with the next strongest candidates.

## Incremental LLM context

The planning prompt uses `incremental_delta_relevance_filtered` context.

Each turn contains:

- product identity;
- only unresolved feature definitions;
- only newly visible text segments when the page changed;
- relevance-ranked controls such as specifications, details, manufacturer, age, warning, and gallery elements;
- relevance-ranked images;
- at most two compact previous action summaries.

The prompt excludes already resolved feature definitions and unchanged page text. Transactional and account controls are negatively ranked.

The browser loop stops without another LLM request when:

- all requested features are already resolved;
- the page is the wrong product or variant;
- the page is not an individual product page;
- access is blocked;
- no safe action can improve the evidence;
- action or turn limits are reached.

## Authoritative candidate record

Each row in `candidates.csv` and `candidate_url_records.json` includes these decision groups:

| Group | Examples |
|---|---|
| Canonical identity | `candidate_id`, `canonical_url`, `final_url`, `domain` |
| SERP support | `search_stages`, `appearance_count`, `best_position`, `serp_title` |
| Admission | `url_type`, `preflight_score`, `admitted_for_scrape`, `admission_reason` |
| Acquisition | `full_scrape_attempted`, `fetch_success`, `content_extracted`, `scrape_accepted` |
| Utility | `product_page_likelihood`, `content_utility_score`, `richness` |
| Identity | `identity_status`, `ean_check`, `title_check`, `variant_status` |
| Feature coverage | `feature_evidence_count`, `coverage`, `missing_features`, `conflicting_features` |
| Browser | `browser_admitted`, `browser_turns`, `browser_actions`, `browser_outcome` |
| Final RCA | `final_status`, `rejection_category`, `selected`, `decision_reasons` |

Feature-specific scalar columns are added dynamically:

```text
feature_<feature_id>_value
feature_<feature_id>_status
feature_<feature_id>_confidence
```

## Final status vocabulary

Every canonical URL has one final status:

```text
SERP_REJECTED_URL_TYPE
SERP_REJECTED_LOW_IDENTITY
QUALIFIED_NOT_SCRAPED_BUDGET
SCRAPE_FAILED
SCRAPE_LOW_UTILITY
IDENTITY_REJECTED
BROWSER_BLOCKED
FEATURE_INCOMPLETE
ELIGIBLE_NOT_SELECTED
REVIEW_SELECTED
STRICT_SELECTED
```

This provides one precise stopping point for each URL.

## Notebook interpretation

The single-product notebook should be read in three layers:

1. **Executive summary** — funnel, chosen URL, final RCA, dominant rejection reason, effective budgets.
2. **Candidate master** — `results_df`, exactly one row per canonical URL.
3. **Drill-down** — raw SERP occurrences, feature evidence, browser actions, LLM plans, and visual artifacts.

Raw JSON and full browser plans remain available as audit artifacts but are not required for the default decision view.
