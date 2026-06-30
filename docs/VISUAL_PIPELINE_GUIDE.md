# Visual Pipeline Guide

This document explains the non-linear product evidence pipeline visually. The harness should be understood as a decision system, not as a single scraper.

## Full pipeline at a glance

```mermaid
flowchart TD
    A[Input CSV / ProductQuery] --> B[Input normalization]
    B --> C[Country + retailer context]
    C --> D[SerpAPI search fan-out]
    D --> E[Organic search results]
    D --> F[AI mode references]
    E --> G[Candidate URL pool]
    F --> G
    G --> H[Preflight ranking]
    H --> I[Top-K candidate cut]
    I --> J[Bounded tournament batches]
    J --> K[Scrape evidence]
    K --> L[Identity verification]
    K --> M[Retailer and country checks]
    K --> N[Scrapability and richness checks]
    L --> O[Candidate scorecards]
    M --> O
    N --> O
    O --> P[Batch winners]
    P --> Q[Champion candidate]
    Q --> R[Champion confirmation]
    R --> S[Production URL gate]
    S --> T{Production ready?}
    T -->|Yes| U[Final submission row]
    T -->|No| V[Review queue]
    U --> W[Product coding input]
    V --> X[Human review]
```

## Why this is non-linear

Many independent tools contribute evidence to a single decision. The winning URL is not selected by search rank alone.

```mermaid
flowchart TD
    A[Candidate URL] --> B[URL/domain signals]
    A --> C[Search title/snippet signals]
    A --> D[Scrape result]
    A --> E[Product identity verifier]
    A --> F[EAN/GTIN checks]
    A --> G[Retailer checks]
    A --> H[Country checks]
    A --> I[Page quality/richness]
    A --> J[Variant conflict detector]

    B --> K[Candidate scorecard]
    C --> K
    D --> K
    E --> K
    F --> K
    G --> K
    H --> K
    I --> K
    J --> K

    K --> L[Tournament winner]
    L --> M[Champion confirmation]
    M --> N[Production handoff decision]
```

## Search and candidate discovery

```mermaid
flowchart LR
    A[main_text] --> D[Search query builder]
    B[country_code] --> D
    C[optional EAN / retailer] --> D
    D --> E[Organic searches]
    D --> F[AI mode searches]
    E --> G[Candidate URLs]
    F --> G
    G --> H[Deduplication]
    H --> I[Candidate pool]
```

## Tournament mode

Tournament mode makes the system faster and stronger than naive sequential scraping.

```mermaid
flowchart TD
    A[Candidate pool] --> B[Preflight scoring]
    B --> C[Top-K cut]
    C --> D[Batch 1 scrape]
    C --> E[Batch 2 scrape]
    C --> F[Batch 3 scrape]
    D --> G[Batch winner 1]
    E --> H[Batch winner 2]
    F --> I[Batch winner 3]
    G --> J[Final champion selection]
    H --> J
    I --> J
    J --> K[Champion confirmation]
```

## Decision gates

A URL cannot become production-ready by being merely reachable. It must pass multiple gates.

```mermaid
flowchart TD
    A[Candidate URL] --> B{Browser openable?}
    B -->|No| R[Review-only]
    B -->|Yes| C{Highly scrapable?}
    C -->|No| R
    C -->|Yes| D{Exact product match?}
    D -->|No| R
    D -->|Yes| E{Country/retailer acceptable?}
    E -->|No| R
    E -->|Yes| F{Champion confirmation passed?}
    F -->|No| R
    F -->|Yes| G[Production-ready champion URL]
```

## Review routing

The harness is designed to avoid false confidence. Weak cases are routed to review instead of being silently automated.

```mermaid
flowchart LR
    A[Final URL candidate] --> B{Production gate}
    B -->|Pass| C[Automated handoff]
    B -->|Fail| D[Review queue]
    D --> E[Failure taxonomy]
    D --> F[Best available URL]
    D --> G[Decision report]
```

## Artifact creation

```mermaid
flowchart TD
    A[Run result] --> B[Business CSV]
    A --> C[Review CSV]
    A --> D[Metrics JSON]
    A --> E[Row artifact folder]

    E --> F[report.md]
    E --> G[trace.json]
    E --> H[tournament_bracket.json]
    E --> I[champion_confirmation.json]
    E --> J[product_coding_input.json]
    E --> K[quality_assessment.md]
```

## Optional offline capture

Offline capture is separate and notebook-only from a user workflow perspective. It starts after champion confirmation, not before.

```mermaid
flowchart LR
    A[Confirmed champion URL] --> B[Notebook 03 only]
    B --> C[Live capture once]
    C --> D[Download images and CSS]
    D --> E[Rewrite references to local paths]
    E --> F[Disable live scripts/forms/links]
    F --> G[Openable offline_page.html]
    F --> H[Validation JSON]
```

## System mental model

```text
Search finds possibilities.
Scraping extracts evidence.
Identity verification protects exactness.
Tournament mode selects the strongest candidate.
Champion confirmation protects handoff quality.
Artifacts make the decision auditable.
Notebooks make the system usable.
```
