# Notebook Usage and Diagnostic Contract

Use only:

```text
notebooks/01_run_product_evidence.ipynb
```

The notebook runs one product and exposes product interpretation, belief state, the manufacturer-first search route, paid search decisions, candidate evidence, browser investigation, requested feature coverage, mandatory URL delivery, and the final manufacturer-versus-retailer authority decision.

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
2. evicts stale Python modules retained by Jupyter/Azure ML;
3. discovers committed feature sets;
4. compares the notebook runtime contract with the running Docker agent;
5. verifies belief resolution, manufacturer-first selection, mandatory URL delivery, browser fallback, search, LLM, and browser capabilities;
6. rebuilds and restarts a missing or stale local stack before any paid SerpAPI call;
7. displays `platform_readiness_df` with the runtime version, manufacturer-first capability, recovery status, clean-build status, and elapsed time.

The final runtime contract is:

```text
belief-url-resolution-v5-manufacturer-primary
```

The health response must include:

```text
manufacturer_first_primary_url=true
```

Notebook defaults:

```python
AUTO_RECOVER_PLATFORM = True
CLEAN_BUILD_ON_RECOVERY = True
```

Equivalent `.env` controls:

```env
PRODUCT_HARNESS_NOTEBOOK_AUTO_RECOVER_PLATFORM=true
PRODUCT_HARNESS_NOTEBOOK_CLEAN_BUILD_ON_RECOVERY=true
```

A clean recovery executes:

```bash
./scripts/azureml_startup.sh --clean-build
```

Recovery occurs before product submission and therefore consumes no SerpAPI credit.

Set `AUTO_RECOVER_PLATFORM = False` only when you intentionally want the readiness cell to fail and leave recovery to the terminal.

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

## Final product-resolution path

```text
deterministic parsing
→ no-web LLM interpretation
→ competing product hypotheses
→ uncertainty metrics
→ Credit 1: official manufacturer/brand product page
→ Credit 2: requested retailer or requested-country retailer
→ Credit 3: global manufacturer-or-retailer fallback
→ strict identity, browser, feature, scrapability, and durability gates
→ manufacturer-first authority ranking
→ primary_url + manufacturer_url + retailer_url
```

A retailer found during the manufacturer-targeted first credit is retained but cannot prematurely stop the search before the official source opportunity is evaluated.

## Stable result schema

The result exposes:

```text
product_identification
search.market_decision_path
primary_url
primary_url_role
manufacturer_url
retailer_url
source_selection
primary_url_acceptance
url_delivery
```

### Interpretation

- `primary_url` is the strongest product-truth page.
- `primary_url_role` identifies whether the selected page is an official manufacturer, retailer, marketplace, or other product source.
- `manufacturer_url` retains the strongest strictly qualified official manufacturer page.
- `retailer_url` retains the strongest strictly qualified commercial reference page.
- `source_selection` records why the manufacturer or retailer became primary.

A retailer becomes primary when the manufacturer page is absent, inaccessible, incomplete, non-product, transient, wrong-model, wrong-variant, wrong-pack, or missing requested feature evidence.

## Mandatory URL contract

Every `COMPLETED` or `REVIEW_REQUIRED` run must deliver a real direct URL in `primary_url` and the URL-delivery fields.

- `COMPLETED`: strict URL acceptance passed.
- `REVIEW_REQUIRED`: a real direct review URL was delivered, but one or more strict gates require confirmation.
- `FAILED`: execution failed, including `MANDATORY_PRODUCT_URL_NOT_FOUND` when no safe direct product-page URL exists.

`validate_result_contract` verifies the final schema before the notebook returns a result. It requires the manufacturer-first authority fields and permits `manufacturer_url` or `retailer_url` to be `null` only when that qualified source role was not found.

## Main DataFrames

| DataFrame | Purpose |
|---|---|
| `platform_readiness_df` | Runtime contract, manufacturer-first capability, recovery attempt, clean-build status, elapsed time |
| `product_identification_df` | Leading hypothesis, probability, margin, readiness, resolution |
| `hypotheses_df` | Competing product hypotheses |
| `uncertainties_df` | Decision-critical unresolved fields |
| `belief_updates_df` | Probability snapshots after evidence |
| `evidence_ledger_df` | Atomic page evidence |
| `source_selection_df` | Primary role, manufacturer URL, retailer URL, authority tier, and selection reason |
| `url_delivery_df` | Mandatory delivery and strict-verification status |
| `source_hierarchy_df` | Source target, engine, query, and outcome by SerpAPI credit |
| `search_actions_df` | Paid-credit decision trace |
| `search_engine_summary_df` | Search-engine yield and conversion |
| `search_handles_df` | Product tokens, IDs, image handles, and immersive-product tokens |
| `search_decision_rca_df` | Budget, planner, fallback, and stopping RCA |
| `results_df` | One authoritative row per canonical candidate URL |
| `agentic_df` | Browser investigations and deterministic LLM-error fallback |
| `feature_evidence_df` | URL-feature evidence |
| `selection_rca_df` | Final strict-selection RCA |

## Workbook and artifacts

The notebook exports:

```text
single_product_diagnostics.xlsx
```

The workbook includes:

```text
platform_readiness
product_identification
product_hypotheses
product_uncertainties
belief_updates
evidence_ledger
source_selection
url_delivery
source_hierarchy
source_tier_summary
candidate and browser diagnostics
feature evidence
final selection RCA
```

Core artifact files:

```text
product_belief.json
product_understanding.md
market_decision_path.md
belief_updates.md
evidence_ledger.jsonl
adaptive_search_trace.json
candidate_url_records.json
candidates.csv
primary_url_acceptance.json
mandatory_url_delivery.json
source_selection.json
orchestrated_result.json
single_product_diagnostics.xlsx
```

`source_selection.json` is the authoritative manufacturer-versus-retailer audit record.

## Reviewer checklist

1. Open `primary_url` and verify exact product, model, form, variant, size, quantity, and pack.
2. Verify requested feature completeness and official product details.
3. Open `retailer_url`, when present, for price, stock, local market, and purchase context.
4. Confirm that a manufacturer page became primary only after all mandatory gates passed.
5. Confirm that retailer fallback was used when manufacturer evidence was inadequate.
6. Treat `REVIEW_REQUIRED` as a delivered review candidate, not an automated exact-match claim.
