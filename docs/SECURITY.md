# Security Contract

This document defines the security boundary for the two-container Product Evidence Platform. It is defense-in-depth engineering, not a formal security certification.

## Credential ownership

| Secret | Container |
|---|---|
| SerpAPI key | Agent only |
| LLM key, endpoint, deployment, API version | Agent only |
| Browser internal API token | Agent and browser through a Compose secret |
| Private feature files | Agent only, read-only mount |

The browser receives no SerpAPI credential, no LLM credential, and no private feature file.

## Automated `.env` handling

The supported command is:

```bash
./scripts/azureml_startup.sh
```

The script attempts `chmod 600 .env` before reading credentials.

- On a normal Linux filesystem, broad permissions remain a startup failure.
- On an Azure ML path under `/cloudfiles/`, the mount may report broad permissions even after `chmod 600`.
- In that specific case, the bootstrap automatically switches to `azureml-cloudfiles-auto-fallback` and emits a warning.
- The fallback changes only the POSIX mode check. It does not weaken credential validation, search limits, LLM endpoint validation, browser safety, feature completeness, or URL durability.
- `.env` contents and API keys are never printed.

For a strict permission-only verification:

```bash
./scripts/azureml_startup.sh --strict-env-permissions
```

Prefer approved enterprise secret injection where available. Never commit `.env`.

## Required agentic trust boundary

The LLM does not receive Playwright, shell, JavaScript, filesystem, arbitrary network, or unrestricted HTTP tools. It receives a bounded observation and may choose one allow-listed browser action:

- click one currently observed `E###` element;
- scroll up, down, top, or bottom;
- inspect one currently observed `I###` image;
- capture the current viewport;
- finish the investigation.

The browser independently rejects invented or stale IDs, cross-site navigation, typing, uploads, login, cart, checkout, payment, order, code execution, CAPTCHA solving, and access-control bypass.

## Prompt-injection handling

Retailer page content is untrusted evidence. Every planning call instructs the LLM to ignore webpage instructions, policy claims, tool-use requests, credential requests, and attempts to change the investigation objective. Page text cannot expand the fixed browser API.

## Final-decision boundary

The LLM controls investigation strategy but does not approve `primary_url`. Deterministic code independently enforces:

- browser accessibility;
- blocker rejection;
- rendered product-page verification;
- exact product and variant identity;
- text scrapability;
- complete requested-feature evidence on one URL;
- no feature conflicts;
- non-expiring durable URL structure;
- requested-retailer, same-country, then global priority.

LLM plans and candidate assessments are audit evidence. `primary_url_acceptance.json` is authoritative.

## Network and container boundary

```text
Notebook -> host 127.0.0.1:8788 -> Agent
Agent -> internal http://browser:9000 -> Browser
```

Only the agent port is published. The browser port is internal and bearer-token protected.

- Both containers run as the invoking non-root Azure ML UID/GID.
- `no-new-privileges` is enabled.
- No Docker socket is mounted.
- Browser sessions use isolated contexts.
- Browser contexts, actions, candidates, LLM turns, images, screenshots, and asset sizes are bounded.
- Temporary browser state is stored in tmpfs.

## Bootstrap failure behavior

Startup fails before notebook use when:

- credentials are missing or still placeholders;
- the LLM endpoint is not HTTPS;
- strict production controls are disabled;
- a feature schema is malformed;
- Docker or Compose is unavailable;
- an unrelated process owns the configured agent port;
- the live agent reports an invalid runtime configuration.

When the agent returns a configuration 503, `wait_for_stack.py` extracts and prints the exact `configuration_error` immediately. It does not print secrets.

## Artifact handling

Artifacts may contain retailer text, product imagery, screenshots, URLs, identifiers, LLM plans, action traces, feature evidence, and rejection reasons. Treat `data/artifacts/` as business data.

- Do not commit generated artifacts.
- Apply enterprise retention policy.
- Restrict workspace and datastore access.
- Review screenshots and page text before external sharing.
- Delete test or failed artifacts when no longer needed.

## Incident response

1. stop containers with `docker compose down`;
2. rotate the affected credential;
3. remove local `.env`, logs, notebook outputs, and affected artifacts;
4. inspect Git history and CI artifacts;
5. notify the platform/security owner;
6. restart only after `./scripts/azureml_startup.sh` passes.

## Verification

```bash
./scripts/azureml_startup.sh
cat data/runtime/stack_health.json
python scripts/validate_environment.py --env-file .env
python -m pytest -q
docker compose config --quiet
docker compose ps
```
