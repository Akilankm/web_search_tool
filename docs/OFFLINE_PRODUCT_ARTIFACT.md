# Offline Product Artifact

## Purpose

The live retailer page should be treated as a temporary discovery source, not the permanent downstream input.

The production handoff should become:

```text
confirmed champion URL
  -> live capture once
  -> validated offline product artifact
  -> downstream scraping and product coding from local files only
```

This avoids relying on the retailer page after discovery. A page can change, block, geo-route, expire, or render differently later; a validated offline artifact keeps the evidence stable and auditable.

## New artifact status

The offline capture builder produces this final status when the local evidence package is usable:

```text
PRODUCTION_READY_OFFLINE_ARTIFACT
```

Rows should be handed to the product coding engine only when the URL gate and offline artifact gate both pass:

```text
production_url_ready = true
needs_review = false
champion_confirmation.passed = true
offline_artifact_ready = true
offline_artifact_status = PRODUCTION_READY_OFFLINE_ARTIFACT
```

## Artifact layout

For each product row, the offline capture writes:

```text
<artifact_dir>/
├── offline_artifact_manifest.json
├── live_capture/
│   ├── raw.html
│   ├── rendered.html
│   ├── rendered_clean.html
│   └── page_text.txt
├── product_data/
│   ├── content.md
│   └── structured_product.json
├── offline/
│   ├── offline_page.html
│   ├── asset_map.json
│   └── assets/
│       ├── css/
│       ├── images/
│       ├── fonts/
│       └── other/
└── validation/
    └── offline_artifact_validation.json
```

## What is made offline

| Live page element | Offline handling |
|---|---|
| HTML | Saved as `live_capture/raw.html` and rewritten into `offline/offline_page.html`. |
| Images | Downloaded into `offline/assets/images/` and rewritten to local relative paths. |
| CSS | Downloaded into `offline/assets/css/` and linked locally. |
| CSS `url(...)` assets | Rewritten recursively where possible. |
| External scripts | Disabled by default and recorded as `data-offline-disabled`. |
| Inline scripts | Disabled by default, except JSON-LD product metadata. |
| Forms | Network-bound `action` attributes are disabled. |
| External links | Rewritten to `#offline-link-disabled` and preserved as `data-offline-href`. |
| Product text | Saved as `live_capture/page_text.txt` and `product_data/content.md`. |
| Structured evidence | Saved as `product_data/structured_product.json`. |
| Validation result | Saved as `validation/offline_artifact_validation.json`. |

## Network-blocking policy

`offline/offline_page.html` injects a Content Security Policy that blocks network calls:

```text
script-src 'none'
connect-src 'none'
frame-src 'none'
form-action 'none'
```

The offline validator also checks for remaining network-bound HTML references in critical attributes such as:

```text
src
href
poster
action
srcset
```

The artifact is not marked production-ready if such references remain.

## Usage

Standalone capture:

```bash
PYTHONPATH=src python scripts/capture_offline_page.py \
  --url "https://retailer.example/product-page" \
  --row-id "input-001" \
  --main-text "Toy product main text" \
  --country-code "CZ" \
  --retailer-name "Example Retailer" \
  --ean "1234567890123"
```

Programmatic capture:

```python
from pathlib import Path

from src.product_evidence_harness.contracts import ProductQuery
from src.product_evidence_harness.offline_capture import OfflineCaptureConfig, LivePageOfflineArtifactBuilder

product = ProductQuery(
    row_id="input-001",
    main_text="Toy product main text",
    country_code="CZ",
    retailer_name="Example Retailer",
    ean="1234567890123",
)

builder = LivePageOfflineArtifactBuilder(
    OfflineCaptureConfig(output_dir=Path("outputs/offline_artifacts"))
)
artifact = builder.capture_url("https://retailer.example/product-page", product=product)

print(artifact.status)
print(artifact.offline_html_path)
```

Open the generated file locally:

```text
offline/offline_page.html
```

## Important limitation

The offline artifact makes downstream processing reproducible after capture. It does not guarantee that the first live capture will always succeed. The first capture can still fail because of retailer downtime, anti-bot controls, geo routing, consent walls, or page removal.

The correct production guarantee is:

```text
Once a champion URL is captured and validated as PRODUCTION_READY_OFFLINE_ARTIFACT,
downstream scraping/coding can run from local evidence without revisiting the live page.
```
