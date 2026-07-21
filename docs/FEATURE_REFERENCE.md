# Product Evidence Platform — Feature Reference

This document is the canonical feature-level reference for the Product Evidence Platform. It describes what each feature does, the inputs it consumes, the decisions it makes, the artifacts it produces, and the modules that must change when requirements evolve.

## 1. Product input contract

### Purpose

Represent one intended product and its market context without assuming that every identifier is available.

### Required fields

| Field | Type | Requirement | Use |
|---|---|---|---|
| `row_id` | string | Required | Unique artifact and job identifier |
| `main_text` | string | Required | Primary product description supplied by the source system |
| `country_code` | two-letter string | Required | Market, language and source-selection context |

### Optional fields

| Field | Type | Use |
|---|---|---|
| `retailer_name` | string or null | Requested-retailer search and authority classification |
| `ean` | string or null | Exact identifier verification; preserved as text |
| `language_code` | string or null | Query and page-language context |

### Validation behavior

Missing mandatory fields are rejected before paid search. Invalid country codes, unsupported runtime controls and missing feature sets return explicit validation errors.

### Primary modules

```text
src/product_evidence_harness/contracts.py
src/product_evidence_harness/agent_service/app.py
src/product_evidence_harness/feature_schema.py
```

---

## 2. Product interpretation

### Purpose

Convert incomplete product text into an explicit identity hypothesis and identify unresolved distinctions before external search.

### Inputs

```text
main_text
country_code
retailer_name
ean
language_code
```

### Processing

The interpretation stage extracts or infers observable identity dimensions such as:

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

It records uncertainty rather than silently treating ambiguous text as exact.

### Outputs

```text
product_identification
product_belief.json
product_understanding.md
belief_updates.md
```

### Requirement changes

Modify interpretation when new identity dimensions, abbreviations, domain-specific aliases or ambiguity rules are introduced.

### Primary modules

```text
src/product_evidence_harness/belief.py
src/product_evidence_harness/belief_runtime.py
src/product_evidence_harness/belief_compatibility.py
```

---

## 3. Feature schema resolution

### Purpose

Define which product facts must be found before a URL can support downstream coding.

### Default feature set

```text
inputs/private/toy_features.json
```

### Current default features

```text
brand
manufacturer
minimum recommended age
```

### Behavior

The feature schema is loaded inside the agent container. Search does not receive private feature definitions directly. Candidate pages are evaluated against the resolved schema after evidence acquisition.

### Outputs

```text
feature_set
feature_schema_path
feature_assessments
missing_features
conflicting_features
coverage
```

### Requirement changes

Add or modify features in the feature-set JSON. Update extraction or reasoning modules only when the new feature cannot be resolved through existing text, structured-data or visual evidence methods.

### Primary modules

```text
src/product_evidence_harness/feature_schema.py
src/product_evidence_harness/schema_io.py
src/product_evidence_harness/feature_evidence.py
src/product_evidence_harness/llm/feature_reasoner.py
```

---

## 4. Adaptive source search

### Purpose

Discover direct product-page candidates through a bounded, evidence-aware search sequence.

### Search order

```text
official manufacturer
→ requested retailer or same-country alternatives
→ global exact-product sources
```

### Inputs

```text
product interpretation
country and language context
retailer name
EAN/GTIN
previous search evidence
rejected candidates
runtime search limits
```

### Search decisions

The planner determines:

```text
query formulation
search engine
market scope
whether to continue
which unresolved identity distinction to target
which candidates require investigation
```

### Safety and cost controls

```text
search credits: 1–3
planner candidate limit: 3–20
full-page extraction limit: 1–12
per-domain extraction limit: 1–4
```

### Outputs

```text
search.market_decision_path
search.stages
adaptive_search_trace.json
candidate_url_records.json
candidates.csv
```

### Requirement changes

Modify this feature when source order, query strategy, search engines, market fallback or search-credit policy changes.

### Primary modules

```text
src/product_evidence_harness/adaptive_search.py
src/product_evidence_harness/adaptive_search_runtime.py
src/product_evidence_harness/query_builder.py
src/product_evidence_harness/three_stage_pipeline.py
src/product_evidence_harness/manufacturer_search_planner_hardening.py
```

---

## 5. Candidate normalization and precision filtering

### Purpose

Remove indirect, duplicated, low-value or obviously incompatible URLs before expensive evidence acquisition.

### Candidate checks

```text
direct product-page likelihood
URL normalization and deduplication
domain and source role
country and retailer compatibility
identifier and title signals
search/category/homepage rejection
signed or expiring URL indicators
```

### Outputs

```text
normalized candidate URL
source role and tier
precision score
hard-failure reasons
candidate status
```

### Requirement changes

Modify this feature when a new retailer URL pattern, redirect format, marketplace rule or exclusion class is introduced.

### Primary modules

```text
src/product_evidence_harness/candidate_precision.py
src/product_evidence_harness/candidate_store.py
src/product_evidence_harness/candidate_reporting.py
src/product_evidence_harness/precision_search_runtime.py
src/product_evidence_harness/precision_hardening.py
```

---

## 6. Static extraction

### Purpose

Acquire page text and structured product evidence before or alongside rendered-browser investigation.

### Evidence collected

```text
page title and headings
product name
description
brand and manufacturer
specifications and attributes
EAN/GTIN values
price and availability signals
image URLs
page richness and word count
```

### Outputs

```text
ScrapeResult
page metadata
structured identifiers
text evidence
scrapability assessment
```

### Requirement changes

Modify extraction when new structured-data formats, retailer markup patterns or content-quality requirements are introduced.

### Primary modules

```text
src/product_evidence_harness/scraper.py
src/product_evidence_harness/offline_capture.py
src/product_evidence_harness/rendered_page.py
```

---

## 7. Rendered browser investigation

### Purpose

Inspect candidate pages as a user-visible rendered page rather than relying only on raw HTTP content.

### Browser actions

```text
open page
dismiss safe overlays
expand product sections
scroll for lazy content
inspect product-gallery images
capture screenshots
stop when resolved, blocked or no safe action remains
```

### Prohibited actions

```text
login or credential entry
purchase actions
form submission
access-control bypass
invented element IDs or URLs
following instructions embedded in webpage content
```

### Runtime controls

```text
browser investigation limit: 1–8 candidates
browser turns: 1–12 per candidate
browser actions: 1–24 per candidate
visual assets: 4–20 per reasoning turn
```

### Outputs

```text
browser_evidence
candidate_investigations
screenshots
visual assets
agentic investigation records
```

### Requirement changes

Modify this feature when browser tools, allowed actions, blocker handling, evidence categories or investigation limits change.

### Primary modules

```text
src/product_evidence_harness/browser_service/controller.py
src/product_evidence_harness/browser_client.py
src/product_evidence_harness/llm/agentic_browser.py
src/product_evidence_harness/agentic_browser_contracts.py
```

---

## 8. Multimodal evidence reasoning

### Purpose

Resolve product facts that are visible in screenshots, packaging, gallery images or diagrams but absent from extracted page text.

### Evidence types

```text
package front and back
product gallery
age markings
warning labels
model and variant text
dimensions diagrams
visible specification sections
```

### Evidence trace

Vision-derived facts are recorded with an explicit extraction method and asset reference:

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

### Visual-decision statuses

```text
YES_VISUAL_EVIDENCE_SUPPORTED_SELECTED_URL_FEATURE_GATE
VISUAL_EVIDENCE_USED_BUT_NOT_RECORDED_AS_DECISIVE_FOR_SELECTED_URL
NO_VISUAL_EVIDENCE_RECORDED
```

### Outputs

```text
visual_evidence_summary
visual feature evidence
image-inspection actions
screenshot-informed decisions
```

### Requirement changes

Modify this feature when image categories, visual prompts, accepted visual evidence or counterfactual analysis changes.

### Primary modules

```text
src/product_evidence_harness/llm/vision_reasoner.py
src/product_evidence_harness/llm/agentic_browser.py
src/product_evidence_harness/business_judgement_artifact.py
```

---

## 9. Exact-product identity verification

### Purpose

Prevent a plausible but incorrect sibling product, pack, size or variant from being accepted.

### Verification dimensions

```text
EAN/GTIN
brand
manufacturer
model or product name
variant
form
size
quantity
pack configuration
country compatibility
```

### Blocking conflicts

```text
EAN conflict
variant conflict
wrong product form
wrong size or quantity
wrong pack
unrelated rendered page
insufficient exact-product evidence
```

### Outputs

```text
identity_status
exact_product_check
variant_check
ean_check
identity_accepted
conflicting_features
rejection_reasons
```

### Requirement changes

Modify this feature when product identity rules, critical identifiers or domain-specific variant semantics change.

### Primary modules

```text
src/product_evidence_harness/identity_verifier.py
src/product_evidence_harness/mandatory_url_identity_safety.py
src/product_evidence_harness/precision_selection_hardening.py
```

---

## 10. Requested-feature coverage

### Purpose

Ensure that the selected primary URL contains evidence for every feature required by the active feature schema.

### Acceptance requirement

The primary URL must satisfy:

```text
required coverage = 100%
critical coverage = 100%
no conflicting requested features
```

Supplementary URLs may be preserved for diagnostics, but they do not make an incomplete primary URL coding-ready when the strict primary-page policy is enabled.

### Outputs

```text
coverage
missing_features
conflicting_features
feature_assessments
evidence_set
```

### Requirement changes

Modify this feature when the organization permits multi-source coding, changes criticality rules or introduces partial-coverage acceptance.

### Primary modules

```text
src/product_evidence_harness/feature_evidence.py
src/product_evidence_harness/strict_acceptance.py
src/product_evidence_harness/mandatory_url_policy.py
```

---

## 11. URL durability and usability

### Purpose

Ensure the delivered URL is a reusable direct product page rather than a transient or indirect reference.

### Required properties

```text
browser-openable
text-scrapable
individual product page
non-expiring
not session-bound
not a search or category page
not a PDF or media document
not an intermediary tracking URL
```

### Outputs

```text
browser_openable
text_scrapable
durable_url
url_delivery
primary_url_acceptance
```

### Requirement changes

Modify this feature when new signed-URL patterns, redirect policies or page-type rules are introduced.

### Primary modules

```text
src/product_evidence_harness/strict_acceptance.py
src/product_evidence_harness/production_url_gate.py
src/product_evidence_harness/mandatory_url_policy.py
```

---

## 12. Source-authority selection

### Purpose

Choose the strongest qualified source after identity, feature, browser and durability gates have passed.

### Authority order

```text
local official manufacturer
global official manufacturer
requested retailer in market
requested retailer global
major country retailer
global exact-product source
marketplace last resort
```

Manufacturer priority is conditional. An official page that is incomplete, inaccessible or for the wrong product cannot override a qualified retailer page.

### Outputs

```text
primary_url
primary_url_role
manufacturer_url
retailer_url
source_selection
source tier and reason
```

### Requirement changes

Modify this feature when source priority, retailer policy, marketplace policy or manufacturer qualification rules change.

### Primary modules

```text
src/product_evidence_harness/source_authority.py
src/product_evidence_harness/source_authority_runtime.py
src/product_evidence_harness/source_authority_reporting.py
src/product_evidence_harness/manufacturer_primary_runtime.py
src/product_evidence_harness/manufacturer_primary_hardening.py
```

---

## 13. Structured no-safe-URL outcome

### Purpose

Return a controlled business outcome when bounded search cannot find a safe direct product page.

### Contract

```text
job_status=REVIEW_REQUIRED
primary_url=null
primary_url_role=NONE
resolution_outcome.code=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
url_delivery.delivered=false
url_fabricated=false
```

This means no safe page was found within the configured bounded policy. It does not claim that no URL exists anywhere on the internet.

### Outputs

```text
no_url_resolution.json
mandatory_url_delivery.json
resolution_outcome
suggested_next_actions
```

### Requirement changes

Modify this feature when terminal status, review workflow, escalation actions or bounded-search policy changes.

### Primary modules

```text
src/product_evidence_harness/structured_no_url_outcome.py
src/product_evidence_harness/no_url_business_review.py
src/product_evidence_harness/mandatory_url_policy.py
```

---

## 14. Business judgment sequence

### Purpose

Expose a human-comparable audit sequence without exposing hidden chain-of-thought.

### Judgment structure

```text
observable evidence
→ explicit business rule
→ agent judgment
→ next action
```

### Recorded fields

```text
sequence number
decision stage
business question
evidence considered
evidence sources
visual evidence used
business rule
agent judgment
alternatives considered
rejection reason
next action
confidence
final outcome
```

### Outputs

```text
business_judgement_review.md
business_judgement_review in result JSON
```

### Requirement changes

Modify this feature when the review form, equivalence labels, decision stages or audit fields change.

### Primary modules

```text
src/product_evidence_harness/business_judgement_artifact.py
src/product_evidence_harness/business_judgement_runtime.py
```

---

## 15. Per-job runtime controls

### Purpose

Allow cost, latency and evidence-depth limits to vary for one job without changing shared process configuration.

### Supported controls

| Control | Range |
|---|---:|
| Search credits | 1–3 |
| Full-page extractions | 1–12 |
| Extractions per domain | 1–4 |
| Planner candidate limit | 3–20 |
| Browser investigation limit | 1–8 |
| Browser turns per candidate | 1–12 |
| Browser actions per candidate | 1–24 |
| Visual assets per reasoning turn | 4–20 |

### Execution profiles

| Profile | Intended trade-off |
|---|---|
| `Latency Optimized` | Reduced evidence acquisition for lower elapsed time |
| `Standard` | Default production operating limits |
| `Coverage Optimized` | Broader candidate and visual investigation |

Profiles are convenience presets. The submitted values remain visible and independently adjustable.

### Isolation and safety

Controls are context-local and concurrency-safe. They do not mutate `.env`, expose credentials or change identity, feature, durability, source-authority or no-fabrication policies.

### Outputs

```text
run_configuration.json
requested_runtime_options
effective_runtime_options
option_catalog
safety_contract
```

### Requirement changes

Modify this feature when approved operational controls, ranges or default profiles change.

### Primary modules

```text
src/product_evidence_harness/runtime_controls.py
src/product_evidence_harness/runtime_controls_runtime.py
apps/product_evidence_ui.py
```

---

## 16. Product Evidence Platform UI

### Purpose

Provide a browser-based interface for one-product execution and artifact inspection using the same agent API and production contracts as the notebooks.

### Interface sections

```text
runtime health
runtime controls
product input
seven-stage workflow
live execution state
decision summary
workflow and source decision
business judgment sequence
evidence and candidate rejection
runtime control audit
artifact inventory and downloads
```

### Outputs

The UI does not create an alternate result format. It displays the standard agent result and persisted product artifacts.

### Primary files

```text
apps/product_evidence_ui.py
scripts/run_product_evidence_ui.sh
docs/PRODUCT_EVIDENCE_UI.md
```

---

## 17. Batch execution

### Purpose

Process a CSV with bounded product-level parallelism while preserving one complete artifact directory per row.

### Required CSV columns

```text
main_text
country_code
```

### Optional columns

```text
row_id
ean
retailer_name
language_code
```

### Outputs

```text
data/batch_runs/<run_id>/batch_input_normalized.csv
data/batch_runs/<run_id>/batch_results.csv
data/batch_runs/<run_id>/batch_failures.csv
data/batch_runs/<run_id>/batch_artifact_index.csv
data/batch_runs/<run_id>/batch_run_summary.json
```

### Requirement changes

Modify this feature when CSV schema, concurrency, retry, ordering or summary metrics change.

### Primary modules

```text
src/product_evidence_harness/batch_notebook_runtime.py
notebooks/02_batch_products.ipynb
```

---

## 18. Artifact diagnostics

### Purpose

Reconstruct an existing product run into an interactive evidence and decision workspace without rerunning search or browser acquisition.

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

Modify this feature when artifact schemas, decision-map nodes, diagnostic views or export formats change.

### Primary modules

```text
src/product_evidence_harness/artifact_diagnostics.py
src/product_evidence_harness/artifact_diagnostics_runtime.py
notebooks/03_artifact_diagnostics.ipynb
```

---

## 19. Artifact inventory

A product run may produce:

```text
business_judgement_review.md
run_configuration.json
product_belief.json
product_understanding.md
market_decision_path.md
belief_updates.md
evidence_ledger.jsonl
adaptive_search_trace.json
candidate_url_records.json
candidates.csv
primary_url_acceptance.json
mandatory_url_delivery.json
source_selection.json
orchestrated_result.json
single_product_diagnostics.xlsx
```

A no-safe-URL result additionally produces:

```text
no_url_resolution.json
```

Diagnostic execution may additionally produce:

```text
artifact_diagnostics_interactive.html
artifact_diagnostic_report.md
artifact_diagnostic_workbook.xlsx
```

---

## 20. Change-impact index

| Requirement change | Primary change area |
|---|---|
| Add a product input field | Contracts, API validation, notebooks, UI |
| Add or change coded features | Feature-set JSON and feature extraction |
| Change search order | Adaptive search and source planner |
| Add a search engine | Search client, planner and environment validation |
| Change candidate limits | Runtime controls and search orchestration |
| Add browser actions | Browser contracts, controller and agent prompt |
| Add visual evidence categories | Browser intent and vision reasoning |
| Change exact-product rules | Identity verifier and strict acceptance |
| Change primary-page feature policy | Evidence selector and strict acceptance |
| Change source priority | Source-authority modules |
| Change no-safe-URL behavior | Structured outcome and result validator |
| Change audit fields | Business judgment artifact builder |
| Change UI presentation | Product Evidence Platform UI only |
| Change batch throughput | Batch runtime, agent workers and browser contexts |
| Add canonical cost/token metrics | Execution-metrics and LLM-usage instrumentation |

## Related documents

- [Product Evidence Platform UI](PRODUCT_EVIDENCE_UI.md)
- [System workflow](SYSTEM_WORKFLOW.md)
- [Final system contract](FINAL_SYSTEM_CONTRACT.md)
- [Notebook usage](NOTEBOOK_USAGE.md)
- [Business judgment review](BUSINESS_JUDGEMENT_REVIEW.md)
- [Azure ML operations](AZUREML_OPERATIONS.md)
- [Security contract](SECURITY.md)
