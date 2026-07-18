# Market Decision Hierarchy

## Business rule

The product URL workflow follows one immutable trajectory:

```text
1. Requested retailer in the requested country, when retailer_name is supplied
2. Alternative retailer within the requested country
3. Global fallback
```

Without `retailer_name`, the path starts with the requested-country market and then moves to global fallback.

These are different commercial markets. The selected scope must remain explicit in search traces and final output.

## Why this hierarchy exists

The team will open the returned URL in a browser and eyeball the product. Therefore a preferred page must satisfy all three conditions:

1. exact product identity;
2. browser-openable, information-rich product-detail page;
3. best available market position.

A retailer-domain match cannot rescue a wrong variant, model, pack, refill/accessory, or non-product page.

## Stage 1 — Requested retailer

Executed only when a retailer is provided. The search preserves the leading product hypothesis, user-provided identifier, critical variant/size/pack attributes, retailer, and country.

Advance when no direct candidate exists, pages are inaccessible, pages are listings/homepages, the result is a sibling product, or the page is too weak for review.

## Stage 2 — Alternative retailer in country

The requested-retailer constraint is removed while country and exact identity constraints remain. Any browser-openable, information-rich retailer product page in the requested country may be selected.

## Stage 3 — Global fallback

Executed only after the requested-country market failed to yield a usable exact URL. Country restrictions are relaxed, but product identity is not. The selected result is labelled `global_fallback`.

Amazon/eBay may appear as requested-retailer or global candidates, but they do not bypass exact identity, browser usability, or the market path.

## Final selection

```text
exact product identity
→ browser-openable individual product page
→ information richness and scrapability
→ requested retailer / country alternative / global fallback
→ confidence and secondary quality signals
```

A global manufacturer page cannot outrank a valid country retailer merely because the source brand is stronger. A country page cannot outrank a requested-retailer page when both pass the same exact-product and usability gates.

## Output fields

```text
selection_scope
selected_domain
selected_retailer_name
selected_from_requested_retailer
selected_from_other_country_retailer
selected_from_global_fallback
url_decision_status
```

## Early stopping

A stage stops the search only after a production-ready URL passes browser, rendered-page, scrape, exact identity, critical evidence, and durability gates. A SERP snippet or unvalidated URL never qualifies.
