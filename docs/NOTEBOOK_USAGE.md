# Notebook Usage and Diagnostic Contract

Use only:

```text
notebooks/01_run_product_evidence.ipynb
```

The notebook runs one product and exposes product interpretation, belief state, immutable market route, paid search decisions, candidate evidence, browser investigation, and mandatory URL delivery.

## Setup

```bash
git checkout master
git pull origin master
cp .env.example .env
# Add real SerpAPI and enterprise LLM values.
./scripts/azureml_startup.sh
```

Restart the kernel after pulling code. The bootstrap cell forces the repository-local package, removes stale modules, discovers available feature sets, checks the live agent, and defaults to the committed `inputs/private/toy_features.json`.

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

## Before search

```text
deterministic parsing
→ no-web LLM interpretation
→ competing product hypotheses
→ uncertainty metrics
→ first market evidence plan
```

The result exposes `product_identification.leading_hypothesis`, resolution status, posterior margin, readiness metrics, critical uncertainties, evidence count, and `search.market_decision_path`.

## Market path

```text
requested retailer, when provided
→ alternative retailer within country
→ global fallback
```

A stage is skipped only when it does not apply. Search may stop early when a production-ready URL is validated.

## Mandatory URL contract

Every `COMPLETED` or `REVIEW_REQUIRED` run must deliver a real direct product URL in `primary_url`, `product_match.product_url`, and the URL-delivery fields. The notebook immediately asserts the contract.

A review-required URL is still browser-openable and useful, but one or more exactness or strict acceptance gates require manual confirmation. When no safe direct product page exists, the terminal reason is `MANDATORY_PRODUCT_URL_NOT_FOUND`; diagnostics never proceed with an empty product URL.

The reviewer should eyeball product identity, model, variant, size, pack interpretation, page detail quality, and selection scope.

## Belief artifacts

```text
product_belief.json
product_understanding.md
market_decision_path.md
belief_updates.md
evidence_ledger.jsonl
```

The JSON file is the complete machine-readable belief state. Markdown files are observable decision summaries, not hidden chain-of-thought.

## Main tables

| DataFrame | Purpose |
|---|---|
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
| `search_decision_rca_df` | Budget, planner, fallback, stop RCA |
| `serp_results_df` | Raw search-result occurrences |
| `results_df` | One authoritative row per canonical URL |
| `source_tier_summary_df` | Candidate conversion summary |
| `agentic_df` | Browser investigations |
| `feature_evidence_df` | URL-feature evidence |
| `funnel_df` | Candidate conversion funnel |
| `rejection_reasons_df` | Rejection and review reasons |
| `selection_rca_df` | Final URL decision RCA |

## Export

The notebook writes `single_product_diagnostics.xlsx` and includes belief, URL delivery, search, candidate, browser, feature, and selection tables. It also retains `adaptive_search_trace.json` and `mandatory_url_delivery.json`.

## Terminal outcomes

- `COMPLETED`: exact URL passed strict gates.
- `REVIEW_REQUIRED`: a real product URL was delivered, but a reviewer must confirm one or more gates.
- `FAILED`: execution failed, including inability to produce a safe direct product-page URL.
