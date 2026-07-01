# PR Summary — Browser-visible Product Gate

## Summary

This PR adds a strict browser-visible product-content gate to prevent a URL from becoming champion simply because it opens in a browser.

The new gate verifies the page a user actually sees. If the URL opens but shows a homepage, category page, search result page, consent wall, login wall, access block, reroute, or wrong product, then it must not remain the production champion.

## Primary rule

```text
browser_openable is necessary but not sufficient.
```

A champion survives only if:

```text
browser_openable = true
user_visible_product_match = true
user_visible_status = USER_VISIBLE_PRODUCT_PAGE_CONFIRMED
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
champion_confirmation.passed = true
needs_review = false
```

## Major implementation areas

```text
src/product_evidence_harness/browser_visible.py
src/product_evidence_harness/production_url.py
src/product_evidence_harness/pipeline.py
src/product_evidence_harness/tournament_pipeline.py
src/product_evidence_harness/review_artifacts.py
```

## Major artifacts

```text
output/<row_id>/browser_visible_verdicts.json
output/<row_id>/browser_visible/<candidate>_browser_preview.png
output/<row_id>/browser_visible/<candidate>_visible_text.txt
output/<row_id>/browser_visible/<candidate>_resolved_url.txt
output/<row_id>/browser_visible/<candidate>_browser_visible_verdict.json
output/<row_id>/browser_visible/<candidate>_browser_visible_verdict.md
```

## Documentation

```text
docs/BROWSER_VISIBLE_PRODUCT_GATE.md
docs/BROWSER_VISIBLE_IMPLEMENTATION_RECORD.md
docs/DECISION_CONTRACTS.md
docs/ARTIFACT_GUIDE.md
docs/README.md
README.md
```

## Notebooks

```text
notebooks/01_single_product_harness.ipynb
notebooks/02_batch_product_harness.ipynb
notebooks/04_review_artifact_reader.ipynb
```

## Validation

Regression test added:

```text
tests/test_production_url_gate.py::test_browser_visible_gate_blocks_openable_wrong_visible_content
```

Full test suite was not run in this environment. Recommended:

```bash
PYTHONPATH=src python -m compileall -q src main.py batch_main.py
PYTHONPATH=src pytest -q
```
