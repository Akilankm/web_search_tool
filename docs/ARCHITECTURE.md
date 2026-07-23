# Notebook-first architecture

## Supported runtime

The supported execution environment is a Jupyter kernel running the resolver directly in one Python process.

```text
Notebook
  ├─ loads .env
  ├─ creates ProductInput
  └─ calls ProductURLOrchestrator.resolve()
       ├─ deterministic interpretation
       ├─ optional structured PCA LLM refinement
       ├─ SerpAPI search
       ├─ HTTP acquisition
       ├─ local Playwright rendering
       ├─ candidate evidence evaluation
       ├─ canonical acceptance policy
       └─ artifact writing
```

There is no UI service, API service, browser service, queue, polling layer, container network, host-port contract, event-loop patch, or compatibility shim.

## Module boundaries

| Module | Single responsibility |
|---|---|
| `models.py` | Immutable input, evidence, and output contracts |
| `config.py` | File and environment configuration |
| `interpretation.py` | Product identity extraction and hypotheses |
| `reasoning.py` | Optional structured PCA LLM refinement |
| `search.py` | Bounded search planning and SerpAPI calls |
| `acquisition.py` | HTTP and JSON-LD acquisition |
| `browser.py` | Local Playwright rendering |
| `evaluation.py` | Candidate evidence production |
| `policy.py` | Final acceptance, source priority, ranking, and delivery |
| `orchestrator.py` | Sequential execution of the above modules |
| `artifacts.py` | Auditable JSON, CSV, Markdown, and screenshots |

## No monkey patching

Jupyter normally owns an active asyncio event loop. The browser implementation does not patch that loop and does not use `nest_asyncio`.

When the resolver is called from a notebook, asynchronous Playwright work is executed in one isolated worker thread with its own event loop. In a normal Python process, it uses `asyncio.run()` directly.

## Decision boundary

`src/product_url_v2/policy.py` is the only module allowed to define:

- mandatory acceptance gates;
- mapping eligibility;
- browser candidate priority;
- source hierarchy;
- final candidate ranking;
- delivery status;
- final selected URL.

Search, acquisition, evaluation, browser, notebook, and artifact code may only produce or present evidence.

## Mandatory gates

A candidate is deliverable only when:

- identity is `EXACT`;
- a supplied EAN, GTIN, or ISBN is verified;
- the URL is a direct product page;
- the URL is durable;
- the page opens in local Playwright;
- rendered product text is scrapable;
- there are no product, edition, field, or URL-identifier conflicts.

Coding completeness, country confidence, and requested-retailer alignment are secondary review axes. They cannot rescue a candidate that fails a mandatory URL gate.

## Notebook outputs

The single-product notebook displays:

- final submission row;
- candidate acceptance table;
- identity signals;
- paid search actions;
- observable stage trace;
- evidence artifact paths;
- final acceptance assertion.

The batch notebook writes a checkpointed output CSV after every row.
