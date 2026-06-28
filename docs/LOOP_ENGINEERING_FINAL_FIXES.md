# Loop Engineering Final Fixes

This build intentionally moves the harness away from a linear `plan -> search -> scrape -> judge -> output` shape.

## Main correction

The planner now prioritizes evidence feedback after every useful action:

```text
LLM identity/search plan
  -> SerpAPI search
  -> candidate pool update
  -> crawl4ai scrape of best current candidate
  -> deterministic detectors/scorecards
  -> LLM exact-product judgement inside the loop
  -> LLM search repair when evidence is weak/wrong
  -> SerpAPI search again
  -> repeat until exact URL or budget exhaustion
```

## Changes applied

1. **Search no longer drains all planned queries before scraping.**
   After the first search creates candidates, the planner scrapes the best current candidate so evidence can drive the next action.

2. **LLM adjudication happens inside the loop.**
   A rejected/insufficient judgement can trigger search repair in the same run.

3. **LLM feedback queries are prioritized over stale candidates.**
   If the LLM diagnoses wrong variants or weak evidence, repaired queries are executed before scraping lower-quality old candidates.

4. **LLM budget keeps a final adjudication reserve.**
   Search feedback cannot consume the last LLM call unless an exact candidate has already been accepted.

5. **Run outputs expose loop behavior.**
   `queries.csv` now includes `loop_phase` and `repair_reason`; `run_summary.json` includes loop/search/scrape/judge/repair/global iteration counts.

6. **Global fallback remains execution-level global.**
   Global queries execute without country `gl` bias in SerpAPI params.

## How to verify looping

Inspect these outputs per row:

- `queries.csv`: should show `loop_phase` such as `country_search`, `repair_search`, `global_fallback_search`.
- `actions.csv`: should show repeated `organic_search -> scrape_url -> llm_exact_adjudication -> llm_search_feedback -> organic_search` cycles for difficult rows.
- `run_summary.json`: check `repair_cycles`, `judge_iterations`, and `global_search_iterations`.

