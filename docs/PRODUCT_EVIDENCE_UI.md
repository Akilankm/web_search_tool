# Product URL Finder UI

## Purpose

The browser application exists to return a usable product URL.

```text
Primary deliverable
= product URL

Supporting validation
= Source + Evidence + Identity + Usability
```

The system uses product identification and evidence gathering to justify the URL. Those are not substitutes for URL delivery.

## Terminal URL outcomes

### Verified URL

```text
URL_DELIVERED_VERIFIED
```

A direct product URL passed the strict identity, browser, evidence-coverage and durability gates.

### Review URL

```text
URL_DELIVERED_REVIEW_REQUIRED
```

A real direct product URL was delivered, but one or more strict production gates remain incomplete. The URL remains visible and usable for human review.

The application must prefer a best available review URL over an empty result when the candidate is:

- a real external URL;
- not a search, category, homepage, social or document URL;
- not a confirmed wrong product;
- not a confirmed wrong variant;
- the strongest remaining candidate after ranking source, evidence, identity and usability signals.

### URL delivery failure

```text
URL_DELIVERY_FAILED
```

This is an exceptional escalation, not a successful business result.

It is allowed only when the complete search and recovery route contains no non-mismatched direct external product-page candidate. The interface displays a red failure state and keeps recovery evidence inside a collapsed diagnostic section.

## Interface hierarchy

The standard screen contains only:

1. Product URL or URL-delivery failure
2. Source status
3. Evidence status
4. Identity status and confidence
5. Usability status
6. Brief justification
7. Collapsed review details

Detailed search traces, candidate comparisons, evidence ledgers, judgment records and artifacts are not part of the default result view.

## Source

Source communicates:

```text
URL delivered or failed
source role
source authority tier
manufacturer or retailer context
```

## Evidence

Evidence communicates:

```text
atomic evidence count
verified claim count
requested evidence coverage
visual and browser evidence availability
```

## Identity

Identity communicates:

```text
identified product
identity status
confidence
unresolved distinctions
confirmed contradictions
```

Confirmed product or variant mismatches can never be promoted as review URLs.

## Usability

Usability checks:

1. Browser openable
2. Text extractable
3. Direct product page
4. Exact product identity
5. Required evidence coverage
6. Reusable non-expiring URL

A review URL may have incomplete checks, but it must remain a real direct product candidate and must not have a confirmed identity conflict.

## Candidate recovery order

The final URL-delivery layer examines:

```text
strict primary URL
product_match URLs
evidence-set selected URLs
candidate records
feature assessments
browser evidence
browser investigations
SERP result URLs
candidate_url_records.json
candidate_state.json
```

Candidates are deduplicated and ranked. Existing strict selections are preferred, followed by verified or probable product pages, manufacturer and retailer authority, browser usability, extraction quality, coverage, confidence and search position.

## Input

Visible fields:

```text
Product text   required
Country code   required
Retailer       optional
EAN / GTIN     optional
```

Collapsed advanced fields:

```text
Search depth
Language
```

Run ID and feature set are assigned automatically.

## Search depth

| Profile | Purpose |
|---|---|
| `Focused` | Reduced investigation breadth for faster execution |
| `Standard` | Default production operating limits |
| `Extended` | Broader search, extraction and browser investigation |

Profiles change evidence-acquisition limits. They do not weaken identity safety or permit fabricated, indirect or confirmed-mismatch URLs.

## Review details

A single collapsed **Review details** section contains:

- Candidates
- Evidence
- Search
- Identity
- Decision audit
- Artifacts

## Runtime compatibility

```text
belief-url-resolution-v11-url-delivery-first
```

Required capability:

```text
best_available_review_url_delivery=true
```

## Azure ML VS Code usage

```bash
git checkout master
git pull origin master
./scripts/azureml_startup.sh --clean-build
bash scripts/run_product_evidence_ui.sh
```

Forward port `8501` privately through the VS Code **Ports** panel.

## Acceptance rules

The UI is correct only when:

1. the URL is the first result;
2. verified and review URLs are both displayed;
3. a confirmed mismatch is never delivered;
4. an empty URL is displayed as a failed delivery, not a normal outcome;
5. Source, Evidence, Identity and Usability remain immediately visible;
6. detailed diagnostics remain collapsed;
7. no URL is fabricated.
