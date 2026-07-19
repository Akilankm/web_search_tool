# Candidate Precision, Progressive Acquisition, and Context Control

## Purpose

This document defines how a single product run moves from high-recall search results to one defensible product-truth URL without spending scrape or LLM context on obviously weak candidates.

The search contract remains exactly three paid SerpAPI requests:

```text
1. manufacturer_primary
2. requested_retailer_country or country_alternative
3. global_fallback
```

The downstream contract is precision-gated:

```text
raw SERP occurrence
→ canonical URL identity
→ deterministic URL-type and identity admission
→ source-role classification
→ bounded full scrape
→ evidence-utility validation
→ requested-feature assessment
→ bounded agentic-browser escalation
→ strict URL gates
→ manufacturer-first authority decision
```

## Two table grains

### Raw SERP occurrence grain

`search.serp_results` and `serp_results_df` retain one row for every search occurrence. The same canonical URL can appear in several queries and positions. Repetition is expected and useful for stage and engine analysis.

### Canonical candidate grain

`candidate_records`, `candidate_url_records.json`, `candidates.csv`, and notebook `results_df` contain exactly one row per canonical URL.

Canonicalization:

- removes fragments;
- removes tracking, campaign, referral, and session parameters;
- normalizes hostname and path;
- preserves product-defining parameters such as `sku`, `productid`, `ean`, `gtin`, and `variant`;
- rejects duplicate canonical URLs from the final ledger.

A duplicate canonical URL is treated as a contract failure rather than silently displayed twice.

## Pre-scrape admission

Every candidate is classified before a full scrape.

Rejected URL classes include:

- homepage;
- internal search result;
- category or collection page;
- family or campaign page;
- social or community page;
- PDF, image, video, or archive;
- malformed or non-HTTP URL.

A remaining candidate receives deterministic preflight signals from:

- requested-product identity overlap;
- exact EAN/GTIN signal, when supplied;
- model, variant, size, quantity, pack, and product-form terms;
- manufacturer or retailer source role;
- probable product-detail path structure;
- independent SERP support;
- best SERP position.

The admission decision is recorded for every canonical URL:

```text
url_type
preflight_score
identity_overlap
source_role
source_tier
admitted_for_scrape
admission_reason
```

Rejected candidates remain in the audit ledger but do not consume a full scrape.

## Source authority classification

Candidates are classified into:

```text
LOCAL_MANUFACTURER
GLOBAL_MANUFACTURER
REQUESTED_RETAILER_LOCAL
REQUESTED_RETAILER_GLOBAL
MAJOR_COUNTRY_RETAILER
OTHER_LOCAL_WEBSITE
OTHER_GLOBAL_WEBSITE
MARKETPLACE_LAST_RESORT
```

Authority does not bypass quality gates. It is used only after exact identity, requested-feature, rendered-page, scrapability, and durability checks pass.

## Progressive acquisition budget

All three searches share one full-scrape budget.

```env
PRODUCT_HARNESS_MAX_FULL_SCRAPES=6
PRODUCT_HARNESS_MAX_SCRAPES_PER_DOMAIN=2
PRODUCT_HARNESS_MIN_PREFLIGHT_SCORE=0.28
```

Unused capacity rolls forward to later credits. The global stage can use remaining capacity only for qualified candidates.

The per-domain limit is cumulative across stages. One source cannot consume the entire scrape budget by returning many similar URLs.

## Acquisition semantics

A technical fetch is not treated as useful product evidence.

| Field | Meaning |
|---|---|
| `full_scrape_attempted` | Candidate consumed a full scrape slot |
| `fetch_success` | HTTP or browser acquisition succeeded |
| `content_extracted` | Usable readable content was obtained |
| `product_page_likelihood` | Evidence that the page is an individual product-detail page |
| `identity_status` | Product and variant decision |
| `feature_evidence_count` | Requested features with grounded support |
| `content_utility_score` | Combined usefulness for the requested product task |
| `scrape_accepted` | Acquisition is suitable for downstream evidence reasoning |

A successful HTTP response, price, or single image does not make a page production-ready.

## Requested feature completeness

A candidate cannot become strict primary unless the requested feature schema is satisfied according to the configured acceptance policy.

The candidate record exposes:

```text
coverage
required_coverage
critical_coverage
missing_features
conflicting_features
feature_evidence_count
```

An official manufacturer page that is missing required evidence does not outrank a complete retailer page.

## Agentic-browser admission

The LLM-controlled browser is an escalation path, not a second crawler for every search result.

A candidate is eligible only when it:

- was fully scraped;
- has no deterministic hard failure;
- is a probable product-detail page;
- has sufficient content utility;
- is not an identity mismatch;
- can plausibly resolve missing evidence or verify a high-quality static candidate.

Effective ceilings:

```env
PRODUCT_HARNESS_MAX_AGENTIC_CANDIDATES=3
PRODUCT_HARNESS_AGENTIC_MAX_TURNS_PER_CANDIDATE=4
PRODUCT_HARNESS_AGENTIC_MAX_ACTIONS_PER_CANDIDATE=6
PRODUCT_HARNESS_AGENTIC_OBSERVATION_CHARS=4000
PRODUCT_HARNESS_AGENTIC_MAX_ELEMENTS=15
PRODUCT_HARNESS_AGENTIC_MAX_IMAGES=8
```

The browser first selects different domains, then fills remaining capacity with the next strongest candidates.

When browser planning fails, including `403 Forbidden`, deterministic rendered-page acquisition retains usable evidence. Strict gates remain unchanged.

## Incremental LLM context

The planning prompt uses `incremental_delta_relevance_filtered` context.

Each turn contains:

- product identity;
- unresolved feature definitions only;
- newly visible text segments when the page changed;
- relevance-ranked controls such as specifications, details, manufacturer, age, warning, and gallery elements;
- relevance-ranked images;
- at most two compact previous action summaries.

The prompt excludes resolved feature definitions and unchanged page text. Transactional and account controls are negatively ranked.

The browser loop stops without another LLM request when:

- all requested features are resolved;
- the page is the wrong product or variant;
- the page is not an individual product page;
- access is blocked;
- no safe action can improve evidence;
- action or turn limits are reached.

## Authoritative candidate record

Each row in `candidates.csv` and `candidate_url_records.json` includes:

| Group | Examples |
|---|---|
| Canonical identity | `candidate_id`, `canonical_url`, `final_url`, `domain` |
| SERP support | `search_stages`, `appearance_count`, `best_position`, `serp_title` |
| Source authority | `source_role`, `source_tier`, `source_tier_name`, `manufacturer_match`, `requested_retailer_match` |
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

Each canonical URL has one precise stopping state.

## Final source outputs

```text
primary_url
primary_url_role
manufacturer_url
retailer_url
source_selection
```

The primary URL is selected from qualified candidates using:

```text
identity and variant correctness
→ rendered-page and scrape usability
→ requested feature completeness
→ durability
→ manufacturer authority
→ retailer and market preference
→ richness and confidence
```

## Notebook interpretation

Read the supported notebook in four layers:

1. **Readiness** — exact runtime version and manufacturer-first capability.
2. **Authority summary** — `source_selection_df`, `primary_url`, `manufacturer_url`, and `retailer_url`.
3. **Candidate master** — `results_df`, exactly one row per canonical URL.
4. **Drill-down** — raw SERP occurrences, feature evidence, browser actions, belief updates, and visual artifacts.

Raw JSON and complete browser plans remain available as audit artifacts but are not required for the default decision view.
