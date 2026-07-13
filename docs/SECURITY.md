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

- missing or symlinked `.env` files;
- broadly readable or writable `.env` files unless the explicit Azure ML mounted-filesystem override is used;
- duplicate or malformed assignments;
- placeholder SerpAPI or LLM values;
- non-HTTPS LLM endpoints;
- any organic-search budget other than exactly three;
- AI Mode search credits in the production workflow;
- disabled country-first, global-fallback, browser, all-features-on-primary, or expiring-URL-rejection controls;
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

This exception is invocation-scoped and emits a security warning. It does not disable credential, search-budget, browser, feature-completeness, or URL-durability validation.

## Network boundary

```text
Notebook -> host 127.0.0.1:8788 -> Agent
Agent -> internal http://browser:9000 -> Browser
```

Only the agent port is published to the Compute Instance host. The browser port is internal.

Expected outbound access:

- SerpAPI;
- approved LLM endpoint;
- candidate retailer/manufacturer pages;
- related image/content CDNs;
- container registries during image pulls and builds.

## Browser policy

Allowed actions:

- open discovered candidate URLs;
- render JavaScript content;
- dismiss ordinary consent or newsletter overlays;
- scroll lazy-loaded content;
- expand product details and specification sections;
- interact with ordinary product galleries;
- download validated image assets;
- capture bounded screenshots and action traces.

Prohibited actions:

- CAPTCHA solving or anti-bot bypass;
- login credential entry;
- paywall circumvention;
- cart, checkout, order, payment, or account actions;
- arbitrary form submission or file upload;
- unrestricted cross-domain navigation;
- arbitrary shell execution;
- Docker socket access;
- host filesystem access outside declared mounts.

Blocked pages become review states rather than bypass attempts.

## Final URL security and durability

A product URL is not accepted merely because it appeared in search results. The final URL must be browser-openable, product-specific, scrapable, exact-product verified, and contain every requested feature.

The durability gate rejects URLs containing parameters associated with temporary access, including:

- expiry or TTL values;
- signatures or HMACs;
- access tokens or JWTs;
- temporary cloud credentials;
- session identifiers;
- embedded username/password credentials.

Normal tracking parameters are not treated as product identity. Weak, blocked, signed, or expiring references remain review evidence and are never promoted to `primary_url`.

## Container boundary

- Agent and browser use separate images and dependency manifests.
- Both images define non-root users.
- Compose uses the invoking Azure ML user UID/GID for bind-mounted file compatibility.
- `no-new-privileges` is enabled.
- No Docker socket is mounted.
- Browser memory, concurrency, action count, timeouts, images, and screenshots are bounded.
- Temporary browser state is stored in tmpfs.
- Every candidate request uses an isolated browser context.

## Artifact handling

Artifacts may contain retailer text, product imagery, screenshots, URLs, identifiers, feature evidence, and URL rejection reasons. Treat `data/artifacts/` as business data.

- Do not commit generated artifacts.
- Apply the enterprise retention policy.
- Restrict access to the Azure ML workspace and datastore.
- Delete failed or test artifacts when no longer needed.
- Review screenshots before external sharing.

## Private feature handling

Private feature files live under `inputs/private/`, are ignored by Git, and are mounted only into the agent.

Feature names, descriptions, allowed values, and coding rules are never included in SerpAPI queries. They are used only after candidate pages have been scraped.

## Incident response

When a credential may have been exposed:

1. stop the containers;
2. rotate the credential;
3. remove local `.env`, logs, notebook outputs, and affected artifacts;
4. inspect Git history and CI artifacts;
5. notify the platform/security owner;
6. restart only after preflight passes.

## Verification

```bash
chmod 600 .env
python scripts/validate_environment.py --env-file .env
python scripts/preflight_azureml.py
docker compose config --quiet
docker compose ps
docker compose logs --tail=100 agent browser
```

Mounted-filesystem exception:

```bash
python scripts/preflight_azureml.py --allow-insecure-env-permissions
```
