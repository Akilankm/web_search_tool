# Notebooks

- `01_resolve_one_product.ipynb`: inspect one product in detail.
- `02_resolve_csv_batch.ipynb`: validate and resolve a CSV batch.

Both notebooks import the same single resolver module and use native top-level `await`.

The only mandatory input fields are `main_text` and `country_code`. `ean` and `retailer_name` are optional.

Budgets are visible in the notebook and enforced by the resolver.
