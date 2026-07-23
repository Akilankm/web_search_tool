# Product URL Finder — Absolute Minimal

Version `3.0.0`.

This codebase does one job: find the most defensible product-detail URL from:

- mandatory `main_text`;
- mandatory two-letter `country_code`;
- optional `ean`;
- optional `retailer_name`.

## Runtime

```text
Notebook
→ optional PCA LLM identity extraction
→ budgeted SerpAPI searches
→ budgeted Crawl4AI page rendering
→ transparent token/EAN/retailer scoring
→ final URL or REVIEW_REQUIRED
→ small evidence folder
```

There is no UI, API server, Docker, CLI application, pipeline framework, queue, polling, browser microservice, thread wrapper, `nest_asyncio`, or monkey patching.

## Complete repository

```text
.env.example
.gitignore
README.md
environment.yml
pyproject.toml
samples/products.csv
src/product_url_finder.py
notebooks/01_resolve_one_product.ipynb
notebooks/02_resolve_csv_batch.ipynb
```

## Setup

```bash
conda env create -f environment.yml
conda activate product-url-minimal
crawl4ai-setup
python -m ipykernel install --user --name product-url-minimal --display-name "product-url-minimal"
cp .env.example .env
jupyter lab
```

Set `SERPAPI_API_KEY` in `.env`.

The PCA LLM contract remains unchanged:

```dotenv
PCA_LLM_API_KEY=nokey
PCA_LLM_API_VERSION=2024-10-21
PCA_LLM_ENDPOINT=https://cis-rnd-llm-api.cis.nielseniq.com
PCA_LLM_DEPLOYMENT=sea-ecomm-gpt-4o
PCA_LLM_CONSUMER_ID=2dc0f06c-d938-4d2d-8ec3-0a6b1b7d600c
```

Enable it with:

```dotenv
PRODUCT_URL_REASONING_ENABLED=true
PRODUCT_URL_REASONING_REQUIRED=false
```

## Budgets

```dotenv
SERP_CALL_BUDGET=3
SERP_RESULTS_PER_CALL=10
CRAWL_CANDIDATE_BUDGET=5
```

Hard limits are applied in code:

- SerpAPI calls: 1–5;
- results per call: 3–20;
- Crawl4AI candidates: 1–10.

## Execution

For one product, open:

```text
notebooks/01_resolve_one_product.ipynb
```

For a CSV batch, open:

```text
notebooks/02_resolve_csv_batch.ipynb
```

The batch input requires only:

```text
main_text,country_code
```

Optional columns:

```text
ean,retailer_name,row_id
```

## Output

The batch notebook writes:

```text
data/product_urls.csv
```

Each product writes only:

```text
data/artifacts/<row_id>/
├── input.json
├── searches.json
├── candidates.json
├── result.json
└── audit.md
```

## Debugging order

1. Check `.env` and the printed budgets.
2. Check `searches.json` for exact queries and SerpAPI responses.
3. Check `candidates.json` for Crawl4AI errors, matched tokens, conflicts, and scores.
4. Check `result.json` for the selected URL and budget usage.
5. Check `audit.md` for the readable summary.

The resolver deliberately runs sequentially. A failure therefore belongs to one visible search or one visible URL instead of being hidden inside concurrency infrastructure.
