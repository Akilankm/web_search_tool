# Review Packet Example

This example shows the intended reviewer experience.

## Default row folder

```text
output/ROW-001/
├── final_row.csv
├── review_summary.md
├── review_decision.json
├── candidate_decisions.csv
└── product_coding_input.json
```

## Start here

Open:

```text
review_summary.md
```

It answers:

```text
What was selected?
Why was it selected?
How was it decided?
What did the model/detectors contribute?
What was rejected and why?
What should the reviewer do next?
```

## Example decision summary

| Field | Value |
|---|---|
| Decision | `ACCEPT_PRODUCTION_URL` |
| Selected URL | `https://retailer.example/product/123` |
| Status | `PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL` |
| Needs review | `False` |
| Confidence | `0.91` |

## Example rejected candidate table

| URL | Decision | Reason |
|---|---|---|
| `https://retailer.example/search?q=toy` | `REJECTED_OR_NOT_PROMOTED` | Listing/search page, not product detail page. |
| `https://other.example/product/variant` | `REJECTED_OR_NOT_PROMOTED` | Variant mismatch. |
| `https://brand.example/product-info` | `REJECTED_OR_NOT_PROMOTED` | Reference page, not retailer product page. |

## Notebook review

Use:

```text
notebooks/04_review_artifact_reader.ipynb
```

This notebook reads:

```text
review_decision.json
candidate_decisions.csv
review_summary.md
```

and renders the decision without requiring the team to browse every artifact manually.
