# Offline Product Artifact Notebook-Only Access

Offline capture is an optional second-stage workflow and is intentionally separated from the primary product URL discovery flow.

## User-facing entrypoint

```text
notebooks/03_offline_product_artifact.ipynb
```

## Not part of primary flow

Offline capture is not part of:

```text
main.py
batch_main.py
notebooks/01_single_product_harness.ipynb
notebooks/02_batch_product_harness.ipynb
```

## Intended sequence

```text
1. Run product discovery.
2. Confirm champion URL.
3. Open notebooks/03_offline_product_artifact.ipynb.
4. Paste champion URL.
5. Generate offline/offline_page.html.
```
