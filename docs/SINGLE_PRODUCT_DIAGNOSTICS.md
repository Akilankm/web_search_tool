# Single-Product Diagnostic Interpretation Guide

The supported notebook produces a complete EDA and root-cause analysis for one product run.

## Diagnostic objective

The report must answer five questions independently:

1. **Search yield:** How many SERP results and unique URLs were obtained?
2. **Technical access:** Which URLs were scraped and opened in the browser?
3. **Product identity:** Which URLs describe the exact requested product and variant?
4. **Feature evidence:** Which URLs support the requested features without conflict?
5. **Final decision:** Why was one `primary_url` selected, or why was no URL accepted?

These dimensions must not be collapsed into a single vague accuracy measure.

## Candidate funnel

| Stage | Definition |
|---|---|
| SERP rows returned | Sum of `results_returned` across the three SerpAPI stages |
| Unique candidate URLs | Deduplicated persisted candidate URLs |
| Scrape attempted | Candidate has a persisted scrape/verification attempt |
| Scrape successful | Candidate produced usable scrapable content |
| Agentic investigated | Candidate has an LLM-controlled browser investigation dossier |
| Browser openable | Rendered page opened successfully |
| Identity accepted | Deterministic feature assessment accepted exact-product identity |
| Feature complete | The individual URL supports 100% of requested features |
| Selected | URL became the strict `primary_url` or was retained in the review evidence set |

The notebook reports conversion from the previous stage and conversion from total SERP rows.

## `results_df`

`results_df` is the main analysis table. It joins:

- `candidates.csv`;
- `candidate_investigations`;
- `browser_evidence`;
- `feature_assessments`;
- `evidence_set`;
- `primary_url_acceptance`.

### Final candidate statuses

| Status | Meaning |
|---|---|
| `STRICT_SELECTED` | Accepted as the authoritative top-level `primary_url` |
| `REVIEW_SELECTED` | Retained as diagnostic/review evidence but not strict primary |
| `NOT_SCRAPED` | Candidate remained in the pool but no scrape was attempted |
| `SCRAPE_FAILED` | Scrape was attempted but usable content was not obtained |
| `BROWSER_BLOCKED` | Agentic browser investigated but could not open the rendered page |
| `IDENTITY_REJECTED` | Candidate was accessible but failed exact-product identity |
| `FEATURE_INCOMPLETE` | Identity passed but the URL lacked one or more requested features |
| `ELIGIBLE_NOT_SELECTED` | Candidate passed core gates but lost to a stronger accepted source |

## Search-stage quality

`stage_quality_df` includes:

- `result_to_new_candidate_rate = new_candidate_urls / results_returned`;
- `new_candidate_to_scrape_rate = candidates_scraped / new_candidate_urls`.

A high SERP count with a low new-candidate rate indicates duplication or weak incremental search value. A high new-candidate count with a low scrape rate indicates ranking or scrape-budget pressure.

## Domain quality

`domain_summary_df` reports per domain:

- candidate count;
- scrape attempts and successes;
- browser investigations;
- identity acceptance;
- feature completeness;
- strict selection;
- mean deterministic confidence;
- mean feature coverage.

This table supports defensible statements about whether one retailer/domain consistently produced stronger evidence.

## Rejection RCA

`rejection_reasons_df` normalizes reasons from:

- candidate deterministic decision reasons;
- feature-assessment rejection reasons;
- browser blockers;
- agentic termination reasons;
- scrape/browser errors.

Use candidate counts rather than raw reason-row counts when explaining prevalence.

## Feature evidence

`feature_evidence_df` retains:

- feature ID and name;
- extracted value;
- evidence status;
- confidence;
- extraction method;
- evidence location;
- source URL and identity state.

The supported statuses are:

- `STRUCTURED_FOUND`;
- `EXPLICITLY_FOUND`;
- `LLM_FOUND`.

`feature_matrix_df` converts those supported statuses into a compact URL × feature matrix for visual comparison.

## Final `primary_url` RCA

`selection_rca_df` is the executive decision table. It includes:

- final job status;
- coding readiness;
- strict primary acceptance;
- chosen `primary_url`;
- supplementary/review URLs;
- URL decision status and selection scope;
- identity and validation status;
- confidence;
- total feature coverage;
- missing and conflicting features;
- strict-acceptance rejection reasons.

A `REVIEW_REQUIRED` result is not an execution failure. It means the deterministic final selector did not find one investigated, durable, exact-product, text-scrapable URL with complete conflict-free requested-feature coverage.

## Graphs

The notebook produces separate charts for:

1. candidate conversion funnel;
2. SERP stage yield;
3. per-candidate outcome counts;
4. confidence distribution;
5. confidence versus feature coverage;
6. candidate volume by domain;
7. rejection/blocker frequency;
8. URL-feature support heatmap.

Each chart has one diagnostic purpose. Tables remain the authoritative values.

## Excel export

The notebook writes:

```text
data/artifacts/<row_id>/single_product_diagnostics.xlsx
```

Worksheets mirror the diagnostic DataFrames, including `results`, `funnel`, `domain_summary`, `rejection_reasons`, `selection_rca`, and feature evidence tables.
