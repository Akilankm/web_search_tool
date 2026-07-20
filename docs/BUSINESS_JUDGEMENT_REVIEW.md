# Business Judgment Review Artifact

## Purpose

Each product run writes a shareable human-validation document:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

It lets a human coder answer a stronger question than “did the agent find the same URL?”:

> Did the agent make the same sequence of business judgments, in the same order, from the same observable evidence?

It records observable evidence, explicit business rules, decisions and resulting actions. It does not expose hidden chain-of-thought.

## What the artifact contains

1. Submitted input: `main_text`, country, retailer, EAN and language.
2. Executive URL decision: `primary_url`, `primary_url_role`, `manufacturer_url`, `retailer_url` and `source_selection`.
3. Chronological business-judgment sequence.
4. Candidate alternatives considered and rejected.
5. Strict browser, identity, feature, scrapability and durability gates.
6. Manufacturer-versus-retailer authority decision.
7. Visual evidence impact.
8. Human coder comparison form.
9. Links to supporting engineering artifacts.

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

The representation is deliberately:

```text
observable evidence
→ explicit business rule
→ business judgment
→ next business action
```

## Visual evidence interpretation

The browser agent receives rendered screenshots and can inspect product/gallery images. Vision-derived feature evidence is recorded using:

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

| Value | Meaning |
|---|---|
| `YES_VISUAL_EVIDENCE_SUPPORTED_SELECTED_URL_FEATURE_GATE` | Vision evidence supported the selected URL's requested-feature gate |
| `VISUAL_EVIDENCE_USED_BUT_NOT_RECORDED_AS_DECISIVE_FOR_SELECTED_URL` | Images/screenshots informed investigation but were not proven decisive |
| `NO_VISUAL_EVIDENCE_RECORDED` | No visual evidence was recorded |

`text_alone_would_have_passed` remains `UNKNOWN_NOT_COUNTERFACTUALLY_TESTED` unless an explicit text-only counterfactual run is performed.

## Human coder protocol

Give the human coder:

1. the original submitted input; and
2. `business_judgement_review.md`.

Ask them to classify:

- `IDENTICAL`: same judgments, order and URL outcome;
- `PARTIALLY IDENTICAL`: same final URL but one or more judgments differ;
- `NOT IDENTICAL`: materially different sequence or final URL.

The reviewer records the first divergent step, agent judgment, human judgment, missing or overweighted evidence, image interpretation and preferred change.

## Acceptance criterion

The URL-identification workflow is behaviorally validated only when the human coder confirms the business-judgment sequence, not merely the final URL.

## Notebook surfaces

### Single product

```text
notebooks/01_single_product.ipynb
```

The first post-run view displays:

- `final_decision_df`;
- `business_judgement_steps_df`;
- `visual_evidence_summary_df`;
- the exact Markdown path to share.

### Batch products

```text
notebooks/02_batch_products.ipynb
```

Every successful or review-required row contains `business_judgement_review_path` and a product-specific artifact directory. Batch execution never replaces the individual judgment artifact with a batch-level opaque explanation.

### Artifact diagnostics

```text
notebooks/03_artifact_diagnostics.ipynb
```

This offline notebook accepts an artifact directory or any file inside it. It reconstructs a decision mindmap, chronological judgment timeline, candidate and feature evidence, belief changes and artifact inventory. It writes:

```text
artifact_diagnostic_report.md
artifact_diagnostic_workbook.xlsx
```

The diagnostic view expands the same observable evidence-and-judgment contract; it does not expose hidden chain-of-thought.

## Runtime contract

```text
belief-url-resolution-v6-business-judgement-review
```

Required health capability:

```text
business_judgement_review_artifact=true
```

Required result field:

```text
business_judgement_review
```

The result field contains the artifact path, schema version, human-review status, visual summary and structured judgment steps.

## Related contracts

- [Final system contract](FINAL_SYSTEM_CONTRACT.md)
- [Notebook usage](NOTEBOOK_USAGE.md)
- [Azure ML operations](AZUREML_OPERATIONS.md)
- [Manufacturer-first authority](SOURCE_AUTHORITY_HIERARCHY.md)
