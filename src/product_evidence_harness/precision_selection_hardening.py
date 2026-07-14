from __future__ import annotations

from collections import Counter
from dataclasses import replace

from src.product_evidence_harness.candidate_precision import (
    CandidatePrecisionGate,
    canonicalize_candidate_url,
)
from src.product_evidence_harness.url_utils import domain_of


def _select_for_scrape(
    self,
    *,
    product,
    candidates,
    already_scraped,
    maximum_new: int,
):
    already = {canonicalize_candidate_url(url) or url for url in already_scraped}
    domain_counts = Counter(domain_of(url) for url in already)
    evaluated = {candidate.url: self.evaluate(product, candidate) for candidate in candidates}
    ranked = sorted(
        candidates,
        key=lambda candidate: (
            evaluated[candidate.url].admitted_for_scrape,
            evaluated[candidate.url].ean_signal,
            evaluated[candidate.url].preflight_score,
            -(candidate.best_position or 999),
        ),
        reverse=True,
    )
    selected = []
    limit = max(0, min(int(maximum_new), self.maximum_full_scrapes))
    for candidate in ranked:
        decision = evaluated[candidate.url]
        if len(selected) >= limit:
            break
        if not decision.admitted_for_scrape or decision.canonical_url in already:
            continue
        if domain_counts.get(decision.domain, 0) >= self.maximum_per_domain:
            evaluated[candidate.url] = replace(
                decision,
                admitted_for_scrape=False,
                admission_reason="QUALIFIED_NOT_SCRAPED_DOMAIN_DIVERSITY_CAP",
            )
            continue
        selected.append(candidate)
        domain_counts[decision.domain] += 1
    return selected, evaluated


def apply_precision_selection_hardening() -> None:
    if getattr(CandidatePrecisionGate, "_cumulative_domain_cap_applied", False):
        return
    CandidatePrecisionGate.select_for_scrape = _select_for_scrape
    CandidatePrecisionGate._cumulative_domain_cap_applied = True
