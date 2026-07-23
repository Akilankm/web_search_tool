# Exact Product Mapping Console and observable trace

## Purpose

The UI is a product-mapping console for human coders and stakeholders. It answers one business question first:

> Did the submitted product map to exactly one accessible and scrapable direct URL?

Discovery candidates, search snippets and inaccessible pages are evidence, not successful mappings.

## Visual hierarchy

The final screen presents:

1. **Exact product mapped — Yes or No**
2. **Supplied identifier verified — Yes or No**
3. **Rendered browser opens — Yes or No**
4. **Product content scrapable — Yes or No**
5. **Selected source role**
6. **One final direct URL**

The interface uses a modern dark visual system, clear evidence cards, compact stage tracking and prominent success/failure states. A failed run does not display a discovery URL as though it were a business result.

## Mapping contract banner

The console permanently displays the four mandatory principles:

- exact identity and edition;
- manufacturer/publisher first, retailer fallback;
- human-openable rendered page;
- scrapable product content.

## Live stages

| Stage | Reviewer visibility |
|---|---|
| Interpret | Submitted text, country, retailer, EAN/GTIN/ISBN, exact signals and unresolved variants |
| Search | Identifier-locked manufacturer, country-retailer and global recovery queries |
| Acquire | HTTP status, final URL, redirects, content type, JSON-LD Product/Book and visible text |
| Evaluate | Exact identifier, conflicting identifiers, direct-page, durability and source role |
| Browser | Rendered HTTP result, final URL, title, product text, controls, errors and screenshot |
| Deliver | Final mapping eligibility, manufacturer-first ranking and one selected URL |

## Candidate proof table

Every candidate row exposes:

- selected;
- final mapping eligible;
- source role;
- exact identity;
- identifier verified;
- browser accessible;
- scrapable;
- direct product page;
- durable URL;
- country and retailer alignment;
- coding completeness;
- conflicts and URL.

A candidate that fails any mandatory gate is marked discovery-only.

## Terminal states

### Verified

The exact product, supplied identifier, direct page, durable URL, rendered-browser access, scrapable text and downstream coding evidence all pass.

### Review required

The exact product URL is already accessible and scrapable. Review is limited to secondary fields such as coding completeness, country confidence or requested-retailer alignment.

### Failed

No URL satisfied the complete mapping contract. The console shows why each discovery candidate was rejected rather than presenting a false success.

### Technical failure

A configuration, dependency or runtime defect prevented a valid campaign.

## Reliability rules

- Search snippets never prove final identity.
- A supplied EAN/GTIN/ISBN must be present in acquired or rendered product content.
- A conflicting identifier in page data or the URL path blocks selection.
- HTTP failure blocks selection.
- Browser failure blocks selection.
- Empty or non-product rendered content blocks selection.
- Redirects to homepages, search, category, login or consent pages block selection.
- Tracking parameters are removed from canonical URLs.
- Manufacturer priority applies only to the same exact product edition.
- Rejected candidates remain visible for audit and recovery.
- Screenshots are mounted read-only into the UI container.

## Observable trace API

```text
GET /v1/jobs/{job_id}/trace?after_sequence=<n>
```

Each event contains a monotonically increasing sequence, stage, event type, reviewer-readable message and structured details. The final result artifact contains the complete trace for replay and audit.

The trace exposes observable evidence and gate outcomes. It does not expose or fabricate hidden chain-of-thought.
