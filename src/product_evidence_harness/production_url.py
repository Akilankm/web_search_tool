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
    critical_product_evidence_complete: bool = False
    country_acceptable: bool = False
    user_visible_product_match: bool = False
    user_visible_status: str = "NOT_VERIFIED"
    user_visible_page_type: str = "unknown"
    user_visible_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProductionURLGate:
    """Gate product URLs for browser use, scraping use, and exact-product use.

    Browser-openable is necessary but not sufficient. A URL can open in a
    browser and still show a homepage, consent wall, search page, access block,
    or a different product. When ``require_user_visible_verification`` is true,
    a candidate must also pass the user-visible product-content verdict.
    """

    require_user_visible_verification: bool = False
    min_richness_score: float = 0.45
    min_word_count: int = 120
    min_title_score: float = 0.70
    min_critical_evidence_items: int = 3

    def assess_card(self, card: CandidateScorecard) -> ProductionURLAssessment:
        url = card.candidate.url
        scrape = card.scrape
        verification = card.verification
        visible = getattr(card, "browser_visible_verdict", None)
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

        user_visible_product_match = self._user_visible_product_match(visible)
        user_visible_status = getattr(visible, "status", "NOT_VERIFIED") if visible else "NOT_VERIFIED"
        user_visible_page_type = getattr(visible, "browser_visible_page_type", "unknown") if visible else "unknown"
        user_visible_confidence = float(getattr(visible, "user_visible_content_confidence", 0.0) or 0.0) if visible else 0.0
        if self.require_user_visible_verification and not user_visible_product_match:
            if visible:
                reasons.append(user_visible_status or "USER_VISIBLE_PRODUCT_CONTENT_NOT_CONFIRMED")
            else:
                reasons.append("USER_VISIBLE_PRODUCT_CONTENT_NOT_VERIFIED")

        critical_product_evidence_complete = self._critical_product_evidence_complete(card)
        if not critical_product_evidence_complete:
            reasons.append("CRITICAL_PRODUCT_DETAILS_NOT_EXTRACTED")

        highly_scrapable = bool(
            browser_openable
            and scrape
            and scrape.is_scrapable
            and scrape.looks_like_product_page
            and scrape.word_count >= self.min_word_count
            and scrape.richness_score >= self.min_richness_score
            and critical_product_evidence_complete
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

        country_acceptable = card.country_check in {"MATCHED", "NOT_PROVIDED", "ALTERNATIVE"}
        if not country_acceptable:
            reasons.append("URL_NOT_COUNTRY_MATCHED")
        if card.country_check == "ALTERNATIVE":
            reasons.append("COUNTRY_ALTERNATIVE_GLOBAL_FALLBACK")
        if card.variant_check == "CONFLICT":
            reasons.append("VARIANT_CONFLICT")
        if card.hard_failures:
            reasons.extend(card.hard_failures)

        visible_ok = user_visible_product_match or not self.require_user_visible_verification
        production_ready = bool(
            browser_openable
            and visible_ok
            and highly_scrapable
            and critical_product_evidence_complete
            and exact_product_match
            and country_acceptable
        )
        score = self._score(
            browser_openable=browser_openable,
            highly_scrapable=highly_scrapable,
            exact_product_match=exact_product_match,
            critical_product_evidence_complete=critical_product_evidence_complete,
            country_acceptable=country_acceptable,
            user_visible_product_match=user_visible_product_match,
            card=card,
        )
        status = "PRODUCTION_READY_EXACT_SCRAPABLE_BROWSER_URL" if production_ready else self._status(
            browser_openable,
            highly_scrapable,
            exact_product_match,
            critical_product_evidence_complete,
            country_acceptable,
            card,
            visible=visible,
            require_user_visible_verification=self.require_user_visible_verification,
        )
        return ProductionURLAssessment(
            url=url,
            production_ready=production_ready,
            browser_openable=browser_openable,
            highly_scrapable=highly_scrapable,
            exact_product_match=exact_product_match,
            status=status,
            reasons=tuple(dict.fromkeys(reasons)),
            score=score,
            critical_product_evidence_complete=critical_product_evidence_complete,
            country_acceptable=country_acceptable,
            user_visible_product_match=user_visible_product_match,
            user_visible_status=user_visible_status,
            user_visible_page_type=user_visible_page_type,
            user_visible_confidence=round(user_visible_confidence, 4),
        )

    @staticmethod
    def _user_visible_product_match(visible: Any) -> bool:
        if not visible:
            return False
        return bool(
            getattr(visible, "champion_should_survive_visible_check", False)
            and getattr(visible, "user_visible_product_match", False)
            and getattr(visible, "browser_visible_page_type", "") == "product_page"
            and getattr(visible, "status", "") == "USER_VISIBLE_PRODUCT_PAGE_CONFIRMED"
        )

    def _critical_product_evidence_complete(self, card: CandidateScorecard) -> bool:
        scrape = card.scrape
        if not scrape or not scrape.success or not scrape.reachable:
            return False
        has_name = bool(scrape.page_product_name or scrape.title or scrape.h1)
        has_description = bool(scrape.description and len(scrape.description.strip()) >= 80)
        has_specs = bool(scrape.specs or scrape.attributes)
        has_brand_or_mfr = bool(scrape.brand or scrape.manufacturer)
        has_images = bool(scrape.image_count > 0 or scrape.image_urls)
        has_gtin = bool(scrape.structured_eans)
        has_commerce_signal = bool(scrape.has_price or scrape.availability)
        critical_count = sum([
            has_description,
            has_specs,
            has_brand_or_mfr,
            has_images,
            has_gtin,
            has_commerce_signal,
        ])
        return bool(has_name and critical_count >= self.min_critical_evidence_items)

    def best_production_card(self, state: ProductSearchState) -> tuple[CandidateScorecard | None, ProductionURLAssessment | None]:
        assessed = [(card, self.assess_card(card)) for card in state.scorecards]
        ready = [(card, assessment) for card, assessment in assessed if assessment.production_ready]
        if not ready:
            return None, None
        return sorted(
            ready,
            key=lambda pair: (
                1 if pair[0].retailer_check == "MATCHED" else 0,
                1 if pair[0].country_check == "MATCHED" else 0,
                1 if pair[0].country_check == "ALTERNATIVE" else 0,
                pair[1].user_visible_confidence,
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
    def _score(*, browser_openable: bool, highly_scrapable: bool, exact_product_match: bool, critical_product_evidence_complete: bool, country_acceptable: bool, user_visible_product_match: bool, card: CandidateScorecard) -> float:
        score = 0.0
        score += 0.17 if browser_openable else 0.0
        score += 0.16 if user_visible_product_match else 0.0
        score += 0.17 if highly_scrapable else 0.0
        score += 0.17 if critical_product_evidence_complete else 0.0
        score += 0.22 if exact_product_match else 0.0
        score += 0.06 if country_acceptable else 0.0
        score += 0.03 if card.retailer_check == "MATCHED" else 0.0
        score += 0.02 * min(1.0, card.richness_score)
        return round(min(1.0, score), 4)

    @staticmethod
    def _status(browser_openable: bool, highly_scrapable: bool, exact_product_match: bool, critical_product_evidence_complete: bool, country_acceptable: bool, card: CandidateScorecard, *, visible: Any, require_user_visible_verification: bool) -> str:
        if not browser_openable:
            return "PRODUCT_URL_NOT_BROWSER_OPENABLE_NEEDS_REVIEW"
        if require_user_visible_verification:
            if visible is None:
                return "BROWSER_VISIBLE_PRODUCT_CONTENT_NOT_VERIFIED_NEEDS_REVIEW"
            visible_status = getattr(visible, "status", "") or "BROWSER_VISIBLE_PRODUCT_CONTENT_NOT_CONFIRMED"
            if not ProductionURLGate._user_visible_product_match(visible):
                return visible_status if visible_status.startswith("BROWSER_OPENABLE_BUT_") else "BROWSER_OPENABLE_BUT_VISIBLE_CONTENT_INSUFFICIENT"
        if not critical_product_evidence_complete:
            return "PRODUCT_URL_CRITICAL_DETAILS_NOT_EXTRACTED_NEEDS_REVIEW"
        if not highly_scrapable:
            return "PRODUCT_URL_NOT_HIGHLY_SCRAPABLE_NEEDS_REVIEW"
        if not exact_product_match:
            return "PRODUCT_URL_NOT_EXACT_MATCH_NEEDS_REVIEW"
        if not country_acceptable:
            return "PRODUCT_URL_GLOBAL_OR_COUNTRY_MISMATCH_NEEDS_REVIEW"
        return "PRODUCT_URL_NOT_PRODUCTION_READY_NEEDS_REVIEW"
