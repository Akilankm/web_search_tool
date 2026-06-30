from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.product_evidence_harness.contracts import CandidateScorecard, ProductSearchState


@dataclass(frozen=True)
class ProductionURLAssessment:
    """High-stakes usability assessment for the URL that teams will open/scrape."""

    url: str
    production_ready: bool
    browser_openable: bool
    highly_scrapable: bool
    exact_product_match: bool
    status: str
    reasons: tuple[str, ...]
    score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProductionURLGate:
    """Gate product URLs for browser use, scraping use, and exact-product use.

    The normal harness can still expose a best discovered URL. This gate is the
    stricter high-stakes layer used to decide whether the URL is actually safe
    for the browser/scraping/product-coding teams to depend on.
    """

    min_richness_score: float = 0.35
    min_word_count: int = 80
    min_title_score: float = 0.70

    def assess_card(self, card: CandidateScorecard) -> ProductionURLAssessment:
        url = card.candidate.url
        scrape = card.scrape
        verification = card.verification
        reasons: list[str] = []

        browser_openable = bool(
            scrape
            and scrape.scraped
            and scrape.success
            and scrape.reachable
            and (scrape.status_code is None or 200 <= int(scrape.status_code) < 400)
            and not scrape.is_soft_404
            and not scrape.looks_like_homepage
        )
        if not browser_openable:
            reasons.append("URL_NOT_CONFIRMED_BROWSER_OPENABLE")

        evidence_rich = bool(
            scrape
            and (
                scrape.richness_score >= self.min_richness_score
                or bool(scrape.structured_eans)
                or bool(scrape.specs)
                or bool(scrape.attributes)
                or bool(scrape.description and len(scrape.description) >= 80)
                or scrape.image_count > 0
            )
        )
        if not evidence_rich:
            reasons.append("PRODUCT_PAGE_EVIDENCE_NOT_RICH_ENOUGH")

        highly_scrapable = bool(
            browser_openable
            and scrape
            and scrape.is_scrapable
            and scrape.looks_like_product_page
            and scrape.word_count >= self.min_word_count
            and evidence_rich
        )
        if not highly_scrapable:
            reasons.append("URL_NOT_HIGHLY_SCRAPABLE_PRODUCT_PAGE")

        exact_product_match = bool(
            verification
            and verification.identity_status == "VERIFIED"
            and verification.exact_product_check == "EXACT_MATCH"
            and verification.variant_check != "CONFLICT"
            and not verification.ean_conflict_is_blocking
            and not card.hard_failures
            and (
                verification.ean_check == "MATCHED"
                or verification.title_match_score >= self.min_title_score
                or card.title_score >= self.min_title_score
            )
        )
        if card.llm_used:
            exact_product_match = bool(
                exact_product_match
                and card.llm_decision in {"EXACT_MATCH", "EXACT_MATCH_WITH_WARNING"}
                and card.llm_exact_product_match
            )
        if not exact_product_match:
            reasons.append("URL_NOT_VERIFIED_EXACT_PRODUCT_MATCH")

        if card.country_check not in {"MATCHED", "NOT_PROVIDED"}:
            reasons.append("URL_NOT_COUNTRY_MATCHED")
        if card.variant_check == "CONFLICT":
            reasons.append("VARIANT_CONFLICT")
        if card.hard_failures:
            reasons.extend(card.hard_failures)

        production_ready = bool(browser_openable and highly_scrapable and exact_product_match and card.country_check in {"MATCHED", "NOT_PROVIDED"})
        score = self._score(browser_openable=browser_openable, highly_scrapable=highly_scrapable, exact_product_match=exact_product_match, card=card)
        status = "PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL" if production_ready else self._status(browser_openable, highly_scrapable, exact_product_match, card)
        return ProductionURLAssessment(
            url=url,
            production_ready=production_ready,
            browser_openable=browser_openable,
            highly_scrapable=highly_scrapable,
            exact_product_match=exact_product_match,
            status=status,
            reasons=tuple(dict.fromkeys(reasons)),
            score=score,
        )

    def best_production_card(self, state: ProductSearchState) -> tuple[CandidateScorecard | None, ProductionURLAssessment | None]:
        assessed = [(card, self.assess_card(card)) for card in state.scorecards]
        ready = [(card, assessment) for card, assessment in assessed if assessment.production_ready]
        if not ready:
            return None, None
        return sorted(
            ready,
            key=lambda pair: (
                1 if pair[0].retailer_check == "MATCHED" else 0,
                1 if pair[0].country_check in {"MATCHED", "NOT_PROVIDED"} else 0,
                pair[1].score,
                pair[0].richness_score,
                pair[0].final_confidence,
            ),
            reverse=True,
        )[0]

    def assess_url_in_state(self, state: ProductSearchState, url: str) -> ProductionURLAssessment | None:
        for card in state.scorecards:
            if card.candidate.url == url:
                return self.assess_card(card)
        return None

    @staticmethod
    def _score(*, browser_openable: bool, highly_scrapable: bool, exact_product_match: bool, card: CandidateScorecard) -> float:
        score = 0.0
        score += 0.25 if browser_openable else 0.0
        score += 0.25 if highly_scrapable else 0.0
        score += 0.30 if exact_product_match else 0.0
        score += 0.10 if card.country_check in {"MATCHED", "NOT_PROVIDED"} else 0.0
        score += 0.05 if card.retailer_check == "MATCHED" else 0.0
        score += 0.05 * min(1.0, card.richness_score)
        return round(min(1.0, score), 4)

    @staticmethod
    def _status(browser_openable: bool, highly_scrapable: bool, exact_product_match: bool, card: CandidateScorecard) -> str:
        if not browser_openable:
            return "PRODUCT_URL_NOT_BROWSER_OPENABLE_NEEDS_REVIEW"
        if not highly_scrapable:
            return "PRODUCT_URL_NOT_HIGHLY_SCRAPABLE_NEEDS_REVIEW"
        if not exact_product_match:
            return "PRODUCT_URL_NOT_EXACT_MATCH_NEEDS_REVIEW"
        if card.country_check not in {"MATCHED", "NOT_PROVIDED"}:
            return "PRODUCT_URL_GLOBAL_OR_COUNTRY_MISMATCH_NEEDS_REVIEW"
        return "PRODUCT_URL_NOT_PRODUCTION_READY_NEEDS_REVIEW"
