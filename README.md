# Product Evidence Platform

A two-container product evidence system for Azure ML Compute Instances.

```text
Notebook / API client
        -> Agent container
             -> one SerpAPI identity search
             -> static extraction and exact-product validation
             -> private feature-gap analysis
             -> Browser container on demand
                    -> Playwright rendering and safe interaction
                    -> direct image acquisition
                    -> element/viewport screenshot fallback
             -> multimodal LLM reasoning
             -> primary URL + supplementary evidence URLs
             -> coding-ready or review-required dossier
```

## Responsibility boundaries

| Service | Owns |
|---|---|
| Agent | Product inputs, private feature files, SerpAPI, static scraping, identity verification, LLM/vision reasoning, final outputs |
| Browser | Rendering, safe overlay handling, section expansion, gallery interaction, image download, screenshots, action trace |
| Notebook | Input preparation, job submission, progress monitoring, evidence inspection |

The browser service never receives the proprietary feature schema. It receives only product identity and generic evidence-acquisition categories.

## Azure ML Compute Instance workflow

```bash
cp .env.example .env
chmod 600 .env
mkdir -p inputs/private artifacts secrets
cp /secure/location/my_feature_set.json inputs/private/toy_features.json
./scripts/azureml_startup.sh
```

The startup script verifies Docker daemon access, generates the internal browser-service token when missing, builds both images, starts Compose, and waits for the agent health endpoint.

Open `notebooks/01_run_product_evidence.ipynb` in Azure ML Studio and submit jobs to:

```text
http://127.0.0.1:8788
```

## Private feature input

Store private feature files under `inputs/private/`. The notebook sends only a logical name:

```json
{
  "product": {
    "row_id": "ROW-001",
    "main_text": "Product identity text",
    "country_code": "CH",
    "retailer_name": "Preferred retailer",
    "ean": "1234567890123"
  },
  "feature_set": "toy_features"
}
```

The agent resolves `toy_features` to `/data/private/toy_features.json` inside the agent container.

## Browser fallback ladder

1. Static HTML and structured data.
2. Browser rendering.
3. Safe overlay dismissal.
4. Product-detail/specification expansion.
5. Direct image download with browser cookies and referer.
6. Gallery interaction.
7. Product-element screenshot.
8. Viewport screenshot fallback.
9. Vision reasoning over validated assets.

CAPTCHA, login walls, paywalls, checkout actions, credential entry, and arbitrary navigation are not bypassed.

## Commands

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f agent browser
python scripts/wait_for_stack.py
```

Stop without deleting artifacts:

```bash
docker compose down
```

## Validation

```bash
PYTHONPATH=src python -m compileall -q src scripts
PYTHONPATH=src pytest -q
```

See [`docs/README.md`](docs/README.md) for the full operating contract.
