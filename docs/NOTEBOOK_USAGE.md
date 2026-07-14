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

## Precision-gated three-stage flow

Each product executes exactly three searches:

1. requested retailer in the requested country, or the primary country search;
2. alternative sources in the requested country;
3. unrestricted global fallback.

The three searches preserve recall. Downstream processing is selective:

```text
raw SERP occurrence
→ canonical URL identity
→ deterministic URL-type and identity admission
→ bounded full scrape
→ evidence-utility acceptance
→ bounded browser escalation
→ strict primary URL decision
```

Obvious home, search, category, collection, social, document, media, and low-identity URLs remain visible for audit but do not consume full scrape or LLM-browser capacity.

## Two intentional table grains

### `serp_results_df`

This is the raw search-occurrence table. The same canonical URL can appear more than once because it may be returned by several search stages or at several positions.

### `results_df`

This is the authoritative candidate table. It contains exactly one row per canonical URL. Tracking, campaign, referral, session, and fragment noise are removed while product-defining query parameters remain.

The runtime writes the same grain to:

```text
data/artifacts/<row_id>/candidate_url_records.json
data/artifacts/<row_id>/candidates.csv
```

Canonical URL uniqueness is asserted by the runtime.

## Main diagnostic tables

After the run, execute the **Build the complete diagnostic model** cell.

| DataFrame | Purpose |
|---|---|
| `overview_df` | Executive metrics and final state |
| `search_stages_df` | Per-credit search-stage and admission yield |
| `serp_results_df` | Raw SERP occurrence inventory |
| `results_df` | One-row-per-canonical-URL decision ledger |
| `agentic_df` | Browser turns, actions, termination, and errors |
| `feature_evidence_df` | URL-feature evidence records |
| `feature_matrix_df` | URL by requested-feature support matrix |
| `funnel_df` | SERP-to-selection conversion |
| `domain_summary_df` | Domain-level quality and conversion |
| `stage_quality_df` | Search-stage yield ratios |
| `rejection_reasons_df` | Normalized rejection and blocker counts |
| `selection_rca_df` | Final `primary_url` root-cause analysis |

## `results_df` contract

The persisted candidate ledger supplies these groups to `results_df`:

| Group | Important fields |
|---|---|
| URL identity | `canonical_url`, `requested_url`, `final_url`, `domain` |
| SERP support | `search_stages`, `appearance_count`, `best_position`, `serp_title` |
| Pre-scrape admission | `url_type`, `preflight_score`, `identity_overlap`, `admitted_for_scrape`, `admission_reason` |
| Acquisition | `full_scrape_attempted`, `fetch_success`, `content_extracted`, `technical_scrapable` |
| Evidence quality | `product_page_likelihood`, `content_utility_score`, `scrape_accepted` |
| Identity | `identity_status`, `ean_check`, `title_check`, `variant_status`, `page_type` |
| Feature support | `feature_evidence_count`, `coverage`, `missing_features`, `conflicting_features` |
| Browser | `browser_admitted`, `browser_admission_reason`, `browser_turns`, `browser_actions`, `browser_outcome` |
| Final RCA | `final_status`, `rejection_category`, `selected`, `decision_reasons` |

Feature-specific scalar columns are created dynamically:

```text
feature_<feature_id>_value
feature_<feature_id>_status
feature_<feature_id>_confidence
```

## Scrape semantics

The notebook's stable `scrape_success` view now means **evidence-quality accepted**, not merely HTTP success.

The detailed distinction remains available:

| Field | Meaning |
|---|---|
| `fetch_success` | Acquisition operation succeeded |
| `content_extracted` | A usable amount of readable content was obtained |
| `technical_scrapable` | Existing technical scrapability signal |
| `product_page_likelihood` | Evidence for an individual product detail page |
| `content_utility_score` | Usefulness for identity and feature evidence |
| `scrape_accepted` | Accepted for downstream evidence reasoning |

A technically reachable page with a price or image is therefore not automatically counted as quality evidence.

## Funnel semantics

The business funnel is:

```text
SERP rows returned
→ canonical candidate URLs
→ admitted for full scrape
→ full scrape attempted
→ scrape accepted for evidence
→ browser admitted
→ browser openable
→ identity accepted
→ feature complete
→ selected
```

The existing notebook display remains backward-compatible. The authoritative stage fields are available directly in `results_df`, `search_stages_df`, and the Excel export.

## Browser and context controls

Only high-potential, already-scraped, unresolved candidates enter the browser. Effective hard ceilings are:

```text
3 candidates
4 turns per candidate
6 actions per candidate
5,000 observation characters maximum
18 relevant controls maximum
10 relevant images maximum
```

The normal defaults are smaller: 4,000 characters, 15 controls, and 8 images.

The prompt mode is `incremental_delta_relevance_filtered`:

- already resolved feature definitions are removed;
- unchanged page text is not resent;
- specification, details, manufacturer, age, warning, gallery, and similar controls are ranked first;
- transactional and account controls are ranked down;
- only two compact prior action summaries are retained;
- no additional LLM call is made when every requested feature is already resolved.

## Final status

Every canonical URL has one terminal RCA label:

```text
SERP_REJECTED_URL_TYPE
SERP_REJECTED_LOW_IDENTITY
QUALIFIED_NOT_SCRAPED_BUDGET
SCRAPE_FAILED
SCRAPE_LOW_UTILITY
IDENTITY_REJECTED
BROWSER_BLOCKED
FEATURE_INCOMPLETE
ELIGIBLE_NOT_SELECTED
REVIEW_SELECTED
STRICT_SELECTED
```

`quality_verified` means the runtime validation status is exactly `VERIFIED`. It is not a subjective notebook score.

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

See:

- `docs/CANDIDATE_PRECISION_AND_CONTEXT.md`
- `docs/SINGLE_PRODUCT_DIAGNOSTICS.md`
