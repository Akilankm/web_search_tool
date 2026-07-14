# LLM-Controlled Agentic Browser

## Purpose

The browser stage behaves like a careful human analyst. For every deduplicated candidate URL retained by the bounded discovery pool, the agent repeatedly:

1. observes the current rendered page;
2. asks the LLM to plan one safe evidence-seeking action;
3. executes that action in an isolated Chromium context;
4. observes the changed page;
5. continues until the candidate is resolved or its budget is exhausted.

The LLM controls investigation strategy. Deterministic code still controls safety, evidence validation, and final URL acceptance.

## Architecture

```text
Notebook
  -> Agent API
      -> Three deterministic SerpAPI searches
      -> Candidate merge, deduplication, preflight and scoring
      -> For every retained candidate:
           AgenticBrowserInvestigator
             -> Browser session start
             -> Observe page + viewport screenshot
             -> LLM next-action plan
             -> Safe browser tool execution
             -> Updated observation
             -> repeat
             -> Browser evidence bundle
      -> Deterministic identity and feature validation
      -> StrictPrimaryURLSelector
      -> COMPLETED or REVIEW_REQUIRED
```

## Agent and browser responsibilities

| Component | Responsibility |
|---|---|
| Agent | Owns the LLM, objective, feature schema, turn budget, planning history, candidate dossiers, deterministic validation, final selection |
| Browser service | Owns Playwright/Chromium, isolated sessions, DOM observation, safe action execution, screenshots, rendered text, browser evidence files |
| LLM | Selects the next safe action from the current observation and explains why it is useful |
| Strict selector | Accepts a URL only after all non-negotiable gates pass |

The browser container never receives SerpAPI or LLM credentials.

## Observation provided to the LLM

Every turn can include:

- current URL;
- page title;
- visible product name;
- bounded rendered text;
- current viewport screenshot;
- observed interactive elements with stable `E###` IDs;
- observed images with stable `I###` IDs;
- blockers and warnings;
- actions already used and remaining budget;
- product identity;
- requested feature definitions and allowed values;
- recent LLM plans.

Webpage text is untrusted evidence. The system prompt instructs the model to ignore page-level prompt injection and never treat retailer content as policy or tool instructions.

## Allowed actions

The LLM may choose exactly one action per turn:

| Action | Constraint |
|---|---|
| `click` | Must reference a currently observed `E###` element |
| `scroll` | Direction must be `up`, `down`, `top`, or `bottom` |
| `inspect_image` | Must reference a currently observed `I###` image |
| `capture_screenshot` | Captures the current viewport as evidence |
| `finish` | Stops when the candidate is resolved, blocked, wrong, or no action can improve evidence |

The execution layer independently rejects:

- invented or direct URL navigation;
- stale or invented element IDs;
- cross-site navigation;
- login, account, upload, cart, checkout, order, subscription, or payment actions;
- typing and file uploads;
- JavaScript or arbitrary code execution;
- CAPTCHA, bot-detection, authentication, or access-control bypass.

## Candidate coverage

The three searches can retain up to 90 merged and deduplicated candidates under the production candidate-pool contract. The default agentic limit is also 90, so every URL retained by that pool receives an investigation.

```env
PRODUCT_HARNESS_MAX_CANDIDATE_POOL=90
PRODUCT_HARNESS_MAX_AGENTIC_CANDIDATES=90
PRODUCT_HARNESS_AGENTIC_MAX_TURNS_PER_CANDIDATE=10
PRODUCT_HARNESS_AGENTIC_MAX_ACTIONS_PER_CANDIDATE=20
```

The cap protects against unbounded external search output. Lowering it deliberately changes the workflow from full retained-pool investigation to top-N investigation. Increasing turns or candidates can materially increase LLM cost and runtime.

## Evidence and trust boundary

The LLM plan and candidate assessment are retained for audit, but the LLM does not directly approve the final URL.

After the session ends, deterministic code independently checks:

- browser-openable;
- access not blocked;
- rendered page is product-like;
- exact requested product and variant;
- text scrapability;
- every requested feature supported on the same URL;
- no conflicting feature evidence;
- durable URL without transient credentials, sessions, signatures, or expiry parameters.

Only candidates that pass every gate enter the accepted pool. Scope priority then prefers:

1. requested retailer in requested country;
2. another retailer in requested country;
3. global fallback.

## Per-candidate artifacts

```text
data/artifacts/<row_id>/CAND-###/agentic/
├── investigation.json
├── latest_observation.json
├── rendered_text.md
├── final_page.html
├── browser_actions.json
├── browser_result.json
├── visual_manifest.json
├── observations/
├── images/
└── screenshots/
```

`investigation.json` records LLM plans, turns, executed actions, termination reason, final model assessment, and errors. `browser_actions.json` is the authoritative executed-action trace.

## Result fields

```python
result["agentic_browser"]
result["candidate_investigations"]
result["browser_evidence"]
result["feature_assessments"]
result["primary_url_acceptance"]
```

`candidate_investigations` is explanatory and auditable. `primary_url_acceptance` remains the authoritative final decision.

## Failure semantics

A candidate-level LLM or browser failure is isolated to that candidate. The agent records the failure and continues to the next retained candidate.

- `COMPLETED`: one candidate passed all strict gates.
- `REVIEW_REQUIRED`: the workflow completed but no candidate passed all strict gates.
- `FAILED`: the overall job could not execute, such as invalid configuration or unavailable required services.
