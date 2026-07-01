# Product Evidence Harness Documentation

This is the single canonical documentation page for the Product Evidence Harness.

The root `README.md` is the short entrypoint. This file is the complete operating reference.

---

## 1. What this system does

The Product Evidence Harness turns product web search into verified, auditable, product-coding-ready evidence.

It is not a simple scraper and it is not a loose search utility. It is a controlled decision pipeline:

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

The core business problem is that a URL can be easy to discover but still be wrong, weak, blocked, non-product, or unrelated to the intended product. This harness makes those differences explicit.

---

## 2. Start with notebooks

Users should start from notebooks, not from `src/`.

| Notebook | Use when | Output |
|---|---|---|
| `notebooks/00_notebook_gateway.ipynb` | You are new to the repo. | Which notebook/workflow to use. |
| `notebooks/01_single_product_harness.ipynb` | You want to test one product end to end. | Champion URL decision, rendered-page gate, production gate, review packet. |
| `notebooks/02_batch_product_harness.ipynb` | You want to run many products. | `final_submission.csv`, `review_queue.csv`, metrics, row artifacts. |
| `notebooks/03_offline_product_artifact.ipynb` | You already have a confirmed champion and need local/offline evidence. | `offline_page.html` and local evidence assets. |

---

## 3. Inputs

| Field | Required | Purpose |
|---|---:|---|
| `row_id` | Recommended | Stable row/product identifier. |
| `main_text` | Yes | Primary product identity text. |
| `country_code` | Yes | Target market/country. |
| `ean` / `gtin` | No | Strong identity anchor when available. Kept as string. |
| `retailer_name` | No | Preferred first evidence source. |
| `language_code` | No | Optional search language override. |
| `region` | No | Optional market hint. |

EAN/GTIN values are read as strings. Invalid or corrupted EAN values are retained for diagnostics but are not treated as exact anchors.

---

## 4. Primary architecture

```text
Input product identity
  -> SerpAPI search fan-out
  -> candidate URL pool
  -> preflight ranking
  -> bounded tournament scraping
  -> evidence extraction
  -> identity / EAN / title / variant checks
  -> country / retailer checks
  -> scrapability / richness checks
  -> rendered page relevance check
  -> candidate scorecards
  -> champion candidate
  -> champion confirmation
  -> production URL gate
  -> final CSV + concise row artifact packet
```

Tournament mode is the default path. The older iterative loop is retained only for explicit debugging/A-B comparison.

```env
PRODUCT_HARNESS_ENABLE_TOURNAMENT_MODE=true
PRODUCT_HARNESS_TOURNAMENT_MAX_SERP_CREDITS=4
PRODUCT_HARNESS_TOURNAMENT_CANDIDATE_POOL=150
PRODUCT_HARNESS_TOURNAMENT_PREFLIGHT_TOP_K=60
PRODUCT_HARNESS_TOURNAMENT_BATCH_SIZE=20
PRODUCT_HARNESS_TOURNAMENT_MAX_BATCHES=3
```

The code clamps `PRODUCT_HARNESS_TOURNAMENT_MAX_SERP_CREDITS` to a maximum of `4`.

---

## 5. Final URL contract

The current contract is intentionally strict:

```text
product_url = production-ready champion only
best_available_url = safe review-only candidate only
candidate_decisions.csv = full candidate audit table, including rejected candidates
```

Hard rejected candidates must not be promoted into `product_url`, `best_available_url`, or selected evidence in `review_summary.md`.

If no safe candidate exists:

```text
product_url = blank
best_available_url = blank
url_decision_status = NO_SAFE_REVIEW_CANDIDATE
needs_review = true
```

Rejected URLs remain visible in `candidate_decisions.csv` for audit.

---

## 6. Production handoff rule

A row is safe for automated browser-opening, scraping, or product-coding handoff only when all of these are true:

```text
product_url is not blank
production_url_ready = true
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
browser_openable = true
rendered_page_check_passed = true
highly_scrapable = true
critical_product_evidence_complete = true
exact_product_url_match = true
champion_confirmation.passed = true
champion_confirmation.success_count = champion_confirmation.required_successes
needs_review = false
```

In plain terms:

```text
Champion = browser-openable
        + rendered product page visible
        + exact product identity validated
        + rich enough product evidence
        + scrapable
        + country/retailer policy acceptable
        + repeated champion confirmation passed
```

Rows outside this filter are review-only.

---

## 7. Rendered-page relevance gate

`browser_openable=true` is necessary but not sufficient.

A URL can open in a browser and still be wrong if it renders:

```text
homepage
category page
search result page
consent/intermediate page
login/access page
store selector
anti-bot/blocked page
empty or broken render
unrelated product content
```

The rendered gate uses rendered/scraped page evidence to answer:

```text
Does the user-visible page actually show the intended product content?
```

Important rendered fields:

```text
rendered_page_check_passed
rendered_page_type
rendered_product_visible
rendered_content_related
rendered_match_confidence
rendered_verdict
rendered_mismatch_reasons
rendered_visible_title
rendered_visible_product_name
rendered_screenshot_path
rendered_screenshot_captured
rendered_llm_used
```

Passing page types:

```text
PRODUCT_DETAIL_PAGE
PRODUCT_VARIANT_PAGE
```

Rendered failure statuses include:

```text
PRODUCT_URL_RENDERED_CONTENT_MISMATCH_NEEDS_REVIEW
PRODUCT_URL_RENDERED_HOMEPAGE_NEEDS_REVIEW
PRODUCT_URL_RENDERED_LISTING_OR_SEARCH_NEEDS_REVIEW
PRODUCT_URL_RENDERED_INTERSTITIAL_NEEDS_REVIEW
```

A candidate with `browser_openable=true` but `rendered_page_check_passed=false` cannot be production champion.

---

## 8. Champion confirmation

Tournament mode confirms the selected champion repeatedly before handoff.

Default requirement:

```text
champion_confirmation.required_attempts = 3
champion_confirmation.required_successes = 3
champion_confirmation.passed = true
champion_confirmation.final_url_stable = true
champion_confirmation.evidence_stable = true
```

These checks are not extra SerpAPI searches. They are post-selection confirmation scrapes/checks.

When deep tournament artifacts are enabled, confirmation details are written to:

```text
champion_confirmation.json
champion_confirmation.md
```

---

## 9. Outputs

### Batch-level outputs

```text
outputs/
├── final_submission.csv
├── review_queue.csv
├── batch_summary.md
└── metrics.json
```

### Default row packet

```text
output/<row_id>/
├── final_row.csv
├── review_summary.md
├── review_decision.json
├── candidate_decisions.csv
└── product_coding_input.json
```

Open `review_summary.md` first. It is the human-facing explanation of what was selected, why, how it was decided, what was rejected, and what to do next.

`candidate_decisions.csv` is the candidate audit table. A URL appearing there is not automatically selected evidence.

### Optional deep/debug artifacts

Deep artifacts are opt-in and should be enabled only for engineering/debugging:

```env
PRODUCT_HARNESS_WRITE_MARKDOWN_REPORTS=true
PRODUCT_HARNESS_WRITE_TRACE_JSON=true
PRODUCT_HARNESS_WRITE_DEBUG_CSVS=true
```

---

## 10. Important CSV fields

Inspect these first:

```text
row_id
main_text
country_code
retailer_name
ean
product_url
verified_exact_url
best_available_url
production_url_ready
production_url_status
browser_openable
rendered_page_check_passed
rendered_page_type
rendered_verdict
rendered_mismatch_reasons
highly_scrapable
exact_product_url_match
needs_review
confidence
quality_tier
failure_taxonomy
review_summary_path
candidate_decisions_path
product_coding_input_path
```

Ready filter:

```python
ready = df[
    df["product_url"].astype(str).str.strip().ne("")
    & df["production_url_ready"].astype(str).str.lower().isin(["true", "1", "yes"])
    & (df["production_url_status"] == "PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL")
    & df["browser_openable"].astype(str).str.lower().isin(["true", "1", "yes"])
    & df["rendered_page_check_passed"].astype(str).str.lower().isin(["true", "1", "yes"])
    & df["highly_scrapable"].astype(str).str.lower().isin(["true", "1", "yes"])
    & df["exact_product_url_match"].astype(str).str.lower().isin(["true", "1", "yes"])
    & ~df["needs_review"].astype(str).str.lower().isin(["true", "1", "yes"])
]
```

Review filter:

```python
review = df[
    df["needs_review"].astype(str).str.lower().isin(["true", "1", "yes"])
    | ~df["production_url_ready"].astype(str).str.lower().isin(["true", "1", "yes"])
    | ~df["rendered_page_check_passed"].astype(str).str.lower().isin(["true", "1", "yes"])
]
```

---

## 11. Key statuses

Production-ready:

```text
PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
```

Review/non-production:

```text
PRODUCT_URL_NOT_BROWSER_OPENABLE_NEEDS_REVIEW
PRODUCT_URL_RENDERED_CONTENT_MISMATCH_NEEDS_REVIEW
PRODUCT_URL_RENDERED_HOMEPAGE_NEEDS_REVIEW
PRODUCT_URL_RENDERED_LISTING_OR_SEARCH_NEEDS_REVIEW
PRODUCT_URL_RENDERED_INTERSTITIAL_NEEDS_REVIEW
PRODUCT_URL_CRITICAL_DETAILS_NOT_EXTRACTED_NEEDS_REVIEW
PRODUCT_URL_NOT_HIGHLY_SCRAPABLE_NEEDS_REVIEW
PRODUCT_URL_NOT_EXACT_MATCH_NEEDS_REVIEW
PRODUCT_URL_GLOBAL_OR_COUNTRY_MISMATCH_NEEDS_REVIEW
NO_SAFE_REVIEW_CANDIDATE
```

Champion confirmation:

```text
CHAMPION_CONFIRMATION_PASSED
CHAMPION_CONFIRMATION_FAILED
NO_CHAMPION_CANDIDATE_TO_CONFIRM
```

---

## 12. Optional offline artifact

Offline page capture is optional and separate from discovery.

Use only:

```text
notebooks/03_offline_product_artifact.ipynb
```

Flow:

```text
confirmed champion URL
  -> notebook 03
  -> live capture once
  -> local assets
  -> offline/offline_page.html
```

The live URL remains provenance. The offline artifact is used only when a workflow explicitly needs local evidence.

---

## 13. Minimal usage

Single product:

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
print("Review artifact: output/<row_id>/review_summary.md")
```

Batch:

```bash
python batch_main.py \
  --input data/products.xlsx \
  --output outputs/final_submission.csv \
  --workers 4
```

---

## 14. Validation commands

Run before release handoff:

```bash
PYTHONPATH=src python -m compileall -q src main.py batch_main.py
PYTHONPATH=src pytest -q tests/test_production_url_gate.py
PYTHONPATH=src pytest -q tests/test_champion_contract.py
PYTHONPATH=src pytest -q
```

---

## 15. Import path note

This project uses a standard `src/` package layout.

In notebooks, add `<repo>/src` to `sys.path`, then import:

```python
import product_evidence_harness
```

Do not import with:

```python
import src.product_evidence_harness
```
