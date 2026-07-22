# Operations

## Configuration

Copy `.env.example` to `.env`. The mandatory search credential is `SERPAPI_API_KEY`.

Optional structured reasoning uses the organization Azure OpenAI-compatible gateway. The preferred variables are:

```dotenv
PRODUCT_URL_REASONING_ENABLED=true
PRODUCT_URL_REASONING_REQUIRED=false
PCA_LLM_API_KEY=<organization-provided-value>
PCA_LLM_API_VERSION=<organization-provided-version>
PCA_LLM_ENDPOINT=<organization-provided-endpoint>
PCA_LLM_DEPLOYMENT=<organization-provided-deployment>
PCA_LLM_CONSUMER_ID=<organization-provided-consumer-id>
```

The runtime sends `PCA_LLM_CONSUMER_ID` as the `X-NIQ-CIS-Consumer` request header and creates an `AzureOpenAI` client with the supplied endpoint, API version and deployment. Generic `LLM_*` names are accepted only as fallback aliases; `PCA_LLM_*` values take precedence. Never commit real values.

Set `PRODUCT_URL_REASONING_REQUIRED=true` only when failure to reach the organization model must stop the run. Otherwise deterministic interpretation remains the fallback.

Operational limits live in `config/default.json`. Per-request overrides are bounded and validated.

## Docker lifecycle

```bash
./scripts/start.sh --build
docker compose ps
docker compose logs -f agent
docker compose logs -f browser
docker compose logs -f ui
```

Source code is copied into images. After code changes, use `--build`; a container restart alone is not a deployment.

## Azure ML interactive compute

Clone the repository in the Azure ML VS Code session, create `.env`, run `./scripts/start.sh --build`, and forward ports `8501` and `8788` privately through the Ports panel.

## Failure classification

- `FAILED` is a completed business outcome with no surviving direct candidate.
- `TECHNICAL_FAILURE` is an operational defect and must be investigated.
- Browser-service unavailability becomes `NOT_ASSESSED` unless browser execution is configured as required.

## Security

- Secrets are never committed.
- The browser accepts an optional bearer token from a Docker secret.
- Containers run as non-root users with `no-new-privileges`.
- Browser navigation accepts only absolute HTTP(S) URLs.
- Artifact paths are constrained by validated row and candidate identifiers.
