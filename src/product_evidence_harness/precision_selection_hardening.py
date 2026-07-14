from __future__ import annotations

from collections import Counter
from dataclasses import replace

from src.product_evidence_harness.candidate_precision import (
    CandidatePrecisionGate,
    candidate_identity_tokens,
    canonicalize_candidate_url,
)
from src.product_evidence_harness.candidate_store import CandidateStore
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


def _wrap_evaluate(original):
    def evaluate(self, product, candidate):
        decision = original(self, product, candidate)
        if not decision.admitted_for_scrape or decision.ean_signal:
            return decision
        # SERP snippets can contain query echoes or nearby-product text. Require
        # an independent identity signal in the URL/title before spending a full
        # scrape when no exact EAN anchor exists.
        tokens = candidate_identity_tokens(product.main_text)
        stable_evidence = " ".join(
            [decision.canonical_url, candidate.title, candidate.domain]
        ).lower()
        stable_overlap = sum(1 for token in tokens if token in stable_evidence) / max(
            1, len(tokens)
        )
        if stable_overlap < 0.18:
            return replace(
                decision,
                admitted_for_scrape=False,
                admission_reason="SERP_REJECTED_LOW_STABLE_IDENTITY_SIGNAL",
            )
        return decision

    return evaluate


def _strip_classification_source_types(candidates):
    return [
        replace(
            candidate,
            source_types=tuple(
                item
                for item in candidate.source_types
                if not str(item).startswith("url_type_")
            ),
        )
        for candidate in candidates
    ]


def _wrap_candidate_merge(original):
    def merge(self, *args, **kwargs):
        return _strip_classification_source_types(original(self, *args, **kwargs))

    return merge


def apply_precision_selection_hardening() -> None:
    if getattr(CandidatePrecisionGate, "_cumulative_domain_cap_applied", False):
        return
    CandidatePrecisionGate.evaluate = _wrap_evaluate(CandidatePrecisionGate.evaluate)
    CandidatePrecisionGate.select_for_scrape = _select_for_scrape
    CandidateStore.merge_organic = _wrap_candidate_merge(CandidateStore.merge_organic)
    CandidateStore.merge_ai = _wrap_candidate_merge(CandidateStore.merge_ai)
    CandidatePrecisionGate._cumulative_domain_cap_applied = True
