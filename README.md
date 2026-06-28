# Product Evidence Harness

Local Python package for **LLM-guided exact product URL discovery**.

This is intentionally not an AzureML component yet. It is a local PDM/Python codebase with notebooks and CLI entrypoints.

## Core strategy

The current strategy is **retailer-scrapability aware loop engineering**:

```text
LLM builds product identity and search campaign
  → SerpAPI performs high-yield search and returns many candidate URLs
  → crawl4ai scrapes useful candidate pages aggressively because scraping is free/open-source
  → deterministic extractors and detectors score page type, richness, exactness, EAN, country fit, and variant conflicts
  → LLM consumes the evidence summary and either adjudicates exact product or repairs the search
  → requested retailer is escaped if it is not scrape-usable/rich/exact
  → same-country alternative retailers are searched
  → global fallback is used only when country evidence fails
  → final selector returns verified exact URL, best available URL, or reference-only URL honestly
```

Important policy:

```text
retailer_name = preferred first evidence source
scrapability/richness/exactness = acceptance gate
wrong variant or non-scrapable requested-retailer page must not block a better same-country/global exact URL
```

## Input contract

| Field | Required | Role |
|---|---:|---|
| `main_text` | Yes | Primary product identity text. |
| `country_code` | Yes | Country-first search market. |
| `ean` / `gtin` | No | Strong user-provided anchor. Must remain a string. LLM must never invent it. |
| `retailer_name` | No | Preferred first evidence source only; not a hard final constraint. |
| `language_code` | No | Optional search language override; otherwise derived from country profile. |
| `region` | No | Optional market hint. |

EAN/GTIN identifiers are read as strings. If Excel has already converted an EAN into scientific notation, the system will flag `EAN_SCIENTIFIC_NOTATION_LOSS_RISK` and avoid using the corrupted value as exact evidence.

## Active notebooks

Only these notebooks are kept:

```text
notebooks/01_single_product_harness.ipynb
notebooks/02_batch_product_harness.ipynb
```

Removed legacy/non-run notebooks to avoid confusion.

## URL decision semantics

| Field | Meaning |
|---|---|
| `product_url` | Final operational URL. Blank if only hard-rejected/reference URLs exist and `PRODUCT_HARNESS_RETURN_REJECTED_REFERENCE_AS_PRODUCT_URL=false`. |
| `verified_exact_url` | Filled only when exact product is proven from scrape evidence and LLM/detector gates pass. |
| `best_available_url` | Best useful non-conflicting URL when exact proof is not complete. |
| `best_reference_url` | Closest rejected/reference URL when only wrong variants or insufficient evidence exist. |
| `needs_review` | True when the final URL is not verified exact. |
| `url_decision_status` | Exact/requested-retailer/country-alternative/global/review/failure status. |

Requested-retailer statuses include:

```text
EXACT_REQUESTED_RETAILER_MATCH
EXACT_COUNTRY_ALTERNATIVE_RETAILER_MATCH
EXACT_GLOBAL_FALLBACK
BEST_AVAILABLE_COUNTRY_NEEDS_REVIEW
BEST_AVAILABLE_GLOBAL_NEEDS_REVIEW
NO_VERIFIED_EXACT_URL
```

## Output contract

The output is now organized as a proper **search + validation + verification artifact**:

```text
CSV = final operational answer
Markdown = readable evidence and decision trace
JSON = compact machine replay/debug trace
```

### Row-level artifact packet

Each product row writes:

```text
output/<row_id>/
├── final_row.csv
├── report.md
├── search_plan.md
├── candidate_review.md
├── scrape_evidence.md
├── retailer_scrapability.md
├── final_decision.md
├── decision_trace.md
└── trace.json
```

The markdown files record what was planned, searched, scraped, rejected, repaired, and selected. This is an observable decision trace and evidence trail, not hidden chain-of-thought.

### Batch-level outputs

```text
outputs/
├── final_submission.csv
├── review_queue.csv
└── batch_summary.md
```

`final_submission.csv` is the business/submission artifact. It contains inputs, candidate URLs, final best URL fields, selected scope, exactness/scrapability flags, resource counters, and `row_report_path` linking to the markdown evidence packet.

### Optional debug CSVs

Detailed diagnostic CSVs are disabled by default. Enable them only for engineering investigation:

```env
PRODUCT_HARNESS_WRITE_DEBUG_CSVS=true
```

When enabled, the old-style CSV diagnostics are written under:

```text
output/<row_id>/debug_csv/
```

## Cost-aware operating model

Paid/controlled:

```text
SerpAPI calls
LLM calls
```

Free/open-source and used aggressively:

```text
crawl4ai scraping
deterministic extraction
detector scoring
candidate dedupe/ranking
```

Recommended defaults in this package favor high-yield SerpAPI and broad scraping:

```env
PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES=3
PRODUCT_HARNESS_SERP_RESULTS=100
PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES=1
PRODUCT_HARNESS_MAX_SCRAPES=180
PRODUCT_HARNESS_MAX_ITERATIONS=240
PRODUCT_HARNESS_LLM_MAX_CALLS_PER_PRODUCT=4
```

## `.env` essentials

```env
SERPAPI_API_KEY=your_serpapi_key

PRODUCT_HARNESS_ENABLE_LLM=true
PRODUCT_HARNESS_ENABLE_LLM_SEARCH_PLANNING=true
PRODUCT_HARNESS_ENABLE_LLM_SEARCH_FEEDBACK=true
PRODUCT_HARNESS_ENABLE_LLM_ADJUDICATION=true
PRODUCT_HARNESS_REQUIRE_LLM_EXACT_MATCH=true
PRODUCT_HARNESS_LLM_MAX_CALLS_PER_PRODUCT=4
PRODUCT_HARNESS_LLM_USE_IMAGES=true
PRODUCT_HARNESS_LLM_PAYLOAD_REDUCTION=true
PRODUCT_HARNESS_RESERVE_LLM_CALL_FOR_ADJUDICATION=true

PRODUCT_HARNESS_REQUESTED_RETAILER_FIRST=true
PRODUCT_HARNESS_REQUESTED_RETAILER_MIN_SCRAPES_FOR_ESCAPE=2
PRODUCT_HARNESS_REQUESTED_RETAILER_MIN_RICHNESS_FOR_EVIDENCE=0.30
PRODUCT_HARNESS_RETURN_REJECTED_REFERENCE_AS_PRODUCT_URL=false

PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES=3
PRODUCT_HARNESS_SERP_RESULTS=100
PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES=1
PRODUCT_HARNESS_MAX_SCRAPES=180
PRODUCT_HARNESS_MAX_ITERATIONS=240
PRODUCT_HARNESS_OUTPUT_DIR=output
PRODUCT_HARNESS_WRITE_OUTPUTS=true
PRODUCT_HARNESS_ALLOW_GLOBAL_FALLBACK=true
PRODUCT_HARNESS_COUNTRY_FIRST=true
PRODUCT_HARNESS_GLOBAL_FALLBACK_LANGUAGE=en
PRODUCT_HARNESS_GLOBAL_FALLBACK_COUNTRY=

AZURE_OPENAI_API_KEY=your_azure_openai_api_key
AZURE_OPENAI_API_VERSION=2024-02-15-preview
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=your_vision_enabled_deployment
LLM_CONSUMER_ID=your_consumer_id

LLM_MAX_TOKENS=1600
LLM_TEMPERATURE=0.0
LLM_CONNECT_TIMEOUT=15
LLM_READ_TIMEOUT=120
LLM_MAX_RETRIES=3
```

## Minimal single-product usage

```python
from product_evidence_harness import HarnessConfig, ProductEvidenceHarness, ProductQuery, SerpAPIConfig

product = ProductQuery(
    row_id="CO-ML-0001",
    main_text="PUT PRODUCT TEXT HERE",
    country_code="CO",
    ean="",  # optional, keep as text
    retailer_name="Mercado Libre",  # optional preferred-first evidence source
)

serp_config = SerpAPIConfig.from_env(country_code=product.country_code, language_code="es")
config = HarnessConfig.from_env(".env")

harness = ProductEvidenceHarness(serp_config=serp_config, config=config)
trace = harness.run(product, return_trace=True)

print(trace.best_match.to_dict())
print("Inspect:", f"{config.output_dir}/{product.row_id}/")
```

## CLI usage

Single product:

```bash
python main.py \
  --row-id CO-ML-0001 \
  --main-text "PUT PRODUCT TEXT HERE" \
  --country-code CO \
  --retailer-name "Mercado Libre" \
  --ean "7701234567890"
```

Batch:

```bash
python batch_main.py \
  --input data/products.xlsx \
  --output outputs/product_url_matches.csv \
  --workers 2
```

## Validation

```bash
PYTHONPATH=src python -m compileall -q src main.py batch_main.py
PYTHONPATH=src pytest -q
```

## Import path note

This project uses a standard `src/` package layout. In notebooks, add `<repo>/src` to `sys.path`, then import with `product_evidence_harness`. Do not import with `src.product_evidence_harness`. See `docs/IMPORT_PATH_FIX.md`.
