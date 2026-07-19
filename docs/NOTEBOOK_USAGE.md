# Notebook Usage and Human Validation Contract

Use only:

```text
notebooks/01_run_product_evidence.ipynb
```

The notebook runs one product and presents the human-comparable business judgment sequence before engineering diagnostics.

## Azure ML setup

```bash
git checkout master
git pull origin master
cp .env.example .env
# Add real SerpAPI and enterprise LLM values.
./scripts/azureml_startup.sh --clean-build
```

## Runtime readiness

Current contract:

```text
belief-url-resolution-v6-business-judgement-review
```

Previous contract for migration reference:

```text
belief-url-resolution-v5-manufacturer-primary
```

Required health capabilities:

```text
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
```

The readiness cell validates these before any paid SerpAPI call and self-heals stale Docker images when enabled.

## Input

```python
FEATURE_SET = 'toy_features'
RUN_SINGLE_PRODUCT = False
product = {
    'row_id': 'TEST-001',
    'main_text': 'Vendor product main text',
    'country_code': 'CZ',
    'retailer_name': None,
    'ean': None,
    'language_code': None,
}
```

`main_text` and `country_code` are mandatory. EAN/GTIN remains text.

## Resolution route

```text
deterministic parsing
→ no-web product interpretation
→ competing hypotheses and uncertainties
→ manufacturer_primary
→ requested_retailer_country or country_alternative
→ global_fallback
→ rendered browser and multimodal evidence
→ strict identity, feature, scrapability and durability gates
→ manufacturer-first authority ranking
→ primary_url + manufacturer_url + retailer_url + source_selection
→ business_judgement_review.md
```

## Primary human review view

After the run, review these first:

| DataFrame / artifact | Purpose |
|---|---|
| `business_judgement_steps_df` | Chronological business questions, evidence, judgments, rules and next actions |
| `visual_evidence_summary_df` | Whether screenshots/images were available, inspected and materially supported the selected URL |
| `business_judgement_review.md` | Shareable document containing the sequence and human comparison form |

The Markdown file is stored at:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

Give the human coder the submitted input and this Markdown file. Ask for:

- `IDENTICAL`;
- `PARTIALLY IDENTICAL`; or
- `NOT IDENTICAL`.

The reviewer records the first divergent step, their preferred judgment, missed or overweighted evidence, image interpretation and recommended system change.

## Visual evidence

The workflow uses rendered screenshots and product/gallery images. Vision-derived feature evidence is identified by:

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

The artifact reports:

```text
image_influenced_final_decision
text_alone_would_have_passed
features_resolved_visually
selected_url_features_resolved_visually
```

`text_alone_would_have_passed` remains `UNKNOWN_NOT_COUNTERFACTUALLY_TESTED` unless an explicit text-only comparison is run.

## Stable result schema

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

## Engineering diagnostics

Use these only after reviewing the business judgment sequence:

```text
product_identification_df
hypotheses_df
uncertainties_df
belief_updates_df
evidence_ledger_df
source_selection_df
url_delivery_df
source_hierarchy_df
search_actions_df
search_engine_summary_df
search_handles_df
search_decision_rca_df
results_df
agentic_df
feature_evidence_df
selection_rca_df
```

The notebook still exposes `url_delivery_df`, `source_selection_df`, `search_actions_df`, `manufacturer_primary`, `manufacturer_url`, `retailer_url`, `source_selection`, and `MANDATORY_PRODUCT_URL_NOT_FOUND` for contract validation.

## Workbook

`single_product_diagnostics.xlsx` includes:

```text
business_judgments
visual_evidence_impact
platform_readiness
product_identification
product_hypotheses
product_uncertainties
belief_updates
evidence_ledger
source_selection
url_delivery
source_hierarchy
source_tier_summary
candidate and browser diagnostics
feature evidence
final selection RCA
```

## Artifact set

```text
business_judgement_review.md
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

The behavioral acceptance criterion is sequence equivalence, not only final URL equality.
