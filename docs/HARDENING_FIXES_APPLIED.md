# Product-grade hardening fixes applied

This patch addresses the main gaps found during the repository retrospective.

## Fixed

1. **True global fallback execution**
   - SerpAPI calls now receive explicit `scope` and `language_code` from planner actions.
   - `scope=global` omits country `gl` and location, so global fallback is no longer country-biased.

2. **LLM adjudication inside the loop**
   - Added `LLM_EXACT_ADJUDICATION` action.
   - The loop can now judge scraped candidates before termination; failed/insufficient judgements can trigger repair/global fallback.

3. **LLM budget discipline**
   - Search planning/feedback keeps budget for adjudication.
   - Adjudication is available as a loop action instead of only a post-loop action.

4. **Hard rejected candidates are not product URLs by default**
   - `product_url` is not populated from a hard-rejected sibling/wrong variant unless explicitly enabled.
   - Such URLs are surfaced as `best_reference_url` for audit/review.

5. **EAN scientific notation safety**
   - Scientific notation EAN values are no longer silently recovered into potentially wrong GTINs.
   - A warning is emitted and the value is not used for exact matching.

6. **Source-aware GTIN extraction**
   - Scraper now uses JSON-LD, spec tables, attributes, and labelled visible text for GTIN evidence.
   - Unlabelled arbitrary digit regex matches are no longer promoted as structured EAN evidence.

7. **Thread safer batch runner**
   - Batch runner now builds one harness per worker call to avoid shared crawler/session state.
   - Input/output paths and worker count are CLI arguments, not hardcoded.

8. **Config externalization started**
   - Product identity taxonomy moved to `configs/product_identity_taxonomy.json` and can be overridden by env var.
   - Page-type signal config added for productization.

9. **Country profile coverage expanded**
   - Added CO, GB, DE, FR, IT, ES, PL, NL, BE, AT, CA, AU profiles.

10. **Candidate lifecycle strengthened**
   - Scorecards now update candidate lifecycle to stages such as `RANKED_FOR_SCRAPE`, `REJECTED_VARIANT_MISMATCH`, `PROMOTED_FOR_LLM`, etc.

## Remaining production considerations

- Add a persistent cache for SerpAPI, scrape, LLM plan, LLM judgement, and image downloads.
- Add batch-level global QPS/cost budget enforcement.
- Upgrade HTML extraction to a full plugin extractor stack with BeautifulSoup/lxml when approved.
- Add domain-level scrape throttling for very large batches.
