# Architecture and decision contract

## Canonical packages

There is one runtime package: `product_url_v2`. It contains no legacy imports, compatibility wrappers, hardening modules, monkey patches or import-time mutation.

| Module | Responsibility |
|---|---|
| `models.py` | Immutable typed contracts and terminal invariants |
| `config.py` | Validated JSON/environment/per-request configuration |
| `interpretation.py` | Normalization, exact identity signals, uncertainty and deterministic hypotheses |
| `reasoning.py` | Optional structured PCA LLM refinement with strict anti-invention validation |
| `search.py` | SerpAPI planning, billable-request deduplication, parsing, URL admission and search progress events |
| `acquisition.py` | Bounded HTTP acquisition, JSON-LD extraction and acquisition progress events |
| `evaluation.py` | Identity, direct-page, source, country, retailer and coding judgments |
| `trace.py` | Public observable evidence and candidate-judgment summaries |
| `ui_presenter.py` | Pure UI table/stage/event transformations |
| `browser.py` | Browser allocation and service client |
| `browser_service.py` | Isolated Playwright renderer and screenshot service |
| `orchestrator.py` | One explicit end-to-end state flow and structured run-event emission |
| `artifacts.py` | Stable machine-readable and reviewer-readable artifacts |
| `api.py` | FastAPI health, synchronous jobs and incremental trace endpoint |
| `cli.py` | Single and batch execution |
| `metrics.py` | Frozen-benchmark metrics and release gates |

## Observable decision trace

The trace contract is `observable-decision-trace-v1`.

It may expose:

- submitted product constraints;
- deterministic identity signals;
- LLM-derived hypotheses that pass anti-invention validation;
- unresolved discriminators and negative constraints;
- each paid search action and its declared purpose;
- retained external sources and structural URL admission;
- fetch, structured-data and browser evidence;
- independent candidate gates;
- explicit strengths, risks, blockers and final selection reasons.

It must not claim to expose hidden chain-of-thought. The trace is a structured audit of observable system state and judgment inputs.

Jobs persist every `RunEvent` in sequence. The API exposes incremental retrieval through:

```text
GET /v1/jobs/{job_id}/trace?after_sequence=<last-consumed-sequence>
```

The final `result.json` contains the complete event sequence for replay and audit.

## Search budget

1. **Establish identity** using EAN/GTIN, model codes and exact submitted text.
2. **Resolve the highest-risk uncertainty**, such as single pack versus bundle/display.
3. **Mandatory URL recovery** using a fresh product entity or AI Mode cited-source recovery.

Duplicate identity is calculated from the actual billable request. Reusing an Immersive Product token is duplicate regardless of a descriptive country/global scope.

## Candidate admission

All external observations remain in the search artifact. Only structurally product-like external URLs enter acquisition. Homepages, search/category pages, documents, social/media URLs, Google redirects and SerpAPI intermediary URLs cannot become deliverable candidates.

## Candidate judgment

Each candidate is evaluated independently across:

- identity match and identity confidence;
- direct product-page evidence;
- URL durability;
- country-market alignment;
- requested-retailer alignment;
- rendered-browser usability;
- text extractability;
- coding-field completeness;
- source role and source authority;
- explicit conflicts and warnings.

A single weighted score cannot overwrite these axes.

## Delivery invariant

`VERIFIED` and `REVIEW_REQUIRED` always contain a direct URL. A URL can be suppressed only by explicit wrong-product evidence, explicit non-product-page evidence, transient/intermediary URL evidence, or complete absence of a direct candidate after recovery.
