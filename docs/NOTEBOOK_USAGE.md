# Notebook Usage and Result Contract

Use only:

```text
notebooks/01_run_product_evidence.ipynb
```

## Before opening the notebook

From a fresh clone:

```bash
cp .env.example .env
# Edit the real SerpAPI and LLM values.
./scripts/azureml_startup.sh
```

The startup script handles directories, internal secrets, Azure ML `cloudfiles` permission fallback, Docker build, container recreation, health checks, and readiness reporting. No additional permission flag or manual `docker compose up` is required.

When it finishes, it prints available `FEATURE_SET` values and writes:

```text
data/runtime/stack_health.json
```

## First notebook cell

The setup cell:

- locates the repository root;
- reads the bootstrap health snapshot when available;
- calls the live agent `/health` endpoint;
- verifies the strict three-stage, LLM-agentic browser, and browser-tool contracts;
- lists `inputs/private/*.json` as notebook-ready feature sets;
- does not print credentials.

If the cell cannot reach the platform, rerun:

```bash
./scripts/azureml_startup.sh
```

## Product input

```python
product = {
    "row_id": "TEST-001",
    "main_text": "Exact product identity text",
    "country_code": "CO",
    "retailer_name": "Mercado Libre",  # optional
    "ean": None,                        # optional; keep as text
    "language_code": None,
}
```

Required: `main_text`, `country_code`.

Optional: `row_id`, `retailer_name`, `ean`, `language_code`.

Select a discovered feature file without `.json`:

```python
FEATURE_SET = "toy_features"
RUN_SINGLE_PRODUCT = True
```

The notebook defaults `RUN_SINGLE_PRODUCT` to `False` to prevent accidental SerpAPI and LLM spend when someone presses Run All before replacing the example product.

## Search and investigation flow

Each product executes three searches in order:

1. requested retailer in the requested country;
2. alternative retailers in the requested country;
3. unrestricted global fallback.

Every retained candidate is then investigated through an independent LLM-controlled browser session. The LLM sees the requested features, rendered page text, screenshot, observed elements, and observed images. Deterministic code still validates product identity, feature evidence, conflicts, accessibility, scrapability, and `primary_url` durability.

## Runtime progress

```text
VALIDATING_INPUT
SEARCHING
AGENTIC_BROWSER_INVESTIGATION
  CAND-001 | turn 1/10 | CLICK | domain
  CAND-001 | turn 2/10 | INSPECT_IMAGE | domain
  CAND-001 | COMPLETED | turns=3 | actions=2
VALIDATING_PRIMARY_URL
WRITING_OUTPUTS
COMPLETED or REVIEW_REQUIRED
```

`COMPLETED` and `REVIEW_REQUIRED` are successful terminal workflow states. `REVIEW_REQUIRED` means execution completed but no investigated URL passed every mandatory gate. Only `FAILED` represents an execution failure.

The notebook suppresses duplicate polling messages and emits a heartbeat every 30 seconds while the same browser or LLM stage remains active.

## Main result fields

```python
pprint(result.get("search") or {})
pprint(result.get("agentic_browser") or {})
pprint(result.get("candidate_investigations") or [])
pprint(result.get("feature_assessments") or [])
pprint(result.get("evidence_set") or {})
pprint(result.get("primary_url_acceptance") or {})
pprint(result.get("browser_evidence") or [])
```

| Path | Meaning |
|---|---|
| `product.row_id` | Original row identifier |
| `job_status` | `COMPLETED` or `REVIEW_REQUIRED` |
| `coding_ready` | Strict deterministic acceptance result |
| `primary_url` | Accepted durable URL or `null` |
| `search.stages` | Three executed search stages |
| `search.serpapi_requests_used` | Exactly three |
| `agentic_browser` | Candidate, action, and turn budgets |
| `candidate_investigations` | Per-candidate LLM plans and actions |
| `feature_assessments` | Per-URL feature evidence and coverage |
| `evidence_set` | Diagnostic multi-source coverage |
| `primary_url_acceptance` | Authoritative final gate decision |
| `browser_evidence` | Rendered and visual evidence |

## Artifacts

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

The notebook can open every `CAND-*/agentic/investigation.json` file directly from the repository-local artifact directory.

## CSV batch

Expected columns:

```text
row_id,main_text,country_code,retailer_name,ean,language_code
```

Batch summaries are written to:

```text
data/artifacts/notebook_batch_summary.csv
```
