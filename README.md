# Product URL Resolver

`product-url-resolver` converts incomplete vendor product text into the strongest auditable **direct product URL**.

## Release

- Version: `1.0.0`
- Runtime contract: `product-url-resolver-v1`
- Python: `3.10–3.12`
- Services: API agent, Playwright browser, Streamlit UI

## Business contract

| Status | Contract |
|---|---|
| `VERIFIED` | Exact identity and all strict URL/coding gates passed; direct URL is mandatory |
| `REVIEW_REQUIRED` | Strongest non-mismatched direct product URL is delivered with explicit warnings |
| `FAILED` | No direct product candidate survived the complete bounded recovery campaign |
| `TECHNICAL_FAILURE` | Configuration, dependency or runtime defect prevented a valid decision |

Product identity, URL delivery, browser automation and coding completeness are independent axes. Browser automation failure does not mean a human cannot open a URL. Missing coding fields do not erase a usable product URL. `NOT_ASSESSED` is never rewritten as `FAIL`.

## Architecture

```text
Input
→ deterministic exact-anchor interpretation
→ optional structured LLM refinement (facts / assumptions / unknowns)
→ competing product hypotheses
→ three-credit information-gain search
→ candidate admission and deduplication
→ bounded HTTP/JSON-LD acquisition
→ identity and direct-page evaluation
→ evidence-diverse rendered-browser checks
→ mandatory URL-delivery policy
→ stable JSON/CSV/Markdown artifacts
```

## Inputs

Required:

```text
main_text
country_code
```

Optional:

```text
row_id
retailer_name
ean
language_code
feature_set
runtime_options
```

All budgets and operational behavior are loaded from `config/default.json` and can be overridden per request through validated `runtime_options`. Feature definitions are external JSON files under `feature_sets/`.

## Start

```bash
cp .env.example .env
# Set SERPAPI_API_KEY in .env
./scripts/start.sh --build
```

Open:

- UI: `http://127.0.0.1:8501`
- API health: `http://127.0.0.1:8788/health`
- API docs: `http://127.0.0.1:8788/docs`

## API

Synchronous:

```bash
curl -X POST http://127.0.0.1:8788/v1/resolve \
  -H 'Content-Type: application/json' \
  -d '{
    "main_text": "PKM ME04 WACHSENDES CHAOS BOOSTER",
    "country_code": "CH",
    "language_code": "de",
    "feature_set": "toy"
  }'
```

Asynchronous:

```text
POST /v1/jobs
GET  /v1/jobs/{job_id}
GET  /v1/jobs/{job_id}/result
```

## CLI

```bash
python -m pip install -e '.[dev]'

product-url resolve \
  --row-id DEMO-1 \
  --main-text 'LEITZ RECYCLE PROSPEKTHÜLLE 100 STÜCK' \
  --country-code DE \
  --language-code de

product-url batch --input samples/products.csv --output data/results.csv

product-url benchmark --cases benchmark/cases.csv --outcomes benchmark/outcomes.csv --report benchmark/report.json
```

## Artifacts

Each run writes one self-contained directory:

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

## Validation

```bash
python -m pip install -e '.[dev]'
./scripts/validate_release.sh
```

CI compiles all Python, validates JSON and shell entry points, validates Docker Compose, rejects legacy/monkey-patch references, and runs the complete test suite on Python 3.10, 3.11 and 3.12.

## Documentation

- [Architecture and decision contract](docs/ARCHITECTURE.md)
- [Operations](docs/OPERATIONS.md)
- [Release and benchmark gates](docs/RELEASE.md)
