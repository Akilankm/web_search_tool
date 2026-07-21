# Business Judgment Review Artifact

## Purpose

Each terminal product result writes:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

The artifact supports a stronger review than final-URL comparison:

> Did the system make the same sequence of business judgments, in the same order, from the same observable evidence—and would a reviewer stop under the same bounded policy?

It records observable evidence, explicit business rules, decisions and resulting actions. It does not expose hidden chain-of-thought.

## Supported result types

1. `COMPLETED` with a strictly accepted direct URL.
2. `REVIEW_REQUIRED` with a real direct review URL.
3. `REVIEW_REQUIRED` with `NO_SAFE_DIRECT_PRODUCT_URL_FOUND` when bounded search produces no safe direct product page.

The third outcome is not successful resolution and is not an internal exception. It records search exhaustion, confirms that no URL was fabricated and provides follow-up actions.

## Artifact contents

```text
submitted input
URL or no-URL decision
chronological business-judgment sequence
candidate alternatives and rejection reasons
browser, identity, feature, scrapability and durability gates
source-authority decision
visual evidence impact
reviewer comparison form
supporting artifact references
```

## Judgment record schema

```text
sequence_number
decision_stage
business_question
evidence_considered
evidence_sources
visual_evidence_used
visual_evidence_details
agent_judgement
judgement_status
alternatives_considered
alternative_rejected
rejection_reason
business_rule_applied
effect_on_next_action
confidence
final_outcome
```

Representation:

```text
observable evidence
→ explicit business rule
→ business judgment
→ next action
```

## No-safe-URL judgment

```text
decision_stage=FINAL_NO_SAFE_URL_REVIEW_OUTCOME
judgement_status=REVIEW_REQUIRED
rejection_reason=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
final_outcome=NO_SAFE_DIRECT_PRODUCT_URL_FOUND_AFTER_BOUNDED_SEARCH
```

Rule:

> Search exhaustion is a controlled business no-match outcome. Preserve the trace and require review rather than inventing or promoting an unsafe URL.

## Visual evidence interpretation

Vision-derived evidence is recorded with:

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

| Value | Meaning |
|---|---|
| `YES_VISUAL_EVIDENCE_SUPPORTED_SELECTED_URL_FEATURE_GATE` | Visual evidence supported the selected URL's requested-feature gate |
| `VISUAL_EVIDENCE_USED_BUT_NOT_RECORDED_AS_DECISIVE_FOR_SELECTED_URL` | Images or screenshots informed investigation but were not proven decisive |
| `NO_VISUAL_EVIDENCE_RECORDED` | No visual evidence was recorded |

`text_alone_would_have_passed` remains `UNKNOWN_NOT_COUNTERFACTUALLY_TESTED` unless an explicit text-only counterfactual is performed.

## Reviewer protocol

Provide the reviewer with:

1. the original submitted input; and
2. `business_judgement_review.md`.

Classification:

- `IDENTICAL`: same judgments, order and URL/no-URL outcome;
- `PARTIALLY IDENTICAL`: same outcome but one or more judgments differ;
- `NOT IDENTICAL`: materially different sequence or outcome.

The reviewer records the first divergent step, alternative judgment, missing or overweighted evidence, image interpretation and preferred system change.

## Review surfaces

### Product Evidence Platform UI

```text
apps/product_evidence_ui.py
```

The **Judgment sequence** tab displays chronological records. The **Artifacts** tab provides the Markdown and complete result JSON.

### Single-product notebook

```text
notebooks/01_single_product.ipynb
```

Displays `final_decision_df`, `business_judgement_steps_df`, `visual_evidence_summary_df`, the Markdown path and any no-safe-URL follow-up actions.

### Batch notebook

```text
notebooks/02_batch_products.ipynb
```

Every terminal row contains a product-specific artifact path. A no-safe-URL row remains `REVIEW_REQUIRED` and is not classified as a technical failure.

### Artifact diagnostics notebook

```text
notebooks/03_artifact_diagnostics.ipynb
```

Reconstructs the result through Decision Map, Judgment Timeline, Candidates, Evidence and Artifacts views.

## Runtime contract

```text
belief-url-resolution-v9-product-evidence-ui
```

Required capabilities:

```text
business_judgement_review_artifact=true
structured_no_url_review_outcome=true
per_job_runtime_controls=true
```

Required result fields:

```text
business_judgement_review
run_configuration
```

## Related documents

- [Feature reference](FEATURE_REFERENCE.md)
- [System workflow](SYSTEM_WORKFLOW.md)
- [Product Evidence Platform UI](PRODUCT_EVIDENCE_UI.md)
- [Structured no-safe-URL outcome](STRUCTURED_NO_URL_OUTCOME.md)
- [Final system contract](FINAL_SYSTEM_CONTRACT.md)
- [Notebook usage](NOTEBOOK_USAGE.md)
- [Azure ML operations](AZUREML_OPERATIONS.md)
- [Interactive artifact diagnostics](INTERACTIVE_ARTIFACT_DIAGNOSTICS.md)
- [Source-authority hierarchy](SOURCE_AUTHORITY_HIERARCHY.md)
