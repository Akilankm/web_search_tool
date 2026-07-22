# Release and benchmark gates

Unit tests prove contracts; they do not prove product quality. Production cutover requires a frozen, representative product benchmark.

## Mandatory business invariant

Every run with at least one non-conflicting product-like external candidate must deliver a URL as `VERIFIED` or `REVIEW_REQUIRED`. A zero-confidence or incomplete-evidence candidate is not automatically wrong. `FAILED` is allowed only when no product-like URL exists or every candidate has an explicit wrong-product, non-product or transient/intermediary blocker.

The release suite must include a regression where seven candidates exist, page verification is incomplete and identity support is zero; the strongest URL must still be returned as `REVIEW_REQUIRED`.

## Required metrics

- URL delivery rate
- Exact URL top-1 accuracy
- Correct-product delivery rate
- Candidate recall@K
- Wrong-product escape rate
- Direct product-page rate
- Browser assessment coverage
- Human review acceptance rate
- Latency and cost per correct URL

## Default gates

| Metric | Gate |
|---|---:|
| URL delivery rate | ≥ 98% |
| Correct-product delivery rate | ≥ 95% |
| Candidate recall@K | ≥ 98% |
| Wrong-product escape rate | ≤ 1% |
| Direct product-page rate | ≥ 98% |

The benchmark must include EAN-present and EAN-absent items, partial/multilingual text, wrong variants, bundles/displays, unavailable local retailers, anti-bot pages and browser-unavailable conditions.
