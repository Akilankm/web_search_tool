from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any

from src.product_evidence_harness.constants import RETAILER_MATCHED, VALIDATION_VERIFIED
from src.product_evidence_harness.contracts import ActionType, CandidateScorecard, ProductSearchState, URLCandidate


def retailer_tokens(name: str | None) -> list[str]:
    if not name:
        return []
    tokens = [t.lower() for t in re.findall(r"[a-zA-Z0-9À-ž]+", name) if len(t) >= 2]
    # Also include a compact variant for names such as Mercado Libre / MercadoLibre.
    compact = "".join(tokens)
    if len(compact) >= 4:
        tokens.append(compact)
    return list(dict.fromkeys(tokens))


def text_matches_retailer(text: str, retailer_name: str | None) -> bool:
    tokens = retailer_tokens(retailer_name)
    if not tokens:
        return False
    folded = (text or "").lower().replace("-", " ").replace("_", " ")
    compact = re.sub(r"[^a-zA-Z0-9À-ž]+", "", folded)
    return any(t in folded or t in compact for t in tokens)


def candidate_matches_requested_retailer(candidate: URLCandidate, retailer_name: str | None) -> bool:
    if not retailer_name:
        return False
    return text_matches_retailer(" ".join([candidate.url, candidate.domain, candidate.title, candidate.snippet]), retailer_name)


@dataclass(frozen=True)
class RequestedRetailerMetrics:
    requested_retailer_name: str | None = None
    requested_retailer_attempted: bool = False
    requested_retailer_domains_found: tuple[str, ...] = ()
    requested_retailer_candidates_found: int = 0
    requested_retailer_candidates_scraped: int = 0
    requested_retailer_scrape_success_count: int = 0
    requested_retailer_rich_pages_count: int = 0
    requested_retailer_exact_candidates_count: int = 0
    requested_retailer_scrapability_status: str = "NOT_PROVIDED"
    requested_retailer_escape_reason: str = ""

    @property
    def should_escape(self) -> bool:
        return self.requested_retailer_scrapability_status in {
            "SEARCHED_NO_CANDIDATES",
            "UNUSABLE_FOR_EVIDENCE",
            "WRONG_VARIANTS_ONLY",
            "WEAK_OR_INSUFFICIENT_EVIDENCE",
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def action_scope(action_record) -> str:
    try:
        return str(action_record.action.metadata.get("scope") or "")
    except Exception:
        return ""


def requested_retailer_search_attempted(state: ProductSearchState) -> bool:
    if not state.task.retailer_name:
        return False
    return any(
        record.action.action_type in {ActionType.ORGANIC_SEARCH, ActionType.AI_MODE_SEARCH}
        and action_scope(record) == "requested_retailer"
        for record in state.actions_taken
    )


def requested_retailer_metrics(
    state: ProductSearchState,
    *,
    min_scrapes_for_escape: int = 2,
    min_richness_for_evidence: float = 0.30,
) -> RequestedRetailerMetrics:
    retailer = state.task.retailer_name
    if not retailer:
        return RequestedRetailerMetrics()

    attempted = requested_retailer_search_attempted(state)
    retailer_query_sources = {
        record.action.query
        for record in state.actions_taken
        if record.action.query and action_scope(record) == "requested_retailer"
    }

    def candidate_from_requested_scope(candidate: URLCandidate) -> bool:
        return bool(retailer_query_sources.intersection(set(candidate.query_sources or ())))

    cards = []
    candidate_urls_from_scope = set()
    for cand in state.candidates:
        if candidate_from_requested_scope(cand):
            candidate_urls_from_scope.add(cand.url)
    for card in state.scorecards:
        if (
            card.retailer_check == RETAILER_MATCHED
            or candidate_matches_requested_retailer(card.candidate, retailer)
            or card.candidate.url in candidate_urls_from_scope
        ):
            cards.append(card)

    # If scorecards are not built yet, count candidates from the candidate pool.
    if not cards and state.candidates:
        for cand in state.candidates:
            if candidate_matches_requested_retailer(cand, retailer) or cand.url in candidate_urls_from_scope:
                candidate_urls_from_scope.add(cand.url)

    domains = sorted({c.candidate.domain for c in cards if c.candidate.domain} | {
        c.domain for c in state.candidates if c.url in candidate_urls_from_scope and c.domain
    })
    candidates_found = len({c.candidate.url for c in cards} | candidate_urls_from_scope)
    scraped_cards = [c for c in cards if c.scrape]
    scraped = len(scraped_cards)
    success = sum(1 for c in scraped_cards if c.scrape and c.scrape.scraped and c.scrape.success and c.scrape.reachable and c.scrape.is_scrapable)
    rich = sum(1 for c in scraped_cards if c.scrape and c.scrape.is_scrapable and c.scrape.looks_like_product_page and c.scrape.richness_score >= min_richness_for_evidence)
    exact = sum(1 for c in scraped_cards if c.validation_status == VALIDATION_VERIFIED and not c.hard_failures)

    if exact:
        status = "EXACT_SCRAPABLE_RICH_FOUND"
        reason = "requested retailer produced at least one verified exact, scrape-usable candidate"
    elif not attempted:
        status = "NOT_ATTEMPTED"
        reason = "requested retailer search has not run yet"
    elif candidates_found == 0:
        status = "SEARCHED_NO_CANDIDATES"
        reason = "requested retailer search returned no usable URL candidates"
    elif scraped == 0:
        status = "CANDIDATES_FOUND_NOT_SCRAPED"
        reason = "requested retailer candidates exist but have not yet been scraped"
    elif scraped < min_scrapes_for_escape and rich == 0:
        status = "SCRAPABILITY_CHECK_IN_PROGRESS"
        reason = "requested retailer candidates are being scraped before escape decision"
    elif scraped >= min_scrapes_for_escape and rich == 0:
        status = "UNUSABLE_FOR_EVIDENCE"
        reason = "requested retailer candidates were scraped but no rich scrape-usable product evidence was extracted"
    elif scraped >= min_scrapes_for_escape and all(c.hard_failures or (c.verification and c.verification.variant_check == "CONFLICT") for c in scraped_cards):
        status = "WRONG_VARIANTS_ONLY"
        reason = "requested retailer scrape evidence only produced hard conflicts or sibling variants"
    elif rich > 0:
        status = "SCRAPABLE_RICH_BUT_NOT_EXACT"
        reason = "requested retailer has scrape-usable/rich pages but no exact product candidate yet"
    else:
        status = "WEAK_OR_INSUFFICIENT_EVIDENCE"
        reason = "requested retailer evidence remained weak or insufficient after scraping"

    return RequestedRetailerMetrics(
        requested_retailer_name=retailer,
        requested_retailer_attempted=attempted,
        requested_retailer_domains_found=tuple(domains),
        requested_retailer_candidates_found=candidates_found,
        requested_retailer_candidates_scraped=scraped,
        requested_retailer_scrape_success_count=success,
        requested_retailer_rich_pages_count=rich,
        requested_retailer_exact_candidates_count=exact,
        requested_retailer_scrapability_status=status,
        requested_retailer_escape_reason=reason,
    )
