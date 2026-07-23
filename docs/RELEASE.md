# Release and benchmark gates

Unit tests prove contracts; they do not prove production product quality. Production cutover requires a frozen, representative benchmark with human-verified exact URLs.

## Mandatory release invariant

A delivered URL must satisfy all of these:

- exact product and edition identity;
- supplied EAN/GTIN/ISBN verified from page or rendered-page evidence;
- no conflicting field or URL-path identifier;
- direct durable product page;
- rendered browser accessibility;
- scrapable rendered product content;
- manufacturer-first ranking applied only among fully eligible exact mappings.

A discovery URL that fails any mandatory gate must not be emitted as `VERIFIED` or `REVIEW_REQUIRED`.

Every submitted product remains an unresolved operational item until an exact usable URL is found. The system does not close the item with a false or inaccessible URL.

## Required regression cases

The release suite must prove:

1. A URL whose path contains a conflicting ISBN is rejected for the supplied EAN.
2. A search snippet containing the exact EAN cannot substitute for page evidence.
3. An HTTP-inaccessible page is rejected.
4. A browser-inaccessible page is rejected.
5. A page without scrapable rendered text is rejected.
6. A publisher print page is rejected for a supplied eBook EAN.
7. An exact accessible country-retailer page can be selected when the manufacturer lacks the exact edition.
8. An exact accessible manufacturer page outranks an exact accessible retailer page.
9. All identifier-based search credits retain the submitted identifier.
10. Tracking parameters such as `srsltid` are removed.

## Required metrics

- exact product mapping rate;
- exact identifier verification rate;
- exact URL top-1 accuracy;
- correct-product delivery rate;
- candidate recall@K;
- wrong-product escape rate;
- direct product-page rate;
- rendered-browser success rate;
- scrapable-page rate;
- manufacturer-source selection rate when an exact manufacturer page exists;
- human review acceptance rate;
- latency and cost per accepted exact mapping.

## Default gates

| Metric | Gate |
|---|---:|
| Exact product mapping rate | ≥ 95% |
| Exact identifier verification among delivered URLs | 100% |
| Correct-product delivery rate | ≥ 99% |
| Wrong-product escape rate | 0% on supplied-identifier cases |
| Browser-accessible rate among delivered URLs | 100% |
| Scrapable-page rate among delivered URLs | 100% |
| Direct product-page rate among delivered URLs | 100% |
| Candidate recall@K | ≥ 98% |

The benchmark must include EAN-present and EAN-absent items, multilingual and partial text, exact-edition conflicts, bundles/displays, manufacturer-versus-retailer alternatives, unavailable local retailers, anti-bot pages, redirects, dead links and browser-unavailable conditions.
