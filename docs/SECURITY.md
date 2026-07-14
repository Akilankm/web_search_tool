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

## Required agentic trust boundary

The LLM does not receive Playwright, shell, JavaScript, filesystem, network, or arbitrary HTTP tools. It receives a bounded observation and may choose one allow-listed browser action.

Allowed actions:

- click one currently observed `E###` element;
- scroll up, down, top, or bottom;
- inspect one currently observed `I###` image;
- capture the current viewport;
- finish the investigation.

Prohibited actions:

- invent or directly navigate to a URL;
- invent an element or image ID;
- type into forms;
- upload files;
- log in or provide credentials;
- submit cart, checkout, payment, account, or order actions;
- execute JavaScript, Python, shell, or arbitrary code;
- solve CAPTCHA or bypass bot detection, paywalls, authentication, or access controls.

The browser validates every requested action before execution. Invalid or stale IDs fail closed.

## Prompt-injection handling

Retailer page content is untrusted evidence. Every planning call instructs the LLM to ignore webpage instructions, policy claims, tool-use requests, credential requests, and attempts to change the investigation objective.

The LLM cannot expand its tool set. Page text cannot grant new capabilities because the browser API itself accepts only the fixed action schema.

## Final-decision boundary

The LLM controls investigation strategy but does not approve `primary_url`.

Deterministic code independently enforces:

- browser accessibility;
- access-blocker rejection;
- rendered product-page verification;
- exact product and variant identity;
- text scrapability;
- complete requested-feature evidence on one URL;
- no feature conflicts;
- non-expiring durable URL structure;
- requested-retailer, same-country, then global scope priority.

LLM plans and candidate assessments are audit evidence. `primary_url_acceptance.json` is authoritative.

## Secret handling

- Copy `.env.example` to `.env` and use mode `0600` where supported.
- Prefer approved Azure ML or enterprise secret injection.
- Never commit `.env`, browser tokens, private feature files, or generated artifacts.
- Never print environment values or credentials in logs, notebooks, reports, screenshots, or exceptions.

The preflight rejects placeholder secrets, non-HTTPS LLM endpoints, invalid search budgets, disabled agentic controls, invalid action budgets, and malformed private feature files.

## Mounted-filesystem exception

When Azure ML mounted storage cannot preserve `chmod 600`:

```bash
./scripts/azureml_startup.sh --allow-insecure-env-permissions
```

This explicit exception weakens local file-permission protection only. It does not disable credential validation, browser safety, search-budget controls, feature completeness, or URL durability.

## Network boundary

```text
Notebook -> host 127.0.0.1:8788 -> Agent
Agent -> internal http://browser:9000 -> Browser
```

Only the agent port is published. The browser port is internal and protected by a bearer token stored as a Compose secret.

Expected outbound access:

- SerpAPI;
- approved LLM endpoint;
- candidate retailer/manufacturer pages;
- related content and image CDNs;
- container registries during image builds.

## Container boundary

- Agent and browser use separate images.
- Both run as non-root users.
- `no-new-privileges` is enabled.
- No Docker socket is mounted.
- Browser sessions use isolated contexts.
- Context count, navigation time, action count, LLM turns, candidate count, screenshots, images, and asset sizes are bounded.
- Temporary browser state is stored in tmpfs.
- Shared storage is limited to declared artifact mounts.

## Artifact handling

Artifacts may contain retailer text, product imagery, screenshots, URLs, identifiers, LLM plans, action traces, feature evidence, and rejection reasons. Treat `data/artifacts/` as business data.

- Do not commit generated artifacts.
- Apply enterprise retention policy.
- Restrict workspace and datastore access.
- Review screenshots and page text before external sharing.
- Delete test or failed artifacts when no longer needed.

## Incident response

When a credential or sensitive artifact may have been exposed:

1. stop the containers;
2. rotate the affected credential;
3. remove local `.env`, logs, notebook outputs, and affected artifacts;
4. inspect Git history and CI artifacts;
5. notify the platform/security owner;
6. restart only after preflight passes.

## Verification

```bash
chmod 600 .env
python scripts/validate_environment.py --env-file .env
python scripts/preflight_azureml.py
python -m pytest -q
docker compose config --quiet
docker compose ps
docker compose logs --tail=100 agent browser
```
