# Structured No-Safe-URL Review Outcome

## Purpose

A bounded web-search workflow can legitimately finish without finding a safe direct product-page URL. That condition must not be confused with either:

- a successful URL resolution; or
- an internal software failure.

The production contract is:

```text
No safe direct URL after bounded search
≠ fabricated URL
≠ successful completion
≠ unhandled exception
= structured REVIEW_REQUIRED outcome
```

## Runtime contract

```text
belief-url-resolution-v7-structured-no-url-review
```

Required health capability:

```text
structured_no_url_review_outcome=true
```

The single and batch notebooks reject stale agents that do not expose this capability.

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

A blank URL is accepted by the notebook result validator only when this complete structured contract is present. Any other blank or contradictory URL response is a hard `INCONSISTENT_URL_DELIVERY_RESULT` contract failure.

## Why this is not `FAILED`

`FAILED` is reserved for genuine technical or contract defects, such as:

- invalid mandatory input;
- missing configuration or credentials;
- stale/incompatible runtime;
- unavailable required service;
- unhandled software exception;
- malformed response schema;
- a response claiming `COMPLETED` without a delivered URL.

Search exhaustion is different. The system may have worked correctly, consumed the configured three credits, rejected unsafe or indirect results, and concluded that no safe direct page was found within the policy boundary.

## No-fabrication boundary

The system must never convert the following into a successful product URL merely to avoid an empty result:

- search-result pages;
- category or collection pages;
- homepages;
- social/community pages;
- PDFs or media documents;
- Google/SerpAPI intermediary links;
- fabricated URLs;
- unverified sibling variants or pack forms.

When none of the discovered candidates is safely deliverable, the correct result is explicit human review.

## Preserved evidence

The no-safe-URL result preserves all available recorded evidence:

- submitted product input;
- product interpretation and unresolved uncertainty;
- manufacturer, country/retailer and global search stages;
- exact queries, engines and scopes;
- credits used;
- result and candidate counts;
- candidate investigations and rejection evidence;
- browser and visual evidence when available;
- requested-feature assessments;
- deterministic acceptance-gate outcome;
- recommended human next actions.

## Generated artifacts

The normal product artifact remains available and additionally includes:

```text
data/artifacts/<row_id>/
├── no_url_resolution.json
├── business_judgement_review.md
├── mandatory_url_delivery.json
├── primary_url_acceptance.json
├── source_selection.json
└── orchestrated_result.json
```

`business_judgement_review.md` begins with a controlled-outcome banner and records that:

- the URL was not found within the bounded policy;
- no URL was fabricated;
- the run is `REVIEW_REQUIRED`;
- the human should review identifiers, search stages and rejected candidates.

## Single-product notebook behavior

`notebooks/01_single_product.ipynb` does not raise a traceback for this condition. It displays:

```text
job_status
resolution_outcome_code
resolution_message
url_delivered
search_credits_used
suggested_next_actions
artifact paths
```

The reviewer can continue directly into the decision trace and artifact diagnostics.

## Batch behavior

A no-safe-URL row remains in `batch_results.csv` as `REVIEW_REQUIRED`. It is not moved to `batch_failures.csv`, because the row did not experience a technical execution failure.

The batch continues processing the remaining products and preserves the full artifact directory for the unresolved row.

## Suggested human actions

The structured result recommends evidence-driven next steps rather than automatically spending more credits:

1. Verify or add EAN/GTIN when available.
2. Verify the main text, exact model, variant and pack form.
3. Supply the expected retailer or a known candidate URL when available.
4. Inspect the three search-stage queries and rejected candidates.
5. Expand the search budget or add a search source only through an explicit policy change.

## Governance meaning

`NO_SAFE_DIRECT_PRODUCT_URL_FOUND` means:

> No safe direct product-page URL was found within the configured bounded search and acceptance policy.

It does **not** mean:

> No URL exists anywhere on the internet.

This distinction must remain explicit in management reporting, KPIs and human review.
