# Azure ML Operations Runbook

## Setup

```bash
git checkout master
git pull origin master
cp .env.example .env
# Add real SerpAPI and enterprise LLM values.
./scripts/azureml_startup.sh --clean-build
```

## Choose the notebook

```text
notebooks/01_single_product.ipynb
notebooks/02_batch_products.ipynb
notebooks/03_artifact_diagnostics.ipynb
```

| Notebook | Use | Runtime requirement |
|---|---|---:|
| `01_single_product.ipynb` | One product, final URL and full judgment trace | Agent and browser must be healthy |
| `02_batch_products.ipynb` | CSV batch with bounded parallel products | Agent and browser must be healthy |
| `03_artifact_diagnostics.ipynb` | Existing artifact mindmap and decision diagnostics | Offline; stack not required |

## Runtime contract

```text
belief-url-resolution-v6-business-judgement-review
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

The single and batch notebooks reject a stale or incomplete agent before product submission and before paid search.

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

## Single-product operations

Open:

```text
notebooks/01_single_product.ipynb
```

Use a unique `row_id`. The notebook displays `final_decision_df`, `business_judgement_steps_df` and `visual_evidence_summary_df` before candidate-level engineering diagnostics.

Outputs are written to:

```text
data/artifacts/<row_id>/
```

The primary human-review file is:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

## Batch operations

Open:

```text
notebooks/02_batch_products.ipynb
```

CSV required columns:

```text
main_text
country_code
```

Optional:

```text
row_id
ean
retailer_name
language_code
```

The notebook validates the complete CSV before search. Product-level concurrency defaults to the safe minimum of `AGENT_WORKERS` and `BROWSER_MAX_CONTEXTS`.

Default capacity controls:

```env
AGENT_WORKERS=2
BROWSER_MAX_CONTEXTS=3
```

Increase only after load testing. A larger notebook thread pool does not create additional API or browser capacity by itself.

Batch outputs:

```text
data/batch_runs/<run_id>/
├── batch_input_normalized.csv
├── batch_results.csv
├── batch_failures.csv
├── batch_artifact_index.csv
└── batch_run_summary.json
```

Each product still writes its complete artifact under `data/artifacts/<row_id>/`. One row failure does not stop the remaining products.

## Artifact diagnostic operations

Open:

```text
notebooks/03_artifact_diagnostics.ipynb
```

Set `ARTIFACT_PATH` to the product directory or any file inside it. The notebook does not call the agent and can be used after the runtime has stopped.

It writes:

```text
artifact_diagnostic_report.md
artifact_diagnostic_workbook.xlsx
```

into the selected product artifact directory.

## Product artifact contract

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

Use this for `STALE_AGENT_IMAGE`, missing runtime capabilities or after pulling runtime changes. Recovery occurs before `submit_product` and consumes no search credit.

Notebook/documentation-only changes do not require a rebuild when the running runtime contract is unchanged.

## Visual evidence controls

```env
PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_REQUIRE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_ENABLE_VISION_REASONING=true
PRODUCT_HARNESS_AGENTIC_MAX_IMAGES=8
PRODUCT_HARNESS_AGENTIC_IMAGE_DETAIL=high
```

Images can support exact-product investigation and feature coverage. The artifacts record whether visual evidence was decisive, merely used, or not recorded.

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
python - <<'PY'
import ast, json
from pathlib import Path
for path in sorted(Path('notebooks').glob('*.ipynb')):
    notebook = json.loads(path.read_text())
    for index, cell in enumerate(notebook['cells']):
        if cell.get('cell_type') == 'code':
            ast.parse(''.join(cell.get('source', [])), filename=f'{path.name}:{index}')
PY
PYTHONPATH=src pytest -q
docker compose config --quiet
```
