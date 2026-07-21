# Leadership Streamlit Demo

## Purpose

The Streamlit application is a presentation surface for management and leadership calls. It does not replace the three supported notebooks and does not implement a second search workflow.

```text
apps/leadership_demo.py
→ Product Evidence Agent API
→ the same feature schema, search planner, browser workflow, strict URL gates and artifacts used by the notebooks
```

The UI is deliberately business-first. It shows the platform's complete capability, the submitted input, live execution stage, per-job budget, final URL/source decision, visual evidence, strict gates, business judgment sequence and downloadable artifacts.

## What the UI demonstrates

- product identity interpretation from incomplete vendor text;
- manufacturer-first product truth;
- adaptive bounded multi-engine search;
- local retailer, country and global fallbacks;
- candidate preflight and full-page extraction;
- rendered browser observe-plan-act investigation;
- text, structured data, screenshots and product/package images;
- exact product/model/form/variant/size/quantity/pack verification;
- requested-feature completeness;
- direct, durable and non-expiring URL enforcement;
- manufacturer-versus-retailer source authority;
- controlled no-safe-URL review outcomes;
- human-comparable business judgment sequence;
- product-level artifact governance.

## Safe per-job budget controls

The sidebar exposes only bounded operational limits:

| Control | Allowed range | Purpose |
|---|---:|---|
| SerpAPI search credits | 1–3 | Maximum paid search actions for one product |
| Full page scrapes | 1–12 | Maximum candidate pages admitted for full extraction |
| Scrapes per domain | 1–4 | Prevent one website consuming the evidence budget |
| Planner candidate context | 3–20 | Candidate context supplied to the adaptive search planner |
| Browser-investigated candidates | 1–8 | Candidate pages opened through the browser workflow |
| Browser turns per candidate | 1–12 | Observe-plan-act reasoning turns |
| Browser actions per candidate | 1–24 | Controlled clicks, expansions and evidence actions |
| Images in visual reasoning | 4–20 | Images available to a browser reasoning turn |

Every option is submitted inside that job, stored under `run_configuration`, and persisted to:

```text
data/artifacts/<row_id>/run_configuration.json
```

The app never edits `.env`, restarts shared containers, exposes credentials or allows the user to change:

- exact-product identity gates;
- EAN conflict policy;
- requested-feature gates;
- URL durability requirements;
- manufacturer-first authority policy;
- no-fabrication behavior.

## Azure ML VS Code setup

Open the repository on the Azure Machine Learning compute instance through **VS Code for the Web** or **VS Code Desktop**.

From the repository terminal:

```bash
git checkout master
git pull origin master
cp .env.example .env
# Add the real SerpAPI and enterprise LLM values only when .env is new.
./scripts/azureml_startup.sh --clean-build
```

Runtime health must report:

```text
runtime_contract_version=belief-url-resolution-v8-leadership-demo
leadership_demo_runtime_options=true
structured_no_url_review_outcome=true
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
```

Install the small host-side demo dependency set once:

```bash
bash scripts/run_leadership_demo.sh --install
```

Subsequent launches:

```bash
bash scripts/run_leadership_demo.sh
```

Default ports:

```text
Product Evidence Agent API: 8788
Leadership Streamlit UI:    8501
```

## Open the UI from Azure ML VS Code

1. Keep the Streamlit terminal running.
2. Open the VS Code **Ports** panel.
3. Forward remote port `8501`.
4. Keep the port visibility **Private**.
5. Select the forwarded address or the browser icon.

The app binds to `0.0.0.0:8501` inside the compute instance, while VS Code provides the authenticated browser route. Do not make the port public when real product or enterprise evidence is displayed.

## Alternate port

```bash
bash scripts/run_leadership_demo.sh --port 8502
```

Then forward port `8502` in VS Code.

## Demo flow

1. Show the runtime status and v8 contract in the sidebar.
2. Explain that the budget controls are isolated to one job and cannot weaken safety gates.
3. Paste one incomplete product description and market code.
4. Run the workflow and narrate the live stages.
5. Open **Decision** and show the URL role, source policy and strict acceptance gates.
6. Open **Search & budget** and compare requested limits with actual credits/candidates consumed.
7. Open **Evidence & images** and show multimodal evidence impact and candidate rejection reasons.
8. Open **Judgment trace** and show the chronological evidence → rule → judgment → next-action sequence.
9. Open **Artifacts** and download the human review Markdown or complete result JSON.

## Terminal outcomes

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

The third state is displayed as an amber business review outcome, not a red software failure. The complete search trace and recommended next actions remain available.

### Genuine failure

Configuration, dependency, runtime and response-contract errors remain red `FAILED` outcomes. The application presents a clean management-facing message and keeps technical detail inside an expandable section.

## Operational notes

- Use a new `row_id` for every execution.
- The Streamlit application and notebooks can coexist because they submit jobs to the same API.
- Per-job budgets use context-local state and do not leak across concurrent agent workers.
- The current job store is in memory; restarting the agent removes job-status history, while persisted product artifacts remain on disk.
- Streamlit is a demo surface. Notebook and batch outputs remain the analytical and submission workflows.
