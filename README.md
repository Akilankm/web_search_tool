# Product URL Resolver

`product-url-resolver` converts incomplete vendor product text into the strongest auditable **direct product URL**.

## Release

- Version: `1.1.0`
- Runtime contract: `product-url-resolver-v1`
- Observable trace contract: `observable-decision-trace-v1`
- Python: `3.10–3.12`
- Services: FastAPI agent, Playwright browser, Streamlit human-review workspace

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
→ optional PCA LLM hypothesis refinement
→ competing product hypotheses
→ three-credit information-gain search
→ candidate admission and deduplication
→ bounded HTTP/JSON-LD acquisition
→ identity/source/page/durability evaluation
→ evidence-diverse rendered-browser checks
→ mandatory URL-delivery policy
→ stable JSON/CSV/Markdown artifacts
→ live observable decision trace for human coders
```

The live trace exposes observable inputs, evidence, hypotheses, gate outcomes and selection judgments. It does not expose or fabricate hidden chain-of-thought.

## Start

```bash
cp .env.example .env
# Set SERPAPI_API_KEY and, when enabled, PCA_LLM_* values in .env
./scripts/start.sh --build
```

For organization LLM reasoning, keep the supplied values under `PCA_LLM_API_KEY`, `PCA_LLM_API_VERSION`, `PCA_LLM_ENDPOINT`, `PCA_LLM_DEPLOYMENT`, and `PCA_LLM_CONSUMER_ID`, then enable `PRODUCT_URL_REASONING_ENABLED=true`. Real credentials remain only in `.env`.

`PRODUCT_URL_HOST_PORT` and `PRODUCT_URL_UI_PORT` are preferred host ports. The launcher automatically selects free alternatives and writes only those non-secret resolved values to `.runtime/ports.env`.

The launcher prints the exact addresses after readiness checks. Defaults, when available:

- UI: `http://127.0.0.1:8501`
- API health: `http://127.0.0.1:8788/health`
- API docs: `http://127.0.0.1:8788/docs`

## Human-review UI

The Streamlit workspace includes:

- live stage tracker;
- observable “thinking mode” decision trace;
- identity signals and competing hypotheses;
- every paid search action and retained source;
- candidate-level identity, page, durability, market, retailer, browser, extraction and coding gates;
- explicit strengths, risks and blockers;
- rendered-page screenshots and product controls;
- selected URL, rejection reasons and downloadable JSON/CSV review artifacts.

See [Human-review UI and trace contract](docs/UI_REVIEW.md).

## API

Use the agent port printed by `scripts/start.sh` or read it from `.runtime/ports.env`.

```text
POST /v1/resolve
POST /v1/jobs
GET  /v1/jobs/{job_id}
GET  /v1/jobs/{job_id}/trace?after_sequence=<n>
GET  /v1/jobs/{job_id}/result
```

The trace endpoint is incremental: callers pass the last consumed sequence number and receive only newer structured events.

Synchronous example using the default port:

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

The UI mounts this directory read-only so human coders can inspect screenshots without granting the UI write access.

## Validation

```bash
python -m pip install -e '.[dev]'
./scripts/validate_release.sh
```

CI compiles all Python, validates JSON and shell entry points, validates Docker Compose, rejects legacy/monkey-patch references, and runs the complete test suite on Python 3.10, 3.11 and 3.12.

## Documentation

- [Architecture and decision contract](docs/ARCHITECTURE.md)
- [Human-review UI and trace contract](docs/UI_REVIEW.md)
- [Operations](docs/OPERATIONS.md)
- [Release and benchmark gates](docs/RELEASE.md)
