# Structured No-Safe-URL Outcome

## Purpose

A bounded web-search workflow can legitimately finish without finding a safe direct product-page URL. That condition must not be confused with successful URL resolution or an internal software failure.

```text
No safe direct URL after bounded search
≠ fabricated URL
≠ successful completion
≠ unhandled exception
= structured REVIEW_REQUIRED outcome
```

## Runtime contract

```text
belief-url-resolution-v9-product-evidence-ui
```

Required capabilities:

```text
structured_no_url_review_outcome=true
per_job_runtime_controls=true
```

The UI, single-product notebook and batch notebook reject incompatible agents before paid search.

## Result schema

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

A blank URL is valid only when the complete structured contract is present. Any other blank or contradictory response is a hard `INCONSISTENT_URL_DELIVERY_RESULT` failure.

## Why this is not `FAILED`

`FAILED` is reserved for invalid mandatory input, missing configuration, incompatible runtime, unavailable required service, unhandled exception, malformed schema or a response claiming `COMPLETED` without a delivered URL.

Search exhaustion is different. The system may have operated correctly, consumed the configured bounded credits, rejected unsafe or indirect candidates and concluded that no safe direct page was found within that policy boundary.

## No-fabrication boundary

The system must never promote the following merely to avoid an empty result:

```text
search-result pages
category or collection pages
homepages
social or community pages
PDFs or media documents
search-engine intermediary links
fabricated URLs
unverified sibling variants or pack forms
```

## Preserved evidence

The result preserves:

```text
submitted input
product interpretation and uncertainty
search stages, queries and engines
requested and effective runtime controls
credits used
candidate counts and rejection reasons
browser and visual evidence
feature assessments
acceptance gates
recommended follow-up actions
```

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

`business_judgement_review.md` records that no URL was fabricated and includes the final controlled no-URL judgment.

## Product Evidence Platform UI behavior

`apps/product_evidence_ui.py` displays this state as a review outcome, not a technical failure. It shows:

```text
job_status=REVIEW_REQUIRED
resolution_outcome.code=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
url_delivery.delivered=false
search credits used and effective limit
search and rejection trace
business judgment sequence
artifact downloads
```

The application continues through **Workflow and decision**, **Judgment sequence**, **Evidence**, **Runtime controls** and **Artifacts** views.

## Notebook behavior

`notebooks/01_single_product.ipynb` displays the reason, credits, follow-up actions and artifact paths, then continues into diagnostics.

A no-safe-URL batch row remains in `batch_results.csv` as `REVIEW_REQUIRED` and is not moved into `batch_failures.csv`.

## Follow-up actions

1. Verify or add EAN/GTIN when available.
2. Verify the main text, exact model, variant and pack form.
3. Supply the expected retailer or a known candidate URL when available.
4. Inspect search-stage queries and rejected candidates.
5. Change the bounded policy only through an explicit governed requirement.

## Governance meaning

`NO_SAFE_DIRECT_PRODUCT_URL_FOUND` means:

> No safe direct product-page URL was found within the configured bounded search and acceptance policy.

It does not mean:

> No URL exists anywhere on the internet.

This distinction must remain explicit in operational reporting and human review.

## Related documents

- [Feature reference](FEATURE_REFERENCE.md)
- [System workflow](SYSTEM_WORKFLOW.md)
- [Product Evidence Platform UI](PRODUCT_EVIDENCE_UI.md)
- [Final system contract](FINAL_SYSTEM_CONTRACT.md)
