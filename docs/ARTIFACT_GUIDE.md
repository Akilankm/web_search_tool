# Artifact Guide

The harness writes business outputs and audit artifacts. This document explains what each artifact is for and how users should interpret it.

## Artifact philosophy

```text
CSV = operational business output
Markdown = human-readable decision story
JSON = machine-readable audit/replay evidence
Notebook = user-facing execution gateway
```

## Batch-level artifact map

```mermaid
flowchart TD
    A[Batch run] --> B[final_submission.csv]
    A --> C[review_queue.csv]
    A --> D[batch_summary.md]
    A --> E[metrics.json]
    A --> F[Row artifact folders]

    B --> G[Business handoff]
    C --> H[Human review worklist]
    D --> I[Management summary]
    E --> J[Operational metrics]
    F --> K[Evidence and audit trail]
```

## Row-level artifact map

```mermaid
flowchart TD
    A[One product row] --> B[final_row.csv]
    A --> C[report.md]
    A --> D[search_plan.md]
    A --> E[candidate_review.md]
    A --> F[scrape_evidence.md]
    A --> G[final_decision.md]
    A --> H[trace.json]
    A --> I[tournament_bracket.json]
    A --> J[champion_confirmation.json]
    A --> K[product_coding_input.json]
    A --> L[quality_assessment.md]
```

## Key business artifacts

| Artifact | Audience | Purpose |
|---|---|---|
| `final_submission.csv` | Business/operations | Main output table for production handoff. |
| `review_queue.csv` | Review team | Rows that should not be automated yet. |
| `batch_summary.md` | Manager/leadership | Human-readable batch-level summary. |
| `metrics.json` | Engineering/ops | Machine-readable performance and quality metrics. |
| `output/<row_id>/report.md` | Everyone | Row-level story explaining what happened. |
| `output/<row_id>/trace.json` | Engineering/audit | Machine-readable replay/debug trace. |
| `output/<row_id>/product_coding_input.json` | Product coding engine | Structured evidence for downstream coding. |
| `output/<row_id>/champion_confirmation.json` | Audit/reviewer | Repeated champion confirmation result. |
| `output/<row_id>/tournament_bracket.json` | Engineering/reviewer | Candidate tournament details. |

## Final submission interpretation

```mermaid
flowchart LR
    A[final_submission.csv] --> B{production_url_ready?}
    B -->|true| C{needs_review?}
    C -->|false| D[Automated handoff]
    C -->|true| E[Review]
    B -->|false| E
```

Automated handoff requires:

```text
production_url_ready = true
needs_review = false
champion_confirmation.passed = true
```

## Product coding handoff

The downstream product coding system should consume:

```text
output/<row_id>/product_coding_input.json
```

It contains the structured evidence package:

```text
selected_url
verified_exact_url
supporting_urls
selected_page_evidence
brand/manufacturer/description/specs/images/EAN evidence
identity_verification
quality_tier
coding_readiness_status
review_flags
```

## Optional offline artifact

Offline artifacts are not created by default. They are created only through:

```text
notebooks/03_offline_product_artifact.ipynb
```

Optional offline artifact map:

```mermaid
flowchart TD
    A[Notebook 03] --> B[offline_artifact_manifest.json]
    A --> C[live_capture/raw.html]
    A --> D[product_data/structured_product.json]
    A --> E[offline/offline_page.html]
    A --> F[offline/assets]
    A --> G[validation/offline_artifact_validation.json]
```

Use offline artifacts only when the workflow explicitly requires offline reproducibility or manual inspection.

## Audit trail value

The artifact system makes the repo enterprise-ready because every decision can be inspected after the run.

```mermaid
flowchart LR
    A[Business result] --> B[Why this URL?]
    B --> C[Candidate review]
    B --> D[Scrape evidence]
    B --> E[Identity checks]
    B --> F[Champion confirmation]
    B --> G[Final decision report]
```
