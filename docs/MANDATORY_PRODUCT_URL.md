# Mandatory product URL delivery

## Business invariant

Every product submitted to the production workflow must finish with a real direct product URL.

A successful or review-required result may not contain an empty `primary_url` or `product_match.product_url`.

```text
input product
→ adaptive source-aware search
→ bounded scraping and browser investigation
→ strict verification when possible
→ always deliver the strongest real product-page URL
```

The system never fabricates a URL and never substitutes a Google result page, SerpAPI URL, category page, social page, document, or media file.

## Terminal behaviour

| Situation | Job status | URL output |
|---|---|---|
| Exact product URL passes every gate | `COMPLETED` | Strictly verified direct URL |
| Real product-page candidate exists but one or more strict gates remain unresolved | `REVIEW_REQUIRED` | Strongest real direct URL, retained in all primary output fields |
| No direct external product-page candidate exists after all three credits | `FAILED` | No successful empty output; error is `MANDATORY_PRODUCT_URL_NOT_FOUND` |

`REVIEW_REQUIRED` therefore means **a URL was delivered but requires human confirmation**. It no longer means that the URL field is blank.

## Search-budget behaviour

The three SerpAPI credits remain adaptive and source-hierarchy aware.

The search stops early only for a strong exact URL from an accepted high-priority source tier. Otherwise it continues using the remaining credits.

If the final credit begins without any direct external candidate, the planner enters mandatory recovery:

1. expand a real Google Shopping immersive-product token when available;
2. otherwise use Google AI Mode, Google Shopping, or Google Search for broad exact-product URL recovery;
3. preserve EAN, model, retailer, country, and product identity terms;
4. request a direct manufacturer or retailer product page;
5. reject search/category/intermediary URLs deterministically.

## Final selection

Strict acceptance and URL delivery are separate decisions:

- `primary_url_acceptance.accepted` indicates whether every strict browser, identity, feature, scrapability, and durability gate passed;
- `url_delivery.delivered` indicates that the mandatory URL requirement was satisfied;
- `url_delivery.strictly_verified` distinguishes strict acceptance from best-available review delivery.

When strict acceptance fails but a real candidate exists:

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

The same URL is retained in:

- `primary_url`;
- `product_match.product_url`;
- `product_match.best_available_url`;
- `evidence_set.primary_url`;
- `evidence_set.selected_urls`.

## Candidate ranking

The best review URL is selected only from direct external product-like URLs. Ranking uses:

1. verified identity and non-conflicting variant evidence;
2. LLM exact-match evidence;
3. absence of hard failures;
4. standardized source-authority tier;
5. product-page likelihood;
6. scrapability and reachability;
7. content richness and confidence;
8. SERP position.

The standardized source hierarchy remains authoritative. Amazon and eBay are last resort unless explicitly requested.

## Audit artifact

Every completed or review-required run writes:

```text
data/artifacts/<row_id>/mandatory_url_delivery.json
```

The artifact records the delivered URL, whether it was strictly verified, and whether review is required.

## Non-negotiable rule

The production workflow must never report success with an empty product URL.
