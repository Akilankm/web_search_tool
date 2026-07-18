# Belief-Driven Product Resolution

## Objective

Resolve the most probable real-world consumer product represented by vendor `MAIN_TEXT`, then return the best direct product-detail URL through a bounded market search.

```text
observe vendor data
→ form explicit claims and competing hypotheses
→ measure uncertainty
→ choose a discriminative evidence action
→ search and scrape
→ update beliefs
→ correct the path
→ validate the final URL
```

## Offline interpretation

Before any paid search, deterministic code extracts model/SKU-like tokens, user-provided GTIN context, measurements, product-form terms, colours, variants, quantities, pack expressions, language/edition terms, country, and retailer constraints.

The configured LLM receives only the input and deterministic identity graph. It has no internet evidence at this stage. It returns structured hypotheses, assumptions, negative constraints, and unknowns—not a final asserted fact.

Claims carry explicit epistemic status such as `EXPLICIT`, `DETERMINISTICALLY_DERIVED`, `INFERRED_FROM_TEXT`, `MODEL_MEMORY_PRIOR`, `WEB_SUPPORTED`, `WEB_VERIFIED`, `CONFLICTING`, or `UNKNOWN`. Model memory never becomes web evidence automatically.

## Hypotheses and metrics

The runtime creates two to five product hypotheses when ambiguity exists, including consumer unit versus vendor case, refill versus primary product, accessory versus compatible device, product-form ambiguity, and regional model differences.

It records:

- parse coverage;
- identity completeness;
- ambiguity entropy;
- assumption burden;
- search readiness;
- posterior margin;
- decision-critical uncertainties.

Probabilities are mechanically normalized and updated from evidence; they are not copied from uncalibrated LLM confidence.

## Immutable market path

```text
requested retailer, when supplied
→ alternative retailer in requested country
→ global fallback
```

Without a retailer, the path begins in the requested-country market and then proceeds to global fallback. A stage advances only when the previous market did not produce a production-ready exact URL.

## Atomic evidence

Every scraped or rendered page produces individual evidence records for reachability, product-page classification, title, brand/manufacturer, structured GTIN, exact-product verification, variant status, quantity/pack status, and content richness.

A URL is not evidence by itself; claims extracted from the page are evidence.

After each page, the system updates hypothesis scores, applies hard penalties for wrong product/model/variant/pack/EAN conflicts, recalculates probabilities and uncertainty, and persists a belief snapshot.

## Final URL selection

Product identity and URL quality are separate decisions:

```text
winning product hypothesis
× exact identity match
× browser openability
× product-page classification
× information richness
× requested retailer/country/global scope
× durability
= final URL eligibility
```

A rich sibling-product page cannot win. A correct but inaccessible or information-poor page cannot be promoted as production-ready.

## Stopping policy

Search stops early only when the current market produces a direct URL that is browser-openable, highly scrapable, information-rich, exact-product verified, free of hard conflicts, and accepted by the production URL gate.

## Artifacts

```text
product_belief.json
product_understanding.md
market_decision_path.md
belief_updates.md
evidence_ledger.jsonl
```

These observable artifacts complement the candidate CSV and final URL output. They do not expose hidden chain-of-thought.
