# Architecture and decision contract

## Canonical packages

There is one runtime package: `product_url_v2`. It contains no legacy imports, compatibility wrappers, hardening modules, monkey patches or import-time mutation.

| Module | Responsibility |
|---|---|
| `models.py` | Immutable typed contracts and terminal invariants |
| `config.py` | Validated JSON/environment/per-request configuration |
| `interpretation.py` | Normalization, exact identity signals, uncertainty and deterministic hypotheses |
| `reasoning.py` | Optional structured LLM refinement with strict anti-invention validation |
| `search.py` | SerpAPI planning, billable-request deduplication, parsing and URL admission |
| `acquisition.py` | Bounded HTTP acquisition, JSON-LD and visible-page extraction |
| `evaluation.py` | Identity, direct-page, source, country, retailer and coding judgments |
| `browser.py` | Browser allocation and service client |
| `browser_service.py` | Isolated Playwright renderer and screenshot service |
| `orchestrator.py` | One explicit end-to-end state flow |
| `artifacts.py` | Stable machine-readable and reviewer-readable artifacts |
| `api.py` | FastAPI health, synchronous and asynchronous endpoints |
| `cli.py` | Single and batch execution |
| `metrics.py` | Frozen-benchmark metrics and release gates |

## Search budget

1. **Establish identity** using EAN/GTIN, model codes and exact submitted text.
2. **Resolve the highest-risk uncertainty**, such as single pack versus bundle/display.
3. **Mandatory URL recovery** using a fresh product entity or AI Mode cited-source recovery.

Duplicate identity is calculated from the actual billable request. Reusing an Immersive Product token is duplicate regardless of a descriptive country/global scope.

## Candidate admission

All external observations remain in the search artifact. Only structurally product-like external URLs enter acquisition. Homepages, search/category pages, documents, social/media URLs, Google redirects and SerpAPI intermediary URLs cannot become deliverable candidates.

## Delivery invariant

`VERIFIED` and `REVIEW_REQUIRED` always contain a direct URL. A URL can be suppressed only by explicit wrong-product evidence, explicit non-product-page evidence, transient/intermediary URL evidence, or complete absence of a direct candidate after recovery.
