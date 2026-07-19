# Mandatory Product URL Delivery

## Business invariant

Every product submitted to the production workflow must finish with a real direct product URL or fail explicitly.

A `COMPLETED` or `REVIEW_REQUIRED` response may not contain an empty `primary_url` or `product_match.product_url`.

```text
input product
→ manufacturer-first adaptive search
→ bounded scraping and browser investigation
→ strict verification when possible
→ explicit source-authority decision
→ always deliver the strongest real product-page URL
```

The system never fabricates a URL and never substitutes a Google result page, SerpAPI URL, category page, social page, document, image, video, or other intermediary.

## Product truth and commercial reference

The final output preserves two independent source roles:

```text
manufacturer_url = strongest strictly qualified official product page
retailer_url     = strongest strictly qualified commercial product page
primary_url      = strongest product-truth URL after all gates and authority ranking
```

A qualified official manufacturer page becomes `primary_url`.

A retailer becomes `primary_url` when the manufacturer page is missing, inaccessible, incomplete, non-product, transient, wrong-model, wrong-variant, wrong-pack, or missing requested feature evidence.

## Terminal behavior

| Situation | Job status | URL output |
|---|---|---|
| Exact URL passes every strict gate | `COMPLETED` | Strictly verified `primary_url` plus available manufacturer/retailer role URLs |
| A real direct candidate exists but one or more strict gates remain unresolved | `REVIEW_REQUIRED` | Strongest real direct review URL retained in all primary delivery fields |
| No direct external product-page candidate exists after all credits | `FAILED` | No successful empty output; error is `MANDATORY_PRODUCT_URL_NOT_FOUND` |

`REVIEW_REQUIRED` means a URL was delivered but needs human confirmation. It does not mean that the URL field is blank.

## Search-budget behavior

The three credits follow:

```text
1. manufacturer_primary
2. requested_retailer_country or country_alternative
3. global_fallback
```

The search stops early only when the current stage produces a source that passes the required gates for that stage.

A retailer discovered during the manufacturer stage is retained but cannot stop the search before manufacturer authority is evaluated.

If the final credit begins without any direct external candidate, mandatory recovery:

1. expands a real Google Shopping immersive-product token when available;
2. otherwise uses Google AI Mode, Shopping, or Search for broad exact-product URL recovery;
3. preserves EAN, model, country, retailer, variant, size, quantity, pack, and product-form terms;
4. requests a direct official manufacturer or retailer product page;
5. rejects search, category, intermediary, social, document, and media URLs deterministically.

## Strict acceptance versus delivery

Strict acceptance and mandatory delivery are separate decisions:

- `primary_url_acceptance.accepted` indicates whether every strict browser, identity, requested-feature, scrapability, and durability gate passed;
- `url_delivery.delivered` indicates that the mandatory direct-URL requirement was satisfied;
- `url_delivery.strictly_verified` distinguishes strict acceptance from best-available review delivery;
- `source_selection` records why the manufacturer or retailer became primary.

## Stable result schema

```text
primary_url
primary_url_role
manufacturer_url
retailer_url
source_selection
primary_url_acceptance
url_delivery
```

`manufacturer_url` and `retailer_url` are stable keys and may be `null` only when no qualified page exists for that role.

Example strict manufacturer-primary result:

```json
{
  "job_status": "COMPLETED",
  "primary_url": "https://manufacturer.example/products/exact-product",
  "primary_url_role": "OFFICIAL_MANUFACTURER",
  "manufacturer_url": "https://manufacturer.example/products/exact-product",
  "retailer_url": "https://retailer.example/product/exact-product",
  "source_selection": {
    "policy": "MANUFACTURER_FIRST_AFTER_PRODUCTION_GATES",
    "selection_reason": "OFFICIAL_MANUFACTURER_PRIMARY_AFTER_STRICT_GATES"
  },
  "url_delivery": {
    "required": true,
    "delivered": true,
    "strictly_verified": true,
    "empty_url_is_success": false
  }
}
```

Example retailer fallback:

```json
{
  "job_status": "COMPLETED",
  "primary_url": "https://retailer.example/product/exact-product",
  "primary_url_role": "RETAILER",
  "manufacturer_url": null,
  "retailer_url": "https://retailer.example/product/exact-product",
  "source_selection": {
    "policy": "MANUFACTURER_FIRST_AFTER_PRODUCTION_GATES",
    "selection_reason": "RETAILER_PRIMARY_AFTER_MANUFACTURER_GATE_FAILURE"
  }
}
```

Example review delivery:

```json
{
  "job_status": "REVIEW_REQUIRED",
  "primary_url": "https://retailer.example/product/exact-product",
  "primary_url_acceptance": {
    "accepted": false,
    "primary_url": "https://retailer.example/product/exact-product",
    "delivery_status": "BEST_AVAILABLE_REVIEW_URL"
  },
  "url_delivery": {
    "required": true,
    "delivered": true,
    "strictly_verified": false,
    "empty_url_is_success": false
  }
}
```

The delivered URL is retained in:

- `primary_url`;
- `product_match.product_url`;
- `product_match.best_available_url`;
- `evidence_set.primary_url`;
- `evidence_set.selected_urls`.

## Candidate ranking

The best strict or review URL is selected only from direct external product-like URLs.

Mandatory comparison order:

1. verified identity and non-conflicting product/variant/pack evidence;
2. rendered-page and direct product-page validation;
3. requested feature completeness;
4. scrapability, reachability, and durability;
5. official manufacturer authority;
6. requested-retailer and requested-country preference;
7. content richness, confidence, and SERP support.

Amazon/eBay and other marketplaces are retained as last-resort candidates unless explicitly requested, and they never bypass strict identity or feature gates.

## Audit artifacts

Every completed or review-required run writes:

```text
data/artifacts/<row_id>/mandatory_url_delivery.json
data/artifacts/<row_id>/source_selection.json
```

`mandatory_url_delivery.json` records whether a URL was delivered and whether it passed strict acceptance.

`source_selection.json` records the manufacturer-versus-retailer authority decision.

## Non-negotiable rule

The production workflow must never report success with an empty product URL.
