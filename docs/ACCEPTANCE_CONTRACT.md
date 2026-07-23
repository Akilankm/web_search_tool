# Canonical product URL acceptance contract

## Purpose

The resolver has one authoritative business decision: whether a discovered candidate may be delivered as the final product URL.

That decision is implemented only in:

```text
src/product_url_v2/policy.py
```

No model, evaluator, browser allocator, trace renderer, UI component, or test may independently reconstruct acceptance.

## Mandatory final gates

A candidate can be delivered only when all mandatory gates pass:

1. exact product identity;
2. supplied EAN, GTIN, or ISBN verified when present;
3. direct product-detail page;
4. durable canonical URL;
5. rendered-browser accessibility;
6. scrapable rendered product content;
7. no identity, edition, or identifier conflicts.

Search snippets are discovery evidence only. They are never final identity proof.

## Source hierarchy

Source priority is defined once in `policy.py`:

1. local manufacturer or publisher;
2. global manufacturer or publisher;
3. requested retailer;
4. country retailer;
5. global retailer;
6. marketplace;
7. unknown.

Source priority is applied only among candidates that already pass every mandatory final gate.

## Pre-browser recovery

Browser allocation intentionally allows candidates whose page-only evidence is incomplete. JavaScript-rendered content may reveal the exact identifier, product controls, and product description.

The browser precheck rejects only explicit mismatch, transient URLs, non-product discovery results, and explicit conflicts. Missing page-only EAN evidence is not treated as a final blocker before rendering.

## Secondary review

`REVIEW_REQUIRED` is permitted only after the final URL is already an exact, accessible, and scrapable mapping. Secondary review may cover:

- incomplete coding fields;
- unconfirmed country alignment;
- requested-retailer fallback.

It is never used to return an inaccessible or uncertain discovery URL.

## Architecture guard

`scripts/check_architecture.py` fails the release when:

- acceptance functions are defined outside `policy.py`;
- source priority is defined outside `policy.py`;
- legacy ad hoc blocker state is reintroduced;
- legacy mapping-eligibility properties are reintroduced in data models.

## Release order

Every release must pass, in this order:

1. Python compilation;
2. JSON, shell, and Docker Compose validation;
3. canonical architecture guard;
4. acceptance contract test suite;
5. complete unit and integration suite;
6. legacy-reference rejection.
