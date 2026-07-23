# Canonical product URL acceptance contract

## Authority

`src/product_url_v2/policy.py` is the only authoritative final URL decision module.

The notebook, search, acquisition, browser, evaluation, trace, and artifact layers cannot independently declare a candidate successful.

## Mandatory gates

A candidate is eligible only when all gates pass:

| Gate | Required result |
|---|---|
| Exact identity | `EXACT` |
| Supplied identifier | Verified, or `NOT_REQUIRED` when absent |
| Direct product page | `PASS` |
| Durable URL | `PASS` |
| Rendered browser | `PASS` |
| Scrapable rendered content | `PASS` |
| Identity conflicts | None |

## Terminal statuses

| Status | Meaning |
|---|---|
| `VERIFIED` | Mandatory gates and downstream coding evidence pass |
| `REVIEW_REQUIRED` | Mandatory URL gates pass; only secondary evidence needs review |
| `FAILED` | No candidate passes the mandatory URL contract |
| `TECHNICAL_FAILURE` | An operational defect prevents a valid decision |

`FAILED` and `TECHNICAL_FAILURE` must not contain a selected URL.

## Source hierarchy

After eligibility is established, source preference is:

1. local manufacturer or publisher;
2. global manufacturer or publisher;
3. requested retailer;
4. country retailer;
5. global retailer;
6. marketplace.

Authority never overrides product identity. A manufacturer page for the wrong edition is rejected.

## Browser evidence

Local Playwright is mandatory by default. It runs directly inside the notebook process.

The implementation does not use `nest_asyncio` or alter the Jupyter event loop. A dedicated worker thread owns the Playwright event loop when the notebook kernel already has one running.

## Observable evidence

The notebooks expose:

- submitted constraints;
- extracted identity signals;
- each paid search action;
- candidate URLs and acquired evidence;
- browser final URL and screenshot;
- every acceptance gate;
- final selection or rejection reasons.

This is an observable decision trace, not hidden chain-of-thought.
