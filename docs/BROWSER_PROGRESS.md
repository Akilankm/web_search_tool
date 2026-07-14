# Browser Candidate Progress

The supported notebook reports browser verification at candidate level.

Example:

```text
TEST-001-...: RUNNING | REQUESTING_BROWSER_EVIDENCE | CAND-001 | attempt 1/3 | STARTED | mercadolibre.com.co
TEST-001-...: RUNNING | REQUESTING_BROWSER_EVIDENCE | CAND-001 | COMPLETED | openable=True | scrapable=True | rendered_exact=True | 18.4s | mercadolibre.com.co
TEST-001-...: RUNNING | REQUESTING_BROWSER_EVIDENCE | CAND-002 | RETRYING | attempt 1/3 failed with ReadTimeout after 180.0s | retailer.example
TEST-001-...: RUNNING | REQUESTING_BROWSER_EVIDENCE | CAND-002 | FAILED | 3/3 attempts | ReadTimeout | 180.0s | retailer.example
```

## Notebook behavior

The notebook polls the job API every three seconds but prints only when `status`, `stage`, or `message` changes. When a browser request remains active, it prints one heartbeat every 30 seconds with total elapsed time instead of repeating the same line every poll.

## Meaning of fields

| Field | Meaning |
|---|---|
| `CAND-001` | Candidate sequence identifier for the current product run |
| `attempt 1/3` | Current browser-service request attempt and configured maximum |
| `STARTED` | Browser request has been submitted |
| `RETRYING` | A transport, timeout, HTTP, or response-decoding error occurred and another attempt will be made |
| `COMPLETED`, `PARTIAL`, `ACCESS_BLOCKED`, `FAILED` | Browser evidence bundle status |
| `openable` | Browser successfully opened the page |
| `scrapable` | Rendered product text was extractable |
| `rendered_exact` | Rendered page matched the requested product identity |
| elapsed seconds | Duration of the current attempt |
| domain | Candidate domain only; query parameters and tokens are never printed |

Candidate failures do not fail the complete product workflow. The orchestrator continues with the next candidate and performs strict final URL acceptance after browser verification finishes.

## Operational diagnosis

Use the notebook output first. For deeper inspection:

```bash
docker compose logs -f --tail=200 agent browser
```

A 30-second heartbeat means the current browser request is still active. A `RETRYING` message means the client is using its configured retry allowance. A terminal candidate `FAILED` message means that candidate was abandoned and the workflow moved to the next candidate.
