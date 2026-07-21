# Product Evidence Platform

A production-oriented, multimodal system for exact-product identification, evidence acquisition and governed product-page URL resolution.

Given `MAIN_TEXT`, `COUNTRY_CODE`, and optional `RETAILER_NAME`, `EAN/GTIN`, and `LANGUAGE_CODE`, the platform identifies the intended product, evaluates direct product-page candidates, returns the strongest qualified URL when one can be safely established, and preserves an auditable sequence of evidence, rules, judgments and actions.

## Core contract

```text
product interpretation
→ manufacturer, market and global search
→ candidate normalization
→ static and rendered evidence acquisition
→ text and visual feature resolution
→ exact-product verification
→ requested-feature verification
→ URL durability verification
→ source-authority selection
→ final result and artifacts
```

The platform separates **product truth** from **commercial reference**:

- an exact, complete and durable manufacturer page is preferred for product truth;
- a qualified retailer page is retained for market, pack, price and availability context;
- a retailer or global source may become `primary_url` when no manufacturer page passes every mandatory gate;
- when no safe direct page is found within the bounded policy, the system returns `REVIEW_REQUIRED` and never fabricates a URL.

## Runtime contract

```text
belief-url-resolution-v9-product-evidence-ui
```

Required capabilities:

```text
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
structured_no_url_review_outcome=true
per_job_runtime_controls=true
```

## Product Evidence Platform UI

Application:

```text
apps/product_evidence_ui.py
```

Start the agent and UI:

```bash
./scripts/azureml_startup.sh --clean-build
bash scripts/run_product_evidence_ui.sh --install   # first use
bash scripts/run_product_evidence_ui.sh             # subsequent use
```

Forward port `8501` privately through the VS Code **Ports** panel.

The UI presents:

```text
runtime health
product input
per-job runtime controls
seven-stage workflow
live execution status
strict acceptance gates
source-selection decision
business judgment sequence
text and visual evidence
artifact inventory and downloads
```

Execution profiles:

| Profile | Operating intent |
|---|---|
| `Latency Optimized` | Lower evidence-acquisition limits for lower elapsed time |
| `Standard` | Default production operating limits |
| `Coverage Optimized` | Broader candidate, browser and visual investigation |

Profiles are convenience presets. Every submitted value remains independently adjustable, validated and recorded in `run_configuration.json`.

## Supported notebooks

| Notebook | Purpose | Agent required |
|---|---|---:|
| `notebooks/01_single_product.ipynb` | Execute and inspect one product-resolution run | Yes |
| `notebooks/02_batch_products.ipynb` | Process a CSV with bounded product-level parallelism | Yes |
| `notebooks/03_artifact_diagnostics.ipynb` | Explore an existing artifact through an interactive diagnostic workspace | No |

## Input contract

Required:

```text
row_id
main_text
country_code
feature_set
```

Optional:

```text
retailer_name
ean
language_code
runtime_options
```

Default feature set:

```text
inputs/private/toy_features.json
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

Controls are context-local and concurrency-safe. They cannot change credentials, exact-product identity rules, requested-feature completeness, URL durability, source-authority policy or no-fabrication behavior.

## Result schema

Every `COMPLETED` or `REVIEW_REQUIRED` result contains:

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

A controlled no-safe-URL result additionally contains:

```text
resolution_outcome.code=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
url_delivery.status=NO_SAFE_DIRECT_PRODUCT_URL_FOUND_AFTER_BOUNDED_SEARCH
```

## Terminal outcomes

| Outcome | Meaning |
|---|---|
| `COMPLETED` | A direct product page passed identity, feature, browser, scrapability, durability and authority gates |
| `REVIEW_REQUIRED` with URL | A real direct reference was delivered but one or more judgments require confirmation |
| `REVIEW_REQUIRED` without URL | No safe direct page was found within the bounded policy; trace preserved and no URL fabricated |
| `FAILED` | Software, configuration, dependency or result-contract failure |

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

## Azure ML setup

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool
cp .env.example .env
# Add real SerpAPI and enterprise LLM values.
./scripts/azureml_startup.sh --clean-build
```

## Validation

```bash
bash -n scripts/azureml_startup.sh
bash -n scripts/run_product_evidence_ui.sh
python -m compileall -q src scripts apps
python -m json.tool inputs/private/toy_features.json >/dev/null
PYTHONPATH=src pytest -q
docker compose config --quiet
```

CI validates Python 3.10 and 3.11, all notebooks, the UI, runtime-control isolation, Docker Compose, structured no-safe-URL behavior, exact-product selection and the complete regression suite.

## Documentation

- [Feature reference](docs/FEATURE_REFERENCE.md)
- [System workflow](docs/SYSTEM_WORKFLOW.md)
- [Product Evidence Platform UI](docs/PRODUCT_EVIDENCE_UI.md)
- [Final system contract](docs/FINAL_SYSTEM_CONTRACT.md)
- [Notebook usage](docs/NOTEBOOK_USAGE.md)
- [Business judgment review](docs/BUSINESS_JUDGEMENT_REVIEW.md)
- [Structured no-safe-URL outcome](docs/STRUCTURED_NO_URL_OUTCOME.md)
- [Interactive artifact diagnostics](docs/INTERACTIVE_ARTIFACT_DIAGNOSTICS.md)
- [Azure ML operations](docs/AZUREML_OPERATIONS.md)
- [Security contract](docs/SECURITY.md)
