# Manufacturer-First Source Authority

## Core business rule

The final URL is selected for **product truth**, not merely for commercial availability.

```text
1. Official manufacturer/brand product page
2. Requested retailer product page
3. Alternative retailer in the requested country
4. Global retailer or other exact product page
5. Marketplace as last resort
```

This hierarchy applies only after a page passes the production gates. Manufacturer authority never rescues a wrong model, sibling product, wrong pack, category page, inaccessible page, or incomplete feature source.

Amazon/eBay are marketplace last-resort sources unless one of them is explicitly supplied as the requested retailer. Even then, an exact qualified official manufacturer page remains the primary product-truth source.

## Mandatory gates before authority

Every primary candidate must satisfy:

1. exact product, model, variant, size and pack identity;
2. browser-openable rendered page;
3. text-scrapable individual product-detail page;
4. rendered product verification;
5. all requested feature evidence on the primary page;
6. durable, non-expiring URL.

Only candidates that pass these gates are compared by source authority.

## Search trajectory

The three SerpAPI credits are used in this order:

```text
Credit 1: manufacturer_primary
Credit 2: requested_retailer_country, when retailer_name exists
          otherwise country_alternative
Credit 3: global_fallback
```

A retailer page discovered during the manufacturer search is retained, but it does not stop the search before the manufacturer opportunity has been evaluated. An exact, qualified manufacturer page may stop the workflow early.

## Authority tiers

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

Local manufacturer pages outrank global manufacturer pages when both represent the same exact product and pass the same gates. Manufacturer pages outrank requested retailers because the manufacturer is the authoritative source for product identity, specifications, warnings, compatibility, dimensions and official feature definitions.

## Manufacturer fallback rule

Manufacturer priority is conditional.

A retailer page becomes `primary_url` when:

- no official manufacturer product page exists;
- the manufacturer page is a category, family or marketing page;
- the manufacturer page is inaccessible or not scrapable;
- the manufacturer page represents a different model, edition, variant or pack;
- the manufacturer page does not contain all requested feature evidence;
- the manufacturer URL is transient or expiring.

The retailer is therefore a controlled fallback, not a lower-quality failure.

## Dual URL output

The result preserves both product truth and commercial reference:

```text
primary_url
primary_url_role
manufacturer_url
retailer_url
source_selection
```

### `primary_url`

The strongest page after strict gates and authority ranking.

### `primary_url_role`

One of:

```text
OFFICIAL_MANUFACTURER
RETAILER
MARKETPLACE
OTHER_PRODUCT_SOURCE
```

### `manufacturer_url`

The strongest strictly qualified official manufacturer page, when available.

### `retailer_url`

The strongest strictly qualified retailer or commerce page, when available. This remains useful for price, availability, local language, assortment and purchase verification even when the manufacturer is primary.

### `source_selection`

A compact decision artifact containing:

- applied policy;
- selected authority tier and role;
- manufacturer and retailer URLs;
- selection reason;
- mandatory gates;
- fallback rule.

The same object is written to:

```text
data/artifacts/<row_id>/source_selection.json
```

## Examples

| Manufacturer page | Retailer page | Primary result |
|---|---|---|
| Exact, complete and accessible | Exact and complete | Manufacturer |
| Exact but missing requested feature | Exact and complete | Retailer |
| Category/family page | Exact product page | Retailer |
| Wrong regional variant | Exact requested variant | Retailer |
| Exact product page only | Not found | Manufacturer |
| Not found | Exact product page only | Retailer |

## Non-negotiable principle

```text
identity and evidence safety
→ manufacturer authority
→ retailer and market preference
→ richness and confidence tie-breakers
```

Authority is applied after safety, never instead of safety.
