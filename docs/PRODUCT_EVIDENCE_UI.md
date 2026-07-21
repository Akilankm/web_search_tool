# Product Evidence Platform UI

## Purpose

The Product Evidence Platform UI provides a browser-based interface for executing and reviewing one product-resolution job. It calls the same Product Evidence Agent API used by the supported notebooks and does not implement an alternate search, browser, validation or artifact workflow.

```text
apps/product_evidence_ui.py
→ Product Evidence Agent API
→ production search, browser, evidence and selection pipeline
```

## Runtime contract

```text
belief-url-resolution-v9-product-evidence-ui
```

Required health capabilities:

```text
per_job_runtime_controls=true
structured_no_url_review_outcome=true
manufacturer_first_primary_url=true
business_judgement_review_artifact=true
```

## Interface structure

### Runtime

Displays:

```text
agent status
browser status
runtime contract version
agent API address
```

The execution button remains disabled when the agent is unavailable or incompatible.

### Runtime controls

The UI exposes three execution profiles:

| Profile | Configuration intent |
|---|---|
| `Latency Optimized` | Lower evidence-acquisition limits for lower elapsed time |
| `Standard` | Default production operating limits |
| `Coverage Optimized` | Broader candidate, browser and visual investigation |

Each profile pre-populates the same independently adjustable controls:

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

The profile names describe execution trade-offs. They do not alter result semantics, safety gates or source-selection policy.

### Product input

Required:

```text
main product text
country code
run ID
feature set
```

Optional:

```text
retailer
EAN / GTIN
language
```

### Workflow visualization

The interface presents the active processing stage:

```text
Input
→ Interpret
→ Search
→ Investigate
→ Verify
→ Select
→ Report
```

| Stage | Meaning |
|---|---|
| Input | Validate product and market fields |
| Interpret | Build the product identity hypothesis and uncertainty state |
| Search | Query manufacturer, market and global sources |
| Investigate | Extract and inspect rendered pages, screenshots and images |
| Verify | Apply identity, feature, scrapability and durability gates |
| Select | Choose the strongest qualified source |
| Report | Persist the result, audit sequence and artifacts |

### Decision summary

Displays:

```text
job status
primary URL role
strict verification status
search credits used
browser candidates investigated
elapsed time
primary URL
manufacturer URL
retailer URL
```

### Workflow and decision

Displays:

```text
product interpretation
source-selection policy
selection reason
source tier
URL-delivery status
search-stage sequence
queries and engines
result and qualification counts
```

### Judgment sequence

Displays the chronological audit structure:

```text
observable evidence
→ explicit rule
→ business judgment
→ next action
```

Each step includes the business question, evidence considered, applied rule, judgment and effect on the next action. This is an audit representation and does not expose hidden chain-of-thought.

### Evidence

Displays:

```text
visual asset count
screenshot count
image-inspection actions
visual decision impact
candidate identity status
feature coverage
missing features
conflicts
rejection reasons
```

### Runtime control audit

Displays:

```text
requested value
effective value
allowed range
fixed governance controls
```

### Artifacts

Displays the product artifact directory and allows download of:

```text
business_judgement_review.md
orchestrated_result.json
```

## Safety boundary

The UI cannot change:

```text
credentials
EAN-conflict policy
exact-product identity rules
requested-feature completeness
URL durability
source-authority order
no-fabrication behavior
```

Runtime controls are validated by the API, scoped to one job and isolated across concurrent workers.

## Azure ML VS Code usage

### Update and start the agent

```bash
git checkout master
git pull origin master
./scripts/azureml_startup.sh --clean-build
```

Verify:

```bash
curl -sS http://127.0.0.1:8788/health | python -m json.tool
```

Expected:

```text
runtime_contract_version=belief-url-resolution-v9-product-evidence-ui
per_job_runtime_controls=true
```

### Install UI requirements

First use:

```bash
bash scripts/run_product_evidence_ui.sh --install
```

Subsequent use:

```bash
bash scripts/run_product_evidence_ui.sh
```

### Access the application

1. Keep the UI terminal running.
2. Open the VS Code **Ports** panel.
3. Forward port `8501`.
4. Keep visibility **Private**.
5. Open the forwarded address.

Alternative port:

```bash
bash scripts/run_product_evidence_ui.sh --port 8502
```

## Terminal outcomes

### Strict acceptance

```text
job_status=COMPLETED
primary_url=<direct product page>
url_delivery.delivered=true
url_delivery.strictly_verified=true
```

### Review with a real URL

```text
job_status=REVIEW_REQUIRED
primary_url=<direct review URL>
url_delivery.delivered=true
url_delivery.strictly_verified=false
```

### Controlled no-safe-URL result

```text
job_status=REVIEW_REQUIRED
primary_url=null
resolution_outcome.code=NO_SAFE_DIRECT_PRODUCT_URL_FOUND
url_delivery.delivered=false
```

### Technical failure

```text
job_status=FAILED
```

Technical failures remain separate from controlled business no-match outcomes.

## Related documents

- [Feature reference](FEATURE_REFERENCE.md)
- [System workflow](SYSTEM_WORKFLOW.md)
- [Final system contract](FINAL_SYSTEM_CONTRACT.md)
- [Azure ML operations](AZUREML_OPERATIONS.md)
