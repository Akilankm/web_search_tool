# Security Contract

This document defines the current security boundary for the two-container Product Evidence Platform. It is defense-in-depth engineering, not a formal security certification.

## Credential ownership

| Secret | Container |
|---|---|
| SerpAPI key | Agent only |
| LLM key, endpoint, deployment, API version | Agent only |
| Browser internal API token | Agent and browser through a Compose secret |
| Private feature files | Agent only, read-only mount |

The browser container receives no SerpAPI credential, no LLM credential, and no private feature schema.

## Approved secret handling

- Copy `.env.example` to `.env` locally and set mode `0600`.
- Prefer approved Azure ML or enterprise secret injection when available.
- Never commit `.env`, browser tokens, credentials, or private feature files.
- Never print the environment or persist credentials in logs, notebooks, CSV files, Markdown reports, traces, screenshots, or exception messages.

The startup preflight rejects:

- missing `.env` files;
- symlinked `.env` files;
- broadly readable or writable `.env` files unless the operator explicitly enables the Azure ML mounted-filesystem override;
- duplicate or malformed assignments;
- placeholder SerpAPI or LLM values;
- non-HTTPS LLM endpoints;
- one-credit settings that permit extra searches;
- invalid private feature JSON files.

### Mounted-filesystem exception

Some Azure ML `cloudfiles` mounts do not preserve `chmod 600`. The platform remains fail-closed unless the operator explicitly invokes:

```bash
./scripts/azureml_startup.sh --allow-insecure-env-permissions
```

or:

```bash
PRODUCT_EVIDENCE_ALLOW_INSECURE_ENV_PERMISSIONS=true \
  ./scripts/azureml_startup.sh
```

This exception is intentionally invocation-scoped and emits a security warning. It does not sanitize or encrypt the `.env` file. A mode such as `777` may allow other users or processes to read or modify SerpAPI and LLM credentials. Local Compute Instance storage with mode `600`, or approved secret injection, remains the preferred deployment.

## Network boundary

```text
Notebook -> host 127.0.0.1:8788 -> Agent
Agent -> internal http://browser:9000 -> Browser
```

Only the agent port is published to the Compute Instance host. The browser port is not published.

Outbound access is limited operationally to:

- SerpAPI;
- the approved LLM endpoint;
- candidate retailer and manufacturer pages;
- related image/content CDNs;
- container registries during image pulls and builds.

## Browser policy

Allowed actions:

- open an already-discovered candidate URL;
- render JavaScript content;
- dismiss ordinary consent or newsletter overlays;
- scroll lazy-loaded content;
- expand product details and specification sections;
- click product gallery thumbnails;
- open ordinary zoom/lightbox views;
- download validated image assets;
- capture element or viewport screenshots;
- record a bounded action trace.

Prohibited actions:

- CAPTCHA solving or anti-bot bypass;
- login credential entry;
- paywall circumvention;
- cart, checkout, order, payment, or account actions;
- arbitrary form submission;
- file upload;
- unrestricted cross-domain navigation;
- arbitrary shell execution;
- Docker socket access;
- host filesystem access outside declared mounts.

Blocked pages become evidence-review states instead of bypass attempts.

## Container boundary

- Agent and browser use separate images and dependency manifests.
- Both images define non-root users.
- Compose uses the Azure ML checkout owner's UID/GID for bind-mounted file compatibility.
- `no-new-privileges` is enabled.
- No Docker socket is mounted.
- Browser shared memory, concurrency, action count, timeouts, image count, image size, and screenshot count are bounded.
- Temporary browser state is stored in a container tmpfs.
- Every product request uses an isolated Playwright browser context.
- Browser contexts are closed after each candidate.

## Artifact handling

Artifacts may contain retailer text, product imagery, screenshots, URLs, identifiers, and inferred feature evidence. Treat `artifacts/` as business data.

- Do not commit artifacts.
- Apply the enterprise retention policy.
- Restrict access to the Azure ML workspace and datastore.
- Delete failed or test artifacts when no longer needed.
- Review screenshots before external sharing because unrelated page content can be visible.

## Private feature handling

Private feature files live under `inputs/private/`, which is ignored by Git and mounted only into the agent.

The notebook sends a logical feature-set name. The agent resolves that name to a local file using a path-constrained registry. The browser receives only generic evidence intents such as gallery, package, dimensions, safety, or specifications.

Feature names, descriptions, allowed values, and coding rules are never included in the SerpAPI query.

## Incident response

If a credential may have been exposed:

1. stop the containers;
2. rotate the affected credential;
3. remove local `.env`, logs, notebook outputs, and artifacts that may contain it;
4. inspect Git history and CI artifacts;
5. notify the platform/security owner;
6. restart only after the preflight passes with the rotated values.

## Verification

Secure local filesystem:

```bash
chmod 600 .env
python scripts/preflight_azureml.py
docker compose config --quiet
docker compose ps
docker compose logs --tail=100 agent browser
```

Explicit mounted-filesystem exception:

```bash
python scripts/preflight_azureml.py \
  --allow-insecure-env-permissions
```
