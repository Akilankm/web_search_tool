# Exact Product Mapping Resolver

`product-url-resolver` maps the submitted product identity to exactly one defensible direct product URL.

## Release

- Version: `1.2.0`
- Runtime contract: `product-url-resolver-v1`
- Mapping policy: `exact-accessible-scrapable-mapping-v3`
- Observable trace contract: `observable-decision-trace-v1`
- Python: `3.10–3.12`
- Services: FastAPI resolver, Playwright browser validator, Streamlit mapping console

## Non-negotiable business contract

```text
Submitted product
→ exact product / edition identity
→ manufacturer or publisher first
→ requested or country retailer fallback
→ rendered browser accessibility
→ scrapable product content
→ exactly one final direct URL
```

A search result is only discovery evidence. It cannot become the final mapping until every mandatory gate passes.

| Mandatory gate | Requirement |
|---|---|
| Exact identity | Title, brand/manufacturer, model, pack, format and edition must not conflict |
| Supplied EAN/GTIN/ISBN | The same identifier must be present in page or rendered-page evidence |
| Source hierarchy | Exact manufacturer/publisher page first; exact retailer page second |
| Direct page | Homepage, category, search, consent, login and intermediary pages are rejected |
| Accessibility | The final URL must open in the rendered browser without an error surface |
| Scrapability | The rendered page must expose usable product text |
| Durability | Session, redirect, tracking and intermediary URLs are rejected or canonicalized |

`REVIEW_REQUIRED` is not a fallback for an uncertain or inaccessible URL. It is allowed only when the URL already satisfies the exact identity, accessibility and scrapability contract and a secondary coding or market field still needs review.

`FAILED` means no candidate satisfied the full mapping contract. Discovery candidates remain in the audit artifact, but the system does not misrepresent them as successful URLs.

## Identifier-locked search strategy

When an EAN, GTIN or ISBN is supplied, all three paid search credits remain locked to that identifier:

1. **Exact manufacturer/publisher discovery** in the requested country.
2. **Exact requested/country retailer recovery**.
3. **Exact global recovery** without identifier broadening.

Manufacturer priority is applied only after the manufacturer page proves the same submitted edition. A publisher page for a print ISBN cannot outrank an exact retailer page for a supplied eBook EAN.

## Architecture

```text
Input
→ deterministic identity interpretation
→ optional structured LLM hypothesis refinement
→ identifier-locked manufacturer-first search
→ candidate admission and URL canonicalization
→ bounded HTTP/JSON-LD/Book acquisition
→ exact identity and identifier conflict analysis
→ rendered-browser accessibility and content validation
→ manufacturer-first ranking among fully eligible mappings
→ exactly one selected URL or an explicit unresolved failure
→ JSON, CSV, Markdown and screenshot evidence artifacts
```

The observable trace exposes inputs, evidence, hypotheses, gate outcomes and selection judgments. It does not expose or fabricate hidden chain-of-thought.

## Start

```bash
cp .env.example .env
# Set SERPAPI_API_KEY and optional PCA_LLM_* values
./scripts/start.sh --build
```

The launcher prints the resolved service addresses. Defaults when available:

- UI: `http://127.0.0.1:8501`
- API health: `http://127.0.0.1:8788/health`
- API docs: `http://127.0.0.1:8788/docs`

The health endpoint exposes the active mapping policy and mandatory gate contract.

## Mapping console

The modern Streamlit console leads with the business result:

- exact product mapped: yes/no;
- supplied identifier verified: yes/no;
- rendered browser opens: yes/no;
- product content scrapable: yes/no;
- selected source role;
- one final URL.

Every discovery candidate remains inspectable with its exact-identity, identifier, direct-page, durability, browser, extraction and final-mapping gates.

See [Human-review UI and trace contract](docs/UI_REVIEW.md).

## API

```text
POST /v1/resolve
POST /v1/jobs
GET  /v1/jobs/{job_id}
GET  /v1/jobs/{job_id}/trace?after_sequence=<n>
GET  /v1/jobs/{job_id}/result
```

Example:

```bash
curl -X POST http://127.0.0.1:8788/v1/resolve \
  -H 'Content-Type: application/json' \
  -d '{
    "main_text": "MENSCH TÖTE DICH NICHT!",
    "country_code": "CH",
    "ean": "9783311706717",
    "language_code": "de",
    "feature_set": "toy"
  }'
```

## CLI

```bash
python -m pip install -e '.[dev]'

product-url resolve \
  --row-id BOOK-1 \
  --main-text 'MENSCH TÖTE DICH NICHT!' \
  --country-code CH \
  --ean 9783311706717 \
  --language-code de

product-url batch --input samples/products.csv --output data/results.csv
product-url benchmark --cases benchmark/cases.csv --outcomes benchmark/outcomes.csv --report benchmark/report.json
```

## Evidence artifacts

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

The evidence package records the submitted identifier, identifiers found on each page, browser final URL, accessibility, extracted text, source role, conflicts, blockers and the reason for final selection or rejection.

## Validation

```bash
python -m pip install -e '.[dev]'
./scripts/validate_release.sh
```

CI compiles all Python, validates JSON, shell and Docker Compose, rejects legacy/monkey-patch references, and runs the complete test suite on Python 3.10, 3.11 and 3.12.

## Documentation

- [Architecture and decision contract](docs/ARCHITECTURE.md)
- [Human-review UI and trace contract](docs/UI_REVIEW.md)
- [Operations](docs/OPERATIONS.md)
- [Release and benchmark gates](docs/RELEASE.md)
