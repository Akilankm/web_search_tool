# Exact Product Mapping Resolver

`product-url-resolver` maps the submitted product identity to one defensible direct product URL.

## Release

- Version: `1.3.0`
- Runtime contract: `product-url-resolver-v1`
- Acceptance policy: `product-url-acceptance-v1`
- Canonical policy module: `src/product_url_v2/policy.py`
- Observable trace: `observable-decision-trace-v1`
- Python: `3.10–3.12`
- Services: FastAPI resolver, Playwright browser validator, Streamlit mapping console

## Non-negotiable business contract

```text
Submitted product
→ exact product and edition identity
→ exact manufacturer or publisher first
→ exact retailer fallback
→ rendered browser accessibility
→ scrapable rendered product content
→ one final direct URL
```

A search result is discovery evidence. It is never a successful mapping by itself.

A candidate can be delivered only when all mandatory gates pass:

| Mandatory gate | Requirement |
|---|---|
| Exact identity | Product, edition, format, model, size, pack and variant must not conflict |
| Supplied identifier | The submitted EAN, GTIN or ISBN must be verified when provided |
| Direct page | Homepage, category, search, login, consent and intermediary pages are rejected |
| Durable URL | Tracking, redirect, session and transient URL forms are removed or rejected |
| Browser access | The final URL must render successfully in the browser service |
| Scrapability | Rendered product-specific content must be available downstream |
| Conflict-free | No contradictory identifier, edition or product evidence may survive |

`REVIEW_REQUIRED` is permitted only after the URL has already passed the complete product-mapping contract. Review may concern secondary coding, country or requested-retailer evidence. It is never a fallback for an inaccessible or uncertain URL.

## One authoritative decision boundary

All final acceptance behavior is implemented in:

```text
src/product_url_v2/policy.py
```

That module alone defines:

- mandatory acceptance gates;
- browser-recovery eligibility;
- manufacturer/retailer source priority;
- final candidate ranking;
- `VERIFIED`, `REVIEW_REQUIRED`, and `FAILED` selection.

`models.py` contains data contracts only. `evaluation.py` produces evidence only. Browser, trace, UI, API and artifacts consume the canonical policy verdict rather than recreating it.

An architecture guard fails CI if acceptance logic or source priority is reintroduced outside `policy.py`.

## Identifier-locked search

When an EAN, GTIN or ISBN is supplied, every paid search remains locked to it:

1. exact manufacturer or publisher discovery;
2. exact requested or country retailer recovery;
3. exact global recovery.

Manufacturer priority is applied only after the manufacturer page proves the same exact edition. A print publisher page cannot outrank an exact eBook retailer page for a supplied eBook EAN.

## Browser recovery

HTTP acquisition is evidence collection, not the final word. A JavaScript-rendered product page may expose the exact identifier only after browser rendering.

Therefore, incomplete HTTP identity evidence may proceed to the browser. Explicit mismatch, conflicting identifier, transient URL or non-product result cannot.

## Architecture

```text
Input
→ deterministic identity interpretation
→ optional structured LLM refinement
→ identifier-locked manufacturer-first search
→ URL canonicalization and candidate admission
→ HTTP / JSON-LD Product and Book evidence
→ evidence-only candidate evaluation
→ rendered-browser identity and scrapability recovery
→ canonical acceptance policy
→ manufacturer-first ranking among accepted candidates
→ one URL or an explicit unresolved failure
→ JSON, CSV, Markdown and screenshot evidence
```

The observable trace exposes inputs, evidence, hypotheses, gate outcomes and selection judgments. It does not expose or fabricate hidden chain-of-thought.

## Start

```bash
cp .env.example .env
# Set SERPAPI_API_KEY and optional PCA_LLM_* values
./scripts/start.sh --build
```

Default addresses when available:

- UI: `http://127.0.0.1:8501`
- API health: `http://127.0.0.1:8788/health`
- API docs: `http://127.0.0.1:8788/docs`

The health endpoint exposes `acceptance_policy`, `acceptance_policy_module`, source priority and browser status.

## API example

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

## Validation

```bash
python -m pip install -e '.[dev]'
./scripts/validate_release.sh
```

Release validation runs in this order:

1. Python compilation;
2. JSON, shell and Docker Compose validation;
3. canonical architecture guard;
4. acceptance-contract regression suite;
5. complete test suite;
6. legacy and monkey-patch reference rejection.

CI runs the full sequence on Python 3.10, 3.11 and 3.12.

## Documentation

- [Canonical acceptance contract](docs/ACCEPTANCE_CONTRACT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Human-review UI](docs/UI_REVIEW.md)
- [Operations](docs/OPERATIONS.md)
- [Release gates](docs/RELEASE.md)
