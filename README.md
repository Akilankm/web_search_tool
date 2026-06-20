# Serp Hybrid Product URL Finder

Notebook-first, importable product URL finder built for **business-grade
correctness**. For each product it discovers candidate URLs with SerpAPI,
validates them with Google AI Mode, scrapes the strongest ones with crawl4ai,
and then **verifies the scraped content is genuinely the requested product**
before any URL is allowed to be the answer.

A returned URL is guaranteed to be:

1. **Consumable** — crawl4ai actually scraped it and it returns real content.
2. **Correct** — its scraped content matches the requested product identity
   (same EAN/GTIN, same distinctive title, **same pack-size / variant**), and is
   not a different variant (e.g. `18 KS` vs `32 KS`), a similar-but-wrong
   product, or a soft-404 "product not found" page that still returns HTTP 200.
3. **Auditable** — confidence is decomposed into weighted components with a
   justification and every cap applied, and any high-confidence result is backed
   by hard evidence, so it can be submitted for downstream validation.

## Why this matters

Scrapability alone is **not** correctness. A page that loads with content can
still be the wrong variant or a soft-404. This project separates the two:

```text
scrapable  = the page loads and returns real content        (consumable)
verified   = the scraped content IS the requested product   (correct)
returned   = scrapable AND identity-verified                 (safe to use)
```

## Inputs

| Field           | Required | Purpose                                              |
| --------------- | -------- | ---------------------------------------------------- |
| `main_text`     | **yes**  | Product title/description. Drives discovery + title/pack-size verification. |
| `country_code`  | **yes**  | Target market (e.g. `CZ`, `DE`, `US`). Drives SerpAPI `gl`, query planning, country scoring. |
| `retailer_name` | optional | Preferred retailer. Biases selection when provided.  |
| `ean`           | optional | EAN/GTIN barcode. Strongest identity proof when provided. |

`main_text` and `country_code` are mandatory. `retailer_name` and `ean` are
optional and the pipeline works fully without them.

## Pipeline

```text
Organic Search #1  → exact identity candidates
Organic Search #2  → adaptive recall / retailer-scoped candidates
AI Mode #1         → validate candidate URLs with evidence + reasons
crawl4ai scrape    → fetch top candidates in a real browser
Identity verify    → EAN, pack-size, title tokens, page-type (soft-404) checks
Ranker             → confidence scoring; identity + scrapability are hard gates
AI Mode #2         → repair only when nothing verified / a variant conflict
Final output       → one URL: scraped, identity-verified, justified
```

## Identity verification

For every scraped page, `ProductIdentityVerifier` cross-checks four independent
axes and produces an `identity_status`:

| Check        | What it proves                                                    |
| ------------ | ----------------------------------------------------------------- |
| EAN / GTIN   | Authoritative. A *different* GTIN on the page is a hard reject.    |
| Pack size    | `18 KS` must not match `32 KS`. A different count is a hard reject. |
| Title tokens | Distinctive, diacritic-folded token overlap (`ZVÍŘÁTKY`↔`zviratky`). |
| Page type    | A real product detail page, not a soft-404 / category / homepage. |

`identity_status` ∈ `VERIFIED | PROBABLE | WEAK | MISMATCH | UNVERIFIED`.
Only `VERIFIED` (and, if enabled, `PROBABLE`) URLs are eligible to be returned.

## Output contract

`ProductURLMatch` (and `.to_dict()`) includes, in addition to the URL:

- `validation_status` — `VERIFIED | NEEDS_REVIEW | REJECTED | NO_MATCH`
- `identity_status`, `ean_check`, `title_check`, `quantity_check`, `page_type_check`
- `requested_quantity`, `page_quantity`
- `justification` — consolidated, human-readable evidence (always present)
- `blocking_reasons` — concrete reasons a candidate was rejected
- `confidence_breakdown` — every weighted component + every cap applied, with a
  base→final confidence trace (designed for submission/validation)

High confidence (`>= 0.75`) is only granted when backed by hard justification
(a confirmed EAN, or a matched pack-size together with a strong title match);
otherwise it is capped into the `NEEDS_REVIEW` band.

## Install

```bash
pdm install
cp ".env copy.example" .env   # or create .env
# add SERPAPI_API_KEY in .env

# Provision the crawl4ai browser (one time):
pdm run python -m playwright install chromium
# or: pdm run crawl4ai-setup
```

## Notebook usage

```text
notebooks/01_hybrid_product_url_finder.ipynb
```

```python
product = ProductQuery(
    row_id="demo-001",
    main_text="FIGURKA BAVYTOY TUBA SE ZVÍŘÁTKY 18 KS",
    country_code="CZ",        # required
    retailer_name="Alza",     # optional
    ean="6922256679066",      # optional
)

trace = pipeline.run(product, return_trace=True)
printer.print_match(trace.best_match)
printer.print_candidates(trace.scored_candidates)
printer.print_verification(trace.scored_candidates[0])  # identity + breakdown
```

## Importable library usage

```python
from serp_hybrid_url_finder import (
    HybridProductURLFinderPipeline,
    PipelineConfig,
    ProductQuery,
    SerpAPIConfig,
)

pipeline = HybridProductURLFinderPipeline(
    serp_config=SerpAPIConfig.from_env(),
    pipeline_config=PipelineConfig(),
)

match = pipeline.run(ProductQuery(main_text="LEGO Technic 42100", country_code="DE"))
print(match.product_url, match.validation_status, match.confidence)
print(match.justification)
```

## Key configuration (`PipelineConfig`)

| Knob | Default | Meaning |
| ---- | ------- | ------- |
| `require_scrapable_final` | `True` | Only return crawl4ai-scrapable URLs. |
| `require_identity_verified` | `True` | Only return identity-verified URLs. |
| `allow_probable_as_final` | `True` | Allow `PROBABLE` (review) matches, not just `VERIFIED`. |
| `high_confidence_requires_justification` | `True` | Cap unjustified high confidence. |
| `max_urls_to_scrape` | `6` | How many top candidates crawl4ai fetches per product. |
| `run_ai_repair` | `True` | Spend the 2nd AI Mode call when nothing verifies. |

## Important behavior

- crawl4ai + identity verification are the final gates: a URL is only returned
  after it has been scraped **and** proven to be the exact requested product.
- A different pack-size / variant, a conflicting GTIN, or a soft-404 page is
  rejected — the pipeline returns **no URL** rather than a wrong or unverified
  one. It never fabricates links.
- Every result carries a justification and an auditable confidence breakdown.
