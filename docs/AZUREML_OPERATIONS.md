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
belief-url-resolution-v8-leadership-demo
```

Required health response includes:

```text
status=healthy
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
structured_no_url_review_outcome=true
leadership_demo_runtime_options=true
compatibility_patches_applied=true
agent_entrypoint=src.product_evidence_harness.agent_service.app:app
serpapi_request_limit=3
agentic_browser_contract_enforced=true
browser_service.agentic_tools=true
```

The Streamlit app, single-product notebook and batch notebook reject stale or incomplete agents before paid search.

## Supported surfaces

| Surface | Use | Runtime requirement |
|---|---|---:|
| `apps/leadership_demo.py` | Management and leadership demonstration | Agent and browser healthy |
| `notebooks/01_single_product.ipynb` | One-product analytical review | Agent and browser healthy |
| `notebooks/02_batch_products.ipynb` | CSV batch with bounded parallel execution | Agent and browser healthy |
| `notebooks/03_artifact_diagnostics.ipynb` | Interactive exploration of an existing artifact | Offline |

## Leadership Streamlit operations

Install the host-side UI dependency set once:

```bash
bash scripts/run_leadership_demo.sh --install
```

Later launches:

```bash
bash scripts/run_leadership_demo.sh
```

Defaults:

```text
Agent API:  http://127.0.0.1:8788
Streamlit:  http://0.0.0.0:8501
```

In Azure ML VS Code:

1. Keep the Streamlit terminal running.
2. Open the **Ports** panel.
3. Forward port `8501`.
4. Keep visibility **Private**.
5. Open the forwarded browser address.

Alternate port:

```bash
bash scripts/run_leadership_demo.sh --port 8502
```

The app submits work through the same Product Evidence Agent API as the notebooks. It does not edit `.env`, restart containers or implement separate search logic.

### Per-job budget contract

The UI can change only bounded operational limits:

```text
SerpAPI credits:                 1–3
full page scrapes:               1–12
scrapes per domain:              1–4
planner candidate context:       3–20
browser-investigated candidates: 1–8
browser turns per candidate:     1–12
browser actions per candidate:   1–24
images in visual reasoning:      4–20
```

Each run writes:

```text
data/artifacts/<row_id>/run_configuration.json
```

Identity gates, requested-feature completeness, EAN-conflict policy, URL durability, manufacturer-first authority and the no-fabrication rule are not UI controls.

## Product workflow

```text
MAIN_TEXT + COUNTRY_CODE
→ identity interpretation and uncertainty
→ manufacturer-first adaptive search
→ retailer / country / global fallback
→ candidate precision and full-page extraction
→ rendered browser and multimodal evidence
→ strict identity, feature, scrapability and durability gates
→ manufacturer-first source selection
→ direct URL or structured no-safe-URL review outcome
→ business_judgement_review.md + run_configuration.json
```

## Single-product notebook

```text
notebooks/01_single_product.ipynb
```

Use a unique `row_id`. The notebook returns normally for URL-backed and controlled no-safe-URL outcomes.

## Batch notebook

```text
notebooks/02_batch_products.ipynb
```

Required columns:

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

Batch outputs:

```text
data/batch_runs/<run_id>/
├── batch_input_normalized.csv
├── batch_results.csv
├── batch_failures.csv
├── batch_artifact_index.csv
└── batch_run_summary.json
```

A no-safe-URL row remains `REVIEW_REQUIRED` in `batch_results.csv`. It is not placed in `batch_failures.csv`.

## Artifact diagnostics

```text
notebooks/03_artifact_diagnostics.ipynb
```

The notebook is offline and produces:

```text
artifact_diagnostics_interactive.html
artifact_diagnostic_report.md
artifact_diagnostic_workbook.xlsx
```

## Product artifacts

```text
data/artifacts/<row_id>/
├── business_judgement_review.md
├── run_configuration.json
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

No-safe-URL outcomes additionally include `no_url_resolution.json`.

## Terminal-result validation

A URL-backed terminal result must have a direct URL and `url_delivery.delivered=true`.

A blank URL is accepted only with:

```text
job_status=REVIEW_REQUIRED
resolution_outcome.code=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
url_delivery.status=NO_SAFE_DIRECT_PRODUCT_URL_FOUND_AFTER_BOUNDED_SEARCH
```

Any other blank or contradictory result raises `INCONSISTENT_URL_DELIVERY_RESULT`.

## Manual verification

```bash
docker compose ps
curl -sS http://127.0.0.1:8788/health | python -m json.tool
cat data/runtime/stack_health.json
```

Expected values:

```text
runtime_contract_version=belief-url-resolution-v8-leadership-demo
leadership_demo_runtime_options=true
structured_no_url_review_outcome=true
```

## Recovery

```bash
./scripts/azureml_startup.sh --clean-build
```

Use a clean rebuild after pulling runtime changes, for `STALE_AGENT_IMAGE`, or for missing capabilities. Recovery happens before product submission and consumes no search credit.

## Validation commands

```bash
bash -n scripts/azureml_startup.sh
bash -n scripts/run_leadership_demo.sh
python -m compileall -q src scripts apps
PYTHONPATH=src pytest -q
docker compose config --quiet
```
