# Product URL Finder

A production-oriented, multimodal system that resolves incomplete product text to the strongest usable product URL.

```text
Primary deliverable
= product URL

Acceptance basis
= Source + Evidence + Identity + Usability
```

Given `MAIN_TEXT`, `COUNTRY_CODE`, and optional `RETAILER_NAME`, `EAN/GTIN`, and `LANGUAGE_CODE`, the platform:

1. interprets the intended product;
2. searches manufacturer, local-market and global sources;
3. collects text, structured, browser and visual evidence;
4. verifies product and variant identity;
5. ranks URL candidates for source authority, evidence, identity and usability;
6. returns a strictly verified URL when available;
7. otherwise returns the strongest real direct review URL that is not a confirmed mismatch;
8. escalates an empty URL only when no non-mismatched direct product candidate exists.

## Delivery contract

| Result | Meaning |
|---|---|
| `URL_DELIVERED_VERIFIED` | Direct product URL passed strict production gates |
| `URL_DELIVERED_REVIEW_REQUIRED` | Strongest direct product URL delivered with explicit review warnings |
| `URL_DELIVERY_FAILED` | Exceptional failure: no non-mismatched direct product candidate remained after recovery |
| `TECHNICAL_FAILURE` | Runtime, dependency, configuration or response-contract defect |

A review URL is preferred over an empty result. Search pages, category pages, homepages, social pages, documents, intermediary URLs, fabricated URLs, confirmed wrong products and confirmed wrong variants are never delivered.

## Workflow

```text
Input
→ Understand product
→ Search sources
→ Acquire evidence
→ Verify identity
→ Rank candidates
→ Deliver product URL
```

## Browser application

```text
apps/product_evidence_ui.py
```

First use:

```bash
bash scripts/run_product_evidence_ui.sh --install
```

Subsequent use:

```bash
bash scripts/run_product_evidence_ui.sh
```

Forward port `8501` privately through the Azure ML VS Code **Ports** panel.

The standard UI shows:

```text
product URL
Source
Evidence
Identity
Usability
brief justification
```

Candidate comparisons, search traces, evidence ledgers, decision records and artifacts remain under one collapsed **Review details** section.

## Search profiles

| Profile | Operating intent |
|---|---|
| `Focused` | Reduced investigation breadth for faster execution |
| `Standard` | Default production operating limits |
| `Extended` | Broader search, extraction and browser investigation |

Profiles change evidence-acquisition depth. They do not weaken identity safety or permit indirect, fabricated or confirmed-mismatch URLs.

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

## Candidate recovery

The final URL-delivery layer examines:

```text
strict primary URL
product_match URLs
evidence-set selected URLs
candidate records
feature assessments
browser evidence
browser investigations
SERP result URLs
candidate_url_records.json
candidate_state.json
```

Candidates are deduplicated and ranked. Strict selections lead, followed by verified or probable identity, manufacturer and retailer authority, browser usability, extraction quality, requested-feature coverage, confidence and search position.

## Supported notebooks

| Notebook | Purpose | Agent required |
|---|---|---:|
| `notebooks/01_single_product.ipynb` | Execute and inspect one URL-resolution run | Yes |
| `notebooks/02_batch_products.ipynb` | Process a CSV with bounded product-level parallelism | Yes |
| `notebooks/03_artifact_diagnostics.ipynb` | Explore an existing product artifact | No |

## Product artifacts

```text
data/artifacts/<row_id>/
├── executive_summary.json
├── product_belief.json
├── product_understanding.md
├── evidence_ledger.jsonl
├── adaptive_search_trace.json
├── candidate_url_records.json
├── candidate_state.json
├── candidates.csv
├── business_judgement_review.md
├── source_selection.json
├── primary_url_acceptance.json
├── mandatory_url_delivery.json
├── orchestrated_result.json
└── single_product_diagnostics.xlsx
```

## Runtime compatibility

```text
belief-url-resolution-v11-url-delivery-first
```

Required capabilities include:

```text
manufacturer_first_primary_url=true
best_available_review_url_delivery=true
executive_url_decision_summary=true
business_judgement_review_artifact=true
per_job_runtime_controls=true
```

## Azure ML setup

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool
cp .env.example .env
# Add real SerpAPI and enterprise LLM values.
./scripts/azureml_startup.sh --clean-build
bash scripts/run_product_evidence_ui.sh
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

CI validates Python 3.10 and 3.11, URL-recovery behavior, UI delivery semantics, notebooks, runtime isolation, Docker Compose and the complete regression suite.

## Documentation

- [Feature reference](docs/FEATURE_REFERENCE.md)
- [System workflow](docs/SYSTEM_WORKFLOW.md)
- [Product URL Finder UI](docs/PRODUCT_EVIDENCE_UI.md)
- [Final system contract](docs/FINAL_SYSTEM_CONTRACT.md)
- [Notebook usage](docs/NOTEBOOK_USAGE.md)
- [Mandatory URL contract](docs/MANDATORY_PRODUCT_URL.md)
- [Business judgment review](docs/BUSINESS_JUDGEMENT_REVIEW.md)
- [Exceptional no-URL escalation](docs/STRUCTURED_NO_URL_OUTCOME.md)
- [Azure ML operations](docs/AZUREML_OPERATIONS.md)
- [Security contract](docs/SECURITY.md)
