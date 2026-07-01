# Decision Contracts

This document defines the business meaning of the major output fields and status values. It is intended for managers, analysts, downstream scraping teams, and product-coding teams.

## Core principle

```text
A URL is not production-ready because it exists.
A URL is production-ready only when it passes browser-openability, browser-visible content verification, production URL gate, and champion confirmation.
```

## Main URL fields

| Field | Business meaning | Automation interpretation |
|---|---|---|
| `product_url` | Selected URL emitted by the harness. | Use only when all production gates pass. |
| `verified_exact_url` | Strict exact URL when exact product proof is strong. | Strongest URL evidence. |
| `best_available_url` | Best review candidate when no confirmed champion exists. | Review-only, not automated handoff. |
| `best_reference_url` | Useful supporting/reference URL. | Evidence only. |

## Handoff fields

| Field | Good value | Meaning |
|---|---|---|
| `production_url_ready` | `true` | URL is safe for browser/scraping/product-coding handoff. |
| `production_url_status` | `PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL` | Final production-readiness class. |
| `needs_review` | `false` | No manual review needed before automated handoff. |
| `browser_openable` | `true` | URL is expected to open in a normal browser. |
| `user_visible_product_match` | `true` | The browser-visible page shows the intended product. |
| `user_visible_status` | `USER_VISIBLE_PRODUCT_PAGE_CONFIRMED` | Browser-visible content passed. |
| `highly_scrapable` | `true` | Page has enough evidence and is scrape-usable. |
| `exact_product_url_match` | `true` | URL matches the intended product, not a sibling/variant. |
| `champion_confirmation.passed` | `true` | Repeated champion confirmation passed. |

## Production decision matrix

| Condition | Business decision |
|---|---|
| `production_url_ready=true` and `user_visible_product_match=true` and `needs_review=false` and `champion_confirmation.passed=true` | Automated handoff allowed. |
| `browser_openable=true` but `user_visible_product_match=false` | Review-only; URL opens but does not show the intended product. |
| `production_url_ready=false` | Review-only. |
| `needs_review=true` | Review-only. |
| `champion_confirmation.passed=false` | Review-only. |
| `best_available_url` exists but `product_url` is not production-ready | Useful for reviewer, not automated handoff. |

## Browser-visible gate contract

```mermaid
flowchart TD
    A[Selected URL] --> B{Browser openable?}
    B -->|No| X[Review-only]
    B -->|Yes| C{User-visible page shows product?}
    C -->|No| X
    C -->|Yes| D{Highly scrapable?}
    D -->|No| X
    D -->|Yes| E{Exact product?}
    E -->|No| X
    E -->|Yes| F{Champion confirmation?}
    F -->|No| X
    F -->|Yes| G[Production-ready handoff]
```

Browser-visible verification records what the user actually sees:

```text
final resolved URL
screenshot when available
visible page text
page type
reroute/substitution status
optional LLM/vision verdict
```

See `BROWSER_VISIBLE_PRODUCT_GATE.md` for the full verifier contract.

## Identity fields

| Field | Meaning |
|---|---|
| `identity_status` | Overall identity judgement for the selected candidate. |
| `ean_check` | Whether input EAN/GTIN matches page evidence. |
| `title_check` | Strength of product title match. |
| `quantity_check` | Whether pack count/quantity appears consistent. |
| `brand_check` | Whether brand evidence is aligned. |
| `variant_check` | Whether the page appears to be a conflicting variant. |
| `blocking_reasons` | Hard reasons preventing production handoff. |

## Browser-visible fields and artifacts

| Field / artifact | Meaning |
|---|---|
| `browser_visible_verdicts.json` | Row-level machine-readable map of visible-content verdicts. |
| `browser_visible/<candidate>_browser_preview.png` | Viewport screenshot, when browser capture is available. |
| `browser_visible/<candidate>_visible_text.txt` | Visible text excerpt used for verification. |
| `browser_visible/<candidate>_resolved_url.txt` | Final browser-resolved URL. |
| `browser_visible/<candidate>_browser_visible_verdict.json` | Candidate-level visible-content verdict. |
| `browser_visible/<candidate>_browser_visible_verdict.md` | Human-readable visible-content verdict. |

## Retailer and country fields

| Field | Meaning |
|---|---|
| `retailer_check` | Whether the URL aligns with requested retailer evidence. |
| `country_check` | Whether URL/page is acceptable for the requested country policy. |
| `selected_domain` | Domain selected by the final decision. |
| `selected_retailer_name` | Retailer inferred/selected from evidence. |
| `selected_from_requested_retailer` | Whether selected URL came from the requested retailer. |
| `selected_from_global_fallback` | Whether a fallback/global candidate was used. |

## Quality fields

| Field | Meaning |
|---|---|
| `confidence` | Overall confidence in selected decision. |
| `quality_tier` | Enterprise quality tier, usually A/B/C/D/E. |
| `failure_taxonomy` | Machine-readable reasons for weak or review outcomes. |
| `coding_readiness_status` | Whether downstream product coding can consume the evidence. |

## Important statuses

| Status | Business meaning |
|---|---|
| `PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL` | Strongest automated handoff class. |
| `USER_VISIBLE_PRODUCT_PAGE_CONFIRMED` | Browser-visible page shows the intended product. |
| `BROWSER_VISIBLE_PRODUCT_CONTENT_NOT_VERIFIED_NEEDS_REVIEW` | No browser-visible verdict was available; review required. |
| `BROWSER_OPENABLE_BUT_REROUTED` | Browser opens, but page appears rerouted/substituted. |
| `BROWSER_OPENABLE_BUT_WRONG_PRODUCT` | Browser opens, but visible product does not match input. |
| `BROWSER_OPENABLE_BUT_NOT_PRODUCT_PAGE` | Browser opens, but the page is not a product page. |
| `BROWSER_OPENABLE_BUT_CONSENT_WALL` | Browser opens to consent/cookie wall. |
| `BROWSER_OPENABLE_BUT_LOGIN_WALL` | Browser opens to login/account wall. |
| `BROWSER_OPENABLE_BUT_CATEGORY_PAGE` | Browser opens to category/listing page. |
| `BROWSER_OPENABLE_BUT_SEARCH_RESULTS_PAGE` | Browser opens to search result page. |
| `BROWSER_OPENABLE_BUT_ACCESS_BLOCKED` | Browser opens to block/captcha/access-denied page. |
| `BROWSER_OPENABLE_BUT_VISIBLE_CONTENT_INSUFFICIENT` | Browser opens, but visible product evidence is insufficient. |
| `CHAMPION_CONFIRMATION_PASSED` | Repeated champion checks passed. |
| `CHAMPION_CONFIRMATION_FAILED` | Candidate was not stable/strong enough after confirmation. |
| `PRODUCT_URL_NOT_BROWSER_OPENABLE_NEEDS_REVIEW` | URL may exist but is not browser-safe. |
| `PRODUCT_URL_NOT_HIGHLY_SCRAPABLE_NEEDS_REVIEW` | Page is not rich/scrape-ready enough. |
| `PRODUCT_URL_NOT_EXACT_MATCH_NEEDS_REVIEW` | URL likely wrong product, variant, or sibling. |
| `PRODUCT_URL_GLOBAL_OR_COUNTRY_MISMATCH_NEEDS_REVIEW` | Country/fallback policy concern. |
| `STRICT_PRODUCT_URL_REQUIRED_BUT_NO_URL_CANDIDATE_AVAILABLE` | No viable candidate was discovered. |

## Review queue philosophy

The review queue is a strength, not a weakness.

```mermaid
flowchart LR
    A[All products] --> B{Enough evidence?}
    B -->|Yes| C[Automated handoff]
    B -->|No| D[Review queue]
    D --> E[Failure reason]
    D --> F[Best available URL]
    D --> G[Audit report]
```

A mature automation system must know when not to automate.
