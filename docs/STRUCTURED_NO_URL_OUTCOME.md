# Structured No-Safe-URL Review Outcome

## Purpose

A bounded web-search workflow can legitimately finish without finding a safe direct product-page URL. That condition must not be confused with either a successful URL resolution or an internal software failure.

```text
No safe direct URL after bounded search
≠ fabricated URL
≠ successful completion
≠ unhandled exception
= structured REVIEW_REQUIRED outcome
```

## Runtime contract

```text
belief-url-resolution-v8-leadership-demo
```

Required capabilities:

```text
structured_no_url_review_outcome=true
leadership_demo_runtime_options=true
```

The Streamlit app, single-product notebook and batch notebook reject stale agents that do not expose the current runtime contract.

## Exact result schema

A controlled no-safe-URL result contains:

```json
{
  "job_status": "REVIEW_REQUIRED",
  "coding_ready": false,
  "primary_url": null,
  "primary_url_role": "NONE",
  "manufacturer_url": null,
  "retailer_url": null,
  "url_delivery": {
    "required": true,
    "delivered": false,
    "url": null,
    "strictly_verified": false,
    "status": "NO_SAFE_DIRECT_PRODUCT_URL_FOUND_AFTER_BOUNDED_SEARCH",
    "empty_url_is_success": false
  },
  "resolution_outcome": {
    "code": "NO_SAFE_DIRECT_PRODUCT_URL_FOUND",
    "category": "CONTROLLED_BUSINESS_NO_MATCH",
    "terminal_status": "REVIEW_REQUIRED",
    "url_fabricated": false,
    "search_budget_exhausted": true,
    "requires_human_review": true
  }
}
```

A blank URL is valid only when this complete structured contract is present. Any other blank or contradictory response is a hard `INCONSISTENT_URL_DELIVERY_RESULT` failure.

## Why this is not `FAILED`

`FAILED` is reserved for genuine defects such as invalid mandatory input, missing configuration, stale runtime, unavailable required service, unhandled exception, malformed schema or a response claiming `COMPLETED` without a delivered URL.

Search exhaustion is different. The system may have worked correctly, consumed the selected bounded credits, rejected unsafe or indirect results, and concluded that no safe direct page was found within that policy boundary.

## No-fabrication boundary

The system must never promote the following merely to avoid an empty result:

- search-result pages;
- category or collection pages;
- homepages;
- social/community pages;
- PDFs or media documents;
- Google/SerpAPI intermediary links;
- fabricated URLs;
- unverified sibling variants or pack forms.

## Preserved evidence

The result preserves submitted input, identity interpretation, uncertainty, search stages, queries, engines, selected/effective budget, credits used, candidate counts, rejected evidence, browser/visual evidence, feature assessments, acceptance gates and recommended human actions.

## Generated artifacts

```text
data/artifacts/<row_id>/
├── no_url_resolution.json
├── business_judgement_review.md
├── run_configuration.json
├── mandatory_url_delivery.json
├── primary_url_acceptance.json
├── source_selection.json
└── orchestrated_result.json
```

`business_judgement_review.md` begins with a controlled-outcome banner and records that no URL was fabricated.

## Leadership Streamlit behavior

`apps/leadership_demo.py` displays this condition as an amber business review outcome, not a red technical failure. It shows:

```text
job_status=REVIEW_REQUIRED
resolution_outcome.code=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
url_delivery.delivered=false
search credits used / selected limit
suggested next actions
judgment trace
artifact downloads
```

The app continues to the same Decision, Search & budget, Evidence & images, Judgment trace and Artifacts tabs used by URL-backed outcomes.

## Notebook behavior

`notebooks/01_single_product.ipynb` does not raise a traceback for this condition. It displays the reason, credits, next actions and artifact paths, then continues into diagnostics.

A no-safe-URL batch row remains in `batch_results.csv` as `REVIEW_REQUIRED` and is not moved into `batch_failures.csv`.

## Suggested human actions

1. Verify or add EAN/GTIN when available.
2. Verify the main text, exact model, variant and pack form.
3. Supply the expected retailer or a known candidate URL when available.
4. Inspect search-stage queries and rejected candidates.
5. Change the bounded policy only through an explicit governed decision.

## Governance meaning

`NO_SAFE_DIRECT_PRODUCT_URL_FOUND` means:

> No safe direct product-page URL was found within the configured bounded search and acceptance policy.

It does not mean:

> No URL exists anywhere on the internet.

This distinction must remain explicit in management reporting, KPIs and human review.
