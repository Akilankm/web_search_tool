# Final Product Evidence System Contract

This document is the canonical end-to-end contract for the production workflow.

## 1. Business objective

Given:

```text
MAIN_TEXT
COUNTRY_CODE
optional RETAILER_NAME
optional EAN/GTIN
optional LANGUAGE_CODE
```

return a real, direct, browser-openable product-detail URL that is defensible for product coding and human review.

The platform separates two needs:

- **product truth** — identity, specifications, warnings, compatibility, dimensions, official product features;
- **commercial reference** — price, stock, local assortment, market, language, and purchasing context.

## 2. Non-negotiable decision order

```text
exact product, model, form, variant, size, quantity and pack
→ browser-openable rendered individual product page
→ text scrapability and information richness
→ requested feature completeness
→ durable non-expiring URL
→ official manufacturer authority
→ requested retailer / requested-country retailer
→ global retailer or other exact product source
→ marketplace last resort
```

Source authority is applied only after mandatory safety and evidence gates pass.

A manufacturer page never wins merely because it is official. It must represent the exact product and contain the evidence required by the requested feature schema.

## 3. Three-credit search route

```text
Credit 1: manufacturer_primary
Credit 2: requested_retailer_country when retailer_name is supplied
          otherwise country_alternative
Credit 3: global_fallback
```

Credit 1 evaluates the official manufacturer or brand product-page opportunity.

Credit 2 preserves the commercial market route. A real Shopping immersive-product token may be expanded here because it leads directly to merchant pages and is more precise than issuing another generic query.

Credit 3 removes the country restriction while preserving exact product identity.

A retailer URL discovered during credit 1 is retained but cannot prematurely stop the search before manufacturer authority has been evaluated.

## 4. Primary URL rule

A qualified official manufacturer product page becomes `primary_url`.

A retailer becomes `primary_url` when the manufacturer page is:

- not found;
- inaccessible or blocked;
- not text-scrapable;
- a homepage, category, family, collection, campaign, or search page;
- the wrong model, form, variant, edition, size, quantity, or pack;
- missing requested feature evidence;
- transient or expiring.

Retailer fallback is a controlled production decision, not a failure.

## 5. Stable result schema

Every `COMPLETED` or `REVIEW_REQUIRED` result exposes:

```text
primary_url
primary_url_role
manufacturer_url
retailer_url
source_selection
primary_url_acceptance
url_delivery
product_identification
search.market_decision_path
```

### `primary_url`

The strongest product-truth URL after all gates and authority ranking.

### `primary_url_role`

One of:

```text
OFFICIAL_MANUFACTURER
RETAILER
MARKETPLACE
OTHER_PRODUCT_SOURCE
```

### `manufacturer_url`

The strongest strictly qualified official manufacturer page, or `null` when none qualified.

### `retailer_url`

The strongest strictly qualified retailer or commerce page, or `null` when none qualified.

### `source_selection`

The explicit authority decision, including the policy, selected source tier and role, manufacturer and retailer URLs, reason, mandatory gates, and fallback rule.

## 6. Terminal outcomes

| Job status | Meaning |
|---|---|
| `COMPLETED` | `primary_url` passed strict identity, browser, feature, scrapability, durability, and authority selection |
| `REVIEW_REQUIRED` | A real direct URL was delivered, but one or more strict gates require human confirmation |
| `FAILED` | No safe direct product-page URL could be delivered, or execution failed |

The workflow never reports success with an empty URL.

When no direct external product-page candidate exists after the bounded search, execution terminates with:

```text
MANDATORY_PRODUCT_URL_NOT_FOUND
```

## 7. Runtime contract

The final agent/notebook compatibility version is:

```text
belief-url-resolution-v5-manufacturer-primary
```

The `/health` response must include:

```text
status=healthy
runtime_contract_version=belief-url-resolution-v5-manufacturer-primary
manufacturer_first_primary_url=true
belief_driven_product_resolution=true
mandatory_review_url_delivery=true
deterministic_browser_fallback_on_llm_error=true
notebook_self_healing_runtime=true
compatibility_patches_applied=true
```

The notebook refuses to submit a paid search against an incompatible agent.

## 8. Core artifacts

```text
data/artifacts/<row_id>/
├── product_belief.json
├── product_understanding.md
├── market_decision_path.md
├── belief_updates.md
├── evidence_ledger.jsonl
├── adaptive_search_trace.json
├── candidate_url_records.json
├── candidates.csv
├── primary_url_acceptance.json
├── mandatory_url_delivery.json
├── source_selection.json
├── orchestrated_result.json
├── review.md
└── single_product_diagnostics.xlsx
```

`source_selection.json` is the authoritative audit record for the manufacturer-versus-retailer decision.

## 9. Supported execution surface

Use only:

```text
notebooks/01_run_product_evidence.ipynb
```

The notebook is a thin API client. Search, scraping, browser investigation, belief updates, selection, and artifact writing run inside the local Docker agent/browser stack.

## 10. Reviewer interpretation

Review both URL roles:

1. Open `primary_url` and verify exact identity and official product evidence.
2. Open `retailer_url`, when present, for price, availability, local market, and purchase context.
3. Confirm that a manufacturer page became primary only after every mandatory gate passed.
4. Confirm that retailer fallback occurred when manufacturer evidence was inadequate.
5. Treat `REVIEW_REQUIRED` as a delivered review candidate, not an automated exact-match claim.
