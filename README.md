# Product Evidence Platform

A production-oriented, two-container product evidence workflow designed for Azure ML Compute Instances.

```text
Azure ML notebook
  -> Agent container
       -> one identity-only SerpAPI request
       -> static extraction and exact-product validation
       -> Browser container only when rendered or visual evidence is needed
            -> Playwright interaction
            -> direct image acquisition
            -> screenshot fallback
       -> text and vision reasoning
       -> primary URL + supplementary evidence URLs
       -> coding-ready or review-required dossier
```

## One supported workflow

This repository intentionally exposes:

- one startup command: `./scripts/azureml_startup.sh`;
- one notebook: `notebooks/01_run_product_evidence.ipynb`;
- one agent API on `http://127.0.0.1:8788`;
- one internal browser API available only inside Docker Compose.

Old direct-run notebooks and CLI entry points have been removed.

## Fresh Azure ML setup

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool

cp .env.example .env
chmod 600 .env
```

Replace every placeholder in `.env`, including the SerpAPI and LLM settings.

If the Azure ML `cloudfiles` mount cannot preserve mode `600`, keep the default fail-closed behavior unless you deliberately accept the mounted-filesystem risk. The explicit invocation-scoped override is:

```bash
./scripts/azureml_startup.sh --allow-insecure-env-permissions
```

This permits broad modes such as `777` for that startup only and emits a security warning. Prefer copying the runtime to local Compute Instance storage and using mode `600` whenever possible.

Add your private feature set:

```bash
mkdir -p inputs/private
cp /secure/location/toy_features.json inputs/private/toy_features.json
```

Feature-file contract:

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

Start the complete platform:

```bash
./scripts/azureml_startup.sh
```

The command validates configuration and Docker access, builds both images, starts both services, waits for health, and prints logs automatically if startup fails.

Then open:

```text
notebooks/01_run_product_evidence.ipynb
```

Set the notebook's `FEATURE_SET` to the feature-file name without `.json`.

## Azure ML prerequisites

These commands must succeed on the Compute Instance:

```bash
docker info
docker compose version
docker ps
```

Recommended starting capacity:

- 4 vCPU;
- 16 GB RAM;
- outbound access to SerpAPI, the approved LLM endpoint, public product pages, image CDNs, and container registries.

If Docker reports permission denied for `/var/run/docker.sock`, an Azure ML administrator must enable Docker access before the platform can start.

## Service responsibilities

| Service | Responsibility |
|---|---|
| Agent | Private feature files, SerpAPI, static extraction, identity validation, LLM/vision reasoning, source selection, outputs |
| Browser | Rendering, safe overlay handling, section expansion, gallery interaction, image downloads, screenshots, action traces |
| Notebook | Input preparation, job submission, progress monitoring, result inspection, optional CSV batching |

The browser never receives the private feature schema or SerpAPI/LLM credentials.

## Browser fallback ladder

1. Static HTML and structured data.
2. Browser rendering.
3. Ordinary overlay dismissal.
4. Product-detail/specification expansion.
5. Direct image download using browser context.
6. Gallery interaction.
7. Product-element screenshot.
8. Viewport screenshot fallback.
9. Vision reasoning over validated assets.

CAPTCHA, login walls, paywalls, purchases, credential entry, and anti-bot bypass are outside the browser contract.

## Repository layout

```text
.
├── docker-compose.yml
├── docker/
│   ├── agent.Dockerfile
│   └── browser.Dockerfile
├── requirements/
│   ├── agent.txt
│   ├── browser.txt
│   └── test.txt
├── scripts/
│   ├── azureml_startup.sh
│   ├── preflight_azureml.py
│   └── wait_for_stack.py
├── notebooks/
│   └── 01_run_product_evidence.ipynb
├── examples/
│   └── features_to_code.example.json
├── docs/
│   ├── AZUREML_OPERATIONS.md
│   └── SECURITY.md
├── src/product_evidence_harness/
├── tests/
├── inputs/private/     # ignored by Git
└── artifacts/          # ignored by Git
```

## Operations

```bash
# Status
docker compose ps

# Logs
docker compose logs -f --tail=200 agent browser

# Stop without deleting artifacts
docker compose down

# Rebuild after a pull
git pull
docker compose down
./scripts/azureml_startup.sh
```

## Validation

```bash
python -m compileall -q src scripts
python -m json.tool notebooks/01_run_product_evidence.ipynb >/dev/null
python -m pytest -q
docker compose config --quiet
```

For a mounted filesystem that cannot preserve mode `600`:

```bash
python scripts/preflight_azureml.py \
  --project-dir "$(pwd)" \
  --allow-insecure-env-permissions
```

## Documentation

- [Azure ML operations runbook](docs/AZUREML_OPERATIONS.md)
- [Security contract](docs/SECURITY.md)
