# Product Identification Platform

A production-oriented, multimodal system for identifying the exact product represented by incomplete vendor text.

The platform does **not** treat a URL as the product result.

```text
Primary result   = identified product
Supporting result = evidence, source pages and artifacts
```

Given `MAIN_TEXT`, `COUNTRY_CODE`, and optional `RETAILER_NAME`, `EAN/GTIN`, and `LANGUAGE_CODE`, the platform:

1. interprets the product identity contained in the input;
2. constructs competing product hypotheses;
3. searches for text, structured and visual evidence;
4. compares supporting and contradicting evidence;
5. resolves the strongest defensible product identity;
6. records uncertainty, alternatives and unresolved distinctions;
7. retains URLs only as evidence locations.

## Core workflow

```text
Input
→ Interpret
→ Discover evidence
→ Compare product hypotheses
→ Resolve product identity
→ Validate evidence consistency
→ Report identification and artifacts
```

## Primary outcome

The primary result is `product_identification`.

```text
resolution_status
leading_hypothesis
canonical product name
brand
manufacturer
model or series
product form
variant
size
quantity or pack
posterior probability
identity claims
alternative hypotheses
uncertainties
unknowns
evidence ledger
```

### Resolution states

| Status | Meaning |
|---|---|
| `EXACT` | One product identity is resolved with sufficient evidence |
| `PROBABLE` | One hypothesis leads but confirmation evidence remains incomplete |
| `AMBIGUOUS` | Multiple plausible products remain |
| `CONFLICTING` | Material evidence supports incompatible identities |
| `INSUFFICIENT_EVIDENCE` | Evidence is not sufficient for a defensible identity |

An `EXACT` product remains identified even when no source URL passes every page-usability check.

## Supporting source evidence

URLs are supporting evidence locations.

```text
primary_url
manufacturer_url
retailer_url
source_selection
primary_url_acceptance
url_delivery
```

These fields describe where evidence was found and whether a source is reusable. They do not replace `product_identification`.

Source-quality states in the UI are:

```text
VERIFIED
NOT VERIFIED
NOT ASSESSED
```

The UI never converts a missing source-quality field into a product `FAIL` verdict.

## Browser application

```text
apps/product_evidence_ui.py
```

Start the application:

```bash
bash scripts/run_product_evidence_ui.sh --install   # first use
bash scripts/run_product_evidence_ui.sh             # subsequent use
```

Forward port `8501` privately through the Azure ML VS Code **Ports** panel.

The application presents:

```text
identified product
resolution status and confidence
resolved identity attributes
identity claims
evidence ledger
alternative product hypotheses
unresolved distinctions
supporting source evidence
decision audit
artifacts
```

## Execution profiles

| Profile | Operating intent |
|---|---|
| `Latency Optimized` | Lower evidence-acquisition limits for lower elapsed time |
| `Standard` | Default production evidence limits |
| `Coverage Optimized` | Broader candidate, browser and visual investigation |

Profiles change evidence depth. They do not change product-identity rules.

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

Controls are context-local and concurrency-safe.

## Supported notebooks

| Notebook | Purpose | Agent required |
|---|---|---:|
| `notebooks/01_single_product.ipynb` | Execute and inspect one product-identification run | Yes |
| `notebooks/02_batch_products.ipynb` | Process a CSV with bounded product-level parallelism | Yes |
| `notebooks/03_artifact_diagnostics.ipynb` | Explore an existing product artifact | No |

## Product artifacts

```text
data/artifacts/<row_id>/
├── product_belief.json
├── product_understanding.md
├── belief_updates.md
├── evidence_ledger.jsonl
├── adaptive_search_trace.json
├── candidate_url_records.json
├── candidates.csv
├── business_judgement_review.md
├── source_selection.json
├── primary_url_acceptance.json
├── mandatory_url_delivery.json
├── orchestrated_result.json
└── single_product_diagnostics.xlsx
```

The product-belief and evidence artifacts are primary. URL artifacts are supporting diagnostics.

## Runtime compatibility

```text
belief-url-resolution-v9-product-evidence-ui
```

The runtime name is retained for backward compatibility. The browser application and documentation use a product-identification-first result hierarchy.

Required capabilities:

```text
business_judgement_review_artifact=true
structured_no_url_review_outcome=true
per_job_runtime_controls=true
```

## Azure ML setup

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool
cp .env.example .env
# Add real SerpAPI and enterprise LLM values.
./scripts/azureml_startup.sh --clean-build
```

For UI-only updates where the runtime contract is unchanged, pull the repository and restart Streamlit; a clean container rebuild is not required.

## Validation

```bash
bash -n scripts/azureml_startup.sh
bash -n scripts/run_product_evidence_ui.sh
python -m compileall -q src scripts apps
python -m json.tool inputs/private/toy_features.json >/dev/null
PYTHONPATH=src pytest -q
docker compose config --quiet
```

CI validates Python 3.10 and 3.11, notebooks, product-identification UI semantics, runtime-control isolation, Compose and the complete regression suite.

## Documentation

- [Feature reference](docs/FEATURE_REFERENCE.md)
- [System workflow](docs/SYSTEM_WORKFLOW.md)
- [Product Identification Platform UI](docs/PRODUCT_EVIDENCE_UI.md)
- [Final system contract](docs/FINAL_SYSTEM_CONTRACT.md)
- [Notebook usage](docs/NOTEBOOK_USAGE.md)
- [Business judgment review](docs/BUSINESS_JUDGEMENT_REVIEW.md)
- [Structured no-safe-URL outcome](docs/STRUCTURED_NO_URL_OUTCOME.md)
- [Interactive artifact diagnostics](docs/INTERACTIVE_ARTIFACT_DIAGNOSTICS.md)
- [Azure ML operations](docs/AZUREML_OPERATIONS.md)
- [Security contract](docs/SECURITY.md)
