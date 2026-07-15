# Standardized Source-Authority Hierarchy

## Business rule

The product URL workflow does not treat all technically valid URLs as equally desirable.

When `retailer_name` is supplied, that retailer is preferred first. Otherwise the standardized internal hierarchy is:

```text
Local/regional manufacturer website
→ Global manufacturer website
→ Major retailer in the requested country
→ Other local website
→ Other global exact-product website
→ Amazon/eBay last resort
```

Amazon or eBay receive requested-retailer priority only when they are explicitly supplied as `retailer_name`.

## Complete hierarchy with retailer input

```text
0. Requested retailer in requested country
1. Requested retailer outside requested country
2. Local/regional manufacturer website
3. Global manufacturer website
4. Major retailer in requested country
5. Other local website
6. Other global exact-product website
7. Amazon/eBay marketplace fallback
```

## Search routing

SerpAPI engine selection happens after the target source tier is determined.

```text
input product
→ determine highest unresolved source tier
→ expose only engines suitable for that tier
→ LLM selects engine and query
→ deterministic validation
→ one SerpAPI credit
→ classify and validate returned URLs
→ stop or move to the next unresolved tier
```

Typical engine choices:

| Target tier | Preferred engines |
|---|---|
| Requested retailer | Retailer-native engine when supported; otherwise Google, Shopping, or AI Mode |
| Local/global manufacturer | Google Search or AI Mode |
| Major country retailer | Google Shopping, Immersive Product, Google Search |
| Other local/global website | Google Search, AI Mode, Shopping where useful |
| Amazon/eBay last resort | Broad Google recovery unless explicitly requested |

The LLM cannot route to a lower source tier while the current higher tier remains the current standardized target.

## Candidate classification

Every canonical URL receives:

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

Manufacturer classification uses the candidate domain together with product brand/manufacturer evidence. Country alignment uses the configured country profiles and localized URL patterns. Merchant URLs returned through Shopping or Immersive Product are classified as major country retailers only when country-aligned.

## Selection semantics

Source authority is lexicographic after mandatory product validity:

```text
exact product identity
→ technically usable product page
→ source tier
→ remaining confidence/richness signals
```

Therefore, a valid manufacturer URL outranks a richer Amazon/eBay page when Amazon/eBay was not requested.

A lower-tier URL can be selected only when:

- stronger-tier URLs were not found;
- stronger-tier URLs failed exact-product identity;
- stronger-tier URLs were inaccessible or not scrapable;
- stronger-tier URLs failed the final evidence policy.

## Early stopping

The search may stop before all three credits only when a validated URL belongs to one of these tiers:

- requested retailer;
- local/regional manufacturer;
- global manufacturer.

A major retailer, other website, Amazon, or eBay result does not cause premature stopping while stronger source tiers can still be investigated with remaining credits.

## Notebook RCA

The supported notebook exposes:

- `source_hierarchy_df`: one row per SerpAPI credit and target source tier;
- `source_tier_summary_df`: candidate, scrape, identity, and selection conversion by tier;
- source authority columns directly in `results_df`;
- a source-tier route chart;
- `source_hierarchy` and `source_tier_summary` Excel worksheets.

This makes the final decision explainable as both:

1. **Was this the exact working product URL?**
2. **Was this the strongest available source according to the internal hierarchy?**

## Audit artifacts

`result.json` and `adaptive_search_trace.json` include:

```text
search.source_authority_hierarchy_enforced
search.requested_retailer_override
search.source_hierarchy
search.amazon_ebay_last_resort
search.target_source_tiers
```

`candidate_url_records.json` and `candidates.csv` retain the source classification for every canonical URL.
