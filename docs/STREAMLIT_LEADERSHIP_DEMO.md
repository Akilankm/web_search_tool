# Leadership Streamlit Demo

## Purpose

The Streamlit application is the presentation surface for management and leadership calls. It calls the same Product Evidence Agent API as the notebooks; it does not implement a second search or decision workflow.

```text
apps/leadership_demo.py
→ Product Evidence Agent API
→ feature schema + adaptive search + browser evidence + strict URL gates
→ business judgment artifact
```

The UI is intentionally concise. It centers the workflow, controllable budget, final decision and observable business judgments rather than narrating every internal component.

## Flow shown in the UI

```text
Input
→ Interpret
→ Search
→ Investigate
→ Verify
→ Select
→ Explain
```

| Stage | Meaning |
|---|---|
| Input | Product text, country, optional retailer, EAN and language |
| Interpret | Identity hypothesis and unresolved distinctions |
| Search | Manufacturer, local-market and global routes |
| Investigate | Full-page extraction, rendered browser and images |
| Verify | Exact identity, requested features, scrapability and durability |
| Select | Authority-aware manufacturer/retailer URL decision |
| Explain | Human-comparable business judgment artifact |

During execution, the active stage is highlighted. After completion, the entire flow is shown as completed.

## Main result views

### Decision flow

Shows the interpreted product, source decision, strict gates and the search-to-decision route.

### Business judgments

Shows the chronological sequence:

```text
observable evidence
→ explicit business rule
→ agent judgment
→ next action
```

This is an auditable decision trace, not hidden chain-of-thought.

### Evidence

Shows visual assets, screenshots, image inspections, candidate feature coverage, conflicts and rejection reasons.

### Budget

Shows requested, effective and allowed per-job limits plus locked governance controls.

### Artifacts

Shows the generated product files and provides downloads for `business_judgement_review.md` and `orchestrated_result.json`.

## Controllable per-job budget

| Control | Allowed range |
|---|---:|
| SerpAPI search credits | 1–3 |
| Full page scrapes | 1–12 |
| Scrapes per domain | 1–4 |
| Planner candidate context | 3–20 |
| Browser-investigated candidates | 1–8 |
| Browser turns per candidate | 1–12 |
| Browser actions per candidate | 1–24 |
| Images in visual reasoning | 4–20 |

The UI cannot change credentials, exact-product identity gates, EAN conflict policy, requested-feature completeness, URL durability, manufacturer-first authority or no-fabrication behavior.

Every job persists its effective settings to:

```text
data/artifacts/<row_id>/run_configuration.json
```

## Null numeric handling

Older Streamlit sessions or external runtime payloads can contain a numeric key with a null value. Calling `int(None)` produces:

```text
TypeError: int() argument must be a string, a bytes-like object or a real number, not 'NoneType'
```

The current implementation normalizes numeric values at every active boundary:

```text
Streamlit session state
→ per-job runtime options
→ strict orchestrator environment values
→ browser-agent configuration
→ source-authority ranking
```

Null, blank or malformed optional values fall back to the governed default and are clamped to the allowed range. Strict API validation still rejects unsupported user-supplied values before queueing.

After pulling this fix, rebuild the agent/browser images so the running containers use the updated code.

## Azure ML VS Code setup

```bash
git checkout master
git pull origin master
./scripts/azureml_startup.sh --clean-build
bash scripts/run_leadership_demo.sh --install   # first use
```

Later launches:

```bash
bash scripts/run_leadership_demo.sh
```

Runtime health must report:

```text
runtime_contract_version=belief-url-resolution-v8-leadership-demo
leadership_demo_runtime_options=true
structured_no_url_review_outcome=true
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
```

## Open the UI in Azure ML VS Code

1. Keep the Streamlit terminal running.
2. Open the VS Code **Ports** panel.
3. Forward port `8501`.
4. Keep visibility **Private**.
5. Open the forwarded address.

Alternate port:

```bash
bash scripts/run_leadership_demo.sh --port 8502
```

## Demo sequence

1. Show runtime readiness and the seven-stage workflow.
2. Select a run-budget profile in the sidebar.
3. Enter one incomplete product description and country code.
4. Run and narrate the highlighted stage transitions.
5. Show the final URL role and strict gate outcomes.
6. Open **Decision flow** to explain search and source selection.
7. Open **Business judgments** to show the chronological evidence/rule/judgment/action sequence.
8. Open **Evidence** to show candidate and visual evidence.
9. Open **Budget** to compare requested and effective limits.
10. Open **Artifacts** to download the review document.

## Outcomes

### Strict success

```text
job_status=COMPLETED
primary_url=<direct product page>
url_delivery.delivered=true
url_delivery.strictly_verified=true
```

### URL-backed review

```text
job_status=REVIEW_REQUIRED
primary_url=<real direct review URL>
url_delivery.delivered=true
url_delivery.strictly_verified=false
```

### Controlled no-safe-URL outcome

```text
job_status=REVIEW_REQUIRED
primary_url=null
resolution_outcome.code=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
url_delivery.delivered=false
```

### Genuine failure

Configuration, dependency, stale-runtime and response-contract defects remain red `FAILED` outcomes. Technical detail is kept inside an expandable section and no result is fabricated.

## Operational notes

- Use a new `row_id` for every execution.
- Pull `master` and perform a clean rebuild after runtime code changes.
- Browser refresh alone does not update the agent container.
- The current job store is in memory; product artifacts remain on disk.
- Streamlit is the demo surface; notebooks remain the analytical and batch workflows.
