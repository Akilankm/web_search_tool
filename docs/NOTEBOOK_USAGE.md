# Notebook Usage and Result Contract

Use only:

```text
notebooks/01_run_product_evidence.ipynb
```

## Before opening the notebook

```bash
cp .env.example .env
# Replace placeholders.

mkdir -p inputs/private
cp /secure/location/toy_features.json inputs/private/toy_features.json

./scripts/azureml_startup.sh
```

For Azure ML mounted storage that cannot preserve mode `600`:

```bash
./scripts/azureml_startup.sh --allow-insecure-env-permissions
```

## Product input

```python
product = {
    "row_id": "TEST-001",
    "main_text": "Exact product identity text",
    "country_code": "CO",
    "retailer_name": "Mercado Libre",  # optional
    "ean": None,                       # optional; keep as text when supplied
    "language_code": None,
}
```

Required fields:

- `main_text`
- `country_code`

Optional fields:

- `row_id`
- `retailer_name`
- `ean`
- `language_code`

## Search behavior

Each product executes exactly three searches:

1. Requested retailer in the requested country, when a retailer is supplied.
2. Other retailers in the requested country, with the retailer constraint removed.
3. Global fallback, with country and retailer constraints removed.

When no retailer is supplied, stage 1 is the primary country search. EAN is optional throughout.

The result exposes:

```python
result["search"]["queries"]
result["search"]["stages"]
result["search"]["serpapi_requests_used"]  # exactly 3
```

## Final URL behavior

The notebook receives a non-null `primary_url` only after the same page passes all final gates:

- browser-openable;
- accessible without bypassing login/CAPTCHA/access controls;
- rendered exact-product match;
- product detail page;
- text-scrapable;
- all requested features present on that same URL;
- no feature conflicts;
- durable URL with no TTL, expiry, signature, token, temporary credential, or session parameter.

Inspect:

```python
result["primary_url_acceptance"]
```

A rejected candidate may still appear as a review reference, but it is not returned as `primary_url`.

## Running one product

```python
FEATURE_SET = "toy_features"
result = run_product(product, FEATURE_SET)
pprint(summarize_result(result))
```

Expected completed result:

```python
{
    "row_id": "TEST-001",
    "job_status": "COMPLETED",
    "coding_ready": True,
    "primary_url": "https://...",
    "serpapi_requests_used": 3,
    "selection_scope": "REQUESTED_RETAILER_COUNTRY",
    "strict_primary_url_accepted": True,
}
```

Expected strict rejection:

```python
{
    "row_id": "TEST-001",
    "job_status": "REVIEW_REQUIRED",
    "coding_ready": False,
    "primary_url": None,
    "serpapi_requests_used": 3,
    "strict_primary_url_accepted": False,
}
```

`REVIEW_REQUIRED` is a successful terminal workflow state. It means execution completed but no URL passed every mandatory final gate.

## Result schema

| Path | Meaning |
|---|---|
| `product.row_id` | Original row identifier |
| `job_status` | `COMPLETED` or `REVIEW_REQUIRED` |
| `coding_ready` | Strict primary URL acceptance result |
| `primary_url` | Accepted durable product URL or `null` |
| `supplementary_urls` | Review references when acceptance fails |
| `search.queries` | Executed search queries |
| `search.stages` | Stage name, scope, result count, and scrape count |
| `search.serpapi_requests_used` | Exactly three |
| `product_match.selection_scope` | Requested retailer/country, country alternative, or global |
| `primary_url_acceptance` | Browser, exact-product, feature, scrapability, and durability gates |
| `evidence_set` | Requested-feature coverage and conflicts |
| `feature_assessments` | Per-URL feature evidence |
| `browser_evidence` | Browser page and visual evidence |
| `artifact_dir` | Container artifact path |

Do not read stale top-level fields such as `result["row_id"]`, `result["status"]`, or `result["feature_evidence"]`.

## Investigation workflow

```python
pprint(result.get("search") or {})
pprint(result.get("product_match") or {})
pprint(result.get("primary_url_acceptance") or {})
pprint(result.get("evidence_set") or {})
pprint(result.get("feature_assessments") or [])
pprint(result.get("browser_evidence") or [])
```

The host artifact folder is:

```text
data/artifacts/<row_id>/
```

Important files:

```text
result.json
review.md
candidates.csv
feature_evidence.csv
primary_url_acceptance.json
orchestrated_result.json
```

`primary_url_acceptance.json` is the authoritative explanation for why the final URL was accepted or rejected.

## CSV batch

Expected columns:

```text
row_id,main_text,country_code,retailer_name,ean,language_code
```

Blank optional values become `None`. Keep EAN/GTIN columns formatted as text.

Batch summaries are written to:

```text
data/artifacts/notebook_batch_summary.csv
```

The summary includes the final status, URL, scope, three-credit usage, strict acceptance outcome, missing features, and artifact path.
