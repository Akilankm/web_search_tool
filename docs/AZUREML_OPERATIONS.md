# Azure ML Operations Runbook

## Setup

```bash
git checkout master
git pull origin master
cp .env.example .env
# Add real SerpAPI and enterprise LLM values.
./scripts/azureml_startup.sh --clean-build
```

## Supported notebooks

```text
notebooks/01_single_product.ipynb
notebooks/02_batch_products.ipynb
notebooks/03_artifact_diagnostics.ipynb
```

| Notebook | Use | Runtime requirement |
|---|---|---:|
| `01_single_product.ipynb` | One product, URL/no-URL outcome and full judgment trace | Agent and browser healthy |
| `02_batch_products.ipynb` | CSV batch with bounded parallel execution | Agent and browser healthy |
| `03_artifact_diagnostics.ipynb` | Interactive exploration of an existing artifact | Offline |

## Runtime contract

```text
belief-url-resolution-v7-structured-no-url-review
```

Required health response includes:

```text
status=healthy
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
structured_no_url_review_outcome=true
compatibility_patches_applied=true
agent_entrypoint=src.product_evidence_harness.agent_service.app:app
serpapi_request_limit=3
agentic_browser_contract_enforced=true
browser_service.agentic_tools=true
```

The single and batch notebooks reject stale or incomplete agents before paid search.

## Product workflow

```text
MAIN_TEXT + COUNTRY_CODE
→ offline interpretation
→ manufacturer_primary
→ requested_retailer_country or country_alternative
→ global_fallback
→ browser and multimodal evidence
→ strict identity, feature, scrapability and durability gates
→ manufacturer-first source selection
→ direct URL or structured no-safe-URL review outcome
→ business_judgement_review.md
```

## Single-product operations

Open:

```text
notebooks/01_single_product.ipynb
```

Use a unique `row_id`. The notebook returns normally for both URL-backed and controlled no-safe-URL business outcomes.

No-safe-URL result:

```text
job_status=REVIEW_REQUIRED
primary_url=null
resolution_outcome.code=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
url_delivery.delivered=false
```

The notebook then loads the artifact and displays the decision trace, reason, search credits and suggested next actions.

Artifacts:

```text
data/artifacts/<row_id>/business_judgement_review.md
data/artifacts/<row_id>/no_url_resolution.json   # no-safe-URL only
```

## Batch operations

Open:

```text
notebooks/02_batch_products.ipynb
```

Required CSV columns:

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

Concurrency defaults to:

```text
min(AGENT_WORKERS, BROWSER_MAX_CONTEXTS, 8)
```

Default controls:

```env
AGENT_WORKERS=2
BROWSER_MAX_CONTEXTS=3
```

Increase only after load testing.

Batch outputs:

```text
data/batch_runs/<run_id>/
├── batch_input_normalized.csv
├── batch_results.csv
├── batch_failures.csv
├── batch_artifact_index.csv
└── batch_run_summary.json
```

A no-safe-URL row remains `REVIEW_REQUIRED` in `batch_results.csv`. It is not a technical failure and is not placed in `batch_failures.csv`. Genuine runtime failures remain isolated per row.

## Artifact diagnostic operations

Open:

```text
notebooks/03_artifact_diagnostics.ipynb
```

Set `ARTIFACT_PATH` to a product directory or any file inside it. The notebook is offline and writes:

```text
artifact_diagnostics_interactive.html
artifact_diagnostic_report.md
artifact_diagnostic_workbook.xlsx
```

The interactive HTML is the primary comprehension surface and includes Decision Map, Judgment Timeline, Candidates, Evidence and Artifacts tabs.

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

No-safe-URL outcomes additionally include:

```text
no_url_resolution.json
```

## Manual verification

```bash
docker compose ps
curl -sS http://127.0.0.1:8788/health | python -m json.tool
cat data/runtime/stack_health.json
```

Expected v7 values:

```text
runtime_contract_version=belief-url-resolution-v7-structured-no-url-review
structured_no_url_review_outcome=true
```

## Recovery

```bash
./scripts/azureml_startup.sh --clean-build
```

Use a clean rebuild after pulling v7 runtime changes, for `STALE_AGENT_IMAGE`, or for missing capabilities. Recovery occurs before `submit_product` and consumes no search credit.

## Visual evidence controls

```env
PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_REQUIRE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_ENABLE_VISION_REASONING=true
PRODUCT_HARNESS_AGENTIC_MAX_IMAGES=8
PRODUCT_HARNESS_AGENTIC_IMAGE_DETAIL=high
```

Images can support exact-product investigation and feature coverage. Artifacts record whether visual evidence was decisive, merely used or absent.

## Result validation

A URL-backed terminal result must have a direct URL and `url_delivery.delivered=true`.

A blank URL is accepted only with the complete structured no-safe-URL result:

```text
job_status=REVIEW_REQUIRED
resolution_outcome.code=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
url_delivery.status=NO_SAFE_DIRECT_PRODUCT_URL_FOUND_AFTER_BOUNDED_SEARCH
```

Any other blank or contradictory result raises `INCONSISTENT_URL_DELIVERY_RESULT`.

## Validation commands

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
