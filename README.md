# Product URL Resolver — Notebook First

This repository resolves a submitted product description to one defensible direct product URL.

## Release

- Version: `2.0.0`
- Runtime contract: `product-url-notebook-v1`
- Acceptance policy: `product-url-acceptance-v1`
- Primary execution: Jupyter notebooks
- Browser validation: local Playwright in the notebook process
- Python: 3.10–3.12

## What was intentionally removed

The supported runtime no longer includes:

- Streamlit;
- FastAPI;
- Docker Compose;
- agent, UI, or browser containers;
- a browser microservice;
- host-port allocation;
- job queues or polling;
- `nest_asyncio`;
- runtime monkey patches;
- compatibility wrappers.

The base execution path is now:

```text
notebook
→ product interpretation
→ optional PCA LLM refinement
→ SerpAPI search
→ HTTP and structured-data acquisition
→ local Playwright rendering
→ canonical acceptance policy
→ one URL or explicit failure
→ auditable artifacts
```

## Notebooks

| Notebook | Purpose |
|---|---|
| `notebooks/01_resolve_one_product.ipynb` | Resolve and inspect one product |
| `notebooks/02_resolve_csv_batch.ipynb` | Resolve a CSV batch and checkpoint the output |

## Setup

Run from the repository root:

```bash
conda env create -f environment.yml
conda activate product-url-notebook
python -m ipykernel install --user --name product-url-notebook --display-name "product-url-notebook"
python -m playwright install chromium
cp .env.example .env
jupyter lab
```

Open either notebook and select the **product-url-notebook** kernel.

Set this mandatory value in `.env`:

```dotenv
SERPAPI_API_KEY=<your-key>
```

The deterministic baseline is:

```dotenv
PRODUCT_URL_BROWSER_ENABLED=true
PRODUCT_URL_BROWSER_REQUIRED=true
PRODUCT_URL_REASONING_ENABLED=false
PRODUCT_URL_REASONING_REQUIRED=false
```

PCA LLM reasoning is optional. When enabled, configure the `PCA_LLM_*` values in `.env.example`.

## Input contract

| Field | Required | Rule |
|---|---:|---|
| `main_text` | Yes | Vendor product description |
| `country_code` | Yes | Two-letter country code |
| `retailer_name` | No | Requested retailer; do not guess |
| `ean` | No | EAN, GTIN, or ISBN; do not guess |
| `language_code` | No | Two-letter language code |

## Acceptance contract

A final URL is delivered only when all mandatory gates pass:

1. exact product and edition identity;
2. supplied EAN, GTIN, or ISBN agreement when provided;
3. direct product-detail page;
4. durable canonical URL;
5. rendered-browser accessibility;
6. scrapable rendered product content;
7. no identity or edition conflict.

`REVIEW_REQUIRED` is allowed only after the URL itself passes every mandatory mapping gate. `FAILED` contains no delivered URL. `TECHNICAL_FAILURE` is reserved for an operational or configuration defect.

## Evidence output

Each row writes:

```text
data/artifacts/<row_id>/
├── input.json
├── interpretation.json
├── search.json
├── candidates.json
├── candidates.csv
├── decision.json
├── result.json
├── audit.md
└── browser/*.png
```

The batch notebook also writes:

```text
data/results/product_urls.csv
```

## Validation

```bash
python -m pip install -e '.[dev]'
python -m playwright install chromium
./scripts/validate_release.sh
```

The release checks compile the Python package and notebook cells, validate the notebook schema, enforce the single acceptance-policy boundary, reject service infrastructure and monkey-patch references, and run the complete test suite.

## Core modules

| Module | Responsibility |
|---|---|
| `interpretation.py` | Product identity signals and hypotheses |
| `search.py` | Bounded SerpAPI discovery |
| `acquisition.py` | HTTP and structured product evidence |
| `browser.py` | Local Playwright rendering without event-loop patches |
| `evaluation.py` | Candidate evidence production |
| `policy.py` | The only final URL acceptance and ranking policy |
| `orchestrator.py` | Straight sequential execution |
| `artifacts.py` | JSON, CSV, Markdown, and screenshot evidence |

See `notebooks/README.md` for the exact notebook workflow.
