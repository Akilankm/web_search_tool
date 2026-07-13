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

## Azure ML prerequisites

The Compute Instance must provide:

- Docker Engine and Docker Compose v2;
- permission to run `docker info` without an interactive password prompt;
- outbound access to the container registry, SerpAPI, the approved LLM endpoint, retailer pages, manufacturer pages, and image CDNs;
- at least 4 vCPU and 16 GB RAM as the recommended starting point;
- sufficient disk space for container images and evidence artifacts.

Verify Docker access:

```bash
docker info
docker compose version
docker ps
```

If `docker info` reports permission denied for `/var/run/docker.sock`, the platform cannot start. The Azure ML administrator must grant Docker access.

## Supported fresh-clone procedure

The intended workflow is exactly:

1. clone the repository;
2. configure `.env`;
3. add the private feature file;
4. run Docker through the startup script;
5. open the notebook and submit products.

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool

cp .env.example .env
chmod 600 .env
```

Edit `.env` and replace every placeholder. At minimum, configure:

```env
SERPAPI_API_KEY=...
LLM_API_KEY=...
LLM_API_VERSION=...
LLM_ENDPOINT=https://...
LLM_DEPLOYMENT=...
```

The LLM settings are mandatory while `PRODUCT_HARNESS_ENABLE_VISION_REASONING=true`.

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

## Azure ML mounted filesystems that cannot preserve mode 600

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

Standard secure startup:

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

No manual `PRODUCT_EVIDENCE_RUNTIME_UID/GID` export, symlink, `/app/output` creation, or artifact copy is part of the supported workflow.

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

Both the one-credit search artifacts and the final orchestrated dossier are written into the same product folder:

```text
data/artifacts/<row_id>/
├── orchestrated_result.json
├── result.json
├── candidates.csv
├── feature_evidence.csv
├── review.md
└── CAND-*/browser/
    ├── browser_result.json
    ├── rendered_text.md
    ├── final_page.html
    ├── browser_actions.json
    ├── visual_manifest.json
    ├── images/
    └── screenshots/
```

Generated `data/artifacts/` and `data/runtime/` content is ignored by Git. If either directory is removed while the stack is stopped, the next startup recreates it.

## Run products

Open this notebook in Azure ML Studio:

```text
notebooks/01_run_product_evidence.ipynb
```

Set `FEATURE_SET` to the private file name without `.json`:

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

After a run:

```bash
find data/artifacts -maxdepth 4 -type f | sort
```

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

The browser service does not perform search and does not receive the private feature schema.

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
| Docker reports `compose` is not a command | Install the Docker Compose v2 CLI plugin for the Compute Instance user |
| `.env` remains broadly readable after `chmod 600` | Use the explicit mounted-filesystem override and accept the warning |
| Preflight reports placeholder value | Replace the named `.env` value and rerun |
| No feature set found | Copy a valid JSON file into `inputs/private/` |
| Runtime directory is not writable | Verify the current notebook user can write inside the cloned repository |
| Agent port already in use | Stop the conflicting process or change `AGENT_HOST_PORT` |
| Browser unhealthy | Check `docker compose logs browser`; confirm shared memory and outbound access |
| Agent unhealthy | Check `docker compose logs agent`; verify SerpAPI and LLM settings |
| CAPTCHA/login/access wall | The candidate is marked blocked; the system does not bypass access controls |
| Notebook cannot connect | Confirm the stack is healthy and `PRODUCT_AGENT_URL` points to `http://127.0.0.1:8788` |

## Validation commands

```bash
python -m compileall -q src scripts
python -m json.tool notebooks/01_run_product_evidence.ipynb >/dev/null
python -m pytest -q
docker compose config --quiet
```

Mounted-filesystem preflight:

```bash
python scripts/preflight_azureml.py \
  --project-dir "$(pwd)" \
  --allow-insecure-env-permissions
```
