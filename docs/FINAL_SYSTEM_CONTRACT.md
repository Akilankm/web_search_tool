# Final Product Evidence System Contract

This is the canonical end-to-end production contract.

## Business objective

Given:

```text
MAIN_TEXT
COUNTRY_CODE
optional RETAILER_NAME
optional EAN/GTIN
optional LANGUAGE_CODE
```

return:

1. a real direct product-detail `primary_url`;
2. qualified `manufacturer_url` and `retailer_url` references;
3. an explicit manufacturer-versus-retailer `source_selection`;
4. a shareable `business_judgement_review.md` recording the observable sequence of business judgments.

## URL decision policy

```text
exact product, model, form, variant, size, quantity and pack
→ browser-openable rendered individual product page
→ text scrapability and information richness
→ requested feature completeness
→ durable non-expiring URL
→ official manufacturer authority
→ requested retailer / requested-country retailer
→ global exact-product source
→ marketplace last resort
```

Manufacturer authority is conditional. A retailer becomes primary when no manufacturer page passes every mandatory gate.

## Search policy

```text
manufacturer_primary
→ requested_retailer_country or country_alternative
→ global_fallback
```

A retailer found during `manufacturer_primary` is retained but cannot stop the search before the manufacturer opportunity is evaluated.

## Multimodal evidence policy

The system uses:

- submitted text and identifiers;
- static and rendered page text;
- browser screenshots;
- product and package images;
- structured page data;
- vision-derived requested-feature evidence;
- source authority and URL durability.

Vision evidence is explicit and auditable:

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

Images may materially complete the selected URL's feature gate. The system reports `UNKNOWN_NOT_COUNTERFACTUALLY_TESTED` for whether text alone would have passed unless a real text-only counterfactual is executed.

## Business judgment artifact contract

Every `COMPLETED` or `REVIEW_REQUIRED` run writes:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

The artifact contains:

```text
submitted input
final URL summary
chronological business questions
observable evidence considered
evidence sources
visual evidence use and impact
agent judgment
judgment status
alternatives considered and rejected
rejection reason
business rule applied
effect on next action
confidence
final outcome
human coder comparison form
```

Each step follows:

```text
observable evidence
→ explicit business rule
→ business judgment
→ resulting action
```

It does not expose hidden chain-of-thought.

## Human validation policy

The human coder receives the original input and `business_judgement_review.md`, reviews independently, and classifies:

- `IDENTICAL`;
- `PARTIALLY IDENTICAL`; or
- `NOT IDENTICAL`.

The reviewer records the first divergent step, human judgment, missed or overweighted evidence, image interpretation and proposed system change.

Behavioral validation requires sequence equivalence, not merely the same final URL.

## Stable response schema

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
```

## Runtime contract

Current:

```text
belief-url-resolution-v6-business-judgement-review
```

Previous migration version:

```text
belief-url-resolution-v5-manufacturer-primary
```

Required capabilities:

```text
belief_driven_product_resolution=true
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
mandatory_review_url_delivery=true
deterministic_browser_fallback_on_llm_error=true
notebook_self_healing_runtime=true
compatibility_patches_applied=true
```

## Notebook contract

Only:

```text
notebooks/01_run_product_evidence.ipynb
```

The first post-run view must expose:

```text
business_judgement_steps_df
visual_evidence_summary_df
business_judgement_review.md path
```

Engineering diagnostics follow below the human comparison view.

## Artifact contract

```text
data/artifacts/<row_id>/
├── business_judgement_review.md
├── product_belief.json
├── product_understanding.md
├── market_decision_path.md
├── belief_updates.md
├── evidence_ledger.jsonl
├── adaptive_search_trace.json
├── candidate_url_records.json
├── candidates.csv
├── primary_url_acceptance.json
├── mandatory_url_delivery.json
├── source_selection.json
├── orchestrated_result.json
└── single_product_diagnostics.xlsx
```

## Terminal outcomes

| Outcome | Contract |
|---|---|
| `COMPLETED` | Strict URL gates passed and the business judgment artifact was written |
| `REVIEW_REQUIRED` | A real direct review URL and business judgment artifact were delivered |
| `FAILED` | No safe direct product URL was found or execution failed |

The workflow never reports success with an empty product URL.

## Operational acceptance

A release is acceptable only when CI validates:

- Python source compilation;
- notebook JSON and every code cell;
- Docker Compose and Azure ML bootstrap;
- runtime capabilities and result schema;
- manufacturer-primary and retailer-fallback behavior;
- multimodal evidence reporting;
- business judgment Markdown generation;
- human comparison form and notebook visibility;
- full historical unit suite on Python 3.10 and 3.11.

## Leadership communication

The speaker-ready explanation of the business problem, workflow, assumptions, constraints, artifacts, selection policy, performance model, token/cost boundaries, KPI framework and change-impact areas is maintained in:

```text
docs/MANAGEMENT_DEMO_GUIDE.md
```

See [Management and leadership demo guide](MANAGEMENT_DEMO_GUIDE.md), [Business judgment review](BUSINESS_JUDGEMENT_REVIEW.md), [Notebook usage](NOTEBOOK_USAGE.md), and [Azure ML operations](AZUREML_OPERATIONS.md).
