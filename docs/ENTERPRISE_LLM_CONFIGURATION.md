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

The bootstrap and agent health checks require only the following four values to be present:

- API key;
- API version;
- endpoint;
- deployment.

`LLM_CONSUMER_ID` remains optional.

## Values are not second-guessed

Enterprise gateways differ from public Azure OpenAI conventions. The platform therefore does not reject an LLM configuration because of:

- a short opaque API key;
- a non-HTTPS or non-URL endpoint string;
- an internal gateway path;
- spaces or organization-specific characters in a deployment identifier;
- a value that resembles a local or custom endpoint;
- different credential lengths or naming conventions.

The actual provider request is the authoritative validation. Authentication, routing, deployment, certificate, and protocol errors are surfaced from the LLM client when the first real request is made.

## Validation that remains

The platform still validates:

- required LLM fields are not empty;
- numeric controls such as token limits, timeouts, temperature, and retry counts are parseable and within supported runtime bounds;
- `.env` syntax and duplicate keys;
- SerpAPI configuration and search-credit controls;
- agentic browser, feature-schema, identity, evidence, and URL-acceptance contracts.

Credential values are never printed in preflight, health, or failure diagnostics.

## Azure ML workflow

```bash
cp .env.example .env
# Update the real SerpAPI and enterprise LLM values.
./scripts/azureml_startup.sh
```

When startup reports the stack as healthy, open:

```text
notebooks/01_run_product_evidence.ipynb
```
