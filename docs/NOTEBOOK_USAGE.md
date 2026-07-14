# Notebook Usage and Result Contract

Use only:

```text
notebooks/01_run_product_evidence.ipynb
```

## Before opening the notebook

```bash
cp .env.example .env
# Replace SerpAPI and LLM placeholders.
mkdir -p inputs/private
cp /secure/location/toy_features.json inputs/private/toy_features.json
./scripts/azureml_startup.sh
```

For mounted storage that cannot preserve mode `600`:

```bash
./scripts/azureml_startup.sh --allow-insecure-env-permissions
```

## Product input

```python
product = {
    "row_id": "TEST-001",
    "main_text": "Exact product identity text",
    "country_code": "CO",
    "retailer_name": "Mercado Libre",  # optional
    "ean": None,                       # optional; keep as text
    "language_code": None,
}
```

Required: `main_text`, `country_code`.

Optional: `row_id`, `retailer_name`, `ean`, `language_code`.

## Runtime flow visible in the notebook

```text
VALIDATING_INPUT
SEARCHING
AGENTIC_BROWSER_INVESTIGATION
  CAND-001 | turn 1/10 | CLICK | domain
  CAND-001 | turn 2/10 | INSPECT_IMAGE | domain
  CAND-001 | COMPLETED | turns=3 | actions=2
  CAND-002 | ...
VALIDATING_PRIMARY_URL
WRITING_OUTPUTS
COMPLETED or REVIEW_REQUIRED
```

The notebook suppresses duplicate polling messages and emits a periodic elapsed-time heartbeat when a browser or LLM call is still running.

## Running one product

```python
FEATURE_SET = "toy_features"
result = run_product(product, FEATURE_SET)
pprint(summarize_result(result))
```

## Agentic investigation inspection

```python
pprint(result["agentic_browser"])

for candidate in result["candidate_investigations"]:
    print(candidate["candidate_id"], candidate["status"], candidate["termination_reason"])
    pprint(candidate["plans"])
```

Each plan describes what the LLM observed, which safe browser action it selected, and why. The executed browser trace remains authoritative:

```text
data/artifacts/<row_id>/CAND-###/agentic/browser_actions.json
```

## Final URL behavior

The LLM investigates candidates but does not directly approve the final URL. `primary_url` is non-null only when deterministic code confirms:

- browser-openable;
- no access blocker;
- exact product and variant;
- rendered product page;
- text-scrapable;
- every requested feature supported on that same URL;
- no conflicting feature evidence;
- durable URL without session, token, signature, credential, expiry, or TTL parameters.

Inspect:

```python
pprint(result["primary_url_acceptance"])
pprint(result["product_match"])
pprint(result["evidence_set"])
```

## Result schema

| Path | Meaning |
|---|---|
| `product.row_id` | Original row identifier |
| `job_status` | `COMPLETED` or `REVIEW_REQUIRED` |
| `coding_ready` | Strict final acceptance result |
| `primary_url` | Accepted durable product URL or `null` |
| `search.queries` | Three executed search queries |
| `search.stages` | Search stage trace |
| `search.serpapi_requests_used` | Exactly three |
| `agentic_browser` | Policy, budgets and investigation counts |
| `candidate_investigations` | Per-candidate LLM plans, turns, actions, conclusions and errors |
| `browser_evidence` | Browser-rendered text, screenshots, blockers and final page status |
| `feature_assessments` | Per-candidate requested-feature evidence |
| `primary_url_acceptance` | Authoritative final gate decision |
| `artifact_dir` | Container artifact path |

## Terminal status semantics

```python
{
    "job_status": "COMPLETED",
    "coding_ready": True,
    "primary_url": "https://..."
}
```

means one investigated candidate passed every strict gate.

```python
{
    "job_status": "REVIEW_REQUIRED",
    "coding_ready": False,
    "primary_url": None
}
```

means execution completed but no investigated candidate passed every gate. Only `FAILED` means the workflow itself failed.

## Artifact investigation

```text
data/artifacts/<row_id>/
├── orchestrated_result.json
├── primary_url_acceptance.json
└── CAND-###/agentic/
    ├── investigation.json
    ├── latest_observation.json
    ├── browser_actions.json
    ├── browser_result.json
    ├── rendered_text.md
    ├── final_page.html
    ├── observations/
    ├── images/
    └── screenshots/
```

## CSV batch

Expected columns:

```text
row_id,main_text,country_code,retailer_name,ean,language_code
```

Batch summaries are written to:

```text
data/artifacts/notebook_batch_summary.csv
```
