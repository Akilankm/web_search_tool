# Architecture and exact mapping contract

## Canonical runtime

There is one runtime package: `product_url_v2`. It contains no legacy imports, compatibility wrappers, monkey patches or import-time mutation.

| Module | Responsibility |
|---|---|
| `models.py` | Immutable contracts, mapping eligibility and terminal invariants |
| `config.py` | Validated configuration with mandatory browser validation defaults |
| `interpretation.py` | Product normalization, exact anchors, variants and uncertainty |
| `reasoning.py` | Optional structured LLM refinement with anti-invention validation |
| `search.py` | Identifier-locked manufacturer-first search, parsing, canonicalization and admission |
| `acquisition.py` | Bounded HTTP acquisition plus JSON-LD Product/Book evidence extraction |
| `evaluation.py` | Exact identity, identifier conflict, source, page, browser and scrapability judgments |
| `browser.py` | Evidence-prioritized browser allocation and service client |
| `browser_service.py` | Playwright HTTP/render/error validation and screenshots |
| `trace.py` | Public gate evidence, strengths, risks and blockers |
| `ui_presenter.py` | Pure mapping-console table transformations |
| `orchestrator.py` | One explicit product-to-URL state flow |
| `artifacts.py` | Stable JSON, CSV, Markdown and screenshot artifacts |
| `api.py` | FastAPI jobs, health policy and incremental trace endpoint |
| `cli.py` | Single, batch and benchmark execution |
| `metrics.py` | Frozen benchmark metrics and release gates |

## Product-to-URL state flow

```text
Submitted identity
→ exact anchors and competing variants
→ identifier-locked manufacturer/publisher search
→ exact requested/country retailer recovery
→ exact global recovery
→ canonical direct-product candidates
→ HTTP and structured-data acquisition
→ page identity and identifier conflict evaluation
→ rendered-browser accessibility and content validation
→ manufacturer-first ranking among fully eligible mappings
→ one URL or an explicit unresolved failure
```

## Identifier-locked search

When an EAN, GTIN or ISBN is supplied, the identifier is never broadened away:

1. `EXACT_IDENTIFIER_MANUFACTURER`
2. `EXACT_IDENTIFIER_COUNTRY_RETAILER`
3. `EXACT_IDENTIFIER_GLOBAL_RECOVERY`

Every billable query contains the submitted identifier. Search snippets support discovery only; they cannot prove final identity.

When no identifier is supplied, the same source order is used with the strongest model, brand, pack, size and product-form anchors available.

## Source hierarchy

Source priority is evaluated only after all mandatory mapping gates pass:

1. local manufacturer or publisher;
2. global manufacturer or publisher;
3. requested retailer;
4. country retailer;
5. global retailer;
6. marketplace.

An authoritative page for a different edition is a mismatch, not a preferred result. For example, a publisher page containing a print ISBN cannot be selected for a supplied eBook EAN.

## Candidate admission versus final mapping

A product-like URL may enter acquisition as a discovery candidate. That does not make it deliverable.

The following remain audit-only until verified:

- URLs outside the acquisition budget;
- HTTP failures;
- anti-bot or consent surfaces;
- browser failures;
- pages without scrapable text;
- pages without the supplied identifier;
- pages with conflicting identifiers;
- redirected homepages, categories, login pages or search pages.

Tracking parameters including `srsltid`, UTM fields and click identifiers are removed during canonicalization.

## Mapping eligibility

A candidate is `mapping_eligible` only when all of these are true:

- identity status is `EXACT`;
- supplied EAN/GTIN/ISBN is verified from acquired or rendered page content;
- no page, field or URL-path identifier conflicts exist;
- direct product-page gate passes;
- durable URL gate passes;
- rendered browser accessibility passes;
- rendered product text is extractable;
- no hard URL blocker remains.

Coding completeness, country confidence and requested-retailer alignment remain separate secondary axes. They can produce `REVIEW_REQUIRED` only after the URL is already a valid exact mapping.

## Terminal decisions

| Status | Contract |
|---|---|
| `VERIFIED` | Exact, accessible and scrapable mapping; downstream coding evidence also passes |
| `REVIEW_REQUIRED` | Exact, accessible and scrapable mapping; only secondary coding or market evidence requires review |
| `FAILED` | No candidate passed the full exact mapping contract |
| `TECHNICAL_FAILURE` | Configuration or runtime defect prevented the campaign from reaching a valid decision |

The system never returns an inaccessible or unverified discovery URL merely to avoid `FAILED`.

## Observable decision trace

The trace contract is `observable-decision-trace-v1`. It exposes:

- submitted constraints and identifier lock;
- deterministic and validated inferred identity signals;
- each paid search query and purpose;
- acquired page status and redirects;
- identifiers found in page fields, text and URL paths;
- source role and authority;
- browser final URL, rendered title, text length, product controls and screenshot;
- exact identity, accessibility, scrapability and mapping-eligibility gates;
- final ranking and decision reasons.

It does not expose or fabricate hidden chain-of-thought.
