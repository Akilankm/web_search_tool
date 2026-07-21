# Product Evidence Platform — System Workflow

## Objective

Resolve incomplete product text into either:

1. a defensible direct product-page URL that passes every production gate; or
2. a structured `REVIEW_REQUIRED` outcome when no safe direct URL is found within the configured bounded policy.

The workflow is evidence-first and artifact-producing. Search results are candidates, not answers.

## End-to-end flow

```text
Product input
→ Product interpretation
→ Adaptive source search
→ Candidate normalization
→ Static extraction
→ Rendered browser investigation
→ Multimodal evidence reasoning
→ Exact-product verification
→ Requested-feature verification
→ URL durability verification
→ Source-authority selection
→ Result and artifact generation
```

## Stage 1 — Product input

The system receives:

```text
row_id
main_text
country_code
optional retailer_name
optional EAN/GTIN
optional language_code
feature_set
optional per-job runtime controls
```

Mandatory-field validation occurs before paid search.

## Stage 2 — Product interpretation

The system constructs an explicit identity hypothesis and uncertainty state. It attempts to resolve:

```text
brand
manufacturer
model or series
product form
variant
size
quantity
pack configuration
market context
```

Ambiguity is recorded and used to guide search. It is not hidden or silently discarded.

## Stage 3 — Adaptive source search

The default authority-aware route is:

```text
official manufacturer
→ requested retailer or same-country alternatives
→ global exact-product sources
```

Each search stage records:

```text
query
engine
scope
reason
results returned
new candidate URLs
qualified candidates
continuation or stop decision
```

Search is bounded by the effective per-job controls.

## Stage 4 — Candidate normalization

Candidates are normalized and deduplicated. Indirect or low-value references are rejected before expensive processing.

Common rejection classes:

```text
search-result page
category page
homepage
tracking or redirect URL
signed or expiring URL
PDF or media document
wrong country or retailer context
obvious sibling product or variant
```

## Stage 5 — Static extraction

Promising candidates are fetched for text and structured evidence. The system attempts to extract:

```text
page title and product name
description
brand and manufacturer
specifications
attributes
EAN/GTIN
price and availability signals
image references
page richness and scrapability
```

Static extraction reduces browser cost and provides an initial evidence record.

## Stage 6 — Rendered browser investigation

Eligible candidates are opened through the isolated browser service.

The browser workflow can:

```text
open the page
dismiss safe overlays
expand product sections
scroll for lazy content
inspect product images
capture screenshots
stop when resolved, blocked or unproductive
```

It cannot log in, enter credentials, purchase, submit forms or bypass access controls.

## Stage 7 — Multimodal evidence reasoning

The system combines:

```text
rendered text
structured page data
screenshots
product gallery images
package front/back images
visible warnings and diagrams
```

Vision-derived evidence is linked to the exact visual asset that supported the conclusion.

## Stage 8 — Exact-product verification

The candidate is checked against the intended product across:

```text
EAN/GTIN
brand
manufacturer
model
variant
form
size
quantity
pack
country context
```

A blocking conflict prevents acceptance even when the page appears otherwise plausible.

## Stage 9 — Requested-feature verification

The active feature schema defines which facts must exist on the selected page.

The strict default requires:

```text
100% required-feature coverage
100% critical-feature coverage
no conflicting requested features
```

## Stage 10 — URL usability and durability

The candidate must be:

```text
browser-openable
text-scrapable
an individual product page
direct and reusable
non-expiring
not session-bound
```

A page that is exact but operationally unusable is not accepted as the final URL.

## Stage 11 — Source-authority selection

Only candidates that pass the production gates are compared by source authority.

```text
local official manufacturer
global official manufacturer
requested retailer in market
requested retailer global
major country retailer
global exact-product source
marketplace last resort
```

Manufacturer priority is conditional. Authority does not override incompleteness, mismatch or access failure.

## Stage 12 — Terminal result

### Accepted URL

```text
job_status=COMPLETED
primary_url=<direct product page>
url_delivery.delivered=true
url_delivery.strictly_verified=true
```

### Review with URL

```text
job_status=REVIEW_REQUIRED
primary_url=<real direct review URL>
url_delivery.delivered=true
url_delivery.strictly_verified=false
```

### No safe URL

```text
job_status=REVIEW_REQUIRED
primary_url=null
resolution_outcome.code=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
url_delivery.delivered=false
```

### Technical failure

```text
job_status=FAILED
```

Technical failure is reserved for software, configuration, dependency or contract errors.

## Decision audit sequence

Every terminal business result exposes:

```text
observable evidence
→ explicit business rule
→ agent judgment
→ next action
```

This sequence is written to:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

The artifact supports human comparison of decision order, evidence use and final outcome without exposing hidden chain-of-thought.

## Runtime control flow

The UI or API may submit approved per-job controls:

```json
{
  "runtime_options": {
    "serpapi_credits": 3,
    "full_scrapes": 6,
    "scrapes_per_domain": 2,
    "planner_candidates": 8,
    "agentic_candidates": 3,
    "browser_turns_per_candidate": 4,
    "browser_actions_per_candidate": 6,
    "images_in_reasoning": 8
  }
}
```

These values are:

```text
validated by the API
stored in context-local state
isolated across workers
applied only to the submitted job
persisted in run_configuration.json
```

They do not modify shared environment variables or safety policies.

## Artifact flow

```text
run starts
→ artifact directory created
→ interpretation and search traces written
→ browser and evidence records written
→ acceptance and source decisions written
→ final result rewritten with runtime configuration
→ diagnostic exports generated when requested
```

Primary artifact directory:

```text
data/artifacts/<row_id>/
```

## Related documents

- [Feature reference](FEATURE_REFERENCE.md)
- [Product Evidence Platform UI](PRODUCT_EVIDENCE_UI.md)
- [Final system contract](FINAL_SYSTEM_CONTRACT.md)
- [Business judgment review](BUSINESS_JUDGEMENT_REVIEW.md)
- [Structured no-safe-URL outcome](STRUCTURED_NO_URL_OUTCOME.md)
