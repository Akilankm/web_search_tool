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

The supported operator flow is:

1. clone the repository;
2. create and populate `.env`;
3. add the private feature JSON;
4. run the startup script;
5. open the notebook and execute products.

## Fresh Azure ML setup

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool

cp .env.example .env
chmod 600 .env
```

Replace every placeholder in `.env`, including the SerpAPI and LLM settings.

Add the private feature set:

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

On an Azure ML `cloudfiles` mount that cannot preserve mode `600`:

```bash
./scripts/azureml_startup.sh --allow-insecure-env-permissions
```

The startup command automatically:

- creates `data/artifacts/`, `data/runtime/`, `inputs/private/`, and `secrets/` when absent;
- generates the browser API token when absent;
- resolves the current non-root Azure ML notebook user as the container UID/GID;
- validates configuration and Docker access;
- builds and starts both containers;
- waits for service health;
- routes every product artifact to `data/artifacts/<row_id>/`.

No manual UID/GID export, symlink, `/app/output` repair, or artifact copy is required.

Then open:

```text
notebooks/01_run_product_evidence.ipynb
```

Set `FEATURE_SET` to the private feature filename without `.json`.

## Notebook result contract

The notebook uses the current orchestrated API schema.

Important fields:

| Path | Meaning |
|---|---|
| `product.row_id` | Original row identifier |
| `job_status` | `COMPLETED` or `REVIEW_REQUIRED` |
| `coding_ready` | Whether evidence is sufficient for coding |
| `primary_url` | Primary validated URL, or `null` |
| `supplementary_urls` | Additional evidence URLs |
| `product_match` | Product URL decision and best review URL |
| `evidence_set` | Coverage, missing features, and conflicts |
| `feature_assessments` | Per-URL feature evidence |
| `browser_evidence` | Rendered and visual evidence |
| `artifact_dir` | Container artifact path |

`REVIEW_REQUIRED` is a successful terminal state, not an execution failure. It means the workflow completed but the available identity or feature evidence was not sufficient for automatic coding.

Use the notebook helper:

```python
result = run_product(product, FEATURE_SET)
pprint(summarize_result(result))
```

Do not read stale top-level fields such as `result["row_id"]`, `result["status"]`, or `result["feature_evidence"]`.

See [Notebook usage and result contract](docs/NOTEBOOK_USAGE.md) for the exact schema, artifact inspection workflow, and `REVIEW_REQUIRED` diagnostics.

## Runtime artifact contract

```text
Host repository: ./data/artifacts
Agent container: /data/artifacts
Browser container: /data/artifacts
Product output:  ./data/artifacts/<row_id>/
```

Typical product output:

```text
data/artifacts/TEST-001/
├── candidates.csv
├── feature_evidence.csv
├── orchestrated_result.json
├── result.json
├── review.md
└── CAND-*/browser/
```

The API reports the container path `/data/artifacts/<row_id>`. The notebook resolves the corresponding host path as `<repo>/data/artifacts/<row_id>/`.

Generated `data/artifacts/` and `data/runtime/` content is ignored by Git. Deleting either directory while the stack is stopped is safe; the next startup recreates it.

Batch summaries are written to:

```text
data/artifacts/notebook_batch_summary.csv
```

## Azure ML prerequisites

These commands must succeed:

```bash
docker info
docker compose version
docker ps
```

Recommended starting capacity:

- 4 vCPU;
- 16 GB RAM;
- outbound access to SerpAPI, the approved LLM endpoint, public product pages, image CDNs, and container registries.

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
├── requirements/
├── scripts/
├── notebooks/
│   └── 01_run_product_evidence.ipynb
├── examples/
├── docs/
│   ├── AZUREML_OPERATIONS.md
│   ├── NOTEBOOK_USAGE.md
│   └── SECURITY.md
├── src/product_evidence_harness/
├── tests/
├── inputs/private/       # created automatically; ignored by Git
└── data/
    ├── artifacts/        # created automatically; ignored by Git
    └── runtime/          # created automatically; ignored by Git
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

After a successful notebook run:

```bash
find data/artifacts -maxdepth 4 -type f | sort
```

## Validation

```bash
python -m compileall -q src scripts
python -m json.tool notebooks/01_run_product_evidence.ipynb >/dev/null
python -m pytest -q
docker compose config --quiet
```

## Documentation

- [Azure ML operations runbook](docs/AZUREML_OPERATIONS.md)
- [Notebook usage and result contract](docs/NOTEBOOK_USAGE.md)
- [Security contract](docs/SECURITY.md)
