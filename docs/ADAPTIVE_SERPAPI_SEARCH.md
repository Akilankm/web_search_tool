# Adaptive Three-Credit SerpAPI Search

## Objective

Use at most three paid SerpAPI requests to obtain a direct, durable, exact-product URL that passes live scrape and browser validation **and** is the strongest available source under the internal source-authority hierarchy.

```text
product identity
→ determine highest unresolved source tier
→ LLM selects one suitable engine/query
→ one SerpAPI request
→ normalize URLs, product tokens, IDs and images
→ classify source authority
→ precision admission and bounded scraping
→ validate current best URL
→ stop or target the next unresolved tier
```

## Standardized source hierarchy

When `retailer_name` is supplied:

```text
Requested retailer in country
→ Requested retailer outside country
→ Local/regional manufacturer
→ Global manufacturer
→ Major country retailer
→ Other local website
→ Other global website
→ Amazon/eBay last resort
```

Without `retailer_name`:

```text
Local/regional manufacturer
→ Global manufacturer
→ Major country retailer
→ Other local website
→ Other global website
→ Amazon/eBay last resort
```

Amazon or eBay receive first priority only when explicitly requested.

See [SOURCE_AUTHORITY_HIERARCHY.md](SOURCE_AUTHORITY_HIERARCHY.md).

## Hard guarantees

- Maximum successful SerpAPI requests per product: **3**.
- One action is selected per credit.
- Each action records `target_source_tier`.
- Duplicate engine/query/token/image actions are blocked.
- Tokens, image URLs, product IDs and direct links must originate from actual SerpAPI responses.
- Google/SerpAPI intermediary links are never accepted as the final URL.
- Every direct or derived URL must pass live scrape, identity, durability and browser gates.
- Source authority is applied after mandatory exact-product validity.
- A lower-tier URL cannot outrank a valid higher-tier URL merely because it is richer.
- Amazon/eBay do not trigger early stopping unless explicitly requested.

## Supported engines

| Engine | Primary role |
|---|---|
| `google` | Requested retailer, manufacturer, EAN/model and direct-page recovery |
| `google_shopping` | Major country retailers, merchant URLs and product-token discovery |
| `google_immersive_product` | Expand a Shopping token into direct store product URLs |
| `google_ai_mode` | Resolve manufacturer/product ambiguity and collect cited URLs |
| `google_lens` | Visual product matching when a real image handle is available |
| `amazon` | Requested-retailer native Amazon search |
| `ebay` | Requested-retailer native eBay search |
| `walmart` | Requested-retailer native Walmart search |
| `home_depot` | Requested-retailer native Home Depot search |

Retailer-native engines are exposed only when the requested retailer matches. Immersive Product requires an actual token. Lens requires an actual image URL.

## How engine routing is identified

The business source tier is selected before the technical engine:

```text
source tier target
→ suitable engine subset
→ LLM engine/query decision
→ deterministic validation
```

Examples:

| Target source tier | Suitable first routes |
|---|---|
| Requested retailer | Native retailer engine, Google Search, Shopping, AI Mode |
| Local/global manufacturer | Google Search or AI Mode |
| Major country retailer | Shopping, Immersive Product, Google Search |
| Other local/global source | Google Search, AI Mode, Lens where justified |
| Amazon/eBay fallback | Broad Google recovery unless explicitly requested |

The LLM cannot select Shopping as the first route for a manufacturer target unless the deterministic policy accepts that engine for the tier. An incompatible action is replaced by a guarded hierarchy action.

## Search planner input

The planner receives a compact state packet:

- product text, EAN/GTIN, retailer, country and language;
- credit number and credits remaining;
- standardized source hierarchy and current target tier;
- previous engine, purpose, URL yield and handle yield;
- product tokens, IDs and image URLs;
- bounded top candidate summaries;
- deterministic rejection counts;
- engines available for the current state.

Raw HTML, complete SerpAPI JSON and browser context are excluded.

## Planner output

```json
{
  "engine": "google",
  "purpose": "source_hierarchy_local_manufacturer",
  "query": "\"5702017584379 LEGO R2-D2 75379\" official manufacturer product GB",
  "scope": "country",
  "language_code": "en",
  "country_code": "GB",
  "expected_signals": [
    "SOURCE_TIER:LOCAL_MANUFACTURER",
    "DIRECT_EXACT_PRODUCT_URL"
  ],
  "reason": "Local/regional manufacturer is the highest unresolved source tier."
}
```

Deterministic code validates engine suitability, required parameters, budget and duplicate signature before execution.

## Typical routes

### Requested retailer supplied

```text
Requested retailer route
→ validate exact retailer page
→ local manufacturer
→ global manufacturer or major country retailer
```

### No retailer supplied

```text
Local/regional manufacturer
→ global manufacturer
→ major country retailer
```

Other local and marketplace results may still appear in any response, but they remain lower-tier candidates.

### Shopping token discovered

```text
Shopping
→ immersive product token
→ direct merchant URLs
→ classify merchant authority and country alignment
```

### Product image discovered

```text
Lens products/exact matches
→ normalize external links
→ classify source tier
→ validate exact product page
```

## Candidate source classification

Every canonical URL is assigned:

```text
source_tier
source_tier_name
source_role
country_alignment
requested_retailer_match
manufacturer_match
major_country_retailer
marketplace
source_priority_reason
higher_priority_tier_exhausted
selected_within_tier
```

Manufacturer classification combines domain identity with product brand/manufacturer evidence. Country alignment uses country profiles and localized URL patterns. Shopping and Immersive merchant results qualify as major country retailers only when country-aligned.

## Final selection

Selection is lexicographic:

```text
exact product identity
→ usable product-detail page
→ source tier
→ confidence/richness within the tier
```

This ensures an official manufacturer page with sufficient validity outranks Amazon/eBay even when the marketplace page has more content.

## Early stopping

The search may stop after credit 1 or 2 only for:

- requested retailer;
- local/regional manufacturer;
- global manufacturer.

Major retailers, other websites and unrequested Amazon/eBay results do not stop the search while credits remain for stronger tiers.

## Response normalization

All engines normalize into one URL candidate contract. Follow-up handles include:

| Handle | Purpose |
|---|---|
| `immersive_product_page_token` | Immersive Product follow-up |
| `image_url` | Lens follow-up |
| `product_id` | Identity trace |
| `asin` | Amazon identity and derived `/dp/` URL |
| `walmart_item_id` | Walmart identity and derived `/ip/` URL |

Derived URLs remain candidates only and require live validation.

## Working URL definition

A working URL is:

- external and direct;
- an individual product-detail page;
- browser-openable;
- technically and semantically scrapable;
- the exact product and variant;
- durable and non-expiring;
- complete enough for final evidence policy.

## Environment contract

```env
PRODUCT_HARNESS_MAX_SERPAPI_CREDITS=3
PRODUCT_HARNESS_ALLOWED_SEARCH_ENGINES=google,google_shopping,google_ai_mode,google_immersive_product,google_lens,amazon,ebay,walmart,home_depot
PRODUCT_HARNESS_ENABLE_LLM_SEARCH_PLANNING=true
PRODUCT_HARNESS_ENABLE_LLM_SEARCH_FEEDBACK=true
PRODUCT_HARNESS_REQUIRE_LLM_SEARCH_PLANNING=true
PRODUCT_HARNESS_EARLY_STOP_ON_WORKING_URL=true
PRODUCT_HARNESS_SEARCH_PLANNER_MAX_CANDIDATES=8
```

The source hierarchy is an internal business standard, not a user-tunable ranking weight.

## Result contract

`result.json` contains:

```text
search.policy
search.maximum_serpapi_credits
search.serpapi_requests_used
search.adaptive_search_contract_enforced
search.source_authority_hierarchy_enforced
search.requested_retailer_override
search.source_hierarchy
search.amazon_ebay_last_resort
search.target_source_tiers
search.engine_sequence
search.planner_calls
search.planner_fallbacks
search.stop_reason
search.actions
search.observations
search.handles
search.serp_results
primary_url
```

## Artifacts and notebook

```text
data/artifacts/<row_id>/
├── adaptive_search_trace.json
├── serp_credit_01_<engine>_raw.json
├── serp_credit_02_<engine>_raw.json
├── serp_credit_03_<engine>_raw.json
├── candidate_url_records.json
├── candidates.csv
├── review.md
└── single_product_diagnostics.xlsx
```

The notebook exposes:

- `source_hierarchy_df`;
- `source_tier_summary_df`;
- `search_actions_df` with `target_source_tier`;
- source authority columns in `results_df`;
- a source-route chart;
- `source_hierarchy` and `source_tier_summary` Excel sheets.
