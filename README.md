# Product Evidence Platform

A production-oriented, multimodal product-identification and URL-resolution system for incomplete vendor product text.

> Given `MAIN_TEXT`, `COUNTRY_CODE`, and optional `RETAILER_NAME`, `EAN/GTIN`, and `LANGUAGE_CODE`, identify the intended product, return the strongest defensible direct product URL when one can be safely found, preserve manufacturer and retailer references, and expose the observable business judgments that produced the result.

## Core business contract

The system separates **product truth** from **commercial reference**:

- an exact, complete and durable official manufacturer page is preferred for product truth;
- a qualified retailer page is retained for local pack, language, price, availability and purchase context;
- a retailer or qualified global page becomes `primary_url` when no official manufacturer page passes every mandatory production gate;
- when bounded search produces no safe direct product page, the system returns an explicit `REVIEW_REQUIRED` result and never fabricates a URL.

```text
exact product, model, form, variant, size, quantity and pack
→ browser-openable rendered individual product page
→ text scrapability and information richness
→ requested-feature completeness
→ durable non-expiring URL
→ official manufacturer authority
→ requested retailer / requested-country retailer
→ global exact-product source
→ marketplace last resort
```

Source authority never bypasses identity, browser, feature, scrapability or durability safety.

## Runtime contract

```text
belief-url-resolution-v8-leadership-demo
```

Required health capabilities include:

```text
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
structured_no_url_review_outcome=true
leadership_demo_runtime_options=true
```

## Leadership Streamlit demo

For management and leadership calls, use:

```text
apps/leadership_demo.py
```

The Streamlit surface calls the same Product Evidence Agent API used by the notebooks. It does not duplicate search, browser, validation or artifact logic.

It shows:

- complete platform capabilities;
- runtime and browser health;
- product input and feature set;
- safe per-job budget controls;
- live execution stage;
- final URL, source role, manufacturer and retailer references;
- strict production gates;
- requested budget versus actual usage;
- text, screenshot and image evidence;
- candidate rejection reasons;
- chronological business judgment sequence;
- product artifacts and downloads.

First use in Azure ML VS Code:

```bash
./scripts/azureml_startup.sh --clean-build
bash scripts/run_leadership_demo.sh --install
```

Later launches:

```bash
bash scripts/run_leadership_demo.sh
```

Forward port `8501` privately through the VS Code **Ports** panel. See [Leadership Streamlit demo](docs/STREAMLIT_LEADERSHIP_DEMO.md).

### Safe per-job budget controls

The demo can vary only bounded operational limits:

```text
SerpAPI search credits
full page scrapes
scrapes per domain
planner candidate context
browser-investigated candidates
browser turns and actions
images available to visual reasoning
```

Every selected value is isolated to one job and persisted in:

```text
data/artifacts/<row_id>/run_configuration.json
```

The UI cannot expose credentials, edit `.env`, restart shared containers or weaken exact-product identity, requested-feature, URL-durability, manufacturer-first or no-fabrication policies.

## Three supported notebooks

The notebooks remain the primary analytical and batch workflows.

| Notebook | Purpose | Requires agent? |
|---|---|---:|
| `notebooks/01_single_product.ipynb` | Execute one product and review the final URL or explicit no-safe-URL outcome, judgment sequence, visual evidence and artifacts | Yes |
| `notebooks/02_batch_products.ipynb` | Validate a CSV, run products with bounded parallelism, isolate technical failures and preserve one complete artifact per row | Yes |
| `notebooks/03_artifact_diagnostics.ipynb` | Explore any existing product artifact through one interactive decision workspace | No |

### Single product

```text
one product input
→ final_decision_df
→ business_judgement_steps_df
→ visual_evidence_summary_df
→ candidate and feature evidence
→ single_product_diagnostics.xlsx
```

The primary human-review file is:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

### Parallel batch

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

Example:

```text
examples/batch_products.example.csv
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

A no-safe-URL product remains a `REVIEW_REQUIRED` row in `batch_results.csv`; it is not a technical failure and is not moved into `batch_failures.csv`.

### Interactive artifact diagnostics

The diagnostics notebook accepts an artifact directory or any file inside it and writes:

```text
data/artifacts/<row_id>/artifact_diagnostics_interactive.html
```

The offline workspace contains:

```text
Decision Map
Judgment Timeline
Candidates
Evidence
Artifacts
```

It visualizes recorded evidence, rules, judgments and actions—not hidden chain-of-thought.

## Human-comparable business judgment artifact

Every terminal business result (`COMPLETED` or `REVIEW_REQUIRED`) writes:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

It records:

- submitted input;
- chronological business questions;
- observable identifier, text, rendered-page and visual evidence;
- explicit business rules;
- agent judgments and statuses;
- alternatives considered and rejected;
- rejection reasons;
- effects on subsequent actions;
- final URL/source decision or controlled no-safe-URL outcome;
- a human form for `IDENTICAL`, `PARTIALLY IDENTICAL` or `NOT IDENTICAL`.

Behavioral validation compares the decision sequence, not only the final URL.

## Multimodal evidence

The browser workflow can use rendered screenshots, product galleries, package images, visible specifications, warning sections, structured page data and rendered text.

Vision evidence is auditable:

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

The artifact distinguishes:

```text
YES_VISUAL_EVIDENCE_SUPPORTED_SELECTED_URL_FEATURE_GATE
VISUAL_EVIDENCE_USED_BUT_NOT_RECORDED_AS_DECISIVE_FOR_SELECTED_URL
NO_VISUAL_EVIDENCE_RECORDED
```

## Stable result schema

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

A no-safe-URL result additionally contains:

```text
resolution_outcome.code=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
url_delivery.status=NO_SAFE_DIRECT_PRODUCT_URL_FOUND_AFTER_BOUNDED_SEARCH
```

## Outcomes

| Outcome | Meaning |
|---|---|
| `COMPLETED` | A direct product URL passed strict identity, browser, feature, scrapability, durability and authority gates |
| `REVIEW_REQUIRED` with URL | A real direct review URL was delivered, but one or more judgments need confirmation |
| `REVIEW_REQUIRED` without URL | Bounded search found no safe direct page; full trace and next actions are preserved and no URL is fabricated |
| `FAILED` | Genuine software, configuration, dependency or response-contract failure |

The system never reports `COMPLETED` with an empty URL.

## Product artifact contract

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

The committed feature schema is:

```text
inputs/private/toy_features.json
```

## Validation

```bash
bash -n scripts/azureml_startup.sh
bash -n scripts/run_leadership_demo.sh
python -m compileall -q src scripts apps
python -m json.tool inputs/private/toy_features.json >/dev/null
PYTHONPATH=src pytest -q
docker compose config --quiet
```

CI validates the agent, all three notebooks, Streamlit contract, per-job budget isolation and the complete historical suite on Python 3.10 and 3.11.

## Documentation

- [Management and leadership demo guide](docs/MANAGEMENT_DEMO_GUIDE.md)
- [Leadership Streamlit demo](docs/STREAMLIT_LEADERSHIP_DEMO.md)
- [Structured no-safe-URL outcome](docs/STRUCTURED_NO_URL_OUTCOME.md)
- [Interactive artifact diagnostics](docs/INTERACTIVE_ARTIFACT_DIAGNOSTICS.md)
- [Final system contract](docs/FINAL_SYSTEM_CONTRACT.md)
- [Notebook usage](docs/NOTEBOOK_USAGE.md)
- [Business judgment review](docs/BUSINESS_JUDGEMENT_REVIEW.md)
- [Azure ML operations](docs/AZUREML_OPERATIONS.md)
- [Security contract](docs/SECURITY.md)
