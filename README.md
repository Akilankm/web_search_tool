# Product Evidence Platform

A production-oriented product URL and feature-evidence workflow for Azure ML Compute Instances.

## Production contract

Every product uses exactly three bounded SerpAPI organic searches:

1. requested retailer in the requested country, or the primary country search;
2. alternative sources within the requested country;
3. unrestricted global fallback.

Search remains high-recall, but downstream work is precision-gated:

```text
raw SERP occurrence
→ canonical URL identity
→ URL-type and product-identity admission
→ bounded full scrape
→ evidence-utility validation
→ bounded agentic-browser escalation
→ strict primary URL decision
```

Obvious home, search, category, collection, social, PDF, media, and low-identity URLs remain visible in the audit ledger but do not consume a full scrape or LLM-controlled browser session.

See [docs/CANDIDATE_PRECISION_AND_CONTEXT.md](docs/CANDIDATE_PRECISION_AND_CONTEXT.md) and [docs/AGENTIC_BROWSER.md](docs/AGENTIC_BROWSER.md).

## One-command Azure ML bootstrap

```bash
git clone https://github.com/Akilankm/web_search_tool.git
cd web_search_tool
cp .env.example .env
# Edit only the SerpAPI and LLM values in .env.
./scripts/azureml_startup.sh
```

Then open:

```text
notebooks/01_run_product_evidence.ipynb
```

The repository already contains `inputs/private/toy_features.json`. No feature-file copy, manual Docker command, permission override, or separate notebook dependency setup is required.

The startup script:

- creates runtime, artifact, private-input, and secret directories;
- creates the internal browser API token when absent;
- runs containers as the Azure ML notebook user;
- adapts automatically to Azure ML managed-mount permission behavior;
- validates required fields, feature schema, Docker, Compose, and production controls;
- removes stale Compose resources;
- builds and recreates the browser and agent containers;
- waits for strict health;
- writes `data/runtime/stack_health.json`;
- prints the notebook and artifact locations.

## Required `.env` values

```env
SERPAPI_API_KEY=<organization-provided-value>
LLM_API_KEY=<organization-provided-value>
LLM_API_VERSION=<organization-provided-value>
LLM_ENDPOINT=<organization-provided-value>
LLM_DEPLOYMENT=<organization-provided-value>
```

Equivalent `AZURE_OPENAI_*` names are accepted. LLM values are treated as organization-provided opaque configuration; startup requires them to be present but does not impose key-length or endpoint-format assumptions.

The precision and context controls in `.env.example` should remain unchanged:

```env
PRODUCT_HARNESS_WORKFLOW=three_stage_feature_aware
PRODUCT_HARNESS_MAX_ORGANIC_SEARCHES=3
PRODUCT_HARNESS_MAX_AI_MODE_SEARCHES=0

PRODUCT_HARNESS_MAX_FULL_SCRAPES=6
PRODUCT_HARNESS_MAX_SCRAPES_PER_DOMAIN=2
PRODUCT_HARNESS_MIN_PREFLIGHT_SCORE=0.28
PRODUCT_HARNESS_MAX_CANDIDATE_POOL=90

PRODUCT_HARNESS_ENABLE_BROWSER_SERVICE=true
PRODUCT_HARNESS_ENABLE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_REQUIRE_AGENTIC_BROWSER=true
PRODUCT_HARNESS_MAX_AGENTIC_CANDIDATES=3
PRODUCT_HARNESS_AGENTIC_MAX_TURNS_PER_CANDIDATE=4
PRODUCT_HARNESS_AGENTIC_MAX_ACTIONS_PER_CANDIDATE=6
PRODUCT_HARNESS_AGENTIC_OBSERVATION_CHARS=4000
PRODUCT_HARNESS_AGENTIC_MAX_ELEMENTS=15
PRODUCT_HARNESS_AGENTIC_MAX_IMAGES=8

PRODUCT_HARNESS_REQUIRE_ALL_FEATURES_ON_PRIMARY=true
PRODUCT_HARNESS_REJECT_EXPIRING_URLS=true
```

An existing `.env` with larger legacy browser values remains startup-compatible, but runtime execution and health reporting clamp to the effective hard ceilings of three candidates, four turns, and six actions.

## Included feature schema

A fresh clone includes:

```text
inputs/private/toy_features.json
```

It defines:

- brand;
- manufacturer;
- minimum recommended age.

The notebook uses:

```python
FEATURE_SET = "toy_features"
```

## One URL, one authoritative row

The runtime keeps two intentionally different table grains.

### Raw SERP occurrences

`search.serp_results` and notebook `serp_results_df` retain one row for every search result occurrence. A URL may occur in several searches or positions.

### Canonical candidate decisions

`candidate_records`, `candidate_url_records.json`, `candidates.csv`, and notebook `results_df` contain exactly one row per canonical URL.

Canonicalization removes tracking, campaign, referral, session, and fragment noise while preserving product-defining parameters such as SKU, product ID, EAN, GTIN, and variant.

The candidate record distinguishes:

- `full_scrape_attempted` from `fetch_success`;
- `fetch_success` from `content_extracted`;
- technical acquisition from `scrape_accepted` evidence quality;
- deterministic admission from browser escalation;
- feature completeness from final URL selection.

Every URL ends with one explicit RCA status such as:

```text
SERP_REJECTED_URL_TYPE
SERP_REJECTED_LOW_IDENTITY
QUALIFIED_NOT_SCRAPED_BUDGET
SCRAPE_FAILED
SCRAPE_LOW_UTILITY
IDENTITY_REJECTED
BROWSER_BLOCKED
FEATURE_INCOMPLETE
ELIGIBLE_NOT_SELECTED
REVIEW_SELECTED
STRICT_SELECTED
```

## Progressive acquisition

All three searches share a default six-URL full-scrape budget. Unused capacity rolls forward to later stages, and no domain may consume more than two full scrapes.

Only candidates with a probable product-detail URL, adequate requested-product identity evidence, and sufficient deterministic preflight score are admitted.

A successful HTTP response alone is not considered quality evidence. The runtime separately records:

| Field | Meaning |
|---|---|
| `fetch_success` | The acquisition operation succeeded |
| `content_extracted` | A usable amount of readable content was obtained |
| `product_page_likelihood` | Evidence that this is an individual product detail page |
| `content_utility_score` | Combined usefulness for product identity and requested evidence |
| `scrape_accepted` | Suitable for downstream evidence reasoning |

## Context-efficient agentic browser

The browser is an escalation path for high-potential unresolved candidates, not a second crawler for the complete SERP pool.

The LLM receives:

- only unresolved feature definitions;
- only newly visible text segments after the first turn;
- relevance-ranked specification, details, manufacturer, age, warning, gallery, and similar controls;
- relevance-ranked images;
- at most two compact previous action summaries.

The prompt mode is:

```text
incremental_delta_relevance_filtered
```

The loop stops without another LLM call when all requested features are already resolved.

## Single-product EDA and RCA notebook

After one product completes, the notebook builds compact pandas tables, a Rich executive summary, Matplotlib and Seaborn charts, and an Excel export.

The principal `results_df` is the authoritative one-row-per-canonical-URL table. Drill-down tables retain raw SERP occurrences, feature evidence, browser actions, and LLM plans without bloating the default decision view.

The funnel is reported explicitly:

```text
SERP rows returned
→ canonical candidate URLs
→ admitted for full scrape
→ full scrape attempted
→ scrape accepted for evidence
→ browser admitted
→ browser openable
→ identity accepted
→ feature complete
→ selected
```

The diagnostic workbook is written to:

```text
data/artifacts/<row_id>/single_product_diagnostics.xlsx
```

See [docs/SINGLE_PRODUCT_DIAGNOSTICS.md](docs/SINGLE_PRODUCT_DIAGNOSTICS.md) and [docs/NOTEBOOK_USAGE.md](docs/NOTEBOOK_USAGE.md).

## Final URL acceptance

A top-level `primary_url` is returned only when one investigated URL is:

- browser-openable and not blocked;
- the rendered exact product and variant;
- evidence-quality accepted;
- complete for every requested feature on the same URL;
- free of feature conflicts;
- durable and non-expiring.

Otherwise the workflow completes as `REVIEW_REQUIRED`, keeps `primary_url=null`, and retains the complete candidate RCA.

## Result contract

| Path | Meaning |
|---|---|
| `product.row_id` | Original row identifier |
| `job_status` | `COMPLETED` or `REVIEW_REQUIRED` |
| `coding_ready` | Strict deterministic final acceptance result |
| `primary_url` | Accepted durable URL or `null` |
| `search.stages` | Three-stage search and precision-admission trace |
| `search.serp_results` | Raw SERP occurrence rows |
| `search.precision_policy` | Effective scrape and preflight controls |
| `candidate_records` | Authoritative one-row-per-canonical-URL decisions |
| `agentic_browser.admission_decisions` | Browser eligibility and budget decisions |
| `agentic_browser.context_policy` | Effective incremental context limits |
| `candidate_investigations` | Per-candidate LLM plans and actions |
| `feature_assessments` | Per-URL requested-feature evidence and coverage |
| `evidence_set` | Diagnostic selected-source coverage |
| `primary_url_acceptance` | Authoritative final gate decision |
| `browser_evidence` | Rendered text, screenshots, blockers, and assets |

## Artifacts

```text
data/artifacts/<row_id>/
├── orchestrated_result.json
├── candidate_state.json
├── candidate_url_records.json
├── candidates.csv
├── feature_evidence.csv
├── primary_url_acceptance.json
└── CAND-###/agentic/
```

## Operations

```bash
./scripts/azureml_startup.sh

docker compose ps
docker compose logs -f --tail=200 agent browser

docker compose down
```

## Validation

```bash
python scripts/validate_environment.py --env-file .env
python -m compileall -q src scripts
python -m json.tool inputs/private/toy_features.json >/dev/null
python -m json.tool notebooks/01_run_product_evidence.ipynb >/dev/null
python -m pytest -q
docker compose config --quiet
```

## Documentation

- [Candidate precision and context control](docs/CANDIDATE_PRECISION_AND_CONTEXT.md)
- [Automated Azure ML operations](docs/AZUREML_OPERATIONS.md)
- [Notebook usage and diagnostic contract](docs/NOTEBOOK_USAGE.md)
- [Single-product diagnostic interpretation](docs/SINGLE_PRODUCT_DIAGNOSTICS.md)
- [Enterprise LLM configuration](docs/ENTERPRISE_LLM_CONFIGURATION.md)
- [LLM-controlled agentic browser](docs/AGENTIC_BROWSER.md)
- [Security contract](docs/SECURITY.md)
