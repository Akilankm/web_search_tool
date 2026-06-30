# Elite Evidence Engine

This repository remains a local/PDM Python package. It is not an AzureML component.

## Purpose

The Product Evidence Harness is now tournament-first. The evidence layer turns the tournament champion and runner-up evidence into enterprise artifacts for product coding, quality review, and governance.

The evidence system does not replace tournament selection. It explains and packages it.

## Production URL handoff

The key operational distinction is:

```text
product_url = best discovered/champion URL emitted by the harness
production_url_ready = whether product_url is safe for browser-opening and downstream scraping/coding
```

For high-stakes team handoff, use only rows where:

```text
production_url_ready = true
production_url_status = PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL
needs_review = false
```

Rows that fail this gate can still have `product_url`, but they are review-only.

## Row outputs

Each row folder includes:

```text
output/<row_id>/
├── tournament_bracket.json
├── tournament_bracket.md
├── batch_winners.csv
├── enterprise_assessment.json
├── evidence_graph.json
├── product_coding_input.json
├── review_feedback_template.json
└── quality_assessment.md
```

## Enterprise concepts

### 1. Tournament evidence graph

`evidence_graph.json` models the row as connected evidence:

```text
input product
  -> normalized identity graph
  -> candidate URLs
  -> scrape evidence
  -> deterministic identity verification
  -> batch winners / champion URL
  -> LLM adjudication when enabled
```

### 2. Production URL readiness

Batch outputs expose:

```text
production_url_ready
production_url_status
browser_openable
highly_scrapable
exact_product_url_match
production_url_score
production_url_reasons
```

This is the handoff contract for teams that manually open or scrape product URLs.

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

### 4. Quality tiers

| Tier | Meaning | Recommended action |
|---|---|---|
| A | Verified exact + production-ready + coding-ready | Auto-submit / use for coding |
| B | Exact and scrape-usable, but not fully coding-rich | Use with monitoring |
| C | URL available but exactness/coding readiness needs review | Review |
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
PRODUCT_URL_NOT_EXACT_MATCH_NEEDS_REVIEW
PRODUCT_URL_NOT_HIGHLY_SCRAPABLE_NEEDS_REVIEW
```

### 6. Product-coding handoff

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

Coding readiness status:

```text
CODING_READY
CODING_PARTIAL
URL_ONLY_NOT_CODING_READY
NEEDS_REVIEW
```

## Batch-level metrics

`outputs/metrics.json` and `outputs/batch_summary.md` include:

```text
operational product URL count
production-ready product URL count
browser-openable product URL count
highly scrapable product URL count
exact product URL match count
verified exact URL count
coding-ready count
needs-review count
quality-tier distribution
coding-readiness distribution
production URL status distribution
failure-taxonomy distribution
SerpAPI / LLM / scrape call counts
```

## Product-coding interpretation

Use this policy:

```text
production_url_ready=true + Tier A/B + CODING_READY/CODING_PARTIAL -> safe handoff / auto-use depending on business tolerance
production_url_ready=false                                      -> review-only, do not hand to scraper as production-ready
Tier C                                                        -> human review before coding
Tier D/E                                                      -> do not auto-code from URL alone
```
