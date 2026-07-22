# Product URL Decision UI

## Purpose

The browser application answers one operational question first:

> Did the system find a justifiable product URL that is safe to use?

The result is organised through four review pillars:

1. **Source** — where the URL came from and its authority tier.
2. **Evidence** — what textual, structured, browser and visual evidence was collected.
3. **Identity** — which exact product was identified and with what confidence.
4. **Usability** — whether the URL is openable, extractable, exact, complete and reusable.

The complete audit is retained, but it is collapsed by default so the primary decision remains immediately visible.

## Primary outcome

The primary outcome is one of three explicit URL decisions:

| Status | Meaning |
|---|---|
| `JUSTIFIABLE_URL_FOUND` | A direct product URL passed the required identity and usability gates and is ready for downstream use. |
| `URL_FOUND_REVIEW_REQUIRED` | A candidate URL exists, but one or more gates still require human review. |
| `NO_JUSTIFIABLE_URL_FOUND` | The bounded search completed, but no candidate was safe enough to return. No URL was fabricated. |

The selected URL is displayed at the top of the result when available.

## Decision-first result hierarchy

The visible result order is:

```text
URL decision
→ identified product
→ overall conclusion
→ Source / Evidence / Identity / Usability metrics
→ URL usability checks
→ decision reasons
→ search work completed when no URL is returned
→ candidate URL decisions
→ collapsed review details
```

This hierarchy is designed for high-stakes review: the conclusion is immediate, while the evidence remains inspectable.

## Source

Source metrics include:

```text
selected URL
source role
source authority tier
manufacturer URL availability
retailer URL availability
search actions used
search stages
results reviewed
candidate URLs seen
qualified candidates
```

Manufacturer-first selection remains conditional on production gates. A manufacturer URL is not accepted merely because it is official.

## Evidence

Evidence metrics include:

```text
identity claim count
web-verified claim count
atomic evidence items
browser evidence records
visual assets
feature assessments
required coverage
critical coverage
total coverage
```

The UI does not invent a synthetic evidence score. It displays factual counts and recorded coverage values.

## Identity

Identity metrics include:

```text
identified product
ResolutionStatus
posterior confidence
hypotheses considered
unresolved items
contradictions
```

Identity remains separately visible when no usable URL exists. This avoids confusing “product understood” with “URL safe to deliver.”

## Usability

The URL usability decision evaluates:

| Check | Meaning |
|---|---|
| Browser openable | The rendered page can be opened. |
| Text extractable | Product evidence can be extracted from the page. |
| Direct product page | The page is a product-detail page, not search/category/navigation content. |
| Exact product identity | The page matches the requested product and variant. |
| Required evidence coverage | The page contains the required feature evidence. |
| Reusable non-expiring URL | The URL is durable and not session-bound or signed. |

Each check is displayed as `PASS`, `FAIL` or `NOT ASSESSED`.

## No justifiable URL

A no-URL result is not presented as empty output. The UI explicitly displays **Search work completed**:

```text
search actions used / limit
results reviewed
candidate URLs seen
qualified candidates
pages extracted
browser investigations completed
```

The conclusion explains that the system rejected unsafe, indirect, mismatched, blocked, incomplete or expiring candidates rather than promoting a weak URL.

Suggested next actions are shown only after the completed work is quantified.

## Candidate URL decisions

The candidate table summarises the strongest evaluated URLs with:

```text
decision
source role
identity status
coverage
browser openability
text extractability
URL reusability
URL
rejection or selection reason
```

This allows reviewers to see why an apparently plausible URL was not selected.

## Review evidence and decision details

Detailed information is preserved in one collapsed section:

- Evidence
- Search
- Identity
- Decision audit
- Artifacts

Raw technical JSON is nested inside the Artifacts tab and is never the default view.

## Product input

Visible by default:

```text
product text
country code
retailer (optional)
EAN / GTIN (optional)
```

Advanced settings are collapsed:

```text
search depth
language (optional)
```

Run ID and feature set are assigned automatically. Users are not asked to manage technical identifiers.

## Search-depth profiles

| Profile | Intent |
|---|---|
| `Fast` | Lower investigation breadth for latency-sensitive use. |
| `Standard` | Default production balance. |
| `Deep review` | Broader candidate, browser and visual investigation for difficult products. |

Profiles change search breadth only. They never weaken identity, evidence or URL-usability gates.

## Executive summary contract

Every completed agent result contains:

```text
executive_summary
```

The same summary is persisted as:

```text
executive_summary.json
```

The contract contains:

```text
overall_status
headline
conclusion
selected_url
product_name
identity_status
identity_confidence
source_role
source_tier
decision_reasons
next_actions
work_completed
pillars.source
pillars.evidence
pillars.identity
pillars.usability
candidate_summary
```

This keeps the UI, API, notebooks and artifacts aligned.

## Runtime compatibility

Current compatibility contract:

```text
belief-url-resolution-v10-decision-first-ui
```

Required capability:

```text
executive_url_decision_summary=true
```

Because the executive summary is generated inside the agent container, this version requires a clean agent rebuild after pulling the code.

## Azure ML VS Code usage

```bash
git checkout master
git pull origin master
./scripts/azureml_startup.sh --clean-build
bash scripts/run_product_evidence_ui.sh
```

Forward port `8501` privately from the VS Code **Ports** panel.

## Acceptance rules

The UI is correct only when:

1. the URL decision is the first visible result;
2. a selected URL is immediately openable from the result;
3. Source, Evidence, Identity and Usability are visible together;
4. the overall conclusion explains whether the URL is safe for downstream use;
5. a no-URL outcome quantifies the work completed;
6. candidate rejection reasons remain available;
7. technical details are collapsed by default;
8. Run ID, feature set and individual runtime knobs are not exposed as standard user inputs;
9. no URL, identity or evidence claim is fabricated.
