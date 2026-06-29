# Scrapability and Import Fix PR

## Summary

This branch fixes two blocking issues found during the audit:

1. Notebook/runtime imports can fail with `ModuleNotFoundError: No module named 'src'` because generated internal modules still use legacy `src.product_evidence_harness` imports while notebooks add only `<repo>/src` to `sys.path`.
2. The submission-facing `product_url` could previously be populated from a best-available candidate even when that candidate was not scrape-usable product-page evidence.

## Changes

- Added a temporary compatibility namespace under `src/src/` so legacy `src.product_evidence_harness` imports resolve when only `<repo>/src` is on `sys.path`.
- Added an operational URL guard in `ProductEvidenceHarness` so non-scrapable or non-product-page best-available candidates are moved to `best_reference_url` instead of being emitted as `product_url`.
- Increased the default candidate pool to `300` and exposed `PRODUCT_HARNESS_MAX_CANDIDATE_POOL` so high-yield SerpAPI calls do not discard candidates before crawl4ai validation.
- Updated import-path regression tests to verify both public package imports and the temporary legacy namespace bridge.
- Added regression tests for the `product_url` scrapability gate.

## Notes

The compatibility namespace is a bridge, not the final desired state. A future cleanup should mechanically replace all internal `src.product_evidence_harness` imports with `product_evidence_harness` once the codebase is ready for a larger import-only patch.
