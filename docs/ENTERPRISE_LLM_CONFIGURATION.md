# Enterprise LLM configuration

The Product Evidence Platform accepts enterprise-issued LLM settings as opaque values.

## Required fields

Supply either the `LLM_*` names:

```env
LLM_API_KEY=...
LLM_API_VERSION=...
LLM_ENDPOINT=...
LLM_DEPLOYMENT=...
LLM_CONSUMER_ID=
```

or the equivalent `AZURE_OPENAI_*` aliases.

The bootstrap and agent health checks require API key, API version, endpoint and deployment. `LLM_CONSUMER_ID` is optional.

## Values are not second-guessed

Enterprise gateways differ from public Azure OpenAI conventions. The platform does not reject a configuration merely because of a short opaque key, internal gateway path, custom endpoint format, organization-specific deployment identifier or different credential length.

The provider request is the authoritative validation. Authentication, routing, deployment, certificate and protocol errors are surfaced from the LLM client.

## Validation that remains

The platform validates:

- required LLM fields are not empty;
- numeric token, timeout, temperature and retry controls are parseable and within bounds;
- `.env` syntax and duplicate keys;
- SerpAPI and search-credit controls;
- agentic browser, feature-schema, identity, evidence and URL-acceptance contracts.

Credential values are never printed in preflight, health or failure diagnostics.

## Azure ML workflow

```bash
cp .env.example .env
# Update the real SerpAPI and enterprise LLM values.
./scripts/azureml_startup.sh
```

Execution notebooks requiring the LLM and browser stack:

```text
notebooks/01_single_product.ipynb
notebooks/02_batch_products.ipynb
```

Offline artifact review does not call the LLM:

```text
notebooks/03_artifact_diagnostics.ipynb
```

The batch notebook can submit multiple product jobs concurrently. Product-level parallelism should remain bounded by agent workers, browser contexts and the enterprise provider's rate limits.
