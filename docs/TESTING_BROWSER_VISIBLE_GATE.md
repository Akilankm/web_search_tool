# Testing Notes — Browser-visible Gate

## What to test manually

Use a small CSV with at least three cases:

| Case | Expected result |
|---|---|
| Exact product page | `USER_VISIBLE_PRODUCT_PAGE_CONFIRMED`, production-ready if all other gates pass. |
| URL that opens to homepage/category/search | `BROWSER_OPENABLE_BUT_REROUTED` or page-type-specific failure. |
| URL that opens to wrong product | `BROWSER_OPENABLE_BUT_WRONG_PRODUCT`. |

## Single-product notebook check

Open:

```text
notebooks/01_single_product_harness.ipynb
```

Verify these outputs:

```text
user_visible_product_match
user_visible_status
user_visible_page_type
user_visible_confidence
```

Verify row artifacts:

```text
output/<row_id>/browser_visible_verdicts.json
output/<row_id>/browser_visible/
```

## Batch notebook check

Open:

```text
notebooks/02_batch_product_harness.ipynb
```

Verify that production-ready filtering includes:

```text
production_url_ready = true
user_visible_product_match = true
needs_review = false
```

## Review notebook check

Open:

```text
notebooks/04_review_artifact_reader.ipynb
```

Set:

```python
ROW_ARTIFACT_DIR = PROJECT_ROOT / "output" / "<row_id>"
```

Verify visible verdict table and artifact list render correctly.

## Automated checks

```bash
PYTHONPATH=src python -m compileall -q src main.py batch_main.py
PYTHONPATH=src pytest -q tests/test_production_url_gate.py
PYTHONPATH=src pytest -q
```

## Dependency note

Browser screenshots require Playwright to be available in the environment. If Playwright is not installed, the verifier still produces deterministic visible-content verdicts from the page text and scrape metadata.
