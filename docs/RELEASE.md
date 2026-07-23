# Release and benchmark gates

Unit tests prove contracts; they do not prove production product quality. Production cutover also requires a frozen representative benchmark with human-verified exact URLs.

## Release invariant

A delivered URL must satisfy `product-url-acceptance-v1`:

- exact product and edition identity;
- supplied EAN, GTIN or ISBN verified when provided;
- no conflicting page, field or URL-path identifier;
- direct durable product page;
- rendered-browser accessibility;
- scrapable rendered product content;
- manufacturer-first ranking applied only among accepted candidates.

A discovery URL that fails any mandatory gate cannot be emitted as `VERIFIED` or `REVIEW_REQUIRED`.

Free-form warnings, search snippets and query purpose cannot determine acceptance or source authority.

## Required release order

Every release must pass:

1. Python compilation;
2. JSON validation;
3. shell validation;
4. Docker Compose validation;
5. canonical architecture guard;
6. acceptance-contract suite;
7. complete unit and integration suite;
8. legacy and monkey-patch reference rejection.

CI runs the complete order on Python 3.10, 3.11 and 3.12.

## Architecture gate

`scripts/check_architecture.py` must prove:

- acceptance functions exist only in `policy.py`;
- source priority exists only in `policy.py`;
- data models contain no business eligibility properties;
- ad hoc hard-blocker state is absent.

This is a merge blocker, not a documentation recommendation.

## Required regressions

The acceptance suite must prove:

1. Each mandatory gate independently blocks delivery.
2. A URL path containing a conflicting ISBN is rejected for the supplied EAN.
3. A search snippet containing the EAN cannot substitute for page or rendered evidence.
4. Browser failure blocks delivery even after successful HTTP acquisition.
5. Missing rendered product content blocks delivery.
6. A publisher print edition is rejected for a supplied eBook EAN.
7. An exact country-retailer page is selectable when no exact manufacturer edition exists.
8. An accepted manufacturer page outranks an accepted retailer page.
9. A failed manufacturer page cannot outrank an accepted retailer page.
10. HTTP 403 may proceed to browser recovery when rendered content can prove the exact product.
11. Search purpose cannot promote a retailer result to manufacturer authority.
12. All identifier-based search credits retain the submitted identifier.
13. Tracking parameters such as `srsltid` are removed.
14. Typed candidates and serialized UI candidates receive identical policy verdicts.

## Required benchmark metrics

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
- latency and cost per accepted mapping.

## Default production gates

| Metric | Gate |
|---|---:|
| Exact product mapping rate | ≥ 95% |
| Exact identifier verification among delivered identifier cases | 100% |
| Correct-product delivery rate | ≥ 99% |
| Wrong-product escape rate on supplied-identifier cases | 0% |
| Browser-accessible rate among delivered URLs | 100% |
| Scrapable-page rate among delivered URLs | 100% |
| Direct product-page rate among delivered URLs | 100% |
| Candidate recall@K | ≥ 98% |

The benchmark must include identifier-present and identifier-absent products, multilingual and partial text, edition conflicts, bundles/displays, manufacturer-versus-retailer alternatives, JavaScript-rendered pages, unavailable retailers, anti-bot pages, redirects, dead links and browser-unavailable conditions.
