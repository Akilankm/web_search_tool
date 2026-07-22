# Product URL Finder — Feature Reference

This is the canonical feature-level reference for the repository.

## Product-result hierarchy

```text
Primary deliverable
= product URL

Acceptance basis
= Source + Evidence + Identity + Usability
```

A strictly verified URL is preferred. When strict gates are incomplete, the strongest real direct non-mismatched URL is delivered for review. Empty URL is an exceptional delivery failure.

---

## 1. Product input contract

**Purpose:** represent one requested product and market context.

**Inputs:** `row_id`, `main_text`, `country_code`, optional `retailer_name`, `ean`, `language_code`, `feature_set`, `runtime_options`.

**Outputs:** validated product payload and artifact identifier.

**Requirement changes:** modify input validation and API payload contracts.

**Primary modules:** `contracts.py`, `agent_service/app.py`, `feature_schema.py`.

---

## 2. Product interpretation

**Purpose:** extract identity dimensions needed to search for and validate the correct URL.

**Processing:** brand, manufacturer, model, series, form, variant, size, quantity, pack and category are separated into explicit, inferred and unresolved claims.

**Outputs:** claims, assumptions, unknowns, constraints and `product_understanding.md`.

**Requirement changes:** modify belief parsing and domain normalization.

**Primary modules:** `belief/contracts.py`, `belief/engine.py`, `belief_runtime.py`.

---

## 3. Product hypothesis construction

**Purpose:** preserve competing product explanations until evidence supports one.

**Outputs:** hypotheses, canonical names, attributes, assumptions, prior/posterior probability, supporting and contradicting evidence IDs.

**Requirement changes:** modify hypothesis generation and ambiguity policy.

**Primary modules:** `belief/contracts.py`, `belief/engine.py`, `belief/artifacts.py`.

---

## 4. Feature schema resolution

**Purpose:** define requested product facts used for URL evidence coverage.

**Default:** `inputs/private/toy_features.json`.

**Outputs:** feature assessments, missing facts and conflicting facts.

**Requirement changes:** update the feature-set JSON or schema loader.

**Primary modules:** `feature_schema.py`, `schema_io.py`, `feature_evidence.py`.

---

## 5. Adaptive source search

**Purpose:** discover direct product URL candidates and evidence.

**Route:** manufacturer → requested retailer/same country → global fallback.

**Special rule:** the final credit recovers a direct merchant or manufacturer URL when none has been collected.

**Outputs:** search stages, queries, handles, candidate URLs and `adaptive_search_trace.json`.

**Requirement changes:** modify engines, query planning, source order or credit limits.

**Primary modules:** `adaptive_search.py`, `adaptive_search_runtime.py`, `query_builder.py`, `three_stage_pipeline.py`.

---

## 6. Candidate normalization and precision filtering

**Purpose:** reject indirect or unusable URLs before expensive acquisition.

**Blocked:** search pages, category pages, homepages, social pages, documents, Google/SerpAPI intermediaries and duplicates.

**Outputs:** canonical URL, source type, precision score, admission status and reasons.

**Requirement changes:** update URL patterns, exclusions and retailer mappings.

**Primary modules:** `candidate_precision.py`, `candidate_store.py`, `candidate_reporting.py`.

---

## 7. Static extraction

**Purpose:** collect product evidence without browser interaction.

**Evidence:** title, identifiers, brand, manufacturer, model, variant, pack, specifications, description, price and image references.

**Outputs:** scrape status, page type, text utility, structured identifiers and richness.

**Requirement changes:** add markup parsers or extraction formats.

**Primary modules:** `scraper.py`, `offline_capture.py`, `rendered_page.py`.

---

## 8. Rendered browser investigation

**Purpose:** verify candidates whose evidence requires rendering or interaction.

**Actions:** open, scroll, expand safe product sections, inspect images and capture screenshots.

**Outputs:** browser evidence, final URL, visible text, screenshots and action trace.

**Requirement changes:** modify allowed actions, blockers or browser limits.

**Primary modules:** `browser_service/controller.py`, `browser_client.py`, `llm/agentic_browser.py`.

---

## 9. Multimodal evidence reasoning

**Purpose:** resolve identity and requested facts visible in packaging, screenshots or galleries.

**Trace:** `extraction_method=vision_llm`, `evidence_location=visual_asset:<asset_id>`.

**Outputs:** visual facts and asset provenance.

**Requirement changes:** add visual evidence types or reasoning policy.

**Primary modules:** `llm/vision_reasoner.py`, `llm/agentic_browser.py`, `business_judgement_artifact.py`.

---

## 10. Evidence ledger

**Purpose:** store atomic supporting, contradicting and neutral evidence.

**Outputs:** field, value, polarity, affected hypothesis, source reliability, extraction confidence, hard-conflict marker and excerpt.

**Requirement changes:** change evidence weighting or provenance requirements.

**Primary modules:** `belief/contracts.py`, `belief/engine.py`, `belief/artifacts.py`.

---

## 11. Hypothesis scoring and product resolution

**Purpose:** determine which product a candidate URL must represent.

**ResolutionStatus:** `EXACT`, `PROBABLE`, `AMBIGUOUS`, `CONFLICTING`, `INSUFFICIENT_EVIDENCE`.

**Outputs:** leading hypothesis, confidence, posterior margin, unresolved distinctions and contradictions.

**Requirement changes:** modify scoring thresholds or terminal identity semantics.

**Primary modules:** `belief/engine.py`, `belief_runtime.py`, `identity_verifier.py`.

---

## 12. Exact-product identity verification

**Purpose:** prevent sibling products, wrong forms, variants, sizes or packs from being delivered.

**Hard rule:** confirmed wrong product, confirmed wrong variant and EAN conflict are never eligible for verified or review URL delivery.

**Outputs:** identity status, conflicts, rejection reasons and verified claims.

**Requirement changes:** update critical identity fields or conflict policy.

**Primary modules:** `identity_verifier.py`, `mandatory_url_identity_safety.py`, `precision_selection_hardening.py`.

---

## 13. Requested-feature coverage

**Purpose:** assess how completely a URL supports downstream product facts.

**Outputs:** coverage, missing features, conflicting features and feature assessments.

**Delivery effect:** incomplete non-identity coverage may produce a review URL; it does not force an empty result when a usable direct URL exists.

**Requirement changes:** update feature definitions or coverage policy.

**Primary modules:** `feature_evidence.py`, `feature_schema.py`, `strict_acceptance.py`.

---

## 14. URL durability and usability

**Purpose:** determine whether a URL can be opened, extracted and reused.

**Checks:** browser openable, text extractable, direct product page, exact identity, requested evidence and non-expiring URL.

**Outputs:** strict gate results and review warnings.

**Requirement changes:** modify expiry detection, browser criteria or extraction thresholds.

**Primary modules:** `url_durability.py`, `production_url.py`, `strict_acceptance.py`.

---

## 15. Source-authority selection

**Purpose:** prefer stronger sources after identity and usability evaluation.

**Order:** manufacturer → requested retailer/same-country retailer → other local → global → marketplace.

**Outputs:** source role, tier, manufacturer URL, retailer URL and selection reason.

**Requirement changes:** update source tiers or market-specific authority rules.

**Primary modules:** `source_authority.py`, `manufacturer_primary_runtime.py`, `manufacturer_primary_hardening.py`.

---

## 16. Strict URL selection

**Purpose:** deliver a production-ready URL when every strict gate passes.

**Output:** `URL_DELIVERED_VERIFIED` with `url_delivery.strictly_verified=true`.

**Requirement changes:** modify strict production gates only through governed acceptance policy.

**Primary modules:** `strict_acceptance.py`, `mandatory_url_policy.py`.

---

## 17. Best-available review URL recovery

**Purpose:** prevent avoidable empty results when a real direct non-mismatched product candidate exists.

**Candidate sources:** result URL fields, candidate records, feature assessments, browser evidence, browser investigations, SERP results, `candidate_url_records.json`, `candidate_state.json`.

**Ranking:** prior selection, identity, source authority, browser usability, extraction quality, coverage, confidence and search position.

**Output:** `URL_DELIVERED_REVIEW_REQUIRED` and `url_delivery_recovery` metadata.

**Requirement changes:** modify recovery sources, mismatch exclusions or ranking weights.

**Primary modules:** `url_delivery_recovery.py`, `mandatory_url_policy.py`, `candidate_reporting.py`.

---

## 18. Structured no-safe-URL outcome

**Purpose:** record an exceptional delivery failure when no non-mismatched direct product candidate exists.

**Output:** `URL_DELIVERY_FAILED`, structured resolution artifact and escalation instructions.

This is not a successful business result.

**Requirement changes:** change only exceptional failure semantics; do not use this path when a review URL exists.

**Primary modules:** `structured_no_url_outcome.py`, `url_delivery_summary_runtime.py`.

---

## 19. Business judgment sequence

**Purpose:** make the URL decision auditable.

**Sequence:** observable evidence → explicit rule → URL/product judgment → next action.

**Output:** `business_judgement_review.md`.

**Requirement changes:** update decision-stage schema or human comparison protocol.

**Primary modules:** `business_judgement_artifact.py`, `business_judgement_runtime.py`.

---

## 20. Per-job runtime controls

**Purpose:** vary investigation depth without changing identity safety.

**Profiles:** `Focused`, `Standard`, `Extended`.

**Output:** `run_configuration.json`.

**Requirement changes:** update bounded controls and environment mapping.

**Primary modules:** `runtime_controls.py`, `runtime_controls_runtime.py`.

---

## 21. Product Identification Platform UI

The canonical application is `apps/product_evidence_ui.py`. Its product name is **Product URL Finder**.

**Default view:** URL, Source, Evidence, Identity, Usability and brief justification.

**Collapsed view:** candidates, evidence, search, identity, decision audit and artifacts.

**Requirement changes:** modify UI composition without duplicating backend search or selection logic.

---

## 22. Batch execution

**Purpose:** resolve many products while preserving one URL result and artifact set per row.

**Outputs:** batch results, failures, artifact index and metrics.

**Primary modules:** `batch_notebook_runtime.py`, `notebooks/02_batch_products.ipynb`.

---

## 23. Artifact diagnostics

**Purpose:** inspect a completed product run offline.

**Outputs:** interactive HTML, Markdown report and workbook.

**Primary modules:** `artifact_diagnostics.py`, `notebooks/03_artifact_diagnostics.ipynb`.

---

## 24. Artifact inventory

```text
executive_summary.json
run_configuration.json
product_belief.json
product_understanding.md
evidence_ledger.jsonl
adaptive_search_trace.json
candidate_url_records.json
candidate_state.json
candidates.csv
business_judgement_review.md
source_selection.json
primary_url_acceptance.json
mandatory_url_delivery.json
orchestrated_result.json
```

---

## 25. Change-impact index

| Requirement change | Primary location |
|---|---|
| Input fields | `contracts.py`, `agent_service/app.py` |
| Search route or queries | `adaptive_search.py`, `query_builder.py` |
| Candidate exclusions | `candidate_precision.py` |
| Product/variant identity | `identity_verifier.py`, `mandatory_url_identity_safety.py` |
| Strict URL gates | `strict_acceptance.py` |
| Review URL recovery | `url_delivery_recovery.py` |
| Source authority | `source_authority.py`, manufacturer policy modules |
| Terminal summary | `executive_summary.py`, `url_delivery_summary_runtime.py` |
| UI | `apps/product_evidence_ui.py` |
| Runtime compatibility | `runtime_contract.py` |
