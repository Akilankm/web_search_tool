from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

from src.product_evidence_harness.contracts import CandidateScorecard, ScrapeResult


PRODUCT_DETAIL_PAGE = "PRODUCT_DETAIL_PAGE"
PRODUCT_VARIANT_PAGE = "PRODUCT_VARIANT_PAGE"
CATEGORY_PAGE = "CATEGORY_PAGE"
SEARCH_RESULTS_PAGE = "SEARCH_RESULTS_PAGE"
HOMEPAGE = "HOMEPAGE"
CONSENT_OR_INTERSTITIAL = "CONSENT_OR_INTERSTITIAL"
LOGIN_OR_ACCESS_WALL = "LOGIN_OR_ACCESS_WALL"
STORE_SELECTOR = "STORE_SELECTOR"
ERROR_PAGE = "ERROR_PAGE"
ANTI_BOT_PAGE = "ANTI_BOT_PAGE"
EMPTY_OR_BROKEN_RENDER = "EMPTY_OR_BROKEN_RENDER"
UNRELATED_CONTENT = "UNRELATED_CONTENT"
NON_PRODUCT_PAGE = "NON_PRODUCT_PAGE"
UNKNOWN_PAGE = "UNKNOWN_PAGE"

PRODUCT_PAGE_TYPES = {PRODUCT_DETAIL_PAGE, PRODUCT_VARIANT_PAGE}


@dataclass(frozen=True)
class RenderedPageCheck:
    """Assessment of what the user actually sees when the URL renders.

    Browser-openable is a technical access check. This rendered check is the
    product-experience check: does the visible/rendered content look like the
    intended product page, or did the URL soft-reroute to unrelated content?
    """

    url: str
    final_url: str | None
    passed: bool
    page_type: str
    product_visible: bool
    content_related_to_intended_product: bool
    match_confidence: float
    verdict: str
    reason: str
    mismatch_reasons: tuple[str, ...] = ()
    visible_title: str = ""
    visible_product_name: str = ""
    screenshot_path: str | None = None
    screenshot_captured: bool = False
    llm_used: bool = False
    llm_verdict: str = "NOT_USED"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RenderedPageVerifier:
    """Verify rendered page relevance using browser-visible scrape evidence.

    The current harness may scrape a page successfully and mark it browser-openable
    while the human-visible page is a homepage, category, search page, interstitial,
    login wall, or unrelated product page. This verifier blocks those cases from
    becoming production-ready champions.

    The fields include screenshot/LLM placeholders so a Playwright/VLM capture path
    can populate the same contract without changing downstream CSV/artifact schemas.
    """

    min_related_confidence: float = 0.58
    min_product_visibility_confidence: float = 0.35

    def assess_card(self, card: CandidateScorecard) -> RenderedPageCheck:
        scrape = card.scrape
        if not scrape:
            return RenderedPageCheck(
                url=card.candidate.url,
                final_url=None,
                passed=False,
                page_type=EMPTY_OR_BROKEN_RENDER,
                product_visible=False,
                content_related_to_intended_product=False,
                match_confidence=0.0,
                verdict="FAIL_RENDERED_NO_SCRAPE",
                reason="No rendered or scraped content was available to verify what the user sees.",
                mismatch_reasons=("RENDERED_CONTENT_NOT_AVAILABLE",),
            )

        page_type = self._classify_page_type(card, scrape)
        product_visible = self._product_visible(scrape)
        related_confidence = self._related_confidence(card, scrape)
        content_related = related_confidence >= self.min_related_confidence
        reasons = self._mismatch_reasons(card, scrape, page_type, product_visible, content_related)
        passed = bool(
            page_type in PRODUCT_PAGE_TYPES
            and product_visible
            and content_related
            and not reasons
        )
        verdict = "PASS_RENDERED_PRODUCT_CONTENT" if passed else self._failure_verdict(page_type, reasons)
        return RenderedPageCheck(
            url=card.candidate.url,
            final_url=scrape.final_url,
            passed=passed,
            page_type=page_type,
            product_visible=product_visible,
            content_related_to_intended_product=content_related,
            match_confidence=round(related_confidence, 4),
            verdict=verdict,
            reason=self._reason(page_type, product_visible, content_related, related_confidence, reasons),
            mismatch_reasons=tuple(dict.fromkeys(reasons)),
            visible_title=scrape.title or scrape.h1 or scrape.page_product_name or card.candidate.title,
            visible_product_name=scrape.page_product_name or scrape.h1 or scrape.title,
        )

    def _classify_page_type(self, card: CandidateScorecard, scrape: ScrapeResult) -> str:
        text = self._visible_text(card, scrape).lower()
        url = (scrape.final_url or card.candidate.url or "").lower()
        path = urlparse(url).path.strip("/").lower()

        if not scrape.success or not scrape.reachable or scrape.is_soft_404:
            return ERROR_PAGE
        if scrape.word_count < 20 or not text.strip():
            return EMPTY_OR_BROKEN_RENDER
        if self._has_any(text, ["captcha", "are you human", "verify you are human", "access denied", "blocked", "bot detection"]):
            return ANTI_BOT_PAGE
        if self._has_any(text, ["sign in", "log in", "login", "create account", "my account"]):
            if not scrape.looks_like_product_page and scrape.richness_score < 0.35:
                return LOGIN_OR_ACCESS_WALL
        if self._has_any(text, ["accept cookies", "cookie settings", "consent", "privacy preferences", "gdpr"]):
            if not scrape.looks_like_product_page and scrape.richness_score < 0.35:
                return CONSENT_OR_INTERSTITIAL
        if self._has_any(text, ["choose your store", "select store", "select location", "delivery location", "pick a store"]):
            if not scrape.looks_like_product_page and scrape.richness_score < 0.35:
                return STORE_SELECTOR
        if scrape.looks_like_homepage or path in {"", "home", "homepage"}:
            return HOMEPAGE
        if self._looks_search_or_category(url, text):
            return SEARCH_RESULTS_PAGE if "search" in url or "search" in text[:500] else CATEGORY_PAGE
        if not scrape.looks_like_product_page:
            return NON_PRODUCT_PAGE
        if card.verification and card.verification.variant_check == "CONFLICT":
            return PRODUCT_VARIANT_PAGE
        return PRODUCT_DETAIL_PAGE

    def _product_visible(self, scrape: ScrapeResult) -> bool:
        name_present = bool(scrape.page_product_name or scrape.h1 or scrape.title)
        commerce_or_media = bool(scrape.image_count > 0 or scrape.image_urls or scrape.has_price or scrape.structured_eans)
        details_present = bool(scrape.description or scrape.specs or scrape.attributes or scrape.brand or scrape.manufacturer)
        confidence = 0.0
        confidence += 0.40 if name_present else 0.0
        confidence += 0.35 if commerce_or_media else 0.0
        confidence += 0.25 if details_present else 0.0
        return confidence >= self.min_product_visibility_confidence

    def _related_confidence(self, card: CandidateScorecard, scrape: ScrapeResult) -> float:
        verification = card.verification
        signals = [
            float(scrape.text_overlap or 0.0),
            float(card.title_score or 0.0),
            float(verification.title_match_score if verification else 0.0),
        ]
        if verification and verification.ean_check == "MATCHED":
            signals.append(1.0)
        if scrape.contains_ean:
            signals.append(0.95)
        if verification and verification.identity_status == "VERIFIED" and verification.exact_product_check == "EXACT_MATCH":
            signals.append(max(0.70, verification.title_match_score))
        if card.llm_used and card.llm_exact_product_match:
            signals.append(max(0.70, card.llm_confidence))
        return max(0.0, min(1.0, max(signals or [0.0])))

    def _mismatch_reasons(self, card: CandidateScorecard, scrape: ScrapeResult, page_type: str, product_visible: bool, content_related: bool) -> list[str]:
        reasons: list[str] = []
        if page_type not in PRODUCT_PAGE_TYPES:
            reasons.append(f"RENDERED_PAGE_TYPE_{page_type}")
        if not product_visible:
            reasons.append("RENDERED_PRODUCT_NOT_VISIBLE")
        if not content_related:
            reasons.append("RENDERED_CONTENT_NOT_RELATED_TO_INPUT_PRODUCT")
        if scrape.final_url and self._major_reroute(card.candidate.url, scrape.final_url):
            reasons.append("RENDERED_FINAL_URL_REROUTED_TO_DIFFERENT_PAGE")
        return reasons

    def _failure_verdict(self, page_type: str, reasons: list[str]) -> str:
        if page_type == HOMEPAGE:
            return "FAIL_RENDERED_HOMEPAGE"
        if page_type in {CATEGORY_PAGE, SEARCH_RESULTS_PAGE}:
            return "FAIL_RENDERED_LISTING_OR_SEARCH"
        if page_type in {CONSENT_OR_INTERSTITIAL, LOGIN_OR_ACCESS_WALL, STORE_SELECTOR, ANTI_BOT_PAGE}:
            return "FAIL_RENDERED_INTERSTITIAL_OR_ACCESS_WALL"
        if "RENDERED_CONTENT_NOT_RELATED_TO_INPUT_PRODUCT" in reasons:
            return "FAIL_RENDERED_UNRELATED_CONTENT"
        return "FAIL_RENDERED_CONTENT_CHECK"

    def _reason(self, page_type: str, product_visible: bool, content_related: bool, confidence: float, reasons: list[str]) -> str:
        if not reasons:
            return f"Rendered page is product-detail-like, product content is visible, and visible/extracted content matches the intended product with confidence {confidence:.2f}."
        return (
            f"Rendered page failed user-visible product relevance. page_type={page_type}; "
            f"product_visible={product_visible}; content_related={content_related}; confidence={confidence:.2f}; "
            f"reasons={'; '.join(reasons)}"
        )

    def _visible_text(self, card: CandidateScorecard, scrape: ScrapeResult) -> str:
        parts = [
            scrape.page_product_name,
            scrape.h1,
            scrape.title,
            scrape.description,
            scrape.markdown_excerpt,
            card.candidate.title,
            card.candidate.snippet,
        ]
        return " ".join(p for p in parts if p)

    def _looks_search_or_category(self, url: str, text: str) -> bool:
        url_markers = ["/search", "?q=", "?query=", "/category", "/c/", "/catalog", "/browse", "/shop/"]
        if any(marker in url for marker in url_markers):
            return True
        listing_terms = ["sort by", "filter by", "results for", "products found", "items found", "categories", "showing", "view all"]
        return self._has_any(text[:3000], listing_terms)

    @staticmethod
    def _has_any(text: str, terms: list[str]) -> bool:
        return any(term in text for term in terms)

    @staticmethod
    def _major_reroute(original_url: str, final_url: str) -> bool:
        original = urlparse(original_url or "")
        final = urlparse(final_url or "")
        if not original.netloc or not final.netloc:
            return False
        if original.netloc.lower() != final.netloc.lower():
            return True
        original_path = original.path.strip("/").lower()
        final_path = final.path.strip("/").lower()
        if original_path and not final_path:
            return True
        return False
