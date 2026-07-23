# Product URL Resolver — Minimal Notebook Edition

Version `3.0.0` is the stripped-down notebook implementation.

There is no UI, API server, CLI, Docker, job queue, browser service, plugin system, architecture framework, or event-loop patching.

## Inputs

| Field | Required |
|---|---:|
| `main_text` | Yes |
| `country_code` | Yes |
| `ean` | No |
| `retailer_name` | No |

## Flow

```text
input
→ optional PCA LLM interpretation
→ budgeted SerpAPI searches
→ budgeted Crawl4AI page crawls
→ simple evidence scoring
→ optional PCA LLM candidate selection
→ final URL or explicit failure
→ run.json, audit.md, crawled Markdown pages
```

## Files that matter

```text
notebooks/01_resolve_one_product.ipynb
notebooks/02_resolve_csv_batch.ipynb
src/product_url/resolver.py
.env
```

## Setup

```bash
conda env create -f environment.yml
conda activate product-url-minimal
crawl4ai-setup
crawl4ai-doctor
python -m ipykernel install --user --name product-url-minimal --display-name "product-url-minimal"
cp .env.example .env
jupyter lab
```

Keep your existing PCA values in `.env`. The code uses the same enterprise variables:

```dotenv
PCA_LLM_API_KEY=
PCA_LLM_API_VERSION=2024-10-21
PCA_LLM_ENDPOINT=
PCA_LLM_DEPLOYMENT=
PCA_LLM_CONSUMER_ID=
PCA_LLM_MAX_RETRIES=2
```

SerpAPI requires:

```dotenv
SERPAPI_API_KEY=
```

## Visible budgets

Budgets are ordinary notebook values, not hidden configuration:

```python
Budgets(searches=3, search_results=10, crawls=6, llm_calls=2)
```

- `searches`: maximum paid SerpAPI calls per product
- `search_results`: maximum results retained per SerpAPI response
- `crawls`: maximum candidate pages opened with Crawl4AI
- `llm_calls`: maximum PCA LLM calls; normally one interpretation and one final selection

## Outputs

The batch notebook writes:

```text
data/results/product_urls.csv
```

Each product writes:

```text
data/artifacts/<row_id>/
├── run.json
├── audit.md
└── pages/
    ├── C01.md
    └── ...
```

`run.json` is the complete debugging record: input, budgets, queries, SerpAPI results, Crawl4AI evidence, scores, LLM selection, final decision, and errors.

## Run locally

Open one of the two notebooks and select the `product-url-minimal` kernel. Execute cells from top to bottom. The notebooks use native top-level `await`; they do not call `asyncio.run`, `nest_asyncio`, or any monkey patch.
