# Human-review UI and observable trace

## Purpose

The UI is a review workspace for product coders. Its purpose is not to display a decorative progress bar; it must let a reviewer understand what the system observed, which alternatives were considered, how each candidate passed or failed independent gates, and why a URL was selected.

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

## Final workspace

The final result is divided into six tabs:

1. **Decision** — selected URL, confidence, reasons, warnings and selected-candidate gates.
2. **Identity** — signals, evidence source, hypotheses, probabilities, unknowns and negative constraints.
3. **Search & sources** — every paid action and every retained source observation.
4. **Candidate judgments** — side-by-side gates and per-candidate strengths, risks, blockers and structured fields.
5. **Browser & usability** — browser status, final URL, controls, errors and screenshots.
6. **Audit & export** — complete trace, result JSON, candidate CSV and artifact directory.

## Reliability rules

- `NOT_ASSESSED` is displayed as unknown, never as failure.
- Browser automation failure is not labeled as human URL failure.
- Missing coding fields do not erase a valid direct product URL.
- Identity conflicts remain hard blockers.
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
