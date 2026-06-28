# Retrospective gaps fixed in this build

This build tightens the product-grade Exact Product Discovery Engine after reviewing the prior output behavior.

## Gap 1 — LLM planning was not feeding the exactness engine

The previous flow let the LLM create search plans, but deterministic detectors still used only the raw input text. This meant the LLM could correctly expand or interpret the product, while the verifier/ranker did not benefit from that interpretation.

**Fix:** after every successful LLM search plan or feedback plan, the harness rebuilds the `ProductIdentityGraph` using the LLM plan. The same graph is now passed into `ProductIdentityVerifier` during scrape verification.

## Gap 2 — model/set/SKU identifiers were too weak

Pure numeric model/set identifiers such as `41731`, `75313`, or long SKU-like tokens were previously not treated as hard identity terms. This could let sibling products pass based on broad title overlap.

**Fix:** the identity graph now extracts `model_or_series_terms` and the detector framework applies a `model_identifier_detector`. Missing or conflicting model/set/SKU-like terms are hard blockers for verified exact matches.

## Gap 3 — repair queries could drift toward wrong variants

Earlier repair logic used the best scraped candidate title as a search clue. If the best scraped candidate was a wrong variant, repair queries could drift toward the wrong product.

**Fix:** repair queries now start from the requested product identity graph: expanded product name, model terms, must-match terms, variant terms, product-form terms, and input EAN. Wrong page terms are used only as negative constraints such as `-A4` or `-Bastelpapier` when detector conflicts are present.

## Gap 4 — only one feedback cycle was possible

Hard cases often need one country repair and one global fallback repair. A single LLM feedback round was too limiting.

**Fix:** added `PRODUCT_HARNESS_LLM_SEARCH_FEEDBACK_MAX_ROUNDS`, defaulting to `2`, while preserving the total `PRODUCT_HARNESS_LLM_MAX_CALLS_PER_PRODUCT` budget.

## Gap 5 — selected language metadata could be blank for LLM-planned queries

LLM-generated queries did not always carry language metadata into output files.

**Fix:** LLM planned queries now receive language metadata from the active country profile, allowing `best_url.csv` and `candidates.csv` to show selected language information more reliably.

## Guardrails retained

- EAN remains user-provided only. The LLM may use it, but must not invent, correct, or suggest EAN/GTIN values.
- crawl4ai scrape evidence remains mandatory before verified exact selection.
- Hard variant/model/product-form conflicts cannot become `verified_exact_url`.
- `best_available_url` can still be returned for operational completeness, but rejected/weak candidates remain marked as review-needed.
