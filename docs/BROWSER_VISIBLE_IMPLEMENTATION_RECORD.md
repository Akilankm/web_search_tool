# Browser-visible Gate Implementation Record

## Implementation date

2026-07-01

## Problem addressed

The previous production URL gate could treat a URL as browser-openable while the page visible to a normal user was not the intended product.

Observed failure mode:

```text
URL opens in browser
but visible content is homepage/category/search/login/consent/wrong product/reroute
```

This is not a URL syntax failure. It is a user-visible content failure.

## Business rule implemented

```text
A champion survives only when:
1. the URL opens,
2. the browser-visible page is a product page,
3. the visible content matches the intended product,
4. the page is not visibly rerouted/substituted/blocked,
5. the normal production URL and champion confirmation gates also pass.
```

## Code implemented

| Area | File | Change |
|---|---|---|
| New verifier | `src/product_evidence_harness/browser_visible.py` | Adds browser-visible capture, deterministic visible-content verification, optional LLM/vision verdict, and artifacts. |
| Config | `src/product_evidence_harness/config.py` | Adds browser-visible config and env flags. |
| Production gate | `src/product_evidence_harness/production_url.py` | Requires visible-product verdict when configured. |
| Base harness | `src/product_evidence_harness/pipeline.py` | Runs visible verification before production URL enforcement. |
| Tournament harness | `src/product_evidence_harness/tournament_pipeline.py` | Applies visible gate before final champion acceptance. |
| Package exports | `src/product_evidence_harness/__init__.py` | Exports verifier/verdict/config classes. |
| Review packet | `src/product_evidence_harness/review_artifacts.py` | Adds visible verdict fields to summary, JSON, and candidate CSV. |
| Tests | `tests/test_production_url_gate.py` | Adds regression for browser-openable wrong visible content. |

## New configuration

```env
PRODUCT_HARNESS_BROWSER_VISIBLE_VERIFY=true
PRODUCT_HARNESS_REQUIRE_BROWSER_VISIBLE_PRODUCT_CONTENT=true
PRODUCT_HARNESS_BROWSER_VISIBLE_CAPTURE=true
PRODUCT_HARNESS_BROWSER_VISIBLE_TOP_K=5
PRODUCT_HARNESS_BROWSER_VISIBLE_TIMEOUT_MS=45000
PRODUCT_HARNESS_BROWSER_VISIBLE_WAIT_MS=1500
PRODUCT_HARNESS_BROWSER_VISIBLE_LLM=false
PRODUCT_HARNESS_BROWSER_VISIBLE_MIN_LLM_CONFIDENCE=0.70
```

## New artifacts

```text
output/<row_id>/
├── browser_visible_verdicts.json
└── browser_visible/
    ├── <candidate>_browser_preview.png
    ├── <candidate>_visible_text.txt
    ├── <candidate>_resolved_url.txt
    ├── <candidate>_browser_visible_verdict.json
    └── <candidate>_browser_visible_verdict.md
```

## New statuses

```text
USER_VISIBLE_PRODUCT_PAGE_CONFIRMED
BROWSER_VISIBLE_PRODUCT_CONTENT_NOT_VERIFIED_NEEDS_REVIEW
BROWSER_OPENABLE_BUT_REROUTED
BROWSER_OPENABLE_BUT_WRONG_PRODUCT
BROWSER_OPENABLE_BUT_NOT_PRODUCT_PAGE
BROWSER_OPENABLE_BUT_CONSENT_WALL
BROWSER_OPENABLE_BUT_LOGIN_WALL
BROWSER_OPENABLE_BUT_CATEGORY_PAGE
BROWSER_OPENABLE_BUT_SEARCH_RESULTS_PAGE
BROWSER_OPENABLE_BUT_ACCESS_BLOCKED
BROWSER_OPENABLE_BUT_VISIBLE_CONTENT_INSUFFICIENT
BROWSER_VISIBLE_VERIFICATION_FAILED_NEEDS_REVIEW
NO_BROWSER_VISIBLE_PRODUCTION_READY_TOURNAMENT_CHAMPION
```

## Notebook updates

| Notebook | Update |
|---|---|
| `notebooks/01_single_product_harness.ipynb` | Shows visible gate config, visible status, visible artifact table, and stronger handoff rule. |
| `notebooks/02_batch_product_harness.ipynb` | Adds visible gate columns and visible-aware production-ready filtering. |
| `notebooks/04_review_artifact_reader.ipynb` | Reads and displays browser-visible verdicts and browser-visible artifacts. |

## Documentation updates

| Document | Update |
|---|---|
| `README.md` | Adds visible gate to architecture, handoff policy, config, and output contract. |
| `docs/BROWSER_VISIBLE_PRODUCT_GATE.md` | New full contract. |
| `docs/BROWSER_VISIBLE_IMPLEMENTATION_RECORD.md` | This implementation record. |
| `docs/DECISION_CONTRACTS.md` | Adds fields/statuses and handoff rules. |
| `docs/ARTIFACT_GUIDE.md` | Adds row artifacts and review workflow. |
| `docs/README.md` | Adds documentation index entry. |

## Validation added

Regression test added:

```text
test_browser_visible_gate_blocks_openable_wrong_visible_content
```

It proves that a URL can be browser-openable and exact by scrape evidence, but still blocked when visible content is wrong.

## Validation not run here

Full test execution was not run in this environment. Recommended checks:

```bash
PYTHONPATH=src python -m compileall -q src main.py batch_main.py
PYTHONPATH=src pytest -q
```
