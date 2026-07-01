# Product Evidence Harness

The Product Evidence Harness turns product web search into verified, auditable, product-coding-ready evidence.

It is a controlled decision pipeline, not a simple scraper or loose search utility.

```text
Input product identity
  -> candidate URL discovery
  -> evidence extraction
  -> identity verification
  -> rendered page relevance validation
  -> production champion gate
  -> concise review artifacts
  -> product-coding evidence
```

## Canonical documentation

All detailed documentation is consolidated here:

```text
docs/README.md
```

Older specialized docs were removed to avoid stale or conflicting references. Use `docs/README.md` as the source of truth for:

```text
notebook workflow
input contract
production URL contract
rendered-page gate
safe review fallback behavior
CSV/output fields
row artifact packet
validation commands
```

## Start with notebooks

| Notebook | Use when | Output |
|---|---|---|
| `notebooks/00_notebook_gateway.ipynb` | You are new to the repo. | Choose the right workflow. |
| `notebooks/01_single_product_harness.ipynb` | Test one product end to end. | Champion URL decision, rendered-page gate, production gate, review packet. |
| `notebooks/02_batch_product_harness.ipynb` | Run many products. | `final_submission.csv`, `review_queue.csv`, metrics, row artifacts. |
| `notebooks/03_offline_product_artifact.ipynb` | Capture local/offline evidence for a confirmed champion. | `offline_page.html` and local assets. |

## High-stakes handoff rule

Use automated browser-opening, scraping, or product-coding handoff only when:

```text
product_url is not blank
production_url_ready = true
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
browser_openable = true
rendered_page_check_passed = true
highly_scrapable = true
exact_product_url_match = true
champion_confirmation.passed = true
champion_confirmation.success_count = champion_confirmation.required_successes
needs_review = false
```

Rows outside this filter are review-only. Hard-rejected candidates remain in `candidate_decisions.csv`; they must not be promoted into selected evidence.

## Minimal single-product usage

```python
from product_evidence_harness import HarnessConfig, ProductEvidenceHarness, ProductQuery, SerpAPIConfig, ProductionURLGate

product = ProductQuery(
    row_id="CO-ML-0001",
    main_text="PUT PRODUCT TEXT HERE",
    country_code="CO",
    ean="",
    retailer_name="Mercado Libre",
)

config = HarnessConfig.from_env(".env")
serp_config = SerpAPIConfig.from_env(country_code=product.country_code, language_code="es")
harness = ProductEvidenceHarness(serp_config=serp_config, config=config)
trace = harness.run(product, return_trace=True)

match = trace.best_match
tournament = getattr(trace.state, "tournament_result", None)
confirmation = getattr(tournament, "champion_confirmation", None) if tournament else None
production = ProductionURLGate().assess_url_in_state(trace.state, match.product_url or "")

print(match.product_url)
print(production.to_dict() if production else "No production assessment")
print(confirmation.to_dict() if confirmation else "No champion confirmation")
```

## Batch usage

```bash
python batch_main.py \
  --input data/products.xlsx \
  --output outputs/final_submission.csv \
  --workers 4
```

## Validation

```bash
PYTHONPATH=src python -m compileall -q src main.py batch_main.py
PYTHONPATH=src pytest -q tests/test_production_url_gate.py
PYTHONPATH=src pytest -q tests/test_champion_contract.py
PYTHONPATH=src pytest -q
```

## Import path note

This project uses a standard `src/` package layout. In notebooks, add `<repo>/src` to `sys.path`, then import with `product_evidence_harness`.
