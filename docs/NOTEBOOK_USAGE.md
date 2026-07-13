# Notebook Usage and Result Contract

This guide documents the supported notebook workflow and the exact result schema returned by the agent API.

## Supported notebook

Use only:

```text
notebooks/01_run_product_evidence.ipynb
```

The notebook is a thin API client. Product discovery, scraping, browser rendering, identity validation, evidence extraction, multimodal reasoning, and artifact generation run inside Docker Compose.

## Run sequence

1. Start the platform from the repository root.
2. Open the supported notebook.
3. Run the health-check cell.
4. Set `FEATURE_SET` to the private feature filename without `.json`.
5. Submit one product or a CSV batch.

Example:

```python
FEATURE_SET = "toy_features"

product = {
    "row_id": "TEST-001",
    "main_text": "BMW M3 WAGON HOT WHEELS ESCALA 1:64 MAINLINES 7CM LARGO - AZUL",
    "country_code": "CO",
    "retailer_name": "Mercado Libre",
    "ean": None,
    "language_code": "es",
}

result = run_product(product, FEATURE_SET)
pprint(summarize_result(result))
```

`main_text` and `country_code` are required. `retailer_name`, `ean`, and `language_code` are optional.

EAN/GTIN values must be supplied as strings so leading zeroes are not lost. Do not infer or add missing digits unless the identifier is independently confirmed from packaging or a trusted source.

## Terminal statuses

| Status | Meaning |
|---|---|
| `COMPLETED` | The workflow completed and the evidence set is coding-ready. |
| `REVIEW_REQUIRED` | The workflow completed, but identity or feature evidence is insufficient for automatic coding. |
| `FAILED` | The workflow encountered an execution error. |

`REVIEW_REQUIRED` is not a crash. It is a successful terminal state that requires human review.

## Result schema

The result endpoint returns an orchestrated payload with the following important fields:

| Path | Meaning |
|---|---|
| `product.row_id` | Original product row identifier. |
| `job_status` | `COMPLETED` or `REVIEW_REQUIRED`. |
| `coding_ready` | Whether the selected evidence set is sufficient for coding. |
| `primary_url` | Primary validated identity/evidence URL, or `null`. |
| `supplementary_urls` | Additional URLs selected to cover missing features. |
| `product_match` | Product URL decision, confidence, validation state, and best review URL. |
| `evidence_set` | Coverage, missing features, conflicts, and coding status. |
| `feature_assessments` | Per-URL, per-feature evidence assessments. |
| `browser_evidence` | Rendered-page, visual-asset, and screenshot evidence bundles. |
| `artifact_dir` | Container path such as `/data/artifacts/TEST-001`. |

The row identifier and workflow status are not top-level `row_id` and `status` fields. Correct access is:

```python
row_id = result.get("product", {}).get("row_id")
status = result.get("job_status")
feature_assessments = result.get("feature_assessments", [])
```

The notebook provides `summarize_result(result)` so callers do not need to manually navigate the nested payload.

## Artifact paths

The API returns the container path:

```text
/data/artifacts/<row_id>
```

The corresponding path inside the cloned repository is:

```text
data/artifacts/<row_id>/
```

The notebook provides `host_artifact_dir(result)` to resolve the repository-local path regardless of whether Jupyter starts from the repository root or the `notebooks/` directory.

Typical files:

```text
data/artifacts/<row_id>/
├── orchestrated_result.json
├── result.json
├── candidates.csv
├── feature_evidence.csv
├── review.md
└── CAND-*/browser/
```

## Investigating `REVIEW_REQUIRED`

Inspect these payloads first:

```python
pprint(result.get("product_match") or {})
pprint(result.get("evidence_set") or {})
pprint(result.get("feature_assessments") or [])
pprint(result.get("browser_evidence") or [])
```

Then inspect:

```text
data/artifacts/<row_id>/review.md
data/artifacts/<row_id>/candidates.csv
```

Important candidate fields include:

| Field | Meaning |
|---|---|
| `validation_status` | Overall candidate validation decision. |
| `identity_status` | Exact-product identity determination. |
| `ean_check` | Identifier agreement or conflict. |
| `title_check` | Product-title agreement. |
| `page_type` | Product page versus category, search, or unsupported page. |
| `scrapable` | Whether usable evidence was extracted. |
| `decision_reasons` | Rejection reasons, warnings, and ranking evidence. |

A missing `primary_url` means no candidate passed the configured identity and production gates. The best available review URL may still be present under `product_match.best_available_url`.

## CSV batch

Input columns:

```text
row_id,main_text,country_code,retailer_name,ean,language_code
```

The notebook writes the batch summary to:

```text
data/artifacts/notebook_batch_summary.csv
```

The summary includes `job_status`, `coding_ready`, the selected URLs, decision status, missing features, and the repository-local artifact directory.
