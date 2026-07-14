# Adaptive Three-Credit SerpAPI Search

## Objective

The search subsystem has one operational goal:

> Use at most three paid SerpAPI requests to obtain a direct, durable, exact-product URL that can pass live scrape and browser validation.

The budget is not mapped to three predefined queries. Before every request, the LLM examines the evidence already obtained and chooses the next engine and parameters.

```text
product identity
→ LLM credit decision
→ one SerpAPI engine call
→ normalize URLs, product tokens, IDs and images
→ precision admission and bounded scraping
→ validate current best URL
→ stop or plan the next credit
```

## Hard guarantees

- Maximum successful SerpAPI requests per product: **3**.
- One action is selected per credit.
- Duplicate engine/query/token/image actions are blocked.
- Tokens, image URLs, product IDs and direct links must come from real SerpAPI responses.
- Google/SerpAPI intermediary links are never accepted as the final product URL.
- Every direct or derived URL must pass the existing live scrape, identity, durability and browser gates.
- The workflow may stop after credit 1 or 2 when a verified working URL is already available.

## Supported engines

| Engine | Primary role |
|---|---|
| `google` | Exact EAN/model search and direct product-page recovery |
| `google_shopping` | Commercial product resolution, merchant results and product-token discovery |
| `google_immersive_product` | Expand a Shopping token into direct store product URLs |
| `google_ai_mode` | Resolve ambiguity and harvest cited/shopping URLs |
| `google_lens` | Visual product matching when a real image handle is available |
| `amazon` | Requested-retailer native Amazon search |
| `ebay` | Requested-retailer native eBay search |
| `walmart` | Requested-retailer native Walmart search |
| `home_depot` | Requested-retailer native Home Depot search |

The planner does not expose retailer-native engines unless the requested retailer matches that engine. It does not expose Immersive Product without a real page token and does not expose Lens without a real image URL.

## Search planner input

The planner receives a compact state packet rather than raw response payloads:

- input product text, EAN/GTIN, retailer, country and language;
- current credit number and credits remaining;
- previous engine, purpose, status, URL yield and handle yield;
- available product tokens, product IDs and image URLs;
- a bounded list of current top candidates;
- deterministic rejection counts;
- available engines for the current state.

Raw HTML, complete SerpAPI JSON and browser context are excluded from the planning prompt.

## Planner output

The LLM returns one JSON action:

```json
{
  "engine": "google_shopping",
  "purpose": "resolve_product_identity_and_product_token",
  "query": "LEGO 75379 R2-D2",
  "scope": "country",
  "language_code": "en",
  "country_code": "GB",
  "page_token": "",
  "image_url": "",
  "lens_type": "products",
  "more_stores": true,
  "expected_signals": ["exact model", "merchant URL", "immersive token"],
  "reason": "Organic candidates were mostly category pages."
}
```

Deterministic code validates the engine, required parameters, remaining budget and duplicate signature before execution.

## Typical adaptive routes

### Exact EAN supplied

```text
Google exact identifier search
→ validate direct URLs
→ Shopping only when direct results are weak
→ Immersive Product when Shopping yields a token
```

### Strong model but no EAN

```text
Google Shopping
→ Immersive Product when token exists
→ Google exact phrase or AI Mode only when unresolved
```

### Ambiguous text

```text
AI Mode or Shopping
→ use resolved brand/model/token
→ direct search, Immersive Product or Lens
```

### Supported retailer requested

```text
retailer-native engine
→ validate direct product URLs
→ Google/Shopping fallback only when needed
```

### Product image discovered

```text
Google Lens products/exact matches
→ normalize external links
→ validate the candidate product page
```

## Response normalization

All engines normalize into the existing URL candidate contract. Additional follow-up evidence is stored as handles:

| Handle | Purpose |
|---|---|
| `immersive_product_page_token` | Follow-up Immersive Product call |
| `image_url` | Optional Lens call |
| `product_id` | Identity trace and diagnostics |
| `asin` | Amazon identity and derived `/dp/` URL |
| `walmart_item_id` | Walmart identity and derived `/ip/` URL |

Derived URLs are candidates only. They are never trusted without live validation.

## Working URL definition

A working URL is:

- an external direct URL;
- an individual product-detail page;
- browser-openable and not access-blocked;
- text or rendered-content scrapable;
- the exact requested product and variant;
- durable and non-expiring;
- complete enough for the configured final acceptance policy.

A successful HTTP response alone is insufficient. A URL that passes the complete acceptance contract is returned as top-level `primary_url`; otherwise `primary_url` remains `null` and the best review candidates stay in the audit artifacts.

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

`PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES` and `PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES` remain only for compatibility with older `.env` files. They do not determine the adaptive route.

## Result and artifact contract

`result.json` contains:

```text
search.policy
search.maximum_serpapi_credits
search.serpapi_requests_used
search.adaptive_search_contract_enforced
search.allowed_engines
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

Artifacts:

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

Only files for credits actually used are written.

## Notebook EDA

The supported notebook exposes:

- `search_actions_df`: one row per paid credit;
- `search_engine_summary_df`: engine-level yield and conversion;
- `search_handles_df`: product tokens, IDs and image handles;
- `search_decision_rca_df`: budget, fallback and stop RCA;
- `serp_results_df`: raw occurrence grain;
- `results_df`: authoritative one-canonical-URL grain.

Charts show credit allocation, engine yield and best-candidate confidence after each credit.
