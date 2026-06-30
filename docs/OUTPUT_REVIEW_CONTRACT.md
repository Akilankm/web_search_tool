# Output Review Contract

## Contract

Default row outputs are concise and reviewer-first.

```text
output/<row_id>/
├── final_row.csv
├── review_summary.md
├── review_decision.json
├── candidate_decisions.csv
└── product_coding_input.json
```

## Deep artifacts

Verbose reports/traces/debug CSVs are opt-in only:

```env
PRODUCT_HARNESS_WRITE_MARKDOWN_REPORTS=true
PRODUCT_HARNESS_WRITE_TRACE_JSON=true
PRODUCT_HARNESS_WRITE_DEBUG_CSVS=true
```

## Notebook review

Use:

```text
notebooks/04_review_artifact_reader.ipynb
```

for precise review of:

```text
what was selected
why it was selected
how it was decided
what was rejected and why
what model/detector evidence contributed
```
