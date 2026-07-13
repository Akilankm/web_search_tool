# Azure ML Operations Runbook

This is the definitive operating procedure for the Product Evidence Platform.

## Supported topology

```text
Azure ML Compute Instance
├── Docker Compose
│   ├── agent:8000   -> host 127.0.0.1:8788
│   └── browser:9000 -> internal Compose network only
├── inputs/private/  -> read-only inside the agent
├── artifacts/       -> shared by agent and browser
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

If `docker info` reports permission denied for `/var/run/docker.sock`, the platform cannot start. The Azure ML administrator must grant Docker access or run the startup script through an approved Compute Instance startup hook.

## Fresh-clone procedure

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool

cp .env.example .env
chmod 600 .env
```

### Azure ML mounted filesystems that cannot preserve mode 600

The platform remains fail-closed by default. If the repository is stored on an Azure ML `cloudfiles` mount where `chmod 600 .env` does not change the reported mode, start with the explicit override:

```bash
./scripts/azureml_startup.sh --allow-insecure-env-permissions
```

The equivalent process-level override is:

```bash
PRODUCT_EVIDENCE_ALLOW_INSECURE_ENV_PERMISSIONS=true \
  ./scripts/azureml_startup.sh
```

This override accepts modes such as `777` only for that invocation and prints a security warning. It does not disable credential, endpoint, feature-file, Docker, Compose, or port validation. Prefer a local Compute Instance directory with mode `600` whenever possible because group or other users may read or modify credentials on a permissive mount.

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

## Start the platform

Standard secure startup:

```bash
./scripts/azureml_startup.sh
```

Mounted-filesystem override when mode `600` cannot be preserved:

```bash
./scripts/azureml_startup.sh --allow-insecure-env-permissions
```

The startup process:

1. validates `.env` syntax, permissions or the explicit permission override, one-credit controls, and credentials;
2. validates every private feature JSON file;
3. creates a generic `example_features.json` only when no private file exists;
4. validates Docker and Compose;
5. checks the agent host port;
6. creates the internal browser API token;
7. builds and starts both containers;
8. waits for agent and browser health;
9. prints container logs automatically when startup fails.

Expected completion message:

```text
Product evidence platform is ready at http://127.0.0.1:8788
```

Verify manually:

```bash
docker compose ps
docker compose logs --tail=100 agent browser
python scripts/wait_for_stack.py
```

Both containers must be healthy.

## Run products

Open this notebook in Azure ML Studio:

```text
notebooks/01_run_product_evidence.ipynb
```

Set `FEATURE_SET` to the private file name without `.json`, for example:

```python
FEATURE_SET = "toy_features"
```

The notebook supports:

- one product;
- an optional CSV batch;
- progress polling;
- result retrieval;
- feature-evidence inspection;
- browser-evidence inspection;
- a batch summary written under `artifacts/`.

Required product fields:

| Field | Required |
|---|:---:|
| `row_id` | Recommended |
| `main_text` | Yes |
| `country_code` | Yes |
| `retailer_name` | No |
| `ean` | No |
| `language_code` | No |

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
  -> result and artifacts are written
```

The browser service does not perform search and does not receive the private feature schema.

## Artifacts

```text
artifacts/<row_id>/
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

If the repository remains on a permissive Azure ML mount, include `--allow-insecure-env-permissions` again because the override is intentionally invocation-scoped.

## Failure guide

| Symptom | Action |
|---|---|
| Docker socket permission denied | Request Docker permission from the Azure ML administrator |
| Docker reports `compose` is not a command | Install the Docker Compose v2 CLI plugin for the Compute Instance user |
| `.env` remains broadly readable after `chmod 600` | Prefer local Compute Instance storage, or explicitly use `--allow-insecure-env-permissions` and accept the warning |
| Preflight reports placeholder value | Replace the named `.env` value and rerun |
| No feature set found | Copy a valid JSON file into `inputs/private/` |
| Agent port already in use | Stop the conflicting process or change `AGENT_HOST_PORT` |
| Browser unhealthy | Check `docker compose logs browser`; confirm shared memory and outbound access |
| Agent unhealthy | Check `docker compose logs agent`; verify SerpAPI and LLM settings |
| CAPTCHA/login/access wall | The candidate is marked blocked; the system does not bypass access controls |
| Notebook cannot connect | Confirm the stack is healthy and `PRODUCT_AGENT_URL` points to `http://127.0.0.1:8788` |

## Validation commands

Secure local filesystem:

```bash
python -m compileall -q src scripts
python -m json.tool notebooks/01_run_product_evidence.ipynb >/dev/null
python -m pytest -q

docker compose config --quiet
```

Mounted-filesystem preflight override:

```bash
python scripts/preflight_azureml.py \
  --project-dir "$(pwd)" \
  --allow-insecure-env-permissions
```
