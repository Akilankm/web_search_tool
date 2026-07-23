# Notebook-first release gates

## Release invariant

A delivered URL must satisfy:

- exact product and edition identity;
- supplied EAN, GTIN, or ISBN verification when applicable;
- no conflicting identifier;
- direct durable product page;
- local Playwright accessibility;
- scrapable rendered product content;
- source ranking only after all mandatory gates pass.

A candidate that fails any mandatory gate must not be emitted as `VERIFIED` or `REVIEW_REQUIRED`.

## Repository simplicity gate

The supported release must contain:

- the core `product_url_v2` package;
- `notebooks/01_resolve_one_product.ipynb`;
- `notebooks/02_resolve_csv_batch.ipynb`;
- configuration, feature sets, samples, tests, and documentation.

The supported release must not contain:

- Streamlit or FastAPI runtime dependencies;
- Docker Compose;
- service Dockerfiles;
- UI, API, or browser-service modules;
- port-resolution scripts;
- `nest_asyncio`;
- monkey patches or compatibility wrappers.

## Notebook gates

CI must:

1. parse every `.ipynb` with `nbformat`;
2. validate the notebook schema;
3. compile every Python code cell;
4. confirm both supported notebook names exist;
5. reject service startup and monkey-patch references;
6. verify the notebooks call `ProductURLOrchestrator` and `evaluate_acceptance` directly.

## Regression cases

The suite must continue to prove:

1. conflicting URL-path identifiers are rejected;
2. search snippets cannot prove final identity;
3. inaccessible pages are not delivered;
4. browser failures are not delivered;
5. non-scrapable pages are not delivered;
6. wrong editions are rejected;
7. exact retailers can recover when manufacturers lack the edition;
8. exact manufacturers outrank exact retailers;
9. browser-rendered identity can recover incomplete HTTP evidence;
10. local browser calls work from an already-running asyncio loop without patching it.

## Validation command

```bash
python -m pip install -e '.[dev]'
./scripts/validate_release.sh
```
