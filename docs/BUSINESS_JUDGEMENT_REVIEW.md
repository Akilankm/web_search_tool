# Business Judgment Review Artifact

## Purpose

Each terminal product business result writes:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

It lets a human coder answer a stronger question than “did the agent find the same URL?”:

> Did the agent make the same sequence of business judgments, in the same order, from the same observable evidence—and would the human stop under the same bounded search policy?

It records observable evidence, explicit business rules, decisions and resulting actions. It does not expose hidden chain-of-thought.

## Supported result types

The artifact supports:

1. `COMPLETED` with a strictly accepted direct URL;
2. `REVIEW_REQUIRED` with a real direct review URL;
3. `REVIEW_REQUIRED` with `NO_SAFE_DIRECT_PRODUCT_URL_FOUND` when bounded search safely produces no direct product page.

The third outcome is not a successful resolution and not an internal exception. The artifact states that no URL was fabricated and records the search-exhaustion evidence and human next actions.

## What the artifact contains

1. Submitted input: `main_text`, country, retailer, EAN and language.
2. Executive URL/no-URL decision.
3. Chronological business-judgment sequence.
4. Candidate alternatives considered and rejected.
5. Strict browser, identity, feature, scrapability and durability gates.
6. Manufacturer-versus-retailer authority decision when qualified URLs exist.
7. Structured search-exhaustion decision when no safe URL exists.
8. Visual evidence impact.
9. Human coder comparison form.
10. Links to supporting engineering artifacts.

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

The representation is:

```text
observable evidence
→ explicit business rule
→ business judgment
→ next business action
```

## No-safe-URL judgment

For a structured no-safe-URL result, the final record is:

```text
decision_stage=FINAL_NO_SAFE_URL_REVIEW_OUTCOME
judgement_status=REVIEW_REQUIRED
rejection_reason=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
final_outcome=NO_SAFE_DIRECT_PRODUCT_URL_FOUND_AFTER_BOUNDED_SEARCH
```

The rule is:

> Search exhaustion is a controlled business no-match outcome. Preserve the trace and require human review rather than inventing or promoting an unsafe URL.

The Markdown begins with `CONTROLLED NO-URL REVIEW OUTCOME` and includes credits used, URL-delivery status, no-fabrication confirmation and required human action.

## Visual evidence interpretation

The browser agent receives rendered screenshots and can inspect product/gallery images. Vision-derived evidence is recorded using:

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

| Value | Meaning |
|---|---|
| `YES_VISUAL_EVIDENCE_SUPPORTED_SELECTED_URL_FEATURE_GATE` | Vision evidence supported the selected URL's requested-feature gate |
| `VISUAL_EVIDENCE_USED_BUT_NOT_RECORDED_AS_DECISIVE_FOR_SELECTED_URL` | Images/screenshots informed investigation but were not proven decisive |
| `NO_VISUAL_EVIDENCE_RECORDED` | No visual evidence was recorded |

`text_alone_would_have_passed` remains `UNKNOWN_NOT_COUNTERFACTUALLY_TESTED` unless an explicit text-only counterfactual is performed.

## Human coder protocol

Give the reviewer:

1. the original submitted input; and
2. `business_judgement_review.md`.

Ask them to classify:

- `IDENTICAL`: same judgments, order and URL/no-URL outcome;
- `PARTIALLY IDENTICAL`: same outcome but one or more judgments differ;
- `NOT IDENTICAL`: materially different sequence or outcome.

For no-safe-URL cases, explicitly ask:

- Would the human also stop after the same bounded search stages?
- Did the agent miss a known manufacturer, retailer, identifier or query formulation?
- Should the input be corrected, or should the search policy itself change?

The reviewer records the first divergent step, human judgment, missing/overweighted evidence, image interpretation and preferred change.

## Review surfaces

### Leadership Streamlit

```text
apps/leadership_demo.py
```

The **Judgment trace** tab displays the chronological records, while **Artifacts** allows the reviewer to preview and download `business_judgement_review.md`.

### Single product notebook

```text
notebooks/01_single_product.ipynb
```

The first post-run view displays `final_decision_df`, `business_judgement_steps_df`, `visual_evidence_summary_df`, the Markdown path and—when applicable—`no_url_resolution.json` plus suggested next actions.

### Batch products

```text
notebooks/02_batch_products.ipynb
```

Every completed/review row contains `business_judgement_review_path` and a product-specific artifact directory. A no-safe-URL row remains review-required and is not mislabeled as a technical failure.

### Artifact diagnostics

```text
notebooks/03_artifact_diagnostics.ipynb
```

This offline notebook reconstructs the same result through an interactive Decision Map, Judgment Timeline, Candidates, Evidence and Artifacts workspace. It writes:

```text
artifact_diagnostics_interactive.html
artifact_diagnostic_report.md
artifact_diagnostic_workbook.xlsx
```

## Runtime contract

```text
belief-url-resolution-v8-leadership-demo
```

Required capabilities:

```text
business_judgement_review_artifact=true
structured_no_url_review_outcome=true
leadership_demo_runtime_options=true
```

Required result fields:

```text
business_judgement_review
run_configuration
```

## Related contracts

- [Leadership Streamlit demo](STREAMLIT_LEADERSHIP_DEMO.md)
- [Structured no-safe-URL outcome](STRUCTURED_NO_URL_OUTCOME.md)
- [Final system contract](FINAL_SYSTEM_CONTRACT.md)
- [Notebook usage](NOTEBOOK_USAGE.md)
- [Azure ML operations](AZUREML_OPERATIONS.md)
- [Interactive artifact diagnostics](INTERACTIVE_ARTIFACT_DIAGNOSTICS.md)
- [Manufacturer-first authority](SOURCE_AUTHORITY_HIERARCHY.md)
