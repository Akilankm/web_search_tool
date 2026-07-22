# Product URL Finder — System Workflow

## Objective

Resolve incomplete product text to the strongest usable direct product URL.

```text
Primary output
= product URL

Acceptance basis
= Source + Evidence + Identity + Usability
```

Product interpretation is necessary because the URL must represent the intended product. It is not an alternative to URL delivery.

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
→ Requested-feature assessment
→ Source-authority selection
→ Strict URL selection
→ Best-available review URL recovery
→ URL delivery
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

The system extracts product identity dimensions required to formulate precise search queries and reject wrong URLs:

```text
brand
manufacturer
model or series
product form
variant
size
quantity
pack
category
```

## Stage 3 — Product hypothesis construction

One or more candidate product identities are maintained until evidence resolves ambiguity. Each hypothesis contains canonical name, attributes, assumptions, constraints, probability and evidence references.

## Stage 4 — Adaptive source search

Search order:

```text
manufacturer sources
→ requested retailer or same-country sources
→ global product sources
```

The final search credit is reserved for direct product-URL recovery when no direct candidate has been collected.

## Stage 5 — Candidate normalization

The system canonicalizes URLs, deduplicates candidates and rejects:

```text
search-result pages
category or collection pages
homepages
social/community pages
documents and media
Google or SerpAPI intermediary URLs
```

## Stage 6 — Static extraction

Static acquisition collects product title, identifiers, structured data, specifications, page type, text extractability, images and URL finalization signals.

## Stage 7 — Rendered browser investigation

The browser validates promising candidates through rendered text, expandable product sections, screenshots and product images.

## Stage 8 — Multimodal evidence reasoning

Visual facts are recorded with provenance:

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

## Stage 9 — Evidence ledger

Material facts are stored as atomic supporting, contradicting or neutral evidence with source reliability and extraction confidence.

## Stage 10 — Hypothesis comparison

The system updates product hypotheses using posterior probability, assumption burden, evidence coverage, contradictions and hard conflicts.

## Stage 11 — Exact-product verification

Every candidate is checked against:

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

Confirmed wrong products and confirmed wrong variants are terminally ineligible for delivery.

## Stage 12 — Product identity resolution

Identity states include:

```text
EXACT
PROBABLE
AMBIGUOUS
CONFLICTING
INSUFFICIENT_EVIDENCE
```

Identity resolution determines whether a URL represents the intended product and how prominently it should rank.

## Stage 13 — Requested-feature assessment

The active feature schema evaluates evidence coverage and conflicts. Missing non-identity features can move a URL from verified delivery to review delivery, but they do not force an empty result when a usable non-mismatched direct URL exists.

## Stage 14 — Source-authority selection

Among otherwise qualified candidates, source priority is:

```text
official manufacturer
→ requested retailer / same-country retailer
→ other same-country source
→ qualified global source
→ marketplace last resort
```

Authority never overrides confirmed identity mismatch.

## Stage 15 — Strict URL selection

A strictly verified URL must be:

```text
direct individual product page
browser-openable
text-extractable
exact product and variant
sufficient requested evidence
non-expiring and reusable
```

Strictly verified URLs produce `URL_DELIVERED_VERIFIED`.

## Stage 16 — Best-available review URL recovery

When strict selection fails, the delivery layer examines all available candidate sources:

```text
product_match URLs
evidence-set selected URLs
candidate records
feature assessments
browser evidence
browser investigations
SERP result URLs
candidate_url_records.json
candidate_state.json
```

Candidates are deduplicated and ranked. The strongest real direct URL is delivered for review when it is not a confirmed product or variant mismatch.

Review URLs produce `URL_DELIVERED_REVIEW_REQUIRED`.

## Stage 17 — Exceptional URL-delivery failure

An empty URL is permitted only when no non-mismatched direct external product-page candidate remains after strict selection and recovery.

```text
URL_DELIVERY_FAILED
```

This is an exceptional escalation and not a successful business output.

## Stage 18 — Decision audit sequence

Each terminal run records:

```text
observable evidence
→ explicit rule
→ URL/product judgment
→ next action
```

This is written to `business_judgement_review.md` and does not expose hidden chain-of-thought.

## Runtime control flow

Per-job controls are validated, concurrency-safe and persisted in `run_configuration.json`.

```text
Focused
Standard
Extended
```

Controls change investigation depth. They do not permit fabricated, indirect or confirmed-mismatch URLs.

## UI result hierarchy

```text
1. product URL
2. verified or review-delivery status
3. Source
4. Evidence
5. Identity
6. Usability
7. brief justification
8. collapsed review details
```

The UI must never present an empty URL as a successful or ordinary result.

## Terminal interpretation

| Status | Meaning |
|---|---|
| `URL_DELIVERED_VERIFIED` | Strict product URL delivered |
| `URL_DELIVERED_REVIEW_REQUIRED` | Strongest real direct product URL delivered with warnings |
| `URL_DELIVERY_FAILED` | No non-mismatched direct product candidate survived recovery |
| `TECHNICAL_FAILURE` | Software, configuration, dependency or contract failure |

## Primary artifacts

```text
executive_summary.json
product_belief.json
product_understanding.md
evidence_ledger.jsonl
candidate_url_records.json
candidate_state.json
business_judgement_review.md
mandatory_url_delivery.json
orchestrated_result.json
```
