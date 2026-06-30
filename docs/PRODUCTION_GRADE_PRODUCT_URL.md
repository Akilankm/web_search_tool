# Production-Grade Product URL Gate

## Requirement

The URL emitted in `product_url` is intended for two downstream teams:

1. a team that opens the URL manually in a browser
2. a team that scrapes the URL to collect complete product information

Because of that, the harness prefers a **production-grade product URL** over a merely discovered URL, and tournament mode also requires **champion confirmation** before handoff.

## Production-grade definition

A URL is production-grade only when it passes all of these gates:

```text
browser_openable = true
highly_scrapable = true
exact_product_url_match = true
country match is acceptable
no hard variant/EAN/product identity conflict
needs_review = false
```

### Browser-openable

The page must be reachable and not look like a homepage, soft-404, blocked page, or thin placeholder.

### Highly scrapable

The page must be scrape-usable, product-page-like, and rich enough for the downstream scraper/coding team. Evidence can include title, product name, JSON-LD/GTIN, specs, attributes, description, images, price, availability, or other structured product evidence.

### Exact product URL match

The page must be verified as the exact product, not just a sibling variant or related product. The gate requires deterministic verification and rejects hard conflicts such as variant conflict or blocking EAN conflict.

## Champion confirmation

In tournament mode, passing the production-grade URL gate is necessary but not sufficient for handoff. The selected champion candidate must also pass repeated confirmation.

Default requirement:

```text
champion_confirmation.required_attempts = 3
champion_confirmation.required_successes = 3
champion_confirmation.passed = true
champion_confirmation.final_url_stable = true
champion_confirmation.evidence_stable = true
```

The details are written to:

```text
champion_confirmation.json
champion_confirmation.md
```

## Final selection behavior

The harness applies three layers:

```text
Layer 1: production-grade URL promotion
Layer 2: champion confirmation gate
Layer 3: strict non-empty fallback URL policy for review-only candidates
```

If any candidate URL is production-grade and passes champion confirmation, it is promoted into `product_url` as the confirmed champion.

If no candidate is confirmed, the harness still preserves the strict non-empty business rule by emitting the best discovered fallback URL, but marks it clearly as non-production/review-only.

## Batch columns and row artifacts

`final_submission.csv` includes production URL fields such as:

```text
production_url_ready
production_url_status
browser_openable
highly_scrapable
exact_product_url_match
production_url_score
production_url_reasons
```

Champion confirmation details are available in row artifacts:

```text
output/<row_id>/champion_confirmation.json
output/<row_id>/champion_confirmation.md
```

## Status values

Production-ready status:

```text
PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
```

Champion confirmation statuses:

```text
CHAMPION_CONFIRMATION_PASSED
CHAMPION_CONFIRMATION_FAILED
NO_CHAMPION_CANDIDATE_TO_CONFIRM
```

Review / non-production statuses:

```text
PRODUCT_URL_NOT_BROWSER_OPENABLE_NEEDS_REVIEW
PRODUCT_URL_NOT_HIGHLY_SCRAPABLE_NEEDS_REVIEW
PRODUCT_URL_NOT_EXACT_MATCH_NEEDS_REVIEW
PRODUCT_URL_GLOBAL_OR_COUNTRY_MISMATCH_NEEDS_REVIEW
PRODUCT_URL_NOT_PRODUCTION_READY_NEEDS_REVIEW
```

Strict no-candidate status:

```text
STRICT_PRODUCT_URL_REQUIRED_BUT_NO_URL_CANDIDATE_AVAILABLE
```

## Operational interpretation

| Column / artifact | How to use it |
|---|---|
| `product_url` | Best URL emitted by the harness. |
| `production_url_ready=true` | Safe only when champion confirmation also passed. |
| `browser_openable=true` | Page is expected to open in a browser. |
| `highly_scrapable=true` | Page has scrape-usable product evidence. |
| `exact_product_url_match=true` | Page represents the exact product. |
| `production_url_status` | Final product URL readiness class. |
| `production_url_reasons` | Why a URL is not production-grade. |
| `champion_confirmation.json` | Repeated confirmation attempt details. |
| `product_coding_input_path` | Path to downstream product-coding handoff JSON. |

## High-stakes usage policy

For high-stakes production coding, treat rows as auto-usable only when:

```text
production_url_ready = true
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
champion_confirmation.passed = true
champion_confirmation.success_count = champion_confirmation.required_successes
needs_review = false
```

Rows that fail this combined gate still have a `product_url`, but they are review-only and should not be handed to the scraping/coding team as production-ready evidence.

## Notebook workflow

Use the notebooks for demonstration and verification:

```text
notebooks/01_single_product_harness.ipynb
notebooks/02_batch_product_harness.ipynb
```

The single-product notebook shows candidate-level production gate diagnostics and champion confirmation. The batch notebook shows the production-ready filter plus the row-level champion confirmation summary.

## Recommended team demo filter

In `outputs/final_submission.csv`, first filter:

```python
ready = df[
    (df["production_url_ready"].astype(str).str.lower().isin(["true", "1", "yes"]))
    & (df["production_url_status"] == "PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL")
    & (~df["needs_review"].astype(str).str.lower().isin(["true", "1", "yes"]))
]
```

Then verify each ready row's `output/<row_id>/champion_confirmation.json` has:

```text
passed = true
success_count = required_successes
```
