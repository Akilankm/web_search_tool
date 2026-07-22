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
```

The launcher performs a clean reconciliation of only the `product-url-resolver` Compose project. It then:

1. Builds images when `--build` is supplied.
2. Treats `PRODUCT_URL_HOST_PORT` and `PRODUCT_URL_UI_PORT` as preferred ports.
3. Selects the next available ports when either preferred port is occupied by another process or project.
4. Stores only the resolved non-secret port values in `.runtime/ports.env`.
5. Starts the stack, waits for agent and UI readiness, and prints the exact URLs.

The launcher never writes PCA or SerpAPI credentials into `.runtime/ports.env` and does not rewrite `.env`. Browser authentication is generated under `secrets/browser_api_token.txt` and mounted into the browser and agent containers as a Docker secret.

After startup:

```bash
cat .runtime/ports.env
docker compose --env-file .env ps
docker compose --env-file .env logs -f agent
docker compose --env-file .env logs -f browser
docker compose --env-file .env logs -f ui
```

Source code is copied into images. After code changes, use `--build`; a container restart alone is not a deployment.

## Azure ML interactive compute

Clone the repository in the Azure ML VS Code session, create `.env`, and run:

```bash
./scripts/start.sh --build
cat .runtime/ports.env
```

Forward the resolved UI and agent ports shown by the launcher privately through the VS Code Ports panel. Do not assume `8501` or `8788` when the launcher selected alternatives.

## Port conflict diagnosis

The launcher handles normal host-port conflicts automatically. To identify the process or container occupying a preferred port manually:

```bash
docker ps --filter publish=8788
ss -ltnp | grep ':8788 '
```

Do not stop unrelated containers merely to force the preferred port. The resolved alternative port is operationally equivalent.

## Failure classification

- `FAILED` is a completed business outcome with no surviving direct candidate.
- `TECHNICAL_FAILURE` is an operational defect and must be investigated.
- Browser-service unavailability becomes `NOT_ASSESSED` unless browser execution is configured as required.

## Security

- `.env`, `.runtime/`, generated artifacts and secrets are Git-ignored.
- Secrets are never committed.
- Browser authentication is mounted from `secrets/browser_api_token.txt` rather than copied into `.env`.
- Containers run as non-root users with `no-new-privileges`.
- Browser navigation accepts only absolute HTTP(S) URLs.
- Artifact paths are constrained by validated row and candidate identifiers.
