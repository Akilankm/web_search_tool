# Azure ML Operations Runbook

## Setup

```bash
git checkout master
git pull origin master
cp .env.example .env
# Add real SerpAPI and enterprise LLM values.
./scripts/azureml_startup.sh --clean-build
```

## Runtime contract

```text
belief-url-resolution-v9-product-evidence-ui
```

Required health response:

```text
status=healthy
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
structured_no_url_review_outcome=true
per_job_runtime_controls=true
compatibility_patches_applied=true
agent_entrypoint=src.product_evidence_harness.agent_service.app:app
browser_service.agentic_tools=true
```

The UI, single-product notebook and batch notebook reject incompatible agents before paid search.

## Supported execution surfaces

| Surface | Use | Agent required |
|---|---|---:|
| `apps/product_evidence_ui.py` | Browser-based single-product execution and review | Yes |
| `notebooks/01_single_product.ipynb` | One-product analytical review | Yes |
| `notebooks/02_batch_products.ipynb` | CSV batch with bounded parallel execution | Yes |
| `notebooks/03_artifact_diagnostics.ipynb` | Interactive analysis of an existing artifact | No |

## Product Evidence Platform UI

Install once:

```bash
bash scripts/run_product_evidence_ui.sh --install
```

Subsequent launches:

```bash
bash scripts/run_product_evidence_ui.sh
```

Defaults:

```text
Agent API: http://127.0.0.1:8788
UI:        http://0.0.0.0:8501
```

In Azure ML VS Code:

1. Keep the UI terminal running.
2. Open the **Ports** panel.
3. Forward port `8501`.
4. Keep visibility **Private**.
5. Open the forwarded browser address.

Alternative port:

```bash
bash scripts/run_product_evidence_ui.sh --port 8502
```

## Per-job runtime controls

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

Each run writes:

```text
data/artifacts/<row_id>/run_configuration.json
```

Runtime controls are isolated to one job. They cannot change credentials, identity gates, requested-feature completeness, EAN-conflict policy, URL durability, source-authority order or no-fabrication behavior.

## Product workflow

```text
MAIN_TEXT + COUNTRY_CODE
→ product interpretation
→ manufacturer, market and global search
→ candidate normalization and extraction
→ rendered browser and visual evidence
→ identity, feature and durability verification
→ source-authority selection
→ URL result or structured no-safe-URL outcome
→ decision and artifact generation
```

## Single-product notebook

```text
notebooks/01_single_product.ipynb
```

Use a unique `row_id`. URL-backed and controlled no-safe-URL results return normally and remain available for diagnostics.

## Batch notebook

```text
notebooks/02_batch_products.ipynb
```

Required CSV columns:

```text
main_text
country_code
```

Optional columns:

```text
row_id
ean
retailer_name
language_code
```

Outputs:

```text
data/batch_runs/<run_id>/
├── batch_input_normalized.csv
├── batch_results.csv
├── batch_failures.csv
├── batch_artifact_index.csv
└── batch_run_summary.json
```

A no-safe-URL row remains `REVIEW_REQUIRED` in `batch_results.csv`; it is not a technical failure.

## Artifact diagnostics

```text
notebooks/03_artifact_diagnostics.ipynb
```

Offline outputs:

```text
artifact_diagnostics_interactive.html
artifact_diagnostic_report.md
artifact_diagnostic_workbook.xlsx
```

## Manual verification

```bash
docker compose ps
curl -sS http://127.0.0.1:8788/health | python -m json.tool
cat data/runtime/stack_health.json
```

Expected:

```text
runtime_contract_version=belief-url-resolution-v9-product-evidence-ui
per_job_runtime_controls=true
structured_no_url_review_outcome=true
```

## Recovery

```bash
./scripts/azureml_startup.sh --clean-build
```

Use a clean rebuild after runtime-contract changes, `STALE_AGENT_IMAGE`, or missing capabilities.

## Validation commands

```bash
bash -n scripts/azureml_startup.sh
bash -n scripts/run_product_evidence_ui.sh
python -m compileall -q src scripts apps
PYTHONPATH=src pytest -q
docker compose config --quiet
```

## Related documents

- [Feature reference](FEATURE_REFERENCE.md)
- [System workflow](SYSTEM_WORKFLOW.md)
- [Product Evidence Platform UI](PRODUCT_EVIDENCE_UI.md)
- [Final system contract](FINAL_SYSTEM_CONTRACT.md)
