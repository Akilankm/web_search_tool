# Product Identification Platform UI

## Purpose

The browser application is a product-identification surface.

Its primary responsibility is to answer:

> Which exact product does this incomplete source text refer to?

Web pages, screenshots, retailer pages, manufacturer pages and URLs are evidence sources used to support or contradict a product hypothesis. They are not the primary result.

```text
apps/product_evidence_ui.py
→ Product Evidence Agent API
→ product interpretation
→ evidence discovery
→ hypothesis comparison
→ product identity resolution
→ evidence and artifact reporting
```

## Primary outcome

The primary outcome is the identified product and the strength of the evidence supporting it.

```text
canonical product name
brand
manufacturer
model or series
product form
variant
size
quantity or pack
ResolutionStatus
posterior confidence
unresolved distinctions
alternative hypotheses
```

A product may remain identified even when no single source URL passes every page-usability or durability check.

## Supporting outcome

Source URLs are retained only as supporting evidence locations.

```text
primary evidence source
manufacturer evidence source
retailer evidence source
search-stage trace
candidate source assessments
source-quality metadata
```

A missing URL does not automatically mean the product was not identified.

## ResolutionStatus

The product-belief contract uses the following resolution states:

| Status | Meaning |
|---|---|
| `EXACT` | One product identity is resolved with sufficient evidence and no material competing hypothesis |
| `PROBABLE` | One product hypothesis leads, but confirmation evidence remains incomplete |
| `AMBIGUOUS` | Multiple plausible products remain |
| `CONFLICTING` | Material evidence supports incompatible identities |
| `INSUFFICIENT_EVIDENCE` | Available evidence cannot support a defensible identity |
| `IN_PROGRESS` | Identification is still being evaluated |
| `INITIALIZED` | Interpretation has started but no resolution has been reached |

The UI headline is based on `product_identification.resolution_status`, not URL acceptance.

## Interface hierarchy

### 1. Product identification summary

The first result section displays:

```text
identified product
resolution status
posterior confidence
identity claim count
evidence item count
number of competing hypotheses
number of unresolved distinctions
```

Resolved identity attributes are shown directly below the headline.

### 2. Product identity

Displays the selected product hypothesis, its structured attributes, belief-state metrics and unresolved distinctions.

### 3. Evidence basis

Displays:

```text
identity claims
claim status
claim confidence
source tokens
atomic evidence ledger
evidence polarity
source reliability
extraction confidence
supporting excerpts
```

### 4. Alternative hypotheses

Displays competing product identities rather than competing URLs.

Each hypothesis includes:

```text
canonical product name
posterior probability
assumptions
contradicting evidence count
selected/not-selected status
```

### 5. Source evidence

URLs are evidence locations.

The UI presents source quality with three states:

| State | Meaning |
|---|---|
| `VERIFIED` | The source property was positively established |
| `NOT VERIFIED` | The source property was checked but not established |
| `NOT ASSESSED` | No reliable assessment was recorded |

The application must not convert an absent source-quality field into `FAIL`.

The source section may display:

```text
rendered evidence
text evidence
product-page evidence
identity support
requested-feature evidence
source reusability
```

These checks describe the evidence source. They do not replace product identification.

### 6. Decision audit

Displays the observable sequence:

```text
observable evidence
→ explicit rule
→ product judgment
→ next action
```

This is an audit representation and does not expose hidden chain-of-thought.

### 7. Artifacts

Displays the product artifact directory and the complete technical result.

## Workflow

```text
Input
→ Interpret
→ Discover
→ Compare
→ Resolve
→ Validate
→ Report
```

| Stage | Responsibility |
|---|---|
| Input | Validate product and market fields |
| Interpret | Extract identity claims, assumptions and ambiguity |
| Discover | Gather relevant text, structured and visual evidence |
| Compare | Evaluate competing product hypotheses |
| Resolve | Select the strongest supported product identity |
| Validate | Check evidence consistency, conflicts and unresolved fields |
| Report | Persist the identification result and audit artifacts |

## Product input

Required:

```text
main product text
country code
run ID
feature set
```

Optional:

```text
retailer context
EAN / GTIN
language
```

EAN, retailer and country are evidence inputs. None of them independently defines the product.

## Execution profiles

| Profile | Intent |
|---|---|
| `Latency Optimized` | Lower evidence-acquisition limits for lower elapsed time |
| `Standard` | Default production evidence limits |
| `Coverage Optimized` | Broader candidate, browser and visual investigation |

Profiles change evidence depth only. They do not change product-identity rules.

## Runtime controls

| Control | Range |
|---|---:|
| Search credits | 1–3 |
| Full-page extractions | 1–12 |
| Extractions per domain | 1–4 |
| Planner candidate limit | 3–20 |
| Browser investigation limit | 1–8 |
| Browser turns per candidate | 1–12 |
| Browser actions per candidate | 1–24 |
| Visual assets per reasoning turn | 4–20 |

## Runtime compatibility

Current compatibility contract:

```text
belief-url-resolution-v9-product-evidence-ui
```

The existing runtime name is retained for backward compatibility. The UI result hierarchy is product-identification-first.

Required capabilities:

```text
per_job_runtime_controls=true
business_judgement_review_artifact=true
structured_no_url_review_outcome=true
```

## Azure ML VS Code usage

```bash
git checkout master
git pull origin master
bash scripts/run_product_evidence_ui.sh --install   # first use
bash scripts/run_product_evidence_ui.sh             # later use
```

Forward port `8501` privately from the VS Code **Ports** panel.

A clean agent rebuild is not required for a UI-only update when the runtime contract has not changed. Restart the Streamlit process after pulling.

## Acceptance rules for the UI

The UI is correct only when:

1. the identified product is the first and most prominent result;
2. resolution status and confidence are visible before source URLs;
3. alternative product hypotheses are explicitly shown;
4. unresolved identity distinctions are visible;
5. URLs are isolated under **Source evidence**;
6. source checks use `VERIFIED`, `NOT VERIFIED` or `NOT ASSESSED`;
7. an `EXACT` product remains identified even when every URL-quality check is false;
8. no source result is fabricated.

## Related documents

- [Feature reference](FEATURE_REFERENCE.md)
- [System workflow](SYSTEM_WORKFLOW.md)
- [Final system contract](FINAL_SYSTEM_CONTRACT.md)
- [Business judgment review](BUSINESS_JUDGEMENT_REVIEW.md)
- [Azure ML operations](AZUREML_OPERATIONS.md)
