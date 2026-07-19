# Notebook Usage and Diagnostic Contract

Use only:

```text
notebooks/01_run_product_evidence.ipynb
```

The notebook runs one product and exposes product interpretation, belief state, market route, paid search decisions, candidate evidence, browser investigation, and mandatory URL delivery.

## Azure ML setup

```bash
git checkout master
git pull origin master
cp .env.example .env
# Add real SerpAPI and enterprise LLM values.
./scripts/azureml_startup.sh
```

Open the notebook after the script reports that the platform is ready.

## Self-healing readiness cell

The first cell:

1. forces the repository-local package;
2. evicts stale Python modules;
3. discovers feature sets;
4. compares the notebook runtime contract with the running Docker agent;
5. verifies belief resolution, mandatory URL delivery, browser fallback, search, LLM, and browser capabilities;
6. rebuilds and restarts a missing or stale local stack before any paid SerpAPI call;
7. displays `platform_readiness_df` with recovery status and elapsed time.

The committed notebook defaults are:

```python
AUTO_RECOVER_PLATFORM = True
CLEAN_BUILD_ON_RECOVERY = True
```

Equivalent `.env` controls are:

```env
PRODUCT_HARNESS_NOTEBOOK_AUTO_RECOVER_PLATFORM=true
PRODUCT_HARNESS_NOTEBOOK_CLEAN_BUILD_ON_RECOVERY=true
```

A clean recovery executes:

```bash
./scripts/azureml_startup.sh --clean-build
```

This removes stale Compose containers, rebuilds agent and browser images without cache, recreates them, and verifies the exact runtime contract. Recovery happens before product submission, so it does not consume a SerpAPI credit.

Set `AUTO_RECOVER_PLATFORM = False` only when you want the readiness cell to fail and leave recovery to the terminal.

## Input

```python
FEATURE_SET = 'toy_features'
RUN_SINGLE_PRODUCT = False

product = {
    'row_id': 'TEST-001',
    'main_text': 'Vendor product main text',
    'country_code': 'CZ',
    'retailer_name': None,
    'ean': None,
    'language_code': None,
}
```

`main_text` and `country_code` are mandatory. EAN/GTIN remains text. Set `RUN_SINGLE_PRODUCT = True` only after replacing the sample input.

## Product-identification path

```text
deterministic parsing
→ no-web LLM interpretation
→ competing product hypotheses
→ uncertainty metrics
→ requested retailer, when provided
→ alternative retailer within country
→ global fallback
→ final browser-openable product URL
```

The result exposes `product_identification`, `search.market_decision_path`, and `url_delivery`.

## Mandatory URL contract

Every `COMPLETED` or `REVIEW_REQUIRED` run must deliver a real direct product URL in `primary_url` and the URL-delivery fields.

- `COMPLETED`: strict URL acceptance passed.
- `REVIEW_REQUIRED`: a real browser-openable review URL was delivered, but one or more strict gates require confirmation.
- `FAILED`: execution failed, including `MANDATORY_PRODUCT_URL_NOT_FOUND` when no safe direct product-page URL exists.

URL validation is centralized in `validate_result_contract`. The notebook no longer dumps thousands of characters of result JSON. A delivery failure reports the job status, delivery status, match reason, best available URL, and artifact directory.

## Main tables

| DataFrame | Purpose |
|---|---|
| `platform_readiness_df` | Runtime contract, recovery attempt, clean-build status and elapsed time |
| `product_identification_df` | Leading hypothesis, probability, margin, readiness, resolution |
| `hypotheses_df` | Competing product hypotheses |
| `uncertainties_df` | Decision-critical unresolved fields |
| `belief_updates_df` | Probability snapshots after evidence |
| `evidence_ledger_df` | Atomic evidence from pages |
| `url_delivery_df` | Mandatory URL and strict-verification status |
| `source_hierarchy_df` | Market/source target by SerpAPI credit |
| `search_actions_df` | Paid-credit decision trace |
| `search_engine_summary_df` | Search-engine yield |
| `search_handles_df` | Product tokens, IDs, image handles |
| `search_decision_rca_df` | Budget, planner, fallback and stopping RCA |
| `results_df` | One authoritative row per canonical URL |
| `agentic_df` | Browser investigations and deterministic fallback |
| `feature_evidence_df` | URL-feature evidence |
| `selection_rca_df` | Final URL decision RCA |

## Artifacts and export

```text
product_belief.json
product_understanding.md
market_decision_path.md
belief_updates.md
evidence_ledger.jsonl
adaptive_search_trace.json
mandatory_url_delivery.json
single_product_diagnostics.xlsx
```

The workbook includes platform readiness, belief, URL delivery, search, candidate, browser, feature, and selection tables.
