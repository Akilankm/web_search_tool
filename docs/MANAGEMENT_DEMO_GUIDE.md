# Product Evidence Platform — Management and Leadership Demo Guide

> Open this document during a leadership demonstration. It explains the business problem, workflow, decision policy, evidence, outputs, assumptions, constraints, performance model, governance and change-impact areas.

---

## 1. Executive opening

The Product Evidence Platform converts incomplete vendor product text into a defensible product-detail URL.

It does not accept the first search result. It:

1. interprets the product and remaining ambiguity;
2. searches the official manufacturer first;
3. searches the requested retailer or country market next;
4. uses global fallback only when required;
5. opens candidate pages in a real browser;
6. validates exact product, model, form, variant, size, quantity and pack;
7. uses page text, structured data, screenshots and product/package images;
8. verifies the features required for coding;
9. rejects blocked, incomplete, wrong-product, category and expiring URLs;
10. selects the strongest qualified manufacturer or retailer page;
11. writes a human-comparable record of the business judgments.

The deliverable is therefore:

```text
primary URL
+ manufacturer and retailer references
+ evidence
+ acceptance decision
+ human-reviewable judgment sequence
```

---

## 2. Business problem

Typical input may be incomplete:

```text
PKM ME04 WACHSENDES CHAOS BOOSTER
```

It may omit manufacturer, full product name, model, edition, product form, variant, unit, pack, EAN, retailer or language.

A plausible search result can still be wrong because it may be:

- a category or collection page;
- a sibling model or edition;
- the wrong size, quantity or pack;
- a marketplace listing with weak authority;
- inaccessible to scraping or browser automation;
- dependent on an expiring session URL;
- missing the features required for coding.

The platform converts that ambiguity into a bounded, auditable resolution process.

---

## 3. Management value

| Need | Capability | Value |
|---|---|---|
| Find the exact product | Belief-driven interpretation and identity gates | Reduces silent miscoding |
| Prefer product truth | Manufacturer-first hierarchy | Improves specification quality |
| Preserve local context | Retailer/country stage | Retains pack, market, price and availability context |
| Use packaging evidence | Screenshot and image reasoning | Recovers evidence absent from text |
| Explain the result | Business judgment Markdown | Enables human governance |
| Control usage | Three search credits and bounded browser/scrape limits | Predictable resource envelope |
| Avoid false success | Explicit `COMPLETED`, `REVIEW_REQUIRED`, `FAILED` | Makes uncertainty visible |
| Improve systematically | First-divergent-step review | Converts feedback into targeted development |

---

## 4. Input and feature contract

```python
product = {
    "row_id": "ROW-001",
    "main_text": "Vendor product main text",
    "country_code": "CH",
    "retailer_name": None,
    "ean": None,
    "language_code": None,
}
```

| Field | Purpose |
|---|---|
| `row_id` | Unique run and artifact folder |
| `main_text` | Primary product-identification signal |
| `country_code` | Target commercial market |
| `retailer_name` | Optional requested retailer |
| `ean` | Optional strong identity evidence |
| `language_code` | Optional search/page language |
| `feature_set` | Evidence that the final page must support |

Default committed feature schema:

```text
inputs/private/toy_features.json
```

The feature schema is part of acceptance, not only reporting. With strict coverage enabled, the final page must support the requested features without unresolved conflicts.

---

## 5. End-to-end architecture

```text
Notebook
  → runtime readiness
  → product interpretation and hypotheses
  → three-credit adaptive search
       1. manufacturer_primary
       2. requested_retailer_country / country_alternative
       3. global_fallback
  → candidate normalization and deduplication
  → static scrape
  → rendered browser and image investigation
  → exact identity and feature assessment
  → strict acceptance gates
  → manufacturer-first authority selection
  → result and artifacts
  → human judgment-sequence comparison
```

Runtime topology:

```text
Azure ML Compute Instance
├── Jupyter notebook
├── Docker Compose
│   ├── Product Evidence Agent
│   └── Browser Service
├── SerpAPI
├── Enterprise Azure OpenAI-compatible endpoint
└── Repository-local artifact storage
```

---

## 6. Processing workflow and business judgments

### Stage 0 — Runtime readiness

Before paid search, the notebook verifies repository-local imports, agent/browser health, LLM configuration, search policy, manufacturer-first selection and artifact capability.

Current contract:

```text
belief-url-resolution-v6-business-judgement-review
```

Required capabilities include:

```text
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
```

A stale agent can be rebuilt before product submission:

```bash
./scripts/azureml_startup.sh --clean-build
```

**Business judgment:** Is the execution environment trustworthy enough to begin?

### Stage 1 — Input validation

Validates mandatory fields, feature-set resolution, EAN normalization, environment and artifact path.

**Business judgment:** Is there enough valid information to interpret the product without inventing missing facts?

### Stage 2 — Offline interpretation

The system extracts or hypothesizes brand, product name, model, edition, form, variant, size, quantity, pack, identifiers and unresolved ambiguity. Competing hypotheses may be retained.

```text
single booster pack
vs display box
vs promotional bundle
```

**Business judgment:** What product is most likely, what alternatives remain plausible and what evidence must search resolve?

### Stage 3 — Three-credit search

```text
Credit 1: manufacturer_primary
Credit 2: requested_retailer_country or country_alternative
Credit 3: global_fallback
```

- Credit 1 seeks official product truth.
- Credit 2 preserves requested-retailer or local-market context.
- Credit 3 relaxes country restriction while retaining exact-product requirements.
- Marketplace pages remain last-resort review candidates.
- A retailer found during credit 1 is retained but cannot stop manufacturer evaluation.

**Business judgment:** Which evidence source should be searched next, and is another paid credit necessary?

### Stage 4 — Candidate formation

Normalizes URLs, removes duplicates, records stage/position, classifies source role and excludes clearly unsafe URLs.

**Business judgment:** Which unique pages justify scrape or browser capacity?

### Stage 5 — Static scraping

Checks reachability, product-page shape, text scrapability, richness and obvious identity conflicts.

**Business judgment:** Does this candidate contain enough credible evidence for deeper investigation?

### Stage 6 — Agentic browser investigation

The browser can inspect rendered product names, expand specifications, capture screenshots, collect gallery/package images, inspect warnings and dimensions and detect blocks or misleading page states.

If the browser-planning LLM fails, deterministic rendered acquisition may preserve evidence; it does not bypass final gates.

**Business judgment:** Which browser action resolves the remaining identity or feature uncertainty?

### Stage 7 — Multimodal evidence

The workflow can use screenshots, product galleries, package front/back, labels, visual identifiers, pack count and diagrams.

Vision evidence is explicit:

```text
extraction_method=vision_llm
evidence_location=visual_asset:<asset_id>
```

The review distinguishes:

```text
YES_VISUAL_EVIDENCE_SUPPORTED_SELECTED_URL_FEATURE_GATE
VISUAL_EVIDENCE_USED_BUT_NOT_RECORDED_AS_DECISIVE_FOR_SELECTED_URL
NO_VISUAL_EVIDENCE_RECORDED
```

It reports `UNKNOWN_NOT_COUNTERFACTUALLY_TESTED` for whether text alone would have passed unless a true text-only comparison was run.

**Business judgment:** Did visual evidence confirm the item, resolve a feature or reveal a conflict?

### Stage 8 — Exact identity

Checks EAN, brand, model, canonical name, edition, form, size, quantity, pack and rendered packaging.

```text
single pack ≠ display box
500 ml ≠ 750 ml
standard edition ≠ collector edition
family page ≠ individual SKU page
```

**Business judgment:** Is this the exact requested product and configuration?

### Stage 9 — Requested-feature coverage

Records supported, missing and conflicting features, overall/required/critical coverage and the evidence source.

**Business judgment:** Does this page contain enough evidence for the intended coding task?

### Stage 10 — Strict primary acceptance

A production-ready URL must pass:

```text
browser-openable
+ text-scrapable
+ rendered individual product verified
+ exact identity verified
+ requested features complete
+ no unresolved conflicts
+ durable non-expiring URL
```

### Stage 11 — Source selection

Authority is applied only after safety gates:

```text
qualified manufacturer
→ requested retailer / country retailer
→ global exact-product source
→ marketplace last resort
```

Final rule:

> Select the official manufacturer when it is exact, complete, accessible and durable. Otherwise select the strongest qualified retailer or exact-product page.

### Stage 12 — Outcome

| Outcome | Meaning |
|---|---|
| `COMPLETED` | Strict production-ready URL delivered |
| `REVIEW_REQUIRED` | Real direct URL delivered but human confirmation required |
| `FAILED` | No safe direct URL or execution failure |

The workflow never reports success with an empty URL. No safe page produces `MANDATORY_PRODUCT_URL_NOT_FOUND`.

---

## 7. Final result fields

| Field | Meaning |
|---|---|
| `primary_url` | Strongest product-truth page |
| `primary_url_role` | Manufacturer, retailer, marketplace or other role |
| `manufacturer_url` | Best qualified official manufacturer page |
| `retailer_url` | Best qualified commercial reference |
| `source_selection` | Why manufacturer or retailer became primary |
| `primary_url_acceptance` | Gate-by-gate decision |
| `url_delivery` | Whether a real URL was delivered |
| `product_identification` | Leading product interpretation and status |
| `search.market_decision_path` | Search-route narrative |
| `business_judgement_review` | Human-comparison artifact metadata and steps |

---

## 8. Human-comparable decision artifact

Every final run creates:

```text
data/artifacts/<row_id>/business_judgement_review.md
```

Each step follows:

```text
business question
→ observable evidence
→ explicit rule
→ agent judgment
→ resulting action
```

The human reviewer selects:

- `IDENTICAL`;
- `PARTIALLY IDENTICAL`;
- `NOT IDENTICAL`.

They record the first divergent step, human judgment, missed/overweighted evidence, image interpretation and recommended change.

The acceptance criterion is therefore not only final-URL equality. It is **behavioral equivalence of the decision sequence**.

---

## 9. Artifacts

```text
data/artifacts/<row_id>/
├── business_judgement_review.md
├── product_belief.json
├── product_understanding.md
├── market_decision_path.md
├── belief_updates.md
├── evidence_ledger.jsonl
├── adaptive_search_trace.json
├── candidate_url_records.json
├── candidates.csv
├── primary_url_acceptance.json
├── mandatory_url_delivery.json
├── source_selection.json
├── orchestrated_result.json
├── review.md
└── single_product_diagnostics.xlsx
```

| Artifact | Purpose |
|---|---|
| `business_judgement_review.md` | Shareable human/management decision narrative |
| `product_belief.json` | Hypotheses, uncertainty and evidence state |
| `adaptive_search_trace.json` | Search credits, engines, queries and outcomes |
| `candidates.csv` | Candidate funnel |
| `primary_url_acceptance.json` | Strict gate results |
| `source_selection.json` | Manufacturer-versus-retailer decision |
| `orchestrated_result.json` | Stable integration response |
| `single_product_diagnostics.xlsx` | Tabular management and engineering review |

Workbook sheets include `business_judgments`, `visual_evidence_impact`, `source_selection`, `url_delivery`, candidate results, feature evidence and selection RCA.

---

## 10. Performance, latency, tokens and cost

### 10.1 Configured resource envelope

| Resource | Default |
|---|---:|
| SerpAPI credits | 3 maximum |
| Full scrapes | 6 maximum |
| Scrapes per domain | 2 maximum |
| Scrape candidates per stage | 2 |
| Agentic browser candidates | 3 |
| Browser turns per candidate | 4 |
| Browser actions per candidate | 6 |
| Images available to browser reasoning | 8 maximum |
| LLM response ceiling | 1,600 generated tokens per call |
| LLM temperature | 0.0 |
| LLM retries | 2 |
| LLM read timeout | 120 seconds |
| Browser navigation timeout | 60 seconds |
| Agent workers | 2 |

These are limits, not actual usage.

### 10.2 End-to-end latency model

```text
readiness
+ interpretation
+ search latency
+ candidate processing
+ static scraping
+ browser navigation/actions
+ image and vision reasoning
+ feature assessment
+ final selection
+ artifact writing
```

Main variable drivers are external page responsiveness, number of search credits required, admitted candidates, browser actions, images, LLM gateway latency and retries.

Current timing evidence includes notebook recovery time, heartbeat elapsed time, job `created_at`/`updated_at`, progress stage and candidate/search/browser counts.

**Current limitation:** the result does not yet persist a canonical per-stage timing table. A fixed SLA must not be claimed from one demo run.

Recommended future artifact:

```text
execution_metrics.json
├── total_elapsed_seconds
├── stage_elapsed_seconds
├── search_seconds_by_credit
├── scrape_seconds_by_candidate
├── browser_seconds_by_candidate
├── vision_seconds
├── selection_seconds
└── retries_and_timeouts
```

### 10.3 Token usage

Each successful LLM call records:

```text
purpose
prompt_tokens
completion_tokens
total_tokens
model
finish_reason
```

Process-level counters aggregate LLM calls and tokens. Tokens may be used by product interpretation, search planning/feedback, browser turns, image inspection, vision feature reasoning and optional text feature reasoning.

**Current limitation:** counters are not yet isolated into one canonical per-product summary when jobs run concurrently. `LLM_MAX_TOKENS` is a response ceiling, not actual usage.

Recommended future artifact:

```text
llm_usage.json
├── calls_by_purpose
├── prompt_tokens_by_purpose
├── completion_tokens_by_purpose
├── total_tokens_by_purpose
├── image_calls
├── retries
└── estimated_cost_when rates are configured
```

### 10.4 Cost model

```text
search credits × search price
+ prompt tokens × prompt rate
+ completion tokens × completion rate
+ compute duration × compute rate
+ retained artifact storage
```

Provider prices are not hardcoded because enterprise contracts vary.

---

## 11. Recommended KPIs

| KPI | Meaning |
|---|---|
| URL delivery rate | Real direct URLs / total runs |
| Strict completion rate | `COMPLETED` / total runs |
| Review-required rate | Human workload |
| Human exact-URL agreement | Core correctness |
| Judgment-sequence agreement | Behavioral equivalence |
| First divergence by stage | Development priority |
| Manufacturer-primary adherence | Authority policy |
| Retailer-fallback correctness | Fallback quality |
| Visual contribution rate | Multimodal value |
| Median/p95 latency | Capacity planning |
| Search credits per product | Search cost |
| LLM tokens per product | Model cost |
| Browser investigations per product | Latency/compute control |
| Failure reason distribution | Operational improvement |

---

## 12. Assumptions

1. `main_text` contains enough product signal to form a hypothesis.
2. `country_code` is the intended market.
3. EAN/GTIN is strong evidence but still validated.
4. A qualified official page is preferred for product truth.
5. Retailers are valuable for local market and commercial context.
6. The feature schema represents downstream coding evidence needs.
7. Search results are candidates, never trusted facts.
8. Images may contain evidence absent from text.
9. Human review is available for uncertain cases and sequence validation.
10. Notebook and containers run the same repository contract.

---

## 13. Constraints and non-goals

### Constraints

- Bounded search, scrape and browser budgets.
- External page accessibility varies by geography and anti-bot controls.
- Manufacturer pages may omit local pack/price/availability.
- Retailer pages may omit authoritative technical detail.
- Vision depends on image quality and asset availability.
- Current job state is in-memory.
- Canonical run-level stage timing and token artifacts are not yet implemented.
- A single page may not contain every feature for every product category.

### Non-goals

The system does not:

- accept the first result;
- select from title similarity alone;
- treat model memory as evidence;
- bypass gates because a domain is official;
- select category pages as exact SKU pages;
- scrape unlimited pages;
- hide uncertainty behind confidence;
- expose hidden chain-of-thought;
- claim image causality without evidence.

---

## 14. Failure handling

| Condition | Behavior |
|---|---|
| Stale runtime | Clean rebuild before paid search |
| Missing credentials | Readiness failure |
| LLM browser-planner failure | Deterministic rendered fallback when allowed |
| Inaccessible page | Candidate rejection/review |
| Wrong variant/pack | Identity rejection |
| Missing requested features | Strict-primary rejection |
| Expiring URL | Durability rejection |
| Incomplete but direct URL | `REVIEW_REQUIRED` |
| No safe direct URL | `MANDATORY_PRODUCT_URL_NOT_FOUND` |

---

## 15. Change-impact map

| Requirement change | Modification area |
|---|---|
| New input fields | Product/API contract and notebook |
| New coding features | Feature schema |
| Change manufacturer/retailer priority | Source-authority and selection policy |
| Change acceptance gates | Strict primary selector |
| Multi-page evidence | Evidence-set and output contract |
| Change search route/provider | Adaptive search planner and provider adapter |
| Change credits/scrape/browser limits | `.env` controls |
| Change model/endpoint | `LLM_*` / `AZURE_OPENAI_*` configuration |
| Change prompts/browser strategy | Agentic browser and reasoners |
| Require images for every completion | Multimodal acceptance policy |
| Add artifacts | Artifact writer, result schema and notebook |
| Add timing/token telemetry | Run-scoped metrics context and artifact |
| Change human review questions | Business judgment artifact builder |

Use the first human divergence to choose the layer:

```text
wrong interpretation → product understanding
wrong query/source → search planning
wrong candidate admitted → ranking/preflight
wrong page judgment → browser/identity/vision
wrong feature result → feature evidence
wrong final source → acceptance/authority
```

---

## 16. Demo script — 10 to 15 minutes

### 0–1 minute: State the risk

> The main risk is not failing to find a URL. It is finding a plausible but incorrect URL and silently coding the wrong product.

Show the input cell.

### 1–2 minutes: Explain authority

> Manufacturer is preferred only after exact identity, accessibility, feature completeness and durability pass. Otherwise retailer is the controlled fallback.

Show the three-credit route.

### 2–4 minutes: Run

Explain readiness-before-search, offline interpretation, uncertainty and bounded credits.

### 4–7 minutes: Show business judgments

Open `business_judgement_steps_df` and `business_judgement_review.md`.

> A human coder compares the agent's ordered judgments and identifies the first disagreement.

### 7–9 minutes: Show images

Open `visual_evidence_summary_df` and one collected screenshot/image.

> Images can confirm identity or complete features; the system states whether they were decisive or merely available.

### 9–11 minutes: Show URL selection

Show/open `primary_url`, `primary_url_role`, `manufacturer_url`, `retailer_url`, `source_selection` and `primary_url_acceptance`.

### 11–13 minutes: Show artifacts

Open the artifact folder and workbook. Distinguish human, management and engineering artifacts.

### 13–15 minutes: Explain evolution

> We change the exact layer responsible for the first divergent human judgment, rather than randomly tuning prompts.

Close with KPIs: sequence agreement, completion rate, review workload, latency, tokens and failure distribution.

---

## 17. Pre-demo checklist and metric card

```bash
git checkout master
git pull origin master
./scripts/azureml_startup.sh --clean-build
curl -sS http://127.0.0.1:8788/health | python -m json.tool
```

Confirm v6 runtime and both manufacturer-first and business-judgment capabilities. Open only `notebooks/01_run_product_evidence.ipynb`, restart the kernel and use a new `row_id`.

Complete this from the actual run:

| Metric | Actual value | Source |
|---|---:|---|
| Outcome |  | result |
| End-to-end elapsed |  | job timestamps/heartbeat |
| Search credits used |  | `search.serpapi_requests_used` |
| Unique candidates |  | candidate diagnostics |
| Scrapes attempted |  | diagnostics |
| Browser investigations |  | `agentic_browser` |
| Images/screenshots |  | visual summary/browser evidence |
| Primary role |  | `primary_url_role` |
| LLM calls/tokens |  | agent logs; per-run artifact pending |
| Human sequence agreement |  | review form |

Do not present configured limits as actual usage.

---

## 18. Leadership questions

**Is this only a search wrapper?** No. Search creates candidates; browser, identity, feature, durability and authority policies decide acceptance.

**Does it always choose manufacturer?** No. Manufacturer must pass every gate; retailer is controlled fallback.

**Does it use images?** Yes. Screenshots and product/package images can support identity and feature decisions.

**Can an LLM hallucination directly select the URL?** No. Deterministic final gates control acceptance and authority.

**What happens when uncertain?** A real URL may be delivered as `REVIEW_REQUIRED`; unresolved cases never become false success.

**How do we validate human equivalence?** Compare the original input and `business_judgement_review.md`; record the first divergent step.

**What is expected latency and cost?** It varies by search, pages, browser actions, images and LLM latency. Production SLA/cost requires run-scoped telemetry and multi-run median/p95 analysis.

**Is it production ready?** The decision policy, runtime, notebook, artifacts and CI are production-oriented. Enterprise production additionally needs persistent job storage, run-scoped telemetry, monitoring, retention, access control, throughput and SLO decisions.

---

## 19. Leadership decisions for scale

Leadership must define:

1. exact-URL and judgment-sequence accuracy targets;
2. acceptable review workload;
3. latency SLO and concurrency;
4. cost-per-product budget;
5. artifact retention and access;
6. whether visual evidence is mandatory;
7. whether multi-page evidence is permitted;
8. country/retailer priorities;
9. no-URL escalation policy;
10. human-review sampling;
11. monitoring ownership;
12. persistent job and batch-orchestration requirements.

---

## 20. Final summary

The platform's strength is not simply finding a URL. It creates an auditable chain of controlled business judgments:

```text
understand product
→ preserve uncertainty
→ search authoritative sources
→ inspect real pages
→ use text and images
→ reject unsafe candidates
→ enforce feature completeness
→ prefer qualified manufacturer truth
→ retain retailer context
→ deliver a stable URL
→ expose the judgment sequence to a human
```

It can therefore be governed and improved at the correct level: whether the agent's business judgments match the human coder's judgments, and exactly where they diverge when they do not.
