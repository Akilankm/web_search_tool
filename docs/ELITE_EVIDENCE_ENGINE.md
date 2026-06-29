# Elite Evidence Engine

This repository remains a local/PDM Python package. This enhancement does **not** convert the harness into an AzureML component.

## Purpose

The Product Evidence Harness now produces enterprise-grade evidence artifacts for product coding, not only a URL decision. The new layer keeps the existing search/scrape/verification/selection logic intact and adds an observable evidence synthesis layer.

## Added enterprise outputs

Each row folder now includes:

```text
output/<row_id>/
├── enterprise_assessment.json
├── evidence_graph.json
├── product_coding_input.json
├── review_feedback_template.json
└── quality_assessment.md
```

These are written in addition to the existing row artifacts such as `final_row.csv`, `report.md`, `decision_trace.md`, and `trace.json`.

## Enterprise concepts

### 1. Evidence graph

`evidence_graph.json` models the row as connected evidence:

```text
input product
  -> normalized identity graph
  -> candidate URLs
  -> scrape evidence
  -> deterministic identity verification
  -> LLM adjudication when enabled
```

This makes the system easier to audit and debug than a flat candidate list.

### 2. Source reliability

Each candidate receives a source reliability estimate based on source/domain type:

- manufacturer-like domains
- retailer/domain evidence
- marketplace evidence
- aggregator/reference evidence

This is used as supporting metadata, not as a replacement for scraping or verification.

### 3. Confidence decomposition

The enterprise layer decomposes confidence into:

```text
identity_confidence
scrapability_confidence
country_confidence
retailer_confidence
variant_confidence
source_consensus_score
coding_readiness_confidence
final_confidence
```

This explains *why* a row is strong or weak.

### 4. Quality tiers

Rows are assigned a quality tier:

| Tier | Meaning | Recommended action |
|---|---|---|
| A | Verified exact + scrape-usable + coding-ready | Auto-submit / use for coding |
| B | Exact and scrape-usable, but not fully coding-rich | Use, monitor coding gaps |
| C | Usable product URL but exactness/coding readiness needs review | Review |
| D | Reference-only or weak evidence | Do not auto-submit |
| E | No usable URL/evidence or runtime error | Manual escalation |

### 5. Failure taxonomy

Rows expose machine-readable failure tags such as:

```text
NO_CANDIDATE_FOUND
NO_SCRAPABLE_PRODUCT_URL_FOUND
REQUESTED_RETAILER_NOT_SELECTED
REQUESTED_RETAILER_BLOCKED_OR_THIN
VARIANT_CONFLICT
EAN_CONFLICT
HOMEPAGE_OR_LISTING_PAGE_CANDIDATE
SOFT_404_OR_REMOVED_PAGE
PRODUCT_PAGE_THIN
LLM_OR_EVIDENCE_INSUFFICIENT
ONLY_GLOBAL_OR_GLOBAL_FALLBACK_SELECTED
```

This allows systematic improvement instead of manual guessing.

### 6. Coding readiness

`product_coding_input.json` gives downstream product feature coding a clean payload:

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

The coding readiness status is one of:

```text
CODING_READY
CODING_PARTIAL
URL_ONLY_NOT_CODING_READY
NEEDS_REVIEW
```

### 7. Review feedback template

`review_feedback_template.json` captures human review corrections in a structured way. Initially this is a template only; future work can use these reviewed records to tune ranking, retailer-domain intelligence, variant rules, and benchmark metrics.

## Batch-level metrics

Batch runs now also write:

```text
outputs/metrics.json
```

The batch summary includes:

- operational product URL count
- verified exact URL count
- coding-ready count
- needs-review count
- quality-tier distribution
- coding-readiness distribution
- failure-taxonomy distribution
- SerpAPI / LLM / scrape call counts

## Product-coding interpretation

Use this policy:

```text
Tier A + CODING_READY      -> safe for automated product coding
Tier B + CODING_PARTIAL    -> usable URL, may need fallback evidence for some features
Tier C                     -> human review before coding or code with caution
Tier D/E                   -> do not auto-code from URL alone
```

## What this does not do yet

This is not an AzureML component and does not train a model. It lays the local package foundation for:

- benchmark dashboards
- feedback-driven rule tuning
- per-retailer memory/cache
- rulebook-aware feature evidence extraction
- future AzureML packaging if/when needed
