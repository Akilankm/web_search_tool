# Team Review Guide

## Goal

Make artifact review fast and precise.

## Open only these by default

```text
review_summary.md
candidate_decisions.csv
```

## Use notebook view

```text
notebooks/04_review_artifact_reader.ipynb
```

## Review decision

| Question | Where to check |
|---|---|
| What was selected? | `review_summary.md` section 1 |
| Why was it selected? | `review_summary.md` section 2 |
| How was it decided? | `review_summary.md` section 3 |
| What did model/detectors contribute? | `review_summary.md` section 5 |
| What was rejected? | `candidate_decisions.csv` |
| Is it safe to automate? | `review_summary.md` review instruction |
