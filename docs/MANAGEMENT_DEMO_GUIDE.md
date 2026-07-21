# Product Evidence Platform — Management and Leadership Demo Guide

> Use the Streamlit application during leadership calls. The three notebooks remain the analytical, batch and diagnostic workflows.

## Executive opening

The platform converts incomplete vendor product text into a defensible exact-product decision. It does not accept the first search result. It interprets product identity, searches for authoritative product truth, investigates promising pages through rendered browser sessions, combines text and image evidence, applies deterministic production gates, and exposes the complete observable business judgment sequence.

When bounded search cannot find a safe direct product page, it does not fabricate a URL and does not collapse into a traceback. It returns a structured `REVIEW_REQUIRED` result with the complete search trace, reason, artifacts and next actions.

Leadership demo surface:

```text
apps/leadership_demo.py
```

Supported notebook workflows:

```text
notebooks/01_single_product.ipynb
notebooks/02_batch_products.ipynb
notebooks/03_artifact_diagnostics.ipynb
```

## Business problem

Inputs such as `PKM ME04 WACHSENDES CHAOS BOOSTER` may omit the exact product form, edition, pack, EAN, retailer and language. A plausible search result may still be a category page, sibling variant, wrong pack, blocked page, expiring link or page missing the features required for coding.

The business problem is therefore not “find a URL.” It is:

```text
identify the intended product
→ gather sufficient evidence
→ reject plausible but wrong alternatives
→ deliver the strongest safe direct page
→ preserve every material decision for review
```

## Management value

| Need | Platform capability | Business value |
|---|---|---|
| Exact product identification | Identity interpretation and conflict gates | Reduces silent miscoding |
| Product truth | Manufacturer-first authority after strict gates | Improves specification quality |
| Market context | Retailer, country and global fallback | Preserves pack and local context |
| Packaging evidence | Screenshots and image reasoning | Recovers facts absent from page text |
| Governance | `business_judgement_review.md` | Enables human sequence comparison |
| Safe search exhaustion | Structured no-safe-URL outcome | Preserves trace without fabrication or crash |
| Budget governance | Per-job UI controls with fixed safety boundaries | Makes cost/latency trade-offs visible |
| Throughput | Bounded parallel CSV notebook | Scales without opaque aggregation |
| Comprehension | Streamlit and interactive artifact diagnostics | Makes the system understandable to non-developers |

## Input and feature contract

Single product input:

```python
product = {
    "row_id": "DEMO-001",
    "main_text": "Vendor product text",
    "country_code": "CH",
    "retailer_name": None,
    "ean": None,
    "language_code": None,
}
```

`main_text` and `country_code` are mandatory. Retailer, EAN/GTIN and language are optional. Requested coding features are resolved through `inputs/private/toy_features.json` by default.

## End-to-end architecture

```text
Leadership Streamlit UI or notebook
→ Product Evidence Agent API
→ identity interpretation and uncertainty
→ adaptive SerpAPI search planner
→ candidate precision gate
→ static extraction and rendered browser
→ screenshot / gallery / package image evidence
→ exact-product and requested-feature validation
→ URL durability and source-authority selection
→ final URL or structured no-safe-URL result
→ product artifacts and human-comparable review
```

Current runtime:

```text
belief-url-resolution-v8-leadership-demo
```

Required capabilities:

```text
leadership_demo_runtime_options=true
structured_no_url_review_outcome=true
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
```

## Leadership Streamlit workflow

Launch:

```bash
bash scripts/run_leadership_demo.sh --install   # first use only
bash scripts/run_leadership_demo.sh             # later runs
```

The UI shows:

- runtime and browser health;
- immutable platform capabilities;
- product input and feature set;
- safe per-job budget controls;
- live execution stage;
- final URL, role, manufacturer and retailer references;
- strict acceptance gates;
- requested versus effective budget and actual usage;
- search stages and rejected candidates;
- visual evidence impact;
- chronological business judgments;
- downloadable Markdown and JSON artifacts.

Budget presets:

```text
Fast leadership demo
Balanced production demo
Deep evidence demo
```

These settings are scoped to one job. The UI cannot change credentials, exact-product gates, feature completeness, URL durability, manufacturer-first policy or the no-fabrication rule.

## Three notebook workflows

### `notebooks/01_single_product.ipynb`

Use for one-product analytical review. It displays `final_decision_df`, `business_judgement_steps_df`, `visual_evidence_summary_df`, candidates, feature evidence and `single_product_diagnostics.xlsx`.

### `notebooks/02_batch_products.ipynb`

Use for bounded parallel CSV execution. It writes:

```text
data/batch_runs/<run_id>/
├── batch_input_normalized.csv
├── batch_results.csv
├── batch_failures.csv
├── batch_artifact_index.csv
└── batch_run_summary.json
```

A no-safe-URL product remains a `REVIEW_REQUIRED` business result and is not classified as an infrastructure failure.

### `notebooks/03_artifact_diagnostics.ipynb`

Use offline for any existing artifact. It provides:

```text
Decision Map
Judgment Timeline
Candidates
Evidence
Artifacts
```

It also writes `artifact_diagnostics_interactive.html`, `artifact_diagnostic_report.md` and `artifact_diagnostic_workbook.xlsx`.

## Processing workflow and business judgments

```text
1. Validate mandatory input
2. Interpret likely product and unresolved distinctions
3. Search official manufacturer/product truth
4. Search requested retailer or country alternatives
5. Use global fallback when needed
6. Deduplicate and preflight candidates
7. Scrape and open promising individual product pages
8. Use rendered text, structured data, screenshots and images
9. Apply exact identity, browser, feature, scrapability and durability gates
10. Select manufacturer or controlled retailer/global fallback
11. Create a structured no-URL outcome when no candidate is safe
12. Write result, run configuration and human-comparable judgment artifacts
```

Each judgment follows:

```text
observable evidence
→ explicit business rule
→ agent judgment
→ next action
```

## URL selection and acceptance

The final URL must be:

```text
exact product/model/form/variant/size/quantity/pack
+ browser-openable individual product page
+ text-scrapable and information-rich
+ complete for requested features
+ free from disqualifying conflicts
+ durable and non-expiring
```

Authority is applied only after those gates:

```text
official manufacturer
→ requested retailer / country retailer
→ global exact-product source
→ marketplace last resort
```

Outputs include `primary_url`, `primary_url_role`, `manufacturer_url`, `retailer_url` and `source_selection`.

No-safe-URL result:

```text
job_status=REVIEW_REQUIRED
primary_url=null
primary_url_role=NONE
resolution_outcome.code=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
url_delivery.delivered=false
url_fabricated=false
```

## Multimodal evidence

The decision is not text-only. The browser can use rendered screenshots, product galleries, package front/back images, visible specifications, warnings and dimension diagrams.

Vision evidence is recorded as:

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

`visual_evidence_summary_df` and the Streamlit Evidence tab distinguish whether images materially supported the selected URL, were used but not proven decisive, or were not recorded.

## Human-comparable decision artifact

Every `COMPLETED` or `REVIEW_REQUIRED` product writes:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

Each step records:

```text
business question
observable evidence
business rule
agent judgment
alternatives and rejection reason
next action
confidence and outcome
visual-evidence use
```

The reviewer marks `IDENTICAL`, `PARTIALLY IDENTICAL` or `NOT IDENTICAL` and identifies the first divergent step. Behavioral validation compares the sequence, not merely the final URL.

## Artifacts

Product artifacts can include:

```text
business_judgement_review.md
run_configuration.json
product_belief.json
product_understanding.md
market_decision_path.md
belief_updates.md
evidence_ledger.jsonl
adaptive_search_trace.json
candidate_url_records.json
candidates.csv
primary_url_acceptance.json
mandatory_url_delivery.json
source_selection.json
orchestrated_result.json
single_product_diagnostics.xlsx
```

No-safe-URL outcomes additionally include `no_url_resolution.json`.

## Performance, latency, tokens and cost

The UI exposes configured per-job limits and actual search credits consumed. Batch outputs record elapsed time, throughput, mean latency, p50, p95, status counts and total SerpAPI credits.

**These are limits, not actual usage.** Early stopping may consume less.

`LLM_MAX_TOKENS` is a response ceiling, not actual usage. Per-call token logs exist, but one canonical per-product summary is not yet persisted. A fixed SLA must not be claimed until representative runs establish p50 and p95 values.

Recommended future artifacts:

```text
execution_metrics.json
llm_usage.json
```

Cost per product combines search credits, input/output tokens, browser/compute time, storage and human review.

## Recommended KPIs

- final URL agreement rate;
- human judgment-sequence equivalence rate;
- first-divergent-step distribution;
- completion, review-required and genuine-failure rates;
- no-safe-direct-URL rate;
- manufacturer-primary and retailer-fallback rates;
- visual-evidence correctness;
- products per minute;
- p50 and p95 latency;
- search credits, LLM calls and tokens per product;
- cost per completed product;
- artifact completeness.

## Assumptions

- each row represents one intended product;
- a direct public product page may exist but is not guaranteed;
- requested features are defined before execution;
- manufacturer authority is conditional on exactness and completeness;
- row IDs uniquely identify artifact directories;
- human feedback is available for behavioral validation.

## Constraints and non-goals

- pages may change, block automation or disappear;
- some products have no durable public URL;
- bounded budgets do not test every source on the internet;
- image availability does not prove image causality;
- the current job store is in memory;
- the app is a demo surface, not a public production deployment;
- the platform does not expose hidden chain-of-thought;
- configured limits are not measured SLA values.

## Failure handling

| Condition | Response |
|---|---|
| Missing input | Reject before paid search |
| Stale runtime | Require clean rebuild |
| Browser-planner LLM failure | Deterministic rendered-page fallback where allowed |
| Manufacturer incomplete | Controlled retailer/global fallback |
| No safe URL after bounded search | Structured `REVIEW_REQUIRED`; preserve trace and do not fabricate |
| Unstructured empty successful result | Hard contract failure |
| Genuine runtime/configuration failure | Red `FAILED` outcome with technical detail separated |
| Missing artifact evidence | Report absence; never invent it |

## Change-impact map

| Requirement | Modification area |
|---|---|
| Change source priority | Source authority and final selector |
| Change requested features | Feature schema |
| Change safe demo budget ranges | `demo_runtime_options.py` |
| Change acceptance rules | Identity and strict URL gate modules |
| Change no-URL policy | Structured no-URL outcome and result contract |
| Increase throughput | Agent workers, browser contexts, queue architecture and load tests |
| Change Streamlit narrative | `apps/leadership_demo.py` |
| Change artifact diagnostics | Interactive diagnostics module and notebook |
| Persist cost/latency | `execution_metrics.json` and `llm_usage.json` instrumentation |
| Change human review form | Business judgment artifact builder |

## Demo script

1. Open the Streamlit UI and show runtime v8 health.
2. Explain the complete capability cards before entering input.
3. Select a budget preset and explain that safety gates remain locked.
4. Submit one incomplete product description and narrate live stages.
5. Show the final URL role and strict acceptance gates.
6. Compare requested budget with actual credits and candidates consumed.
7. Show visual evidence and candidate rejection reasons.
8. Show the chronological judgment trace.
9. Download `business_judgement_review.md`.
10. Optionally open the same artifact in `03_artifact_diagnostics.ipynb` for deeper engineering review.

## Pre-demo checklist and metric card

```text
[ ] latest master pulled
[ ] runtime v8 health is green
[ ] leadership_demo_runtime_options=true
[ ] structured_no_url_review_outcome=true
[ ] Streamlit port 8501 is forwarded privately
[ ] unique row_id prepared
[ ] business_judgement_review.md is generated
[ ] no unsupported SLA or cost claim is shown
```

Record submitted products, completed/review/failed counts, no-safe-URL count, elapsed time, credits used, manufacturer/retailer selections, image-supported decisions and human-equivalent sequences.

## Leadership questions

**Is it a search wrapper?** No. Search discovers candidates; browser evidence and deterministic gates decide whether any URL is safe.

**Does it always prefer the manufacturer?** Only when the exact official page passes every mandatory gate.

**Does it use images?** Yes, and it records whether visual evidence supported the final feature gate.

**Can leadership change the budget?** Yes, within safe per-job bounds. Safety and source policies remain locked.

**What happens when no safe URL is found?** The platform returns `REVIEW_REQUIRED` with `NO_SAFE_DIRECT_PRODUCT_URL_FOUND`, preserves every artifact and refuses to fabricate an answer.

**Can it process CSVs?** Yes, through the bounded parallel batch notebook with one full artifact per product.

**Can people understand the decisions?** Yes. Streamlit presents the executive view; the diagnostic notebook reconstructs the complete interactive evidence workspace.

## Leadership decisions for scale

Leadership should define acceptable human-equivalence, review and no-safe-URL rates; batch volumes; p95 targets; cost-per-product ceiling; artifact retention; governance ownership; public deployment requirements; and whether a persistent distributed queue is required.
