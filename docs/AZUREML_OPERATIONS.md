# Azure ML Operations Runbook

This is the definitive operating procedure for the Product Evidence Platform.

## Supported topology

```text
Azure ML Compute Instance
├── Docker Compose
│   ├── agent:8000   -> host 127.0.0.1:8788
│   └── browser:9000 -> internal Compose network only
├── inputs/private/  -> read-only inside the agent
├── data/
│   ├── artifacts/   -> shared by agent and browser
│   └── runtime/     -> repository-local transient runtime state
└── notebooks/01_run_product_evidence.ipynb
```

The notebook is only a client. SerpAPI discovery, static extraction, product identity validation, browser control, image acquisition, screenshots, multimodal reasoning, and output writing happen inside the containers.

## Prerequisites

The Compute Instance must provide:

- Docker Engine and Docker Compose v2;
- permission to run `docker info` without an interactive password prompt;
- outbound access to SerpAPI, the approved LLM endpoint, retailer pages, manufacturer pages, image CDNs, and container registries;
- at least 4 vCPU and 16 GB RAM as the recommended starting point;
- sufficient disk space for container images and evidence artifacts.

Verify Docker access:

```bash
docker info
docker compose version
docker ps
```

## Fresh-clone procedure

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool

cp .env.example .env
chmod 600 .env
```

Edit `.env` and replace every placeholder.

Add the private feature file:

```bash
mkdir -p inputs/private
cp /secure/location/toy_features.json inputs/private/toy_features.json
```

Required JSON contract:

```json
{
  "features_to_code": [
    "private feature name",
    {
      "name": "another private feature",
      "description": "Optional extraction guidance"
    }
  ]
}
```

Feature names are never sent to SerpAPI. They are introduced only after URL discovery.

## Azure ML mounted filesystems

The platform remains fail-closed by default. If `chmod 600 .env` does not change the reported mode, start with:

```bash
./scripts/azureml_startup.sh --allow-insecure-env-permissions
```

The equivalent process-level override is:

```bash
PRODUCT_EVIDENCE_ALLOW_INSECURE_ENV_PERMISSIONS=true \
  ./scripts/azureml_startup.sh
```

The override is invocation-scoped and does not disable credential, endpoint, feature-file, Docker, Compose, or port validation.

## Start the platform

Standard startup:

```bash
./scripts/azureml_startup.sh
```

Mounted-filesystem startup:

```bash
./scripts/azureml_startup.sh --allow-insecure-env-permissions
```

The startup process automatically:

1. creates `data/artifacts/`, `data/runtime/`, `inputs/private/`, and `secrets/` when absent;
2. creates the browser API token when absent;
3. validates `.env`, credentials, one-credit controls, feature files, Docker, Compose, and the agent port;
4. uses the current non-root Azure ML notebook user as the container UID/GID;
5. confirms repository-local runtime folders are writable;
6. builds and starts both containers;
7. waits for agent and browser health;
8. prints logs automatically when startup fails.

Expected completion messages:

```text
Product evidence platform is ready at http://127.0.0.1:8788
Artifacts will be written under <repo>/data/artifacts/<row_id>/
```

Verify manually:

```bash
docker compose ps
docker compose logs --tail=100 agent browser
python scripts/wait_for_stack.py
```

## Artifact path contract

```text
Host repository: ./data/artifacts
Agent container: /data/artifacts
Browser container: /data/artifacts
One-credit writer: PRODUCT_HARNESS_OUTPUT_DIR=/data/artifacts
```

Both the one-credit search artifacts and final orchestrated dossier are written into:

```text
data/artifacts/<row_id>/
├── orchestrated_result.json
├── result.json
├── candidates.csv
├── feature_evidence.csv
├── review.md
└── CAND-*/browser/
```

Generated `data/artifacts/` and `data/runtime/` content is ignored by Git. If either directory is removed while the stack is stopped, the next startup recreates it.

## Run products

Open:

```text
notebooks/01_run_product_evidence.ipynb
```

Set the private feature filename without `.json`:

```python
FEATURE_SET = "toy_features"
```

Required product fields:

| Field | Required |
|---|:---:|
| `row_id` | Recommended |
| `main_text` | Yes |
| `country_code` | Yes |
| `retailer_name` | No |
| `ean` | No |
| `language_code` | No |

EAN/GTIN values must be supplied as strings so leading zeroes are preserved.

Run one product:

```python
result = run_product(product, FEATURE_SET)
pprint(summarize_result(result))
```

## Job and result semantics

The polling endpoint and result endpoint expose related but different structures.

### Polling endpoint

`GET /v1/jobs/{job_id}` returns the execution record:

| Field | Meaning |
|---|---|
| `status` | `RUNNING`, `COMPLETED`, `REVIEW_REQUIRED`, or `FAILED` |
| `stage` | Current workflow stage |
| `message` | Human-readable progress message |
| `error` | Error text only for failed jobs |

### Result endpoint

`GET /v1/jobs/{job_id}/result` returns the orchestrated product result:

| Path | Meaning |
|---|---|
| `product.row_id` | Original product row identifier |
| `job_status` | `COMPLETED` or `REVIEW_REQUIRED` |
| `coding_ready` | Whether the evidence set is sufficient for coding |
| `primary_url` | Primary validated product/evidence URL |
| `supplementary_urls` | Additional feature-evidence URLs |
| `product_match` | URL decision, confidence, and best review URL |
| `evidence_set` | Coverage, missing features, and conflicts |
| `feature_assessments` | Per-URL feature evidence |
| `browser_evidence` | Rendered and visual evidence bundles |
| `artifact_dir` | Container path under `/data/artifacts` |

The result does not expose top-level `row_id`, `status`, or `feature_evidence` fields. Use:

```python
row_id = result.get("product", {}).get("row_id")
job_status = result.get("job_status")
feature_assessments = result.get("feature_assessments", [])
```

The notebook's `summarize_result(result)` helper provides the supported flattened view.

## Status interpretation

| Status | Interpretation |
|---|---|
| `COMPLETED` | Workflow completed and the evidence set is coding-ready |
| `REVIEW_REQUIRED` | Workflow completed, but evidence is insufficient for automatic coding |
| `FAILED` | Execution failed |

`REVIEW_REQUIRED` is not an infrastructure or Python failure.

A result such as:

```python
{
    "job_status": "REVIEW_REQUIRED",
    "coding_ready": False,
    "primary_url": None,
}
```

means no candidate passed the configured identity and evidence gates. Inspect `product_match.best_available_url`, `evidence_set`, `review.md`, and `candidates.csv`.

## Artifact inspection

The API reports:

```text
/data/artifacts/<row_id>
```

The corresponding repository path is:

```text
data/artifacts/<row_id>/
```

The notebook uses `host_artifact_dir(result)` to resolve the host path even when the kernel starts inside `notebooks/`.

For review-required cases inspect:

```python
pprint(result.get("product_match") or {})
pprint(result.get("evidence_set") or {})
pprint(result.get("feature_assessments") or [])
pprint(result.get("browser_evidence") or [])
```

Then inspect:

```text
data/artifacts/<row_id>/review.md
data/artifacts/<row_id>/candidates.csv
```

## CSV batch

Expected input columns:

```text
row_id,main_text,country_code,retailer_name,ean,language_code
```

The notebook writes:

```text
data/artifacts/notebook_batch_summary.csv
```

The summary includes `job_status`, `coding_ready`, selected URLs, decision status, missing features, and the host artifact directory.

## Runtime flow

```text
Notebook
  -> POST /v1/jobs
  -> agent runs one identity-only SerpAPI request
  -> agent performs static extraction and identity validation
  -> agent requests browser evidence only when needed
  -> browser renders, expands, downloads images, or captures screenshots
  -> agent performs text and vision reasoning
  -> agent selects primary and supplementary evidence URLs
  -> result and artifacts are written to data/artifacts/<row_id>/
```

## Operations

Restart:

```bash
docker compose restart browser agent
python scripts/wait_for_stack.py
```

View logs:

```bash
docker compose logs -f --tail=200 agent browser
```

Stop while retaining artifacts:

```bash
docker compose down
```

Rebuild after pulling code changes:

```bash
git pull
docker compose down
./scripts/azureml_startup.sh
```

On a permissive Azure ML mount, include `--allow-insecure-env-permissions` again.

## Failure guide

| Symptom | Action |
|---|---|
| Docker socket permission denied | Request Docker permission from the Azure ML administrator |
| Docker reports `compose` is not a command | Install the Docker Compose v2 CLI plugin |
| `.env` remains broadly readable | Use the explicit mounted-filesystem override and accept the warning |
| Preflight reports placeholder value | Replace the named `.env` value and rerun |
| No feature set found | Copy a valid JSON file into `inputs/private/` |
| Runtime directory is not writable | Verify the current notebook user can write inside the repository |
| Agent port already in use | Stop the conflicting process or change `AGENT_HOST_PORT` |
| Browser unhealthy | Check `docker compose logs browser` |
| Agent unhealthy | Check `docker compose logs agent`; verify SerpAPI and LLM settings |
| Notebook shows `row_id=None` or `status=None` | Pull the latest notebook and use `summarize_result(result)` |
| `REVIEW_REQUIRED` with no primary URL | Inspect `product_match`, `evidence_set`, `review.md`, and `candidates.csv` |
| CAPTCHA/login/access wall | The candidate is marked blocked; access controls are not bypassed |

## Validation commands

```bash
python -m compileall -q src scripts
python -m json.tool notebooks/01_run_product_evidence.ipynb >/dev/null
python -m pytest -q
docker compose config --quiet
```

See also [Notebook Usage and Result Contract](NOTEBOOK_USAGE.md).
