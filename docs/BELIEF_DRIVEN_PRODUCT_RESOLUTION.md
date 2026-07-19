# Belief-Driven Product Resolution

## Objective

Resolve the most probable real-world consumer product represented by vendor `MAIN_TEXT`, then return the strongest direct product-detail URL through a bounded manufacturer-first search.

```text
observe vendor data
→ form explicit claims and competing hypotheses
→ measure uncertainty
→ choose a discriminative evidence action
→ search and scrape
→ update beliefs
→ correct the path
→ validate requested features and URL quality
→ apply source authority
→ deliver primary, manufacturer, and retailer URLs
```

## Offline interpretation

Before any paid search, deterministic code extracts:

- model, SKU, and item tokens;
- user-provided GTIN/EAN context;
- measurements;
- product-form terms;
- colours and variants;
- quantities and pack expressions;
- language and regional edition terms;
- country and retailer constraints.

The configured LLM receives only the input and deterministic identity graph. It has no internet evidence at this stage. It returns structured hypotheses, assumptions, negative constraints, and unknowns—not a final asserted fact.

Claims carry explicit epistemic status such as:

```text
EXPLICIT
DETERMINISTICALLY_DERIVED
INFERRED_FROM_TEXT
MODEL_MEMORY_PRIOR
WEB_SUPPORTED
WEB_VERIFIED
CONFLICTING
UNKNOWN
```

Model memory never becomes web evidence automatically.

## Hypotheses and metrics

The runtime creates competing hypotheses when ambiguity exists, including:

- consumer unit versus vendor case;
- refill versus primary product;
- accessory versus compatible device;
- product-form ambiguity;
- sibling model or edition;
- regional variant;
- quantity or pack interpretation.

It records:

- parse coverage;
- identity completeness;
- ambiguity entropy;
- assumption burden;
- search readiness;
- posterior margin;
- decision-critical uncertainties.

Probabilities are mechanically normalized and updated from evidence. They are not copied from uncalibrated LLM confidence.

## Final source route

```text
Credit 1: manufacturer_primary
Credit 2: requested_retailer_country when retailer_name is supplied
          otherwise country_alternative
Credit 3: global_fallback
```

This is not a rule that manufacturer pages win automatically. It is a search and evaluation order.

A manufacturer page becomes primary only after it passes exact identity, browser, requested-feature, scrapability, and durability gates.

A retailer found during credit 1 is retained as commercial evidence but cannot prematurely stop the manufacturer evaluation.

## Atomic evidence

Every scraped or rendered page produces individual evidence records for:

- reachability and access state;
- product-page classification;
- visible title and product name;
- brand and manufacturer;
- structured GTIN/EAN;
- exact-product verification;
- product form;
- model and variant;
- size, quantity, and pack;
- requested feature values;
- content richness and utility;
- URL durability.

A URL is not evidence by itself. Claims extracted from the page are evidence.

After each page, the system updates hypothesis scores, applies hard penalties for wrong product/model/variant/pack/EAN conflicts, recalculates probabilities and uncertainty, and persists a belief snapshot.

## Product truth versus commerce

The final system preserves:

```text
manufacturer_url = strongest qualified official source
retailer_url     = strongest qualified commercial source
primary_url      = strongest product-truth source
```

Manufacturer authority is valuable for:

- official product naming;
- specifications;
- warnings and age guidance;
- dimensions and materials;
- compatibility;
- official feature definitions.

Retailer evidence is valuable for:

- price;
- availability;
- local assortment;
- market and language;
- purchase context.

## Final URL eligibility

```text
winning product hypothesis
× exact identity and variant match
× browser openability
× individual product-page classification
× text scrapability and information richness
× requested feature completeness
× URL durability
× source authority
= final URL eligibility
```

A rich sibling-product page cannot win. An official category page cannot win. A correct but inaccessible or feature-incomplete manufacturer page cannot displace a qualified retailer page.

## Manufacturer fallback rule

A retailer becomes `primary_url` when the manufacturer page is:

- not found;
- inaccessible or blocked;
- not an individual product page;
- not text-scrapable;
- the wrong product, model, variant, form, size, quantity, or pack;
- missing requested feature evidence;
- transient or expiring.

Retailer fallback is a deliberate production decision, not a failed search.

## Stopping policy

Search stops early only when the current stage produces a direct URL that passes the gates applicable to that stage.

In particular:

- credit 1 stops only for a strictly qualified manufacturer page;
- a retailer discovered during credit 1 does not stop the search;
- credit 2 may stop for a strictly qualified retailer when no qualified manufacturer page exists;
- credit 3 is the final global exact-product fallback.

## Stable outputs

```text
product_identification
primary_url
primary_url_role
manufacturer_url
retailer_url
source_selection
search.market_decision_path
url_delivery
```

## Artifacts

```text
product_belief.json
product_understanding.md
market_decision_path.md
belief_updates.md
evidence_ledger.jsonl
source_selection.json
```

These observable artifacts complement the candidate CSV, browser evidence, and final URL output. They do not expose hidden chain-of-thought.
