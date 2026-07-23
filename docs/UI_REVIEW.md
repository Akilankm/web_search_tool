# Exact Product Mapping Console and observable trace

## Purpose

The UI answers one business question first:

> Did the submitted product pass the canonical policy and map to exactly one accessible, scrapable direct URL?

Discovery candidates, search snippets and inaccessible pages are evidence, not successful mappings.

## Visual hierarchy

The final screen presents:

1. exact product mapped;
2. supplied identifier verified;
3. rendered browser accessibility;
4. product content scrapability;
5. selected source role;
6. one final direct URL.

The active `acceptance_policy` and `acceptance_policy_module` are shown in the sidebar. Candidate tables are produced from the same canonical verdict used by the API and orchestrator.

## Contract banner

The console permanently presents:

- exact identity and edition;
- supplied identifier agreement;
- browser-accessible direct page;
- scrapable product content.

Manufacturer or publisher priority is applied only after these gates pass.

## Live stages

| Stage | Reviewer visibility |
|---|---|
| Interpret | Submitted constraints, exact signals and unresolved variants |
| Search | Identifier-locked manufacturer, retailer and global queries |
| Acquire | HTTP status, redirects, content type and structured data |
| Evaluate | Page identity, identifiers, direct-page evidence and source role |
| Browser | Rendered final URL, title, product text, controls, errors and screenshot |
| Deliver | `product-url-acceptance-v1`, source-priority ranking and selected URL |

## Candidate proof table

Every row exposes:

- selected;
- canonical mapping eligibility;
- acceptance policy;
- source role;
- exact identity;
- identifier verification;
- browser accessibility;
- scrapability;
- direct-page and durability gates;
- secondary country, retailer and coding gates;
- canonical blockers;
- conflicts and URL.

The UI does not independently calculate acceptance.

## Terminal states

### Verified

Every mandatory gate and downstream coding evidence pass, with no secondary review reason.

### Review required

Every mandatory mapping gate passes. Review is limited to secondary coding, country or requested-retailer evidence.

### Failed

No candidate passes the canonical acceptance contract. Discovery candidates remain visible without being presented as successful mappings.

### Technical failure

A configuration, dependency or runtime defect prevents a valid decision.

## Reliability rules

- Search snippets never prove final identity.
- A supplied EAN, GTIN or ISBN must be present in acquired or rendered product evidence.
- Conflicting product, edition or identifier evidence blocks selection.
- Static HTTP failure may proceed to browser recovery when the URL is product-like and no explicit conflict exists.
- Browser failure blocks final selection.
- Empty or non-product rendered content blocks final selection.
- Redirects to homepages, search, category, login or consent pages block final selection.
- Tracking parameters are removed during canonicalization.
- Search purpose cannot change source authority.
- Manufacturer priority applies only to the same exact product edition.
- Warning text cannot change business status.
- Rejected candidates remain visible for audit and recovery.
- Screenshots are mounted read-only into the UI container.

## Observable trace API

```text
GET /v1/jobs/{job_id}/trace?after_sequence=<n>
```

Each event contains a monotonically increasing sequence, stage, event type, reviewer-readable message and structured details. The final result artifact contains the complete trace for replay and audit.

The trace exposes observable evidence and policy gate outcomes. It does not expose or fabricate hidden chain-of-thought.
