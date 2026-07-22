# Product URL Resolution v2 — Clean-Slate Revamp

## Status

This is the canonical replacement architecture for the product URL workflow.

The existing `product_evidence_harness` runtime remains available only as a legacy comparison system during migration. New v2 code must not monkey-patch, import-mutate, or depend on the legacy runtime.

## Non-negotiable business invariant

Every submitted product must terminate in exactly one of these outcomes:

| Outcome | Required URL | Meaning |
|---|---:|---|
| `VERIFIED` | Yes | Exact product and strict automation/coding gates passed |
| `REVIEW_REQUIRED` | Yes | Strongest real direct product URL retained with precise uncertainty |
| `FAILED` | No | No defensible direct product URL survived after the full recovery budget, or a technical failure prevented completion |

A completed or review-required row with an empty URL is invalid.

## Four independent decision axes

The system must never collapse these axes into one status.

### 1. Product identity

- exact product
- probable product
- ambiguous identity
- conflicting identity
- insufficient evidence

Identity comparison includes brand, manufacturer, model/series, variant, size, quantity, pack configuration, product form, country/language form and EAN/GTIN.

### 2. URL delivery

- verified URL delivered
- review URL delivered
- URL delivery failed

URL delivery answers whether the coding team received a real direct product page.

### 3. Automation usability

Each gate is independently `PASS`, `FAIL`, or `NOT_ASSESSED`:

- browser automation access
- text extraction
- direct product-page confirmation
- URL durability

A browser automation failure is not evidence that a human cannot open the URL.

### 4. Coding readiness

Coding readiness reports whether the selected evidence contains all requested coding facts. Missing coding evidence cannot erase an otherwise usable exact product URL.

## Canonical pipeline

```text
INTERPRET_INPUT
→ BUILD_HYPOTHESES
→ SEARCH
→ ADMIT_CANDIDATES
→ SCRAPE
→ BROWSER_INVESTIGATION
→ EVALUATE
→ DELIVER
→ COMPLETE | FAILED
```

Every transition is explicit and audit-recorded. There are no import-time behavior changes.

## Hypothesis-driven reasoning

Before paid search, the system builds one or more product hypotheses containing:

- canonical product name
- known attributes
- assumptions
- negative constraints
- unresolved discriminators
- supporting and contradicting evidence

Each subsequent search action must target the uncertainty with the largest risk or information value.

Example:

```text
Input: PKM ME04 WACHSENDES CHAOS BOOSTER

Leading hypothesis:
- Pokémon ME04 Wachsendes Chaos
- German language
- single booster pack

Must distinguish from:
- booster bundle
- 36-pack display
- another language edition
- sibling ME04 product form
```

## Search budget contract

The default three paid search actions have stable purposes, while the engine/query is chosen adaptively.

1. **Establish exact identity**
   - prioritize EAN/GTIN, model, exact name and manufacturer evidence
2. **Resolve the highest-risk uncertainty**
   - variant, pack, size, quantity, language, market or requested retailer
3. **Mandatory direct URL recovery**
   - maximize recall of a real manufacturer or retailer product-detail URL

The final recovery action may use Google Search, Shopping, AI Mode, Immersive Product or another supported SerpAPI surface, but must preserve all known identity anchors and negative constraints.

## Candidate admission

Candidate admission is a cost-allocation decision, not a final product judgment.

A cheap preflight score may prioritize candidates, but must not permanently eliminate a candidate solely because:

- its URL uses an internal product ID;
- the product name is translated or abbreviated;
- the retailer slug differs from the submitted text;
- the page has weak SERP snippets;
- the product is newly released.

High-value candidates can be admitted through exact identifiers, source authority, requested-retailer match, country relevance, competing-hypothesis coverage or direct-page signals.

## Scrape and browser budgets

Budgets are allocated by evidence diversity.

Browser investigation should cover, when available:

1. strongest manufacturer candidate;
2. strongest requested/local retailer candidate;
3. strongest competing product hypothesis or distinct domain.

Remaining slots are filled by expected information gain, not raw score alone.

## Candidate comparison order

Final selection is lexicographic across explicit axes rather than one opaque weighted score:

1. explicit wrong-product/variant/pack conflicts;
2. product identity strength;
3. direct product-page evidence;
4. URL durability;
5. browser and extraction evidence;
6. source authority;
7. country and retailer relevance;
8. coding evidence completeness;
9. SERP support and residual confidence.

Strict verification requires all mandatory gates. Review delivery requires a real product-like URL without explicit wrong-product, wrong-page, conflict or transient-URL blockers.

## Metrics and release gates

Unit tests are necessary but do not establish production quality.

The frozen benchmark must report:

- URL delivery rate
- exact URL top-1 accuracy
- correct-product delivery rate
- candidate recall@K
- wrong-product escape rate
- strict verified rate
- review-required rate
- human review acceptance rate
- direct product-page rate
- browser assessment coverage
- mean latency
- cost per case and cost per correct delivery

Default release thresholds in `product_url_v2.metrics` are:

| Metric | Gate |
|---|---:|
| URL delivery rate | ≥ 98% |
| Correct-product delivery rate | ≥ 95% |
| Candidate recall@K | ≥ 98% |
| Wrong-product escape rate | ≤ 1% |
| Direct product-page rate | ≥ 98% |

Thresholds will be finalized against the approved business benchmark before cutover.

## Migration plan

### Phase 0 — Foundation

- canonical typed contracts
- deterministic state machine
- mandatory URL policy
- diversity-aware browser allocation
- benchmark metrics and release gates

### Phase 1 — Product interpretation and hypothesis builder

- multilingual text decomposition
- EAN/model/quantity/pack extraction
- competing hypotheses and negative constraints
- structured uncertainty register

### Phase 2 — SerpAPI search adapter

- adaptive engine/query selection from hypothesis state
- search observations and handles
- three-credit information-gain policy
- mandatory final recovery

### Phase 3 — Candidate acquisition

- canonical URL handling
- cheap fetch and structured-data extraction
- cost-aware full scrape allocation
- source-role and market classification

### Phase 4 — Browser investigation

- deterministic browser evidence contract
- LLM action selection inside a strict tool boundary
- explicit technical failure versus page failure
- multimodal identity and pack/variant verification

### Phase 5 — Canonical orchestrator and API

- one v2 orchestrator
- no compatibility patch chain
- stable JSON result schema
- artifact ledger and decision audit

### Phase 6 — UI and dual-run benchmark

- legacy and v2 run side-by-side on the frozen benchmark
- human adjudication
- failure taxonomy and regression corpus
- release-gate approval

### Phase 7 — Cutover and legacy deletion

The legacy patched runtime is removed only after v2 passes benchmark thresholds and operational soak testing.

## Engineering rules

- No monkey patches.
- No import-time mutation.
- No hidden fallback that changes business meaning.
- `NOT_ASSESSED` is never converted to `FAIL`.
- Search, scrape, browser, identity, delivery and coding evidence remain separate.
- Every terminal decision is reproducible from stored evidence and explicit rules.
- A framework is adopted only when it reduces operational risk or implementation complexity.
