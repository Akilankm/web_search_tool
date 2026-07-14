# Notebook Usage and Diagnostic Contract

Use only `notebooks/01_run_product_evidence.ipynb`.

The notebook is both the supported single-product runner and the complete EDA/RCA report.

## Fresh setup

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool
cp .env.example .env
# Edit only the real SerpAPI and LLM values.
./scripts/azureml_startup.sh
```

The repository already includes `inputs/private/toy_features.json`. No feature-file copy, permission flag, manual Docker command, or separate notebook package setup is required. The first notebook cell installs only missing analytical packages into the active kernel.

## Run one product

```python
FEATURE_SET = "toy_features"
RUN_SINGLE_PRODUCT = True

product = {
    "row_id": "TEST-001",
    "main_text": "Exact product identity text",
    "country_code": "CO",
    "retailer_name": "Mercado Libre",
    "ean": None,
    "language_code": None,
}
```

`main_text` and `country_code` are required. The other fields are optional. `RUN_SINGLE_PRODUCT` defaults to `False` to avoid accidental API usage before the sample input is replaced.

## Three-stage deterministic flow

Each product executes exactly three searches:

1. requested retailer in the requested country, or the primary country search;
2. alternative retailers in the requested country;
3. unrestricted global fallback.

Every retained candidate may then receive an isolated LLM-controlled agentic browser investigation. Deterministic code remains authoritative for identity, access, scrapability, requested-feature evidence, conflicts, and durable `primary_url` acceptance.

## Main diagnostic tables

After the run, execute the **Build the complete diagnostic model** cell.

| DataFrame | Purpose |
|---|---|
| `overview_df` | Executive metrics and final state |
| `search_stages_df` | Per-credit search-stage yield |
| `serp_results_df` | SERP URL inventory |
| `results_df` | Principal candidate-level audit table |
| `agentic_df` | Browser turns, actions, termination, and errors |
| `feature_evidence_df` | URL-feature evidence records |
| `feature_matrix_df` | URL by requested-feature support matrix |
| `funnel_df` | SERP-to-selection conversion |
| `domain_summary_df` | Domain-level quality and conversion |
| `stage_quality_df` | Search-stage yield ratios |
| `rejection_reasons_df` | Normalized rejection and blocker counts |
| `selection_rca_df` | Final `primary_url` root-cause analysis |

## `results_df` contract

`results_df` contains one row per deduplicated retained candidate. It includes:

- search stage and best SERP position;
- deterministic confidence and content richness;
- scrape attempted and scrape success flags;
- agentic-browser status, turns, and actions;
- browser openability and text scrapability;
- deterministic identity acceptance;
- requested-feature coverage and conflicts;
- deterministic `quality_verified` status;
- strict or review-set selection;
- a compact `final_candidate_status` explaining the pass/fail stage.

`quality_verified` means the runtime validation status is exactly `VERIFIED`. It is not a subjective notebook score.

## Funnel semantics

```text
SERP rows returned
→ unique candidate URLs
→ scrape attempted
→ scrape successful
→ agentic investigated
→ browser openable
→ identity accepted
→ feature complete
→ selected
```

This separates search quality, technical access, exact-product identity, feature completeness, and final decision quality.

## Graphical EDA

Matplotlib and Seaborn create separate figures for:

- conversion funnel;
- search-stage yield;
- candidate outcome distribution;
- confidence distribution;
- confidence versus feature coverage;
- domain contribution;
- rejection reason frequency;
- URL-feature support heatmap.

## Final RCA

`selection_rca_df` reports the final status, coding readiness, strict acceptance, selected `primary_url`, supplementary URLs, selection scope, identity status, confidence, feature coverage, missing/conflicting features, and exact rejection reasons.

`COMPLETED` and `REVIEW_REQUIRED` are successful terminal workflow states. `REVIEW_REQUIRED` means no candidate passed every mandatory deterministic gate. Only `FAILED` is an execution failure.

## Export

The export cell writes:

```text
data/artifacts/<row_id>/single_product_diagnostics.xlsx
```

Every diagnostic DataFrame is written as a separate worksheet. JSON and CSV artifacts remain the source-of-truth audit records.

See `docs/SINGLE_PRODUCT_DIAGNOSTICS.md` for metric definitions and interpretation guidance.
