# Artifact Output Strategy

The harness now separates the **submission answer** from the **search/validation evidence**.

## Principle

```text
CSV = final operational output / submission artifact
Markdown = human-readable search, validation, and verification audit
JSON = compact machine replay trace
Debug CSV = optional engineering-only export
```

The row artifact is a readable evidence packet, not a dump of every internal table.

## Row-level output

For each product row:

```text
output/<row_id>/
├── final_row.csv
├── report.md
├── search_plan.md
├── candidate_review.md
├── scrape_evidence.md
├── retailer_scrapability.md
├── final_decision.md
├── decision_trace.md
└── trace.json
```

When `PRODUCT_HARNESS_WRITE_DEBUG_CSVS=true`, the detailed diagnostic CSVs are written under:

```text
output/<row_id>/debug_csv/
```

## Batch-level output

```text
outputs/
├── final_submission.csv
├── review_queue.csv
└── batch_summary.md
```

## Why markdown matters

Markdown records the evidence trail in a format that is easy for humans and LLMs to read:

1. What product identity was understood.
2. What search plan was used.
3. Which candidates were discovered.
4. Which candidates were scraped.
5. What crawl4ai actually saw.
6. Whether the requested retailer was scrape-usable.
7. Why the agent escaped to other country retailers or global fallback.
8. Why the selected URL was chosen.
9. Why competing URLs were rejected.

This is an observable **decision trace**, not hidden chain-of-thought.

## Main CSV columns

`final_submission.csv` and each row-level `final_row.csv` contain the submission-ready fields:

```text
row_id
main_text
country_code
ean
retailer_name
product_url
verified_exact_url
best_available_url
best_reference_url
url_decision_status
resolution_status
selection_scope
selected_domain
selected_retailer_name
is_exact_product_match
is_scrapable
is_product_page
needs_review
confidence
requested_retailer_attempted
requested_retailer_scrapability_status
requested_retailer_escape_reason
selected_from_requested_retailer
selected_from_other_country_retailer
selected_from_global_fallback
candidate_urls
candidate_count
scored_candidate_count
scraped_candidate_count
scrape_success_count
product_detail_pages_found
serp_calls_used
ai_mode_calls_used
llm_calls_used
scrape_calls_used
repair_cycles
global_fallback_used
llm_decision
final_justification
termination_reason
row_report_path
```

## Output flags

```env
PRODUCT_HARNESS_WRITE_OUTPUTS=true
PRODUCT_HARNESS_WRITE_MARKDOWN_REPORTS=true
PRODUCT_HARNESS_WRITE_TRACE_JSON=true
PRODUCT_HARNESS_WRITE_DEBUG_CSVS=false
```

Keep `PRODUCT_HARNESS_WRITE_DEBUG_CSVS=false` for normal runs. Enable it only when detailed engineering diagnostics are needed.
