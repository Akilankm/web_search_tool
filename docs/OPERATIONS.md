# Operations

## Configuration

Copy `.env.example` to `.env`. The mandatory search credential is `SERPAPI_API_KEY`.

Optional structured reasoning uses the organization Azure OpenAI-compatible gateway:

```dotenv
PRODUCT_URL_REASONING_ENABLED=true
PRODUCT_URL_REASONING_REQUIRED=false
PCA_LLM_API_KEY=<organization-provided-value>
PCA_LLM_API_VERSION=<organization-provided-version>
PCA_LLM_ENDPOINT=<organization-provided-endpoint>
PCA_LLM_DEPLOYMENT=<organization-provided-deployment>
PCA_LLM_CONSUMER_ID=<organization-provided-consumer-id>
```

The runtime sends `PCA_LLM_CONSUMER_ID` as `X-NIQ-CIS-Consumer`. Generic `LLM_*` names remain fallback aliases; `PCA_LLM_*` values take precedence. Never commit real values.

Set `PRODUCT_URL_REASONING_REQUIRED=true` only when failure to reach the organization model must stop the run. Otherwise deterministic interpretation remains the fallback.

## Docker lifecycle

```bash
./scripts/start.sh --build
```

The launcher:

1. builds images when `--build` is supplied;
2. treats `PRODUCT_URL_HOST_PORT` and `PRODUCT_URL_UI_PORT` as preferred ports;
3. selects the next available ports when needed;
4. writes only resolved non-secret ports to `.runtime/ports.env`;
5. starts the stack and waits for agent/UI readiness;
6. prints exact URLs and PCA reasoning status.

The launcher does not rewrite `.env`. Browser authentication is generated under `secrets/browser_api_token.txt` and mounted as a Docker secret.

After startup:

```bash
cat .runtime/ports.env
docker compose --env-file .env ps
docker compose --env-file .env logs -f agent
docker compose --env-file .env logs -f browser
docker compose --env-file .env logs -f ui
```

Source code is copied into images. After code changes, rebuild with `./scripts/start.sh --build`.

## Human-review UI

Open the UI URL printed by the launcher. Enable **Thinking mode: live decision trace** in the sidebar.

The UI polls the incremental trace endpoint and renders:

- live stage state;
- identity signals and hypotheses;
- each search credit and source result;
- page acquisition outcomes;
- candidate gate judgments;
- browser usability and screenshots;
- final selection and rejection logic.

The UI mounts `data/artifacts` read-only. It can display screenshots and export reviews but cannot alter evidence files.

## Notebook trace polling

```python
last_sequence = 0
trace = requests.get(
    f"{API_URL}/v1/jobs/{job_id}/trace",
    params={"after_sequence": last_sequence},
    timeout=30,
).json()
last_sequence = trace["last_event_sequence"]
new_events = trace["events"]
```

The trace contains observable evidence and judgments, not hidden chain-of-thought.

## Azure ML interactive compute

Run:

```bash
./scripts/start.sh --build
cat .runtime/ports.env
```

Forward the resolved UI and agent ports privately through the VS Code Ports panel. Do not assume `8501` or `8788` if alternatives were selected.

## Port conflict diagnosis

```bash
docker ps --filter publish=8788
ss -ltnp | grep ':8788 '
```

Do not stop unrelated containers merely to force the preferred port.

## Failure classification

- `FAILED` is a completed business outcome with no surviving direct candidate.
- `TECHNICAL_FAILURE` is an operational defect and must be investigated.
- Browser-service unavailability becomes `NOT_ASSESSED` unless browser execution is required.

## Security

- `.env`, `.runtime/`, generated artifacts and secrets are Git-ignored.
- Secrets are never committed.
- Browser authentication is mounted from `secrets/browser_api_token.txt`.
- The UI artifact mount is read-only.
- Containers run as non-root users with `no-new-privileges`.
- Browser navigation accepts only absolute HTTP(S) URLs.
- Artifact paths are constrained by validated row and candidate identifiers.
