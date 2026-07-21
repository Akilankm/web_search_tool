# Product Identification Platform — Feature Reference

This document is the canonical feature-level reference for the repository.

## Product-result hierarchy

```text
Primary outcome
= identified product + resolution status + evidence confidence

Supporting outcome
= evidence sources + URLs + source-quality metadata + artifacts
```

A URL is never treated as the product itself. URL checks describe the usefulness of an evidence source. They do not determine whether a product hypothesis exists.

---

## 1. Product input contract

### Purpose

Represent one intended product and its market context without assuming every identifier is available.

### Inputs

| Field | Required | Use |
|---|---:|---|
| `row_id` | Yes | Job and artifact identifier |
| `main_text` | Yes | Incomplete vendor or source product description |
| `country_code` | Yes | Market and language context |
| `retailer_name` | No | Retailer-specific context and search scope |
| `ean` | No | Strong exact-product evidence when available |
| `language_code` | No | Query and page-language context |
| `feature_set` | Yes | Requested product facts |
| `runtime_options` | No | Per-job evidence-depth controls |

### Processing

Mandatory fields are validated before paid search. Identifiers are preserved as text.

### Outputs

```text
validated product payload
normalized country and language
artifact row identifier
resolved feature-set name
```

### Requirement changes

Modify when the external input schema changes.

### Primary modules

```text
src/product_evidence_harness/contracts.py
src/product_evidence_harness/agent_service/app.py
src/product_evidence_harness/feature_schema.py
```

---

## 2. Product interpretation

### Purpose

Convert incomplete text into explicit product claims, assumptions, unknowns and identity dimensions.

### Identity dimensions

```text
brand
manufacturer
model or series
product form
variant
size
quantity
pack configuration
category
market context
```

### Processing

The interpretation stage distinguishes explicit text, normalized values, deterministic derivations, model priors and unresolved fields.

### Outputs

```text
claims
negative_constraints
unknowns
parse_coverage
identity_completeness
search_readiness
product_understanding.md
```

### Requirement changes

Modify for new abbreviations, identity dimensions or domain-specific parsing rules.

### Primary modules

```text
src/product_evidence_harness/belief/contracts.py
src/product_evidence_harness/belief/engine.py
src/product_evidence_harness/belief_runtime.py
```

---

## 3. Product hypothesis construction

### Purpose

Create explicit competing explanations for which product the input may represent.

### Hypothesis fields

```text
hypothesis_id
canonical_name
category
attributes
assumptions
negative_constraints
prior_score
posterior_probability
supporting_evidence_ids
contradicting_evidence_ids
```

### Processing

The system must preserve multiple plausible hypotheses until evidence justifies resolving one.

### Outputs

```text
hypotheses
leading_hypothesis
selected_hypothesis_id
uncertainties
ambiguity_entropy
```

### Requirement changes

Modify when candidate identity generation, prior construction or ambiguity policy changes.

### Primary modules

```text
src/product_evidence_harness/belief/contracts.py
src/product_evidence_harness/belief/engine.py
src/product_evidence_harness/belief/artifacts.py
```

---

## 4. Feature schema resolution

### Purpose

Define product facts required by downstream coding or review.

### Default schema

```text
inputs/private/toy_features.json
```

### Processing

Feature requirements guide evidence collection and completeness assessment. They do not replace product identity.

### Outputs

```text
feature_set
feature assessments
missing requested facts
conflicting requested facts
```

### Requirement changes

Modify the feature-set JSON when requested product facts change.

### Primary modules

```text
src/product_evidence_harness/feature_schema.py
src/product_evidence_harness/schema_io.py
src/product_evidence_harness/feature_evidence.py
```

---

## 5. Adaptive source search

### Purpose

Find evidence capable of distinguishing product hypotheses.

### Search order

```text
manufacturer sources
→ requested retailer or same-country sources
→ global product sources
```

### Processing

Queries target unresolved product distinctions, identifiers, models, variants, forms and pack configurations.

### Outputs

```text
search stages
queries and engines
market decision path
adaptive_search_trace.json
candidate_url_records.json
```

### Requirement changes

Modify for new search engines, query strategy, source order or search-credit limits.

### Primary modules

```text
src/product_evidence_harness/adaptive_search.py
src/product_evidence_harness/adaptive_search_runtime.py
src/product_evidence_harness/query_builder.py
src/product_evidence_harness/three_stage_pipeline.py
```

---

## 6. Candidate normalization and precision filtering

### Purpose

Remove duplicate, indirect or obviously irrelevant evidence sources before expensive acquisition.

### Checks

```text
URL normalization
domain classification
direct product-page likelihood
identifier and title signals
country and retailer compatibility
search/category/homepage rejection
signed or transient URL indicators
```

### Outputs

```text
normalized candidate
source role
precision score
hard-failure reasons
candidate status
```

### Requirement changes

Modify for new retailer URL patterns, redirect formats or exclusion classes.

### Primary modules

```text
src/product_evidence_harness/candidate_precision.py
src/product_evidence_harness/candidate_store.py
src/product_evidence_harness/candidate_reporting.py
```

---

## 7. Static extraction

### Purpose

Acquire product evidence from page text and structured data.

### Evidence

```text
product name
brand
manufacturer
model
EAN/GTIN
variant
size
quantity
pack
specifications
description
image references
```

### Outputs

```text
page text
structured identifiers
metadata
scrapability information
image URLs
```

### Requirement changes

Modify for new structured-data formats or retailer markup.

### Primary modules

```text
src/product_evidence_harness/scraper.py
src/product_evidence_harness/offline_capture.py
src/product_evidence_harness/rendered_page.py
```

---

## 8. Rendered browser investigation

### Purpose

Collect evidence that is visible only after rendering or interaction.

### Allowed actions

```text
open page
dismiss safe overlays
expand product details
scroll lazy content
inspect product images
capture screenshots
```

### Prohibited actions

```text
login
credential entry
purchase
form submission
access-control bypass
```

### Outputs

```text
rendered text
screenshots
visual assets
browser action trace
candidate investigations
```

### Requirement changes

Modify for browser tools, allowed actions or blocker policy.

### Primary modules

```text
src/product_evidence_harness/browser_service/controller.py
src/product_evidence_harness/browser_client.py
src/product_evidence_harness/llm/agentic_browser.py
```

---

## 9. Multimodal evidence reasoning

### Purpose

Resolve identity facts visible in packaging, screenshots, gallery images or diagrams.

### Evidence examples

```text
package front and back
model text
variant markings
age markings
quantity and pack count
dimension diagrams
visible warnings
```

### Evidence trace

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

### Outputs

```text
visual evidence facts
visual asset references
image-inspection actions
visual decision impact
```

### Requirement changes

Modify for new visual evidence types or reasoning policy.

### Primary modules

```text
src/product_evidence_harness/llm/vision_reasoner.py
src/product_evidence_harness/llm/agentic_browser.py
src/product_evidence_harness/business_judgement_artifact.py
```

---

## 10. Evidence ledger

### Purpose

Represent each material fact as atomic evidence that supports, contradicts or remains neutral toward product hypotheses.

### Evidence fields

```text
evidence_id
source_url
field
value
polarity
affected_hypothesis_ids
directness
source_reliability
extraction_confidence
hard_conflict
excerpt
```

### Outputs

```text
evidence_ledger
belief snapshots
evidence_ledger.jsonl
```

### Requirement changes

Modify when evidence weighting, polarity or provenance requirements change.

### Primary modules

```text
src/product_evidence_harness/belief/contracts.py
src/product_evidence_harness/belief/engine.py
src/product_evidence_harness/belief/artifacts.py
```

---

## 11. Hypothesis scoring and product resolution

### Purpose

Determine which product hypothesis is best supported.

### ResolutionStatus

```text
EXACT
PROBABLE
AMBIGUOUS
CONFLICTING
INSUFFICIENT_EVIDENCE
IN_PROGRESS
INITIALIZED
```

### Decision factors

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

### Outputs

```text
product_identification.resolution_status
product_identification.leading_hypothesis
selected_hypothesis_id
posterior probability
unresolved distinctions
```

### Requirement changes

Modify when scoring thresholds or terminal identity semantics change.

### Primary modules

```text
src/product_evidence_harness/belief/engine.py
src/product_evidence_harness/belief_runtime.py
src/product_evidence_harness/identity_verifier.py
```

---

## 12. Exact-product identity verification

### Purpose

Prevent sibling products, wrong variants, wrong forms or wrong pack configurations from being treated as the intended product.

### Verification dimensions

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

### Outputs

```text
identity status
conflicts
rejection reasons
verified identity claims
```

### Requirement changes

Modify for new product identity rules or critical identifiers.

### Primary modules

```text
src/product_evidence_harness/identity_verifier.py
src/product_evidence_harness/mandatory_url_identity_safety.py
src/product_evidence_harness/precision_selection_hardening.py
```

---

## 13. Requested-feature coverage

### Purpose

Assess whether available evidence supports the requested product facts.

### Important distinction

Requested-feature coverage is an evidence-completeness measure. It is not the complete definition of product identity.

### Outputs

```text
coverage
missing_features
conflicting_features
feature_assessments
```

### Requirement changes

Modify when feature criticality or multi-source evidence policy changes.

### Primary modules

```text
src/product_evidence_harness/feature_evidence.py
src/product_evidence_harness/strict_acceptance.py
src/product_evidence_harness/mandatory_url_policy.py
```

---

## 14. URL durability and usability

### Purpose

Determine whether an evidence source can be reused operationally.

### Source properties

```text
browser-openable
text-accessible
individual product page
non-expiring
not session-bound
not a search or category page
```

### Product-first rule

A failed URL check means the source is not qualified for that operational use. It does not automatically mean the product hypothesis is false.

### UI states

```text
VERIFIED
NOT VERIFIED
NOT ASSESSED
```

### Outputs

```text
primary_url_acceptance
url_delivery
source-quality metadata
```

### Requirement changes

Modify for new transient URL patterns or reuse requirements.

### Primary modules

```text
src/product_evidence_harness/strict_acceptance.py
src/product_evidence_harness/production_url_gate.py
src/product_evidence_harness/mandatory_url_policy.py
```

---

## 15. Source-authority selection

### Purpose

Choose the strongest qualified evidence source after product evidence has been evaluated.

### Authority order

```text
local official manufacturer
global official manufacturer
requested retailer
major market retailer
global exact-product source
marketplace last resort
```

### Product-first rule

Source authority ranks evidence locations. It does not create the product identity.

### Outputs

```text
primary_url
manufacturer_url
retailer_url
source_selection
```

### Requirement changes

Modify when source priority or marketplace policy changes.

### Primary modules

```text
src/product_evidence_harness/source_authority.py
src/product_evidence_harness/source_authority_runtime.py
src/product_evidence_harness/manufacturer_primary_runtime.py
```

---

## 16. Structured no-safe-URL outcome

### Purpose

Record that no reusable direct source URL was found within the bounded source-search policy.

```text
resolution_outcome.code=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
```

### Product-first rule

`NO_SAFE_DIRECT_PRODUCT_URL_FOUND` is a source-delivery outcome. It does not, by itself, mean `product_identification` is empty or failed.

### Outputs

```text
no_url_resolution.json
mandatory_url_delivery.json
suggested source follow-up actions
```

### Requirement changes

Modify when source-delivery escalation or bounded-search policy changes.

### Primary modules

```text
src/product_evidence_harness/structured_no_url_outcome.py
src/product_evidence_harness/no_url_business_review.py
src/product_evidence_harness/mandatory_url_policy.py
```

---

## 17. Business judgment sequence

### Purpose

Expose an auditable product-decision sequence without exposing hidden chain-of-thought.

```text
observable evidence
→ explicit rule
→ product judgment
→ next action
```

### Outputs

```text
business_judgement_review.md
business_judgement_review result object
```

### Requirement changes

Modify when review fields or equivalence labels change.

### Primary modules

```text
src/product_evidence_harness/business_judgement_artifact.py
src/product_evidence_harness/business_judgement_runtime.py
```

---

## 18. Per-job runtime controls

### Purpose

Vary evidence depth without mutating shared configuration.

### Execution profiles

```text
Latency Optimized
Standard
Coverage Optimized
```

### Outputs

```text
run_configuration.json
requested_runtime_options
effective_runtime_options
```

### Requirement changes

Modify when approved controls or ranges change.

### Primary modules

```text
src/product_evidence_harness/runtime_controls.py
src/product_evidence_harness/runtime_controls_runtime.py
```

---

## 19. Product Identification Platform UI

### Purpose

Present the identified product before supporting source evidence.

### Primary sections

```text
product identification summary
product identity
evidence basis
alternative hypotheses
source evidence
decision audit
artifacts
```

### Mandatory UI behavior

```text
EXACT product + no usable URL = product remains identified
missing source field = NOT ASSESSED, not FAIL
URL controls never appear as the primary verdict
```

### Outputs

The UI displays the standard result object and does not create an alternate product schema.

### Requirement changes

Modify when result presentation or review workflow changes.

### Primary modules

```text
apps/product_evidence_ui.py
docs/PRODUCT_EVIDENCE_UI.md
tests/test_product_evidence_ui.py
```

---

## 20. Batch execution

### Purpose

Process products with bounded parallelism while preserving one product artifact per row.

### Outputs

```text
batch_results.csv
batch_failures.csv
batch_artifact_index.csv
batch_run_summary.json
```

### Requirement changes

Modify for CSV schema, concurrency or retry behavior.

### Primary modules

```text
src/product_evidence_harness/batch_notebook_runtime.py
notebooks/02_batch_products.ipynb
```

---

## 21. Artifact diagnostics

### Purpose

Reconstruct a product identification from persisted evidence without rerunning paid search.

### Views

```text
Decision Map
Judgment Timeline
Candidates
Evidence
Artifacts
```

### Outputs

```text
artifact_diagnostics_interactive.html
artifact_diagnostic_report.md
artifact_diagnostic_workbook.xlsx
```

### Requirement changes

Modify when artifact schemas or diagnostic views change.

### Primary modules

```text
src/product_evidence_harness/artifact_diagnostics.py
src/product_evidence_harness/artifact_diagnostics_runtime.py
notebooks/03_artifact_diagnostics.ipynb
```

---

## 22. Artifact inventory

Primary identity artifacts:

```text
product_belief.json
product_understanding.md
belief_updates.md
evidence_ledger.jsonl
business_judgement_review.md
```

Supporting discovery and source artifacts:

```text
adaptive_search_trace.json
candidate_url_records.json
candidates.csv
primary_url_acceptance.json
mandatory_url_delivery.json
source_selection.json
```

Complete result and diagnostics:

```text
orchestrated_result.json
single_product_diagnostics.xlsx
artifact_diagnostics_interactive.html
artifact_diagnostic_report.md
artifact_diagnostic_workbook.xlsx
run_configuration.json
```

---

## 23. Change-impact index

| Requirement change | Primary change area |
|---|---|
| Add a product input field | Contracts, API, notebooks and UI |
| Add an identity dimension | Belief contracts, interpretation and evidence extraction |
| Change hypothesis generation | Belief engine |
| Change resolution thresholds | Belief scoring and identity verifier |
| Add a coded feature | Feature schema and feature evidence |
| Change search strategy | Adaptive search and query builder |
| Add browser evidence | Browser controller and agentic browser |
| Add visual evidence | Vision reasoner and evidence ledger |
| Change URL reuse policy | URL durability modules only |
| Change source priority | Source-authority modules only |
| Change UI hierarchy | Product Identification Platform UI |
| Change audit fields | Business judgment artifact builder |
| Change batch throughput | Batch runtime and worker configuration |
