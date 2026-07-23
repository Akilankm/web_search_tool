# Architecture and canonical acceptance contract

## Runtime boundary

There is one runtime package: `product_url_v2`. It contains no legacy imports, compatibility wrappers, monkey patches or import-time mutation.

| Module | Responsibility |
|---|---|
| `models.py` | Immutable data contracts and type invariants only |
| `config.py` | Validated configuration and browser-required defaults |
| `interpretation.py` | Product normalization, exact anchors, variants and uncertainty |
| `reasoning.py` | Optional structured LLM refinement with anti-invention validation |
| `search.py` | Identifier-locked manufacturer-first search, parsing and URL canonicalization |
| `acquisition.py` | Bounded HTTP acquisition and JSON-LD Product/Book extraction |
| `evaluation.py` | Evidence production: identity, identifiers, direct page, source and secondary gates |
| `browser.py` | Browser client and policy-driven recovery allocation |
| `browser_service.py` | Playwright render, HTTP/error validation, text and screenshot collection |
| `policy.py` | The only acceptance, source-priority, ranking and delivery decision boundary |
| `trace.py` | Observable policy verdicts and evidence summaries |
| `ui_presenter.py` | UI projections derived from the canonical verdict |
| `orchestrator.py` | Explicit evidence flow and policy invocation |
| `artifacts.py` | Stable JSON, CSV, Markdown and screenshot artifacts |
| `api.py` | Jobs, health, active policy metadata and incremental trace endpoint |
| `cli.py` | Single, batch and benchmark execution |
| `metrics.py` | Frozen benchmark metrics and release gates |

## State flow

```text
Submitted identity
→ deterministic and optional LLM interpretation
→ identifier-locked manufacturer or publisher search
→ exact retailer and global recovery
→ canonical direct-product candidates
→ HTTP and structured-data acquisition
→ evidence-only candidate evaluation
→ browser recovery and rendered evidence
→ product-url-acceptance-v1
→ source-priority ranking among accepted candidates
→ one final URL or explicit unresolved failure
```

## Decision ownership

Only `policy.py` may define:

- mandatory acceptance gates;
- browser precheck;
- browser candidate ranking;
- source hierarchy;
- final candidate ranking;
- delivery status and selected URL.

Every other module either produces evidence or consumes `AcceptanceVerdict`. No other layer may reconstruct “mapping eligible.”

## Identifier-locked search

When an EAN, GTIN or ISBN is supplied, the identifier is retained in every billable search:

1. `EXACT_IDENTIFIER_MANUFACTURER`
2. `EXACT_IDENTIFIER_COUNTRY_RETAILER`
3. `EXACT_IDENTIFIER_GLOBAL_RECOVERY`

Search snippets support discovery only. They cannot prove exact identity.

## Evidence and browser recovery

HTTP acquisition is not the final acceptance boundary. JavaScript-rendered content may expose an identifier or product details that are absent from static HTML.

A candidate may proceed to browser validation when page-only evidence is incomplete. It cannot proceed when there is an explicit product/edition mismatch, conflicting identifier, transient URL or non-product result.

After browser rendering, the evaluator recomputes identity, direct-page, durability and scrapability evidence. The policy then makes the final decision.

## Source classification and hierarchy

Source role is inferred from domain/entity evidence, not from the search query that discovered the page. A retailer returned by a manufacturer-focused query remains a retailer.

The source hierarchy is defined once in `policy.py`:

1. local manufacturer or publisher;
2. global manufacturer or publisher;
3. requested retailer;
4. country retailer;
5. global retailer;
6. marketplace;
7. unknown.

Priority is applied only among candidates that already pass every mandatory gate. An authoritative page for a different edition is rejected.

## Mandatory acceptance gates

`product-url-acceptance-v1` requires:

- exact identity;
- supplied identifier verified when present;
- direct product-detail page;
- durable canonical URL;
- rendered-browser accessibility;
- scrapable rendered product content;
- no identity or edition conflicts.

Coding completeness, country alignment and requested-retailer alignment are secondary. They may produce `REVIEW_REQUIRED` only after the URL passes all mandatory gates.

Free-form warnings and explanatory messages never determine status.

## Terminal decisions

| Status | Contract |
|---|---|
| `VERIFIED` | Every mandatory gate and downstream coding evidence pass, with no secondary review reason |
| `REVIEW_REQUIRED` | Every mandatory gate passes; only secondary evidence needs review |
| `FAILED` | No candidate passes the canonical acceptance contract |
| `TECHNICAL_FAILURE` | Configuration or runtime failure prevents a valid decision |

The system never returns an inaccessible, unverified or conflicting discovery URL to avoid `FAILED`.

## Architecture enforcement

`scripts/check_architecture.py` fails CI when:

- acceptance functions or legacy eligibility properties are defined outside `policy.py`;
- source priority is defined outside `policy.py`;
- ad hoc hard-blocker state is reintroduced.

Acceptance-contract tests run before the full suite on every supported Python version.

## Observable trace

The trace exposes:

- submitted constraints and identifier lock;
- identity signals and hypotheses;
- each paid search action;
- page acquisition and redirects;
- identifiers found in page and URL evidence;
- source classification evidence;
- browser final URL, rendered text, controls and screenshot;
- the canonical acceptance policy and gate verdicts;
- final ranking and decision reasons.

It does not expose or fabricate hidden chain-of-thought.
