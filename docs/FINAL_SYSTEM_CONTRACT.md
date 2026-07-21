# Final Product Identification System Contract

This document defines the canonical production contract.

## Objective

Given:

```text
MAIN_TEXT
COUNTRY_CODE
optional RETAILER_NAME
optional EAN/GTIN
optional LANGUAGE_CODE
```

identify the strongest defensible exact product and preserve the evidence used to reach that identity.

```text
Primary business result
= product_identification

Supporting operational result
= reusable source URL when available
```

The system must not fabricate a product identity, a product attribute or a URL.

## Two-axis result model

Product identification and source delivery are separate axes.

### Axis 1 — Product identification

Use:

```text
product_identification.resolution_status
```

Allowed values:

| Status | Meaning |
|---|---|
| `EXACT` | One product identity is resolved |
| `PROBABLE` | One identity leads with residual uncertainty |
| `AMBIGUOUS` | Multiple plausible identities remain |
| `CONFLICTING` | Evidence supports incompatible identities |
| `INSUFFICIENT_EVIDENCE` | Evidence cannot support a defensible identity |
| `IN_PROGRESS` | Resolution is still being evaluated |
| `INITIALIZED` | Interpretation has begun |

### Axis 2 — Source delivery

Use:

```text
primary_url
primary_url_acceptance
url_delivery
resolution_outcome
```

This axis describes whether a reusable evidence source was found.

### Required interpretation

```text
EXACT product + no safe URL
= product identified, source delivery unresolved
```

A URL failure must not be presented as a product-identification failure.

## Product identity contract

The product result contains:

```text
resolution_status
leading_hypothesis
selected_hypothesis_id
hypotheses
claims
uncertainties
unknowns
evidence_ledger
metrics
```

The leading hypothesis contains:

```text
canonical_name
category
attributes
assumptions
negative_constraints
posterior_probability
supporting_evidence_ids
contradicting_evidence_ids
```

## Evidence contract

Accepted evidence may include:

```text
submitted text
EAN/GTIN
retailer and country context
static page text
structured page data
rendered page text
browser screenshots
product and package images
manufacturer evidence
retailer evidence
```

Every material fact should be traceable to an evidence item with provenance, polarity, reliability and extraction confidence.

Vision-derived evidence must include:

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

## Hypothesis comparison contract

The system must preserve competing product hypotheses until evidence supports resolution.

Resolution considers:

```text
posterior probability
posterior margin
identity completeness
ambiguity entropy
assumption burden
supporting evidence
contradicting evidence
hard conflicts
```

## Exact-product verification

The leading identity is evaluated across:

```text
EAN/GTIN
brand
manufacturer
model or series
variant
product form
size
quantity
pack configuration
market context
```

A sibling product, wrong variant or wrong pack must not be accepted merely because it is visually or semantically similar.

## Requested-feature contract

The active feature schema defines facts needed for downstream coding.

Feature coverage is reported separately from identity resolution.

```text
product may be identified
while one or more requested coding facts remain unresolved
```

## Source evidence contract

URLs are evidence locations.

```text
primary_url
manufacturer_url
retailer_url
source_selection
primary_url_acceptance
url_delivery
```

Source quality may include:

```text
browser-openable
text-accessible
individual product page
identity-supporting
feature-supporting
non-expiring
reusable
```

The UI represents these as:

```text
VERIFIED
NOT VERIFIED
NOT ASSESSED
```

The repository must not expose these source checks as the headline product verdict.

## Source-authority policy

Source authority ranks qualified evidence locations:

```text
local official manufacturer
global official manufacturer
requested retailer
major market retailer
global exact-product source
marketplace last resort
```

Authority does not create product identity and cannot override contradictory product evidence.

## Structured no-safe-URL outcome

When no reusable direct source is found within the bounded source-search policy:

```text
resolution_outcome.code=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
url_delivery.delivered=false
```

This means:

> No safe reusable source URL was found within the configured search boundary.

It does not mean:

> The product was not identified.

## Job-status compatibility

The existing runtime retains the current technical and source-delivery job statuses:

```text
COMPLETED
REVIEW_REQUIRED
FAILED
```

Because the current validator is source-delivery-aware, an `EXACT` product may still have `job_status=REVIEW_REQUIRED` when no safe source URL is available.

Consumers must use:

```text
product_identification.resolution_status
```

for the product verdict, not `job_status` alone.

`FAILED` remains reserved for software, configuration, dependency or response-contract errors.

## Stable result schema

Every terminal business result contains:

```text
product_identification
search.market_decision_path
primary_url
primary_url_role
manufacturer_url
retailer_url
source_selection
primary_url_acceptance
url_delivery
business_judgement_review
run_configuration
```

A no-safe-URL result may additionally contain:

```text
resolution_outcome.code=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
url_delivery.status=NO_SAFE_DIRECT_PRODUCT_URL_FOUND_AFTER_BOUNDED_SEARCH
```

## Decision audit contract

Every terminal business result writes:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

The observable sequence is:

```text
observable evidence
→ explicit rule
→ product judgment
→ next action
```

The artifact does not expose hidden chain-of-thought.

## Product Identification Platform UI contract

Application:

```text
apps/product_evidence_ui.py
```

The UI must display, in this order:

```text
identified product
resolution status
posterior confidence
resolved identity attributes
identity claims
evidence ledger
alternative product hypotheses
unresolved distinctions
supporting source evidence
decision audit
artifacts
```

Mandatory behavior:

```text
EXACT product + all URL checks false
→ show Product identified
→ do not show FAIL as the product verdict
→ keep URL checks under Source evidence
```

## Runtime controls

Approved per-job controls:

```text
serpapi_credits:                 1–3
full_scrapes:                    1–12
scrapes_per_domain:              1–4
planner_candidates:              3–20
agentic_candidates:              1–8
browser_turns_per_candidate:     1–12
browser_actions_per_candidate:   1–24
images_in_reasoning:             4–20
```

Controls change evidence depth only. They do not change product-identity semantics.

## Runtime compatibility

```text
belief-url-resolution-v9-product-evidence-ui
```

The runtime name is retained for backward compatibility. The canonical consumer contract is product-identification-first.

Required capabilities:

```text
belief_driven_product_resolution=true
business_judgement_review_artifact=true
structured_no_url_review_outcome=true
per_job_runtime_controls=true
compatibility_patches_applied=true
```

## Product artifacts

Primary identity artifacts:

```text
product_belief.json
product_understanding.md
belief_updates.md
evidence_ledger.jsonl
business_judgement_review.md
orchestrated_result.json
```

Supporting source artifacts:

```text
adaptive_search_trace.json
candidate_url_records.json
candidates.csv
primary_url_acceptance.json
mandatory_url_delivery.json
source_selection.json
```

Operational artifacts:

```text
run_configuration.json
single_product_diagnostics.xlsx
```

## Supported execution surfaces

```text
apps/product_evidence_ui.py
notebooks/01_single_product.ipynb
notebooks/02_batch_products.ipynb
notebooks/03_artifact_diagnostics.ipynb
```

All surfaces must interpret product resolution and source delivery as separate dimensions.

## Release acceptance

CI must verify:

```text
source and UI compilation
product-identification-first UI hierarchy
EXACT identity remains identified without a usable URL
source states use VERIFIED / NOT VERIFIED / NOT ASSESSED
alternative product hypotheses are visible
all notebook JSON and code cells
runtime-control validation and isolation
Docker Compose and Azure ML bootstrap
business judgment artifacts
complete regression suite
```

## Related documents

- [Feature reference](FEATURE_REFERENCE.md)
- [System workflow](SYSTEM_WORKFLOW.md)
- [Product Identification Platform UI](PRODUCT_EVIDENCE_UI.md)
- [Business judgment review](BUSINESS_JUDGEMENT_REVIEW.md)
- [Notebook usage](NOTEBOOK_USAGE.md)
- [Azure ML operations](AZUREML_OPERATIONS.md)
