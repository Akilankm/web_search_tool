# Handoff Validation Checklist

This checklist summarizes the merged behavior after the latest safety fixes.

## Fixes covered

```text
PR #20: safe review fallback gate
PR #21: rendered-page relevance gate
```

## Safe review fallback rule

Hard-rejected candidates must not appear as selected evidence.

Correct behavior:

```text
hard rejected candidate
  -> candidate_decisions.csv only
  -> not product_url
  -> not best_available_url
  -> not selected evidence in review_summary.md
```

If no safe review candidate exists:

```text
product_url = blank
best_available_url = blank
url_decision_status = NO_SAFE_REVIEW_CANDIDATE
needs_review = true
```

## Rendered-page rule

A candidate that opens is not automatically production-ready.

Correct behavior:

```text
browser_openable = true
rendered_page_check_passed = false
production_url_ready = false
needs_review = true
```

Common rendered failures:

```text
homepage
category page
search result page
intermediate page
wrong visible product content
unrelated rendered content
```

## Production champion rule

A candidate can become the production champion only when:

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

## CSV columns to inspect

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

## Ready filter

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

## Human review rule

Open `review_summary.md` first. Then inspect `candidate_decisions.csv` for selected flag, validation status, identity status, exact product check, variant check, scrape success, product page flag, and reason.

A rejected URL can be useful evidence, but it is not selected evidence.

## Validation commands

```bash
PYTHONPATH=src python -m compileall -q src main.py batch_main.py
PYTHONPATH=src pytest -q tests/test_production_url_gate.py
PYTHONPATH=src pytest -q tests/test_champion_contract.py
PYTHONPATH=src pytest -q
```

## Validation boundary

The repository changes include regression tests and updated docs. The full test suite still needs to be run in the target development environment because this chat environment cannot execute the repository test suite directly.
