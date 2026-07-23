# Supported notebooks

The repository has two supported execution entry points:

1. `01_resolve_one_product.ipynb` — resolve and audit one submitted product.
2. `02_resolve_csv_batch.ipynb` — resolve a CSV batch and checkpoint the output after every row.

Both notebooks execute the resolver directly in the Jupyter kernel. They do not start or call a UI, API server, Docker container, browser microservice, queue, or polling process.

## Setup

From the repository root:

```bash
conda env create -f environment.yml
conda activate product-url-notebook
python -m playwright install chromium
cp .env.example .env
jupyter lab
```

Set `SERPAPI_API_KEY` in `.env` before running either notebook.

PCA LLM reasoning is optional. The deterministic baseline is:

```dotenv
PRODUCT_URL_REASONING_ENABLED=false
PRODUCT_URL_REASONING_REQUIRED=false
```

When reasoning is enabled, configure the `PCA_LLM_*` values shown in `.env.example`.

## Acceptance rule

A URL is delivered only when the candidate passes exact identity, supplied-identifier agreement when applicable, direct-page proof, URL durability, local Playwright accessibility, scrapable rendered content, and zero identity or edition conflicts.

`FAILED` contains no delivered URL. `TECHNICAL_FAILURE` is reserved for an operational defect.
