# Optional Offline Product Artifact

## Purpose

Offline product artifact capture is an **optional second-stage workflow**. It is not part of the default tournament run and should not be treated as mandatory for every product.

Use it when you want to freeze a confirmed champion URL into a local, openable evidence package that can be inspected or reused without depending on the live retailer page.

The optional flow is:

```text
confirmed champion URL
  -> optional live capture once
  -> validated offline product artifact
  -> optional downstream scraping/coding from local files only
```

This avoids relying on the retailer page after discovery for workflows that require reproducibility. A page can change, block, geo-route, expire, or render differently later; a validated offline artifact keeps the captured evidence stable and auditable.

## Separation of concerns

Offline capture is deliberately isolated:

| Concern | Owner |
|---|---|
| Product discovery and champion selection | `notebooks/01_single_product_harness.ipynb` and `notebooks/02_batch_product_harness.ipynb` |
| Offline page freezing | `notebooks/03_offline_product_artifact.ipynb` only |
| Core implementation support | `src/product_evidence_harness/offline_capture.py` |

Offline capture is not wired into:

```text
main.py
batch_main.py
notebooks/01_single_product_harness.ipynb
notebooks/02_batch_product_harness.ipynb
top-level product_evidence_harness imports
```

## When to use it

Use offline capture when:

```text
you need to open the captured page later without internet
you need a stable audit artifact for manual review
you want product coding to consume frozen local evidence
you want to avoid repeat live retailer scraping after champion validation
```

Do not use it when the normal champion URL handoff is sufficient.

## New artifact status

The offline capture builder produces this status when the local evidence package is usable:

```text
PRODUCTION_READY_OFFLINE_ARTIFACT
```

For the optional offline handoff, use rows only when the URL gate and offline artifact gate both pass:

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

## User workflow

Offline capture is available through one dedicated notebook:

```text
notebooks/03_offline_product_artifact.ipynb
```

Use it as follows:

```text
1. Run the normal discovery notebook or batch flow.
2. Take only a confirmed champion URL.
3. Open notebooks/03_offline_product_artifact.ipynb.
4. Paste the champion URL and product metadata.
5. Run the capture cells.
6. Open offline/offline_page.html from the generated artifact folder.
7. Check validation/offline_artifact_validation.json.
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
offline-enabled downstream workflows can run from local evidence without revisiting the live page.
```
