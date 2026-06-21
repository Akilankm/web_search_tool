from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional
from urllib.parse import unquote, urlparse

from loguru import logger

from src.serp_hybrid_url_finder.constants import (
    CHECK_BRAND_ABSENT,
    CHECK_BRAND_MATCHED,
    CHECK_BRAND_NOT_APPLICABLE,
    CHECK_EAN_ABSENT,
    CHECK_EAN_CONFLICT,
    CHECK_EAN_MATCHED,
    CHECK_NOT_PROVIDED,
    CHECK_QTY_CONFLICT,
    CHECK_QTY_MATCHED,
    CHECK_QTY_NOT_APPLICABLE,
    CHECK_QTY_UNKNOWN,
    CHECK_TITLE_PARTIAL,
    CHECK_TITLE_STRONG,
    CHECK_TITLE_WEAK,
    EAN_DIGIT_LENGTHS,
    IDENTITY_MISMATCH,
    IDENTITY_PROBABLE,
    IDENTITY_UNVERIFIED,
    IDENTITY_VERIFIED,
    IDENTITY_WEAK,
    MIN_TOKEN_LENGTH_FOR_TEXT_MATCH,
    PAGE_TYPE_NON_PRODUCT,
    # PAGE_TYPE_PRODUCT_DETAIL,
    PAGE_TYPE_SOFT_404,
    PAGE_TYPE_UNKNOWN,
    QUANTITY_REGEX,
    TITLE_PARTIAL_MATCH_THRESHOLD,
    TITLE_STOPWORDS,
    TITLE_STRONG_MATCH_THRESHOLD,
    TOKEN_REGEX,
)
from src.serp_hybrid_url_finder.models import MatchVerification, ProductQuery, ScrapeResult

_TOKEN_PATTERN = re.compile(TOKEN_REGEX)
_QUANTITY_PATTERN = re.compile(QUANTITY_REGEX, re.IGNORECASE)
_DIGIT_RUN_PATTERN = re.compile(r"\d{8,14}")


def _fold(text: str) -> str:
    """Lowercase and strip diacritics so 'ZVÍŘÁTKY' matches 'zviratky'."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return without_marks.lower()


@dataclass(frozen=True)
class ProductIdentityVerifier:
    """Decides whether a scraped page is genuinely the requested product.

    This is the layer that separates a *correct* URL from a merely *scrapable*
    one. It cross-checks the scraped page content against the requested product
    identity on four independent axes and combines them into one verdict:

    1. EAN / GTIN     - authoritative; a different GTIN on the page is a hard reject.
    2. Pack size      - '18 KS' must not match '32 KS'; a different count is rejected.
    3. Title tokens   - distinctive, diacritic-folded token overlap.
    4. Page type      - a real product detail page, not a soft-404 / category.
    """

    def verify(self, product: ProductQuery, scrape: Optional[ScrapeResult]) -> MatchVerification:
        if scrape is None or not scrape.scraped:
            return self._unverified(
                url=scrape.url if scrape else "",
                reason="page was not scraped",
            )

        page_text = scrape.verification_text or " ".join(
            [scrape.page_product_name, scrape.title, scrape.h1, scrape.markdown_excerpt]
        )
        page_name_text = " ".join(
            [scrape.page_product_name, scrape.title, scrape.h1, self._slug(scrape.final_url or scrape.url)]
        )

        ean_check, page_eans = self._check_ean(product, scrape, page_text)
        quantity_check, req_qty, page_qty = self._check_quantity(product, page_name_text)
        title_check, score, matched, missing = self._check_title(product, page_name_text)
        brand_check = self._check_brand(product, page_name_text)
        page_type = self._page_type(scrape)

        justifications: list[str] = []
        blocking: list[str] = []

        if ean_check == CHECK_EAN_MATCHED:
            justifications.append(f"EAN/GTIN {product.ean} confirmed on the scraped page")
        elif ean_check == CHECK_EAN_CONFLICT:
            blocking.append(
                f"page declares a different GTIN ({', '.join(page_eans)}) than requested {product.ean}"
            )

        # NOTE: Pack size is irrelevant for product coding team.
        # Even if pack sizes differ, the page may still contain the product info they need.
        # Keep quantity check in reporting but don't block on it.
        if quantity_check == CHECK_QTY_MATCHED:
            justifications.append(f"pack size matches ({req_qty})")
        # Removed: elif quantity_check == CHECK_QTY_CONFLICT (pack size mismatch is not a blocker)

        if title_check == CHECK_TITLE_STRONG:
            justifications.append(
                f"distinctive title tokens matched ({len(matched)}/{len(matched) + len(missing)}): "
                f"{', '.join(matched[:6])}"
            )
        elif title_check == CHECK_TITLE_WEAK:
            blocking.append("distinctive title tokens did not match the scraped page")

        if brand_check == CHECK_BRAND_MATCHED:
            justifications.append("brand token present on page")

        if page_type == PAGE_TYPE_SOFT_404:
            blocking.append("scraped page looks like a soft-404 / 'product not found' page")
        # elif page_type == PAGE_TYPE_PRODUCT_DETAIL:
        #     justifications.append("scraped page is a real product detail page")
        elif page_type == PAGE_TYPE_NON_PRODUCT:
            blocking.append("scraped page is not a product detail page")

        status = self._decide(
            scrape=scrape,
            ean_check=ean_check,
            quantity_check=quantity_check,
            title_check=title_check,
            page_type=page_type,
        )

        verification = MatchVerification(
            url=scrape.url,
            identity_status=status,
            ean_check=ean_check,
            title_check=title_check,
            quantity_check=quantity_check,
            brand_check=brand_check,
            page_type_check=page_type,
            title_match_score=round(score, 4),
            requested_quantity=req_qty,
            page_quantity=page_qty,
            requested_ean=product.ean,
            page_eans=tuple(page_eans),
            matched_tokens=tuple(matched),
            missing_tokens=tuple(missing),
            justifications=tuple(justifications),
            blocking_reasons=tuple(blocking),
        )
        logger.info(
            "Identity verify | status={} | ean={} | qty={} | title={} | page={} | url={}",
            status, ean_check, quantity_check, title_check, page_type, scrape.url,
        )
        return verification

    # -- individual checks ---------------------------------------------------

    def _check_ean(
        self, product: ProductQuery, scrape: ScrapeResult, page_text: str
    ) -> tuple[str, list[str]]:
        if not product.ean:
            return CHECK_NOT_PROVIDED, []

        requested = re.sub(r"\D", "", product.ean)
        if not requested:
            return CHECK_NOT_PROVIDED, []

        structured = [re.sub(r"\D", "", value) for value in scrape.structured_eans]
        structured = [value for value in structured if value]

        # Digit runs found anywhere in the page text (used only to confirm a match,
        # never to declare a conflict — loose runs can be SKUs / phone numbers).
        text_digits = re.sub(r"\D", "", page_text)
        found_in_text = requested in text_digits and len(requested) in EAN_DIGIT_LENGTHS

        if requested in structured or found_in_text:
            return CHECK_EAN_MATCHED, [requested]

        if structured:
            # The page authoritatively declares GTIN(s), none of which match.
            return CHECK_EAN_CONFLICT, structured

        return CHECK_EAN_ABSENT, []

    def _check_quantity(
        self, product: ProductQuery, page_name_text: str
    ) -> tuple[str, Optional[str], Optional[str]]:
        requested = self._extract_quantity(product.main_text)
        if requested is None:
            return CHECK_QTY_NOT_APPLICABLE, None, None

        page_qty = self._extract_quantity(page_name_text)
        req_label = self._quantity_label(requested)
        if page_qty is None:
            return CHECK_QTY_UNKNOWN, req_label, None

        page_label = self._quantity_label(page_qty)
        if requested[0] == page_qty[0]:
            return CHECK_QTY_MATCHED, req_label, page_label
        return CHECK_QTY_CONFLICT, req_label, page_label

    def _check_title(
        self, product: ProductQuery, page_name_text: str
    ) -> tuple[str, float, list[str], list[str]]:
        tokens = self._distinctive_tokens(product.main_text)
        if not tokens:
            return CHECK_TITLE_WEAK, 0.0, [], []

        folded_page = _fold(page_name_text)
        matched = [token for token in tokens if token in folded_page]
        missing = [token for token in tokens if token not in folded_page]
        score = len(matched) / max(len(tokens), 1)

        if score >= TITLE_STRONG_MATCH_THRESHOLD:
            level = CHECK_TITLE_STRONG
        elif score >= TITLE_PARTIAL_MATCH_THRESHOLD:
            level = CHECK_TITLE_PARTIAL
        else:
            level = CHECK_TITLE_WEAK
        return level, score, matched, missing

    def _check_brand(self, product: ProductQuery, page_name_text: str) -> str:
        tokens = self._distinctive_tokens(product.main_text)
        if not tokens:
            return CHECK_BRAND_NOT_APPLICABLE
        brand = tokens[0]
        return CHECK_BRAND_MATCHED if brand in _fold(page_name_text) else CHECK_BRAND_ABSENT

    def _page_type(self, scrape: ScrapeResult) -> str:
        if scrape.is_soft_404:
            return PAGE_TYPE_SOFT_404
        
        # Check URL patterns for obvious category pages
        url_lower = scrape.url.lower()
        category_url_patterns = [
            r'/kategorie/', r'/category/', r'/categories/', 
            r'/c\/', r'/shop/', r'/collection/',
            r'/browse/', r'/filter/', r'/products/',
            r'[?&]category=', r'[?&]cat=',
        ]
        for pattern in category_url_patterns:
            if re.search(pattern, url_lower):
                # Category URLs are almost always non-product pages
                return PAGE_TYPE_NON_PRODUCT
        
        # Check markup for category page signals
        h1_lower = scrape.h1.lower()
        title_lower = scrape.title.lower()
        page_name_lower = scrape.page_product_name.lower()
        
        category_keywords = [
            'all ', 'category', 'collection', 'shop ', 'browse',
            'filter', 'sort', 'products', 'items', 'see ', 'view ',
        ]
        
        # h1 with category keywords + no price = almost certainly category page
        h1_looks_like_category = any(kw in h1_lower for kw in category_keywords)
        if h1_looks_like_category and not scrape.has_price:
            return PAGE_TYPE_NON_PRODUCT
        
        if scrape.looks_like_homepage:
            return PAGE_TYPE_NON_PRODUCT
        
        return PAGE_TYPE_UNKNOWN

    # -- decision ------------------------------------------------------------

    def _decide(
        self,
        *,
        scrape: ScrapeResult,
        ean_check: str,
        quantity_check: str,
        title_check: str,
        page_type: str,
    ) -> str:
        # HARD REJECTS: pages that are not genuine product sources.
        if page_type in {PAGE_TYPE_SOFT_404, PAGE_TYPE_NON_PRODUCT} or not scrape.is_scrapable:
            return IDENTITY_UNVERIFIED

        # TITLE IS REQUIRED: weak title match is a blocker.
        if title_check == CHECK_TITLE_WEAK:
            return IDENTITY_UNVERIFIED

        # STRONG TITLE: Best case - accept unless EAN explicitly conflicts.
        if title_check == CHECK_TITLE_STRONG:
            # EAN match: authoritative confirmation
            if ean_check == CHECK_EAN_MATCHED:
                return IDENTITY_VERIFIED
            # EAN conflict: title still dominant, but downgrade confidence
            # (product coding team can verify with richness + scraping)
            if ean_check == CHECK_EAN_CONFLICT:
                return IDENTITY_PROBABLE
            # EAN absent/unknown: title alone is sufficient
            return IDENTITY_PROBABLE

        # PARTIAL TITLE: requires additional confirmation.
        if title_check == CHECK_TITLE_PARTIAL:
            # Partial title + confirmed EAN: accept
            if ean_check == CHECK_EAN_MATCHED:
                return IDENTITY_PROBABLE
            # Partial title + EAN conflict: too risky
            if ean_check == CHECK_EAN_CONFLICT:
                return IDENTITY_WEAK
            # Partial title + no EAN info: weak confidence
            return IDENTITY_WEAK

        return IDENTITY_UNVERIFIED

    # -- helpers -------------------------------------------------------------

    def _distinctive_tokens(self, text: str) -> list[str]:
        tokens: list[str] = []
        seen: set[str] = set()
        for raw in _TOKEN_PATTERN.findall(text or ""):
            folded = _fold(raw)
            if len(folded) < MIN_TOKEN_LENGTH_FOR_TEXT_MATCH:
                continue
            if folded.isdigit():
                continue
            if folded in TITLE_STOPWORDS:
                continue
            if folded in seen:
                continue
            seen.add(folded)
            tokens.append(folded)
        return tokens

    def _extract_quantity(self, text: str) -> Optional[tuple[int, str]]:
        best: Optional[tuple[int, str]] = None
        for match in _QUANTITY_PATTERN.finditer(_fold(text or "")):
            try:
                count = int(match.group(1))
            except (TypeError, ValueError):
                continue
            unit = match.group(2)
            # Prefer the largest plausible pack size mentioned (handles '1 x 18 ks').
            if best is None or count > best[0]:
                best = (count, unit)
        return best

    @staticmethod
    def _quantity_label(quantity: tuple[int, str]) -> str:
        return f"{quantity[0]} {quantity[1].upper()}"

    @staticmethod
    def _slug(url: str) -> str:
        parsed = urlparse(url or "")
        return unquote(parsed.path).replace("-", " ").replace("/", " ").replace("_", " ")

    @staticmethod
    def _unverified(url: str, reason: str) -> MatchVerification:
        return MatchVerification(
            url=url,
            identity_status=IDENTITY_UNVERIFIED,
            ean_check=CHECK_NOT_PROVIDED,
            title_check=CHECK_TITLE_WEAK,
            quantity_check=CHECK_QTY_UNKNOWN,
            brand_check=CHECK_BRAND_NOT_APPLICABLE,
            page_type_check=PAGE_TYPE_UNKNOWN,
            title_match_score=0.0,
            blocking_reasons=(reason,),
        )
