# Product Identification Platform — System Workflow

## Objective

Resolve incomplete product text into the strongest defensible product identity.

```text
Primary output
= product_identification

Supporting output
= evidence sources, URLs and artifacts
```

Search results and URLs are evidence locations. They are not answers by themselves.

## End-to-end workflow

```text
Product input
→ Product interpretation
→ Product hypothesis construction
→ Adaptive source search
→ Candidate normalization
→ Static extraction
→ Rendered browser investigation
→ Multimodal evidence reasoning
→ Atomic evidence ledger
→ Hypothesis comparison
→ Exact-product verification
→ Product identity resolution
→ Requested-feature assessment
→ Supporting source selection
→ Decision audit and artifacts
```

## Stage 1 — Product input

Inputs:

```text
row_id
main_text
country_code
optional retailer_name
optional EAN/GTIN
optional language_code
feature_set
optional runtime controls
```

Validation occurs before paid search.

## Stage 2 — Product interpretation

The system extracts explicit claims, normalized values, assumptions, unknowns and negative constraints.

```text
brand
manufacturer
model
series
product form
variant
size
quantity
pack
category
```

## Stage 3 — Product hypothesis construction

The system creates one or more candidate product identities.

Each hypothesis contains:

```text
canonical name
attributes
assumptions
negative constraints
prior score
posterior probability
supporting evidence
contradicting evidence
```

Multiple hypotheses remain active until evidence resolves the ambiguity.

## Stage 4 — Adaptive source search

Search is used to find evidence that distinguishes hypotheses.

```text
manufacturer sources
→ requested retailer or same-country sources
→ global product sources
```

Search queries target unresolved identity fields rather than simply collecting many URLs.

## Stage 5 — Candidate normalization

Indirect, duplicate and obviously irrelevant sources are removed before expensive processing.

## Stage 6 — Static extraction

The system extracts text and structured facts such as product name, identifiers, specifications, brand, manufacturer, model, variant and pack.

## Stage 7 — Rendered browser investigation

The browser collects evidence unavailable through static requests:

```text
rendered text
expanded specifications
lazy-loaded content
screenshots
product gallery
package images
```

## Stage 8 — Multimodal evidence reasoning

Visual evidence is converted into explicit facts with asset provenance.

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

## Stage 9 — Evidence ledger

Every material fact is represented as atomic evidence.

```text
SUPPORTS
CONTRADICTS
NEUTRAL
```

Evidence includes source reliability, extraction confidence, affected hypotheses and hard-conflict status.

## Stage 10 — Hypothesis comparison

Posterior probabilities are updated using supporting and contradicting evidence.

Decision diagnostics include:

```text
identity completeness
ambiguity entropy
assumption burden
posterior margin
evidence count
hard conflicts
```

## Stage 11 — Exact-product verification

The leading hypothesis is checked across:

```text
EAN/GTIN
brand
manufacturer
model
variant
form
size
quantity
pack
market context
```

Sibling products and wrong variants must remain rejected even when their pages are visually similar.

## Stage 12 — Product identity resolution

Resolution states:

```text
EXACT
PROBABLE
AMBIGUOUS
CONFLICTING
INSUFFICIENT_EVIDENCE
```

The primary result is:

```text
product_identification.resolution_status
product_identification.leading_hypothesis
product_identification.hypotheses
product_identification.claims
product_identification.uncertainties
product_identification.evidence_ledger
```

## Stage 13 — Requested-feature assessment

The active feature schema determines whether requested downstream facts are supported.

Feature completeness is reported separately from product identity.

## Stage 14 — Supporting source selection

Qualified source pages may be selected for evidence reuse.

```text
manufacturer evidence
retailer evidence
global evidence
```

### Source-authority selection

Authority ranks evidence sources after their relevance and usability are evaluated.

### URL durability and usability

URL checks describe the source:

```text
browser-openable
text-accessible
individual product page
non-expiring
reusable
```

A failed source check does not automatically invalidate an `EXACT` product identification.

## Stage 15 — Structured no-safe-URL outcome

When no reusable direct source is available:

```text
resolution_outcome.code=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
```

This is a source-delivery result. It does not claim that the product identity is absent.

## Stage 16 — Decision audit sequence

Every terminal product result exposes:

```text
observable evidence
→ explicit rule
→ product judgment
→ next action
```

This is written to:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

## Runtime control flow

Per-job controls are validated, context-local, concurrency-safe and persisted in `run_configuration.json`.

```text
Latency Optimized
Standard
Coverage Optimized
```

Controls change evidence depth, not identity semantics.

## UI result hierarchy

```text
1. identified product
2. resolution status and confidence
3. resolved identity fields
4. evidence basis
5. alternative product hypotheses
6. unresolved distinctions
7. supporting source evidence
8. audit and artifacts
```

Source-quality values are displayed as:

```text
VERIFIED
NOT VERIFIED
NOT ASSESSED
```

The UI must never use URL checks as the headline product verdict.

## Terminal interpretation

| Product resolution | Meaning |
|---|---|
| `EXACT` | Product identified |
| `PROBABLE` | Leading product identified with residual uncertainty |
| `AMBIGUOUS` | Multiple plausible products remain |
| `CONFLICTING` | Evidence materially disagrees |
| `INSUFFICIENT_EVIDENCE` | Product cannot be defensibly identified |

Technical `FAILED` remains reserved for software, configuration, dependency or result-contract errors.

## Primary artifacts

```text
product_belief.json
product_understanding.md
belief_updates.md
evidence_ledger.jsonl
business_judgement_review.md
orchestrated_result.json
```

## Supporting source artifacts

```text
adaptive_search_trace.json
candidate_url_records.json
candidates.csv
source_selection.json
primary_url_acceptance.json
mandatory_url_delivery.json
```

## Related documents

- [Feature reference](FEATURE_REFERENCE.md)
- [Product Identification Platform UI](PRODUCT_EVIDENCE_UI.md)
- [Final system contract](FINAL_SYSTEM_CONTRACT.md)
- [Business judgment review](BUSINESS_JUDGEMENT_REVIEW.md)
