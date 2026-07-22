# Release and benchmark gates

Unit tests prove contracts; they do not prove product quality. Production cutover requires a frozen, representative product benchmark.

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
