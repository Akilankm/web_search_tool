# Azure ML Operations Runbook

## Supported flow

```bash
git checkout master
git pull origin master
cp .env.example .env
# Add real SerpAPI and enterprise LLM credentials.
./scripts/azureml_startup.sh --clean-build
```

Open only:

```text
notebooks/01_run_product_evidence.ipynb
```

## Runtime contract

Current:

```text
belief-url-resolution-v6-business-judgement-review
```

Previous migration contract:

```text
belief-url-resolution-v5-manufacturer-primary
```

Required health response:

```text
status=healthy
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
compatibility_patches_applied=true
agent_entrypoint=src.product_evidence_harness.agent_service.app:app
serpapi_request_limit=3
agentic_browser_contract_enforced=true
browser_service.agentic_tools=true
```

The notebook rejects a stale or incomplete agent before product submission and before any paid SerpAPI call.

## Product workflow

```text
MAIN_TEXT + COUNTRY_CODE
→ offline interpretation
→ manufacturer_primary
→ requested_retailer_country or country_alternative
→ global_fallback
→ browser and multimodal evidence
→ strict identity, feature, scrapability and durability gates
→ manufacturer-first source_selection
→ primary_url + manufacturer_url + retailer_url
→ business_judgement_review.md
```

## Human review output

Every completed or review-required run writes:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

This is the artifact to share with a human coder. It contains the submitted input, chronological business judgments, visual-evidence impact and the `IDENTICAL / PARTIALLY IDENTICAL / NOT IDENTICAL` response form.

The notebook displays:

```text
business_judgement_steps_df
visual_evidence_summary_df
```

The workbook includes:

```text
business_judgments
visual_evidence_impact
source_selection
```

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

## Manual verification

```bash
docker compose ps
curl -sS http://127.0.0.1:8788/health | python -m json.tool
cat data/runtime/stack_health.json
```

## Recovery

```bash
./scripts/azureml_startup.sh --clean-build
```

Use this for `STALE_AGENT_IMAGE`, a missing `business_judgement_review_artifact` capability, or after pulling runtime/notebook changes. Recovery happens before `submit_product` and therefore consumes no search credit.

## Visual evidence controls

```env
PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_REQUIRE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_ENABLE_VISION_REASONING=true
PRODUCT_HARNESS_AGENTIC_MAX_IMAGES=8
PRODUCT_HARNESS_AGENTIC_IMAGE_DETAIL=high
```

Images can support exact-product investigation and requested-feature coverage. The final artifact records whether image evidence was decisive, merely used, or not recorded; it does not claim a text-only counterfactual without testing one.

## Final result schema

```text
primary_url
primary_url_role
manufacturer_url
retailer_url
source_selection
primary_url_acceptance
url_delivery
product_identification
search.market_decision_path
business_judgement_review
```

## Validation

```bash
bash -n scripts/azureml_startup.sh
python -m compileall -q src scripts
python -m json.tool notebooks/01_run_product_evidence.ipynb >/dev/null
PYTHONPATH=src pytest -q
docker compose config --quiet
```
