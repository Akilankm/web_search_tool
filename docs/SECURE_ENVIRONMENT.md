# Secure Environment Operations

This document defines the production handling contract for SerpAPI and optional LLM credentials.

## Security posture

The implementation uses defense in depth and fails before any paid network call when configuration is unsafe or ambiguous. It is not presented as a formal government, military, FIPS, Common Criteria, or ISO certification.

## Secret locations

Approved:

1. local `.env` with mode `0600`;
2. process environment injected by Azure ML, CI, a secret manager, or an approved runtime;
3. constructor injection in isolated tests only.

Prohibited:

- committed `.env` files;
- notebooks containing API keys;
- YAML files containing API keys;
- command-line arguments containing secrets;
- source-code constants containing secrets;
- logs, Markdown artifacts, CSV outputs, trace JSON, or exception messages containing secrets.

`.gitignore` excludes `.env`, `.env.*`, `*.secret`, `secrets/`, and `credentials/`, while explicitly allowing `.env.example`.

## Local setup

```bash
cp .env.example .env
chmod 600 .env
```

Replace `SERPAPI_API_KEY`. Configure LLM variables only when post-scrape LLM feature reasoning is enabled.

## Azure ML and managed runtimes

Prefer runtime secret injection instead of persisting `.env` on shared compute. When process-level variables are already injected, the runner permits a missing `.env` file and validates the injected values.

Do not print the environment, execute `env`, or persist a secret-bearing configuration snapshot in pipeline outputs.

## Mandatory one-credit controls

```env
PRODUCT_HARNESS_WORKFLOW=one_credit_feature_aware
PRODUCT_HARNESS_ENABLE_TOURNAMENT_MODE=false
PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES=1
PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES=0
PRODUCT_HARNESS_ENABLE_LLM_SEARCH_PLANNING=false
PRODUCT_HARNESS_ENABLE_LLM_SEARCH_FEEDBACK=false
```

The validator rejects legacy LLM orchestration flags and tournament search expansion. The new harness also forces the SerpAPI client retry count to one request attempt.

## SerpAPI credential

```env
SERPAPI_API_KEY=<real secret>
```

Validation rejects:

- missing values;
- example or placeholder text;
- unusually short values;
- whitespace and control characters.

The SerpAPI client masks its key from provider errors before logging.

## Optional LLM feature reasoning

Enable only when required:

```env
PRODUCT_HARNESS_ENABLE_LLM_FEATURE_REASONING=true
PRODUCT_HARNESS_LLM_MAX_CALLS_PER_PRODUCT=2
```

Use one naming family.

Generic/internal gateway:

```env
LLM_API_KEY=<real secret>
LLM_API_VERSION=<approved version>
LLM_ENDPOINT=https://approved-gateway.example.net/
LLM_DEPLOYMENT=<approved deployment>
LLM_CONSUMER_ID=
```

Azure aliases:

```env
AZURE_OPENAI_API_KEY=<real secret>
AZURE_OPENAI_API_VERSION=<approved version>
AZURE_OPENAI_ENDPOINT=https://approved-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT=<approved deployment>
AZURE_OPENAI_CONSUMER_ID=
```

Defining both naming families is allowed only when corresponding values are identical. Conflicts are rejected.

### LLM transport checks

The endpoint must:

- use HTTPS;
- be absolute and contain a hostname;
- contain no embedded username or password;
- contain no query string or fragment;
- not target localhost or loopback interfaces.

Token, temperature, retry, timeout, and per-product call limits are range checked.

### LLM evidence checks

The LLM runs only after deterministic product identity acceptance and scraping. It cannot initiate search or fetch a URL.

An LLM feature value is discarded unless:

1. the feature ID exists in the supplied feature schema;
2. deterministic extraction did not already support that feature;
3. the response is valid JSON;
4. a non-empty evidence quote is supplied;
5. that quote exists in the bounded scraped page text;
6. closed-set values exactly match an allowed value;
7. confidence is at least `0.50`;
8. the per-product call budget is not exhausted.

Accepted LLM confidence is capped at `0.75`, below deterministic structured-data evidence.

## Startup validation

Both `main.py` and `batch_main.py` execute:

```python
validate_runtime_environment(".env")
```

Validation occurs before worker creation and before SerpAPI or LLM client calls. Failure terminates the run instead of silently falling back to unsafe defaults.

The returned report is secret-free and contains only:

- whether the environment file was loaded;
- whether POSIX permissions were checked;
- whether SerpAPI is configured;
- whether LLM feature reasoning is enabled and configured;
- whether the one-credit contract was enforced;
- names of checks that passed.

## Rotation procedure

1. Generate or obtain the replacement secret through the approved provider.
2. Update the secret manager or local `.env` without committing it.
3. Re-run environment validation.
4. Execute a controlled smoke test against one non-sensitive product.
5. Revoke the old secret.
6. Check logs and artifacts for accidental disclosure.

## Incident response

When a secret may have been exposed:

1. revoke or rotate it immediately;
2. stop active jobs using the compromised value;
3. inspect Git history, CI logs, notebook outputs, artifacts, and shared storage;
4. purge exposed artifacts according to organizational policy;
5. document the exposure window and affected systems;
6. add a regression test for the leakage path.

## Validation tests

```bash
PYTHONPATH=src pytest -q tests/test_environment_security.py
PYTHONPATH=src pytest -q tests/test_llm_feature_reasoner.py
```

The complete CI matrix runs these tests on Python 3.10 and 3.11 before the full repository suite.
