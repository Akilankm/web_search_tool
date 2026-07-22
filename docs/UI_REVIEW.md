# Human-review UI and observable trace

## Purpose

The UI is a product URL delivery workbench for human coders. Its first responsibility is to show whether a usable direct URL was delivered. Evidence quality, identity confidence, browser behavior and coding readiness are secondary independent judgments.

The workspace must not display a stakeholder-facing failure when non-conflicting product-like candidates exist. Incomplete evidence changes the delivery grade to `REVIEW_REQUIRED`; it does not erase the URL.

## Thinking mode

The sidebar control **Thinking mode: live decision trace** enables real-time rendering of the `observable-decision-trace-v1` event stream.

The wording “thinking mode” is user-facing. The technical contract is intentionally narrower and auditable: it exposes observable evidence, hypotheses, gate outcomes and selection judgments. It does not expose or fabricate hidden chain-of-thought.

## Live stages

| Stage | Reviewer visibility |
|---|---|
| Interpret | Input constraints, deterministic signals, PCA LLM hypotheses, unresolved discriminators |
| Search | Credit number, engine, purpose, query, rationale, source results and admitted candidates |
| Acquire | URL selection budget, fetch status, redirects, HTTP status, JSON-LD and text availability |
| Evaluate | Identity, direct-page, durability, country, retailer, extraction and coding gates |
| Browser | Allocation, browser access, final URL, product controls, screenshot and automation errors |
| Deliver | Candidate ranking, strengths, risks, blockers, selected URL and decision reasons |

## Stakeholder hierarchy

The final screen presents outcomes in this order:

1. **URL delivered — Yes or No**
2. **Selected direct product URL**
3. **Delivery grade — Verified or Review Required**
4. **Identity evidence confidence**
5. **Candidate, source, browser and coding evidence**

A 0% automated identity-evidence score is not displayed as an overall system failure when a usable URL is delivered. It means the URL requires human identity confirmation.

## Final workspace

The final result is divided into six tabs:

1. **Decision** — selected URL, delivery grade, reasons, warnings and selected-candidate gates.
2. **Candidate evidence** — side-by-side candidates, delivery basis, structured fields, strengths, risks and blockers.
3. **Identity & hypotheses** — signals, evidence source, hypotheses, probabilities and unresolved discriminators.
4. **Search sources** — every paid action and retained source observation.
5. **Browser usability** — browser status, final URL, controls, errors and screenshots.
6. **Audit & export** — complete trace, result JSON, candidate CSV and artifact directory.

## Reliability rules

- A non-conflicting product-like candidate must be delivered.
- Missing identity support is `UNVERIFIED`, not `MISMATCH`.
- `NOT_ASSESSED` is displayed as unknown, never as failure.
- Browser automation failure is not labeled as human URL failure.
- Acquisition failure does not erase the original product-like search URL.
- A redirect to a homepage, consent page or login page does not replace the original product URL.
- Missing coding fields do not erase a valid direct product URL.
- Explicit EAN/model conflicts remain hard blockers.
- Homepages, categories, search pages and intermediary URLs cannot be selected.
- The selected candidate is visually distinguished, but rejected candidates remain visible.
- Evidence screenshots are mounted read-only into the UI container.

## API contract

```text
GET /v1/jobs/{job_id}/trace?after_sequence=<n>
```

Response fields:

- `trace_contract`
- `notice`
- `status`
- `stage`
- `message`
- `event_count`
- `last_event_sequence`
- `events`

Each event contains:

- monotonically increasing `sequence`;
- `stage`;
- `event_type`;
- reviewer-readable `message`;
- structured `details`.

The final result artifact contains the complete event sequence so the UI trace can be replayed after execution.
