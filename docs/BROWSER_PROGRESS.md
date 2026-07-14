# Agentic Browser Candidate Progress

The supported notebook reports the LLM-controlled browser investigation at candidate and turn level.

Example:

```text
TEST-001-...: RUNNING | AGENTIC_BROWSER_INVESTIGATION | LLM-investigating 12 candidate URLs with observe-plan-act browser sessions
TEST-001-...: RUNNING | AGENTIC_BROWSER_INVESTIGATION | CAND-001 | turn 0/10 | OBSERVED | retailer.example
TEST-001-...: RUNNING | AGENTIC_BROWSER_INVESTIGATION | CAND-001 | turn 1/10 | CLICK | retailer.example
TEST-001-...: RUNNING | AGENTIC_BROWSER_INVESTIGATION | CAND-001 | turn 2/10 | SCROLL | retailer.example
TEST-001-...: RUNNING | AGENTIC_BROWSER_INVESTIGATION | CAND-001 | turn 3/10 | INSPECT_IMAGE | retailer.example
TEST-001-...: RUNNING | AGENTIC_BROWSER_INVESTIGATION | CAND-001 | COMPLETED | turns=4 | actions=3 | openable=True | scrapable=True | retailer.example
```

## Notebook behavior

The notebook polls every three seconds but prints only when `status`, `stage`, or `message` changes. When an LLM or browser operation remains active, it prints one heartbeat every 30 seconds with total elapsed time.

## Meaning of fields

| Field | Meaning |
|---|---|
| `CAND-001` | Candidate identifier for the current product run |
| `turn 2/10` | Current LLM planning turn and configured maximum |
| `OBSERVED` | Initial browser state is available to the LLM |
| `CLICK` | LLM selected one currently observed `E###` element |
| `SCROLL` | LLM selected a bounded page scroll |
| `INSPECT_IMAGE` | LLM selected one currently observed `I###` image for evidence |
| `CAPTURE_SCREENSHOT` | LLM preserved the current viewport as evidence |
| `COMPLETED` | Candidate session finalized into a browser evidence bundle |
| `openable` | Chromium opened a usable rendered page |
| `scrapable` | Sufficient rendered text was extracted |
| domain | Domain only; query parameters, tokens, and credentials are not printed |

The LLM action is a plan, not the final URL decision. Every action is checked against the current observation before execution. The final URL is still selected by deterministic identity, feature, access, scrapability, conflict, durability, and scope-priority gates.

## Candidate failure isolation

A candidate may fail because of:

- browser timeout or transport failure;
- invalid or stale LLM-selected element ID;
- access blocker;
- invalid LLM JSON;
- exhausted turn or action budget.

That failure is recorded in:

```text
data/artifacts/<row_id>/CAND-###/agentic/investigation.json
```

The workflow continues to the next admitted candidate.

## Operational diagnosis

```bash
docker compose logs -f --tail=200 agent browser
find data/artifacts/<row_id> -maxdepth 8 -type f | sort
```

A 30-second heartbeat means the current LLM or browser call remains active. Inspect `investigation.json`, `latest_observation.json`, and `browser_actions.json` to distinguish model planning, browser execution, and deterministic final acceptance.
