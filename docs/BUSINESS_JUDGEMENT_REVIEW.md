# Business Judgment Review Artifact

## Purpose

Each product run writes a shareable human-validation document:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

The artifact lets a human coder answer a stronger question than “did the agent find the same URL?”:

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

Every recorded step contains:

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

The artifact distinguishes three cases:

| Value | Meaning |
|---|---|
| `YES_VISUAL_EVIDENCE_SUPPORTED_SELECTED_URL_FEATURE_GATE` | Vision evidence was recorded for the selected URL and supported its requested-feature gate |
| `VISUAL_EVIDENCE_USED_BUT_NOT_RECORDED_AS_DECISIVE_FOR_SELECTED_URL` | Screenshots or images informed investigation, but the record does not prove they changed the final URL |
| `NO_VISUAL_EVIDENCE_RECORDED` | No visual evidence was recorded in the result |

The field `text_alone_would_have_passed` remains `UNKNOWN_NOT_COUNTERFACTUALLY_TESTED` unless an explicit text-only counterfactual run is performed. The system must not claim image causality merely because images were available.

## Human coder protocol

Give the human coder only:

1. the original submitted input; and
2. `business_judgement_review.md`.

Ask the coder to review independently and classify the comparison:

- `IDENTICAL`: same judgments, same order and same final URL role/outcome;
- `PARTIALLY IDENTICAL`: same final URL but one or more judgments or ordering differ;
- `NOT IDENTICAL`: materially different sequence or final URL.

The reviewer records:

- first divergent step number;
- agent judgment;
- human judgment;
- missing or overweighted evidence;
- whether image evidence was interpreted correctly;
- preferred business-rule or system change.

## Acceptance criterion

The URL-identification workflow should be considered behaviorally validated only when the human coder confirms the business-judgment sequence, not merely the final URL.

A different sequence with the same URL is useful feedback and should remain visible rather than being scored as a complete match.

## Notebook view

The supported notebook is:

```text
notebooks/01_run_product_evidence.ipynb
```

Its first post-run section displays:

- `business_judgement_steps_df`;
- `visual_evidence_summary_df`;
- the exact `business_judgement_review.md` path to share.

The lower notebook sections retain engineering diagnostics for investigation after the business comparison.

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
