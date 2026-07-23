# Product URL Finder — Fundamental Notebook Version

This repository finds the best direct product URL from four inputs:

| Input | Required |
|---|---:|
| `main_text` | Yes |
| `country_code` | Yes |
| `ean` | No |
| `retailer_name` | No |

## What exists

```text
notebooks/
├── 01_resolve_one_product.ipynb
└── 02_resolve_csv_batch.ipynb

src/product_url_finder/
├── __init__.py
└── core.py
```

That is the complete application.

There is no UI, API server, Docker, queue, browser service, polling, agent framework, plugin system, compatibility layer, event-loop patch, or monkey patch.

## Flow

```text
input
→ Azure OpenAI interprets the product
→ SerpAPI returns candidate URLs
→ Crawl4AI renders and extracts candidate pages
→ Azure OpenAI verifies the exact product
→ one URL or FAILED
```

## Explicit per-product budget

The notebooks use a plain `Budget` object:

```python
Budget(
    search_calls=3,
    crawl_pages=5,
    llm_calls=2,
)
```

No step can exceed these values.

## Setup

```bash
conda env create -f environment.yml
conda activate product-url-notebook
crawl4ai-setup
python -m ipykernel install --user \
  --name product-url-notebook \
  --display-name "product-url-notebook"
cp .env.example .env
jupyter lab
```

Set the existing credentials in `.env`:

```dotenv
SERPAPI_API_KEY=

PCA_LLM_API_KEY=
PCA_LLM_API_VERSION=2024-10-21
PCA_LLM_ENDPOINT=
PCA_LLM_DEPLOYMENT=
PCA_LLM_CONSUMER_ID=

PRODUCT_URL_ARTIFACT_ROOT=data/artifacts
```

The PCA enterprise header remains:

```text
X-NIQ-CIS-Consumer: <PCA_LLM_CONSUMER_ID>
```

## Single product

Open:

```text
notebooks/01_resolve_one_product.ipynb
```

Edit only the input and budget cells, then run all cells.

## CSV batch

Open:

```text
notebooks/02_resolve_csv_batch.ipynb
```

Mandatory columns:

```text
main_text,country_code
```

Optional columns:

```text
ean,retailer_name,row_id
```

Output:

```text
data/results/product_urls.csv
```

## Output columns

```text
ROW_ID
MAIN_TEXT
COUNTRY
RETAILER
EAN
CANDIDATE_URLS
PRODUCT_URL
CONFIDENCE
VALIDATION_STATUS
IDENTITY_STATUS
RETAILER_CHECK
JUSTIFICATION
ARTIFACT_DIR
```

## Debug artifacts

Each product writes only five small files:

```text
data/artifacts/<row_id>/
├── input.json
├── interpretation.json
├── search_results.json
├── crawled_candidates.json
├── result.json
└── trace.md
```

Start debugging from `trace.md`, then inspect the JSON files in execution order.
