from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from loguru import logger

from src.product_evidence_harness.config import HarnessPolicy
from src.product_evidence_harness.constants import (
    CHECK_ABSENT,
    CHECK_CONFLICT,
    CHECK_MATCHED,
    CHECK_NOT_APPLICABLE,
    CHECK_NOT_PROVIDED,
    CHECK_PARTIAL,
    CHECK_STRONG,
    CHECK_UNKNOWN,
    CHECK_WEAK,
    EXACT_PRODUCT_MATCH,
    EXACT_PRODUCT_MISMATCH,
    EXACT_PRODUCT_WEAK,
    IDENTITY_MISMATCH,
    IDENTITY_PROBABLE,
    IDENTITY_UNVERIFIED,
    IDENTITY_VERIFIED,
    IDENTITY_WEAK,
    LISTING_URL_HINTS,
    PAGE_TYPE_LISTING,
    PAGE_TYPE_NON_PRODUCT,
    PAGE_TYPE_PRODUCT_DETAIL,
    PAGE_TYPE_SOFT_404,
    PAGE_TYPE_UNKNOWN,
    PRODUCT_URL_HINTS,
    QUANTITY_REGEX,
    TITLE_STOPWORDS,
    TOKEN_REGEX,
    VARIANT_CONFLICT,
    VARIANT_CONFLICT_TERMS,
    VARIANT_MATCH,
    VARIANT_UNKNOWN,
)
from src.product_evidence_harness.contracts import MatchVerification, ProductQuery, ScrapeResult
from src.product_evidence_harness.gtin import compare_expected_to_page_gtins
from src.product_evidence_harness.identity.graph import ProductIdentityGraphBuilder
from src.product_evidence_harness.detectors.variants import VariantConflictDetector


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


@dataclass(frozen=True)
class ProductIdentityVerifier:
    policy: HarnessPolicy = HarnessPolicy()

    def __post_init__(self) -> None:
        object.__setattr__(self, "identity_builder", ProductIdentityGraphBuilder())
        object.__setattr__(self, "variant_detector", VariantConflictDetector())

    def verify(self, product: ProductQuery, scrape: Optional[ScrapeResult], *, identity_graph=None) -> MatchVerification:
        if scrape is None or not scrape.scraped:
            return self._unverified(scrape.url if scrape else "", "page was not scraped")

        page_text = scrape.verification_text or " ".join([scrape.page_product_name, scrape.title, scrape.h1, scrape.markdown_excerpt])
        page_name = " ".join([scrape.page_product_name, scrape.title, scrape.h1, self._slug(scrape.final_url or scrape.url)])

        ean_check, page_eans, gtin_cmp = self._check_ean(product, scrape, page_text)
        qty_check, req_qty, page_qty = self._check_quantity(product, page_name)
        title_check, title_score, matched, missing = self._check_title(product, page_name)
        identity_graph = identity_graph or self.identity_builder.build(product)
        detector_findings = self.variant_detector.analyze(identity_graph, " ".join([page_name, page_text[:8000]]))
        variant_check = VARIANT_CONFLICT if self.variant_detector.has_hard_conflict(detector_findings) else self._legacy_variant_status(product.main_text, page_name)
        variant_conflicts = list(self.variant_detector.conflict_labels(detector_findings))
        brand_check = self._check_brand(product, page_name)
        page_type = self._page_type(scrape)

        exact_product_check = self._exact_product_check(
            title_check=title_check,
            title_score=title_score,
            quantity_check=qty_check,
            variant_check=variant_check,
            page_type=page_type,
        )

        justifications: list[str] = []
        blockers: list[str] = []

        if ean_check == CHECK_MATCHED:
            justifications.append(f"EAN/GTIN {product.ean} confirmed")
        elif ean_check == CHECK_CONFLICT:
            msg = gtin_cmp.reason or f"page declares different valid GTIN(s): {', '.join(page_eans)}"
            # EAN is an anchor, not the sole authority. It becomes blocking only
            # when exact product identity is not independently strong.
            if exact_product_check == EXACT_PRODUCT_MATCH:
                justifications.append(f"warning: {msg}; kept because main_text/product-form evidence is exact")
            else:
                blockers.append(msg)
        elif ean_check == CHECK_ABSENT and product.ean:
            justifications.append(f"EAN/GTIN {product.ean} not found on page; using product text/form evidence")
        elif ean_check == CHECK_UNKNOWN and product.ean:
            justifications.append(gtin_cmp.reason)

        if qty_check == CHECK_MATCHED:
            justifications.append(f"pack size matches ({req_qty})")
        elif qty_check == CHECK_CONFLICT:
            msg = f"pack size conflict: requested {req_qty}, page {page_qty}"
            if self.policy.allow_pack_size_mismatch:
                justifications.append(f"warning: {msg}")
            else:
                blockers.append(msg)

        if variant_check == VARIANT_CONFLICT:
            blockers.append("variant/product-form conflict: " + ", ".join(variant_conflicts))
        elif variant_check == VARIANT_MATCH:
            justifications.append("variant/product-form evidence matches")

        if title_check == CHECK_STRONG:
            justifications.append(f"strong title token overlap ({len(matched)}/{max(1, len(matched)+len(missing))})")
        elif title_check == CHECK_PARTIAL:
            justifications.append(f"partial title token overlap ({len(matched)}/{max(1, len(matched)+len(missing))})")
        else:
            blockers.append("distinctive title tokens did not match")

        if page_type == PAGE_TYPE_SOFT_404:
            blockers.append("soft-404/product-not-found page")
        elif page_type in {PAGE_TYPE_NON_PRODUCT, PAGE_TYPE_LISTING}:
            blockers.append(f"not a product detail page ({page_type})")

        status, identity_driver = self._decide(
            scrape=scrape,
            ean_check=ean_check,
            quantity_check=qty_check,
            title_check=title_check,
            exact_product_check=exact_product_check,
            page_type=page_type,
            blockers=blockers,
        )
        verification = MatchVerification(
            url=scrape.url,
            identity_status=status,
            ean_check=ean_check,
            title_check=title_check,
            quantity_check=qty_check,
            brand_check=brand_check,
            page_type_check=page_type,
            title_match_score=title_score,
            exact_product_check=exact_product_check,
            variant_check=variant_check,
            variant_conflict_terms=tuple(variant_conflicts),
            identity_driver=identity_driver,
            ean_status=gtin_cmp.status,
            ean_conflict_is_blocking=bool(ean_check == CHECK_CONFLICT and exact_product_check != EXACT_PRODUCT_MATCH),
            input_ean_valid=gtin_cmp.requested_valid if product.ean else None,
            input_ean_normalized=gtin_cmp.requested_normalized,
            page_gtins_valid=gtin_cmp.page_gtins_valid,
            page_gtins_ignored=gtin_cmp.page_gtins_ignored,
            requested_quantity=req_qty,
            page_quantity=page_qty,
            requested_ean=product.ean,
            page_eans=tuple(page_eans),
            matched_tokens=tuple(matched),
            missing_tokens=tuple(missing),
            justifications=tuple(justifications),
            blocking_reasons=tuple(blockers),
            detector_findings=tuple(f.to_dict() for f in detector_findings),
        )
        logger.info(
            "Identity verification | status={} | exact={} | variant={} | ean={} | qty={} | title={} | page={} | url={}",
            status, exact_product_check, variant_check, ean_check, qty_check, title_check, page_type, scrape.url,
        )
        return verification

    def _decide(self, *, scrape: ScrapeResult, ean_check: str, quantity_check: str, title_check: str, exact_product_check: str, page_type: str, blockers: list[str]) -> tuple[str, str]:
        if not scrape.is_scrapable:
            return IDENTITY_UNVERIFIED, "SCRAPE_UNUSABLE"
        if blockers:
            return IDENTITY_MISMATCH, "BLOCKING_EXACT_PRODUCT_FAILURE"
        if exact_product_check == EXACT_PRODUCT_MATCH:
            if ean_check == CHECK_MATCHED:
                return IDENTITY_VERIFIED, "MAIN_TEXT_VARIANT_AND_EAN"
            return IDENTITY_VERIFIED, "MAIN_TEXT_AND_VARIANT"
        if title_check == CHECK_STRONG and page_type in {PAGE_TYPE_PRODUCT_DETAIL, PAGE_TYPE_UNKNOWN}:
            return IDENTITY_PROBABLE, "STRONG_TEXT_BUT_NOT_EXACT"
        if title_check == CHECK_PARTIAL:
            return IDENTITY_WEAK, "PARTIAL_TEXT"
        return IDENTITY_UNVERIFIED, "INSUFFICIENT_IDENTITY_EVIDENCE"

    def _exact_product_check(self, *, title_check: str, title_score: float, quantity_check: str, variant_check: str, page_type: str) -> str:
        if page_type in {PAGE_TYPE_LISTING, PAGE_TYPE_NON_PRODUCT, PAGE_TYPE_SOFT_404}:
            return EXACT_PRODUCT_MISMATCH
        if variant_check == VARIANT_CONFLICT:
            return EXACT_PRODUCT_MISMATCH
        if quantity_check == CHECK_CONFLICT and not self.policy.allow_pack_size_mismatch:
            return EXACT_PRODUCT_MISMATCH
        if title_check == CHECK_STRONG and title_score >= self.policy.min_exact_title_overlap:
            return EXACT_PRODUCT_MATCH
        if title_check in {CHECK_STRONG, CHECK_PARTIAL}:
            return EXACT_PRODUCT_WEAK
        return EXACT_PRODUCT_MISMATCH

    def _check_ean(self, product: ProductQuery, scrape: ScrapeResult, page_text: str):
        cmp = compare_expected_to_page_gtins(
            product.ean,
            structured_values=scrape.structured_eans,
            page_text=page_text,
        )
        if not product.ean:
            return CHECK_NOT_PROVIDED, [], cmp
        if not cmp.requested_valid:
            return CHECK_UNKNOWN, list(cmp.page_gtins_valid), cmp
        if cmp.match:
            return CHECK_MATCHED, list(cmp.page_gtins_valid or (cmp.requested_normalized,)), cmp
        if cmp.conflict:
            return CHECK_CONFLICT, list(cmp.page_gtins_valid), cmp
        return CHECK_ABSENT, [], cmp

    def _check_quantity(self, product: ProductQuery, page_name: str) -> tuple[str, Optional[str], Optional[str]]:
        requested = self._extract_qty(product.main_text)
        if requested is None:
            return CHECK_NOT_APPLICABLE, None, None
        page_qty = self._extract_qty(page_name)
        requested_label = f"{requested[0]} {requested[1]}"
        if page_qty is None:
            return CHECK_UNKNOWN, requested_label, None
        page_label = f"{page_qty[0]} {page_qty[1]}"
        return (CHECK_MATCHED if requested[0] == page_qty[0] else CHECK_CONFLICT), requested_label, page_label

    def _check_title(self, product: ProductQuery, page_name: str) -> tuple[str, float, list[str], list[str]]:
        tokens = self._tokens(product.main_text)
        if not tokens:
            return CHECK_WEAK, 0.0, [], []
        folded_page = _fold(page_name)
        matched = [t for t in tokens if t in folded_page]
        missing = [t for t in tokens if t not in folded_page]
        score = round(len(matched) / max(1, len(tokens)), 4)
        if score >= self.policy.min_exact_title_overlap:
            level = CHECK_STRONG
        elif score >= self.policy.min_title_overlap:
            level = CHECK_PARTIAL
        else:
            level = CHECK_WEAK
        return level, score, matched, missing

    def _legacy_variant_status(self, requested_text: str, page_name: str) -> str:
        req = _fold(requested_text)
        page = _fold(page_name)
        if not page:
            return VARIANT_UNKNOWN
        # Legacy generic sibling-variant guard, kept as a supplemental detector.
        for term in VARIANT_CONFLICT_TERMS:
            folded_term = _fold(term)
            req_has = self._contains_phrase(req, folded_term)
            page_has = self._contains_phrase(page, folded_term)
            if req_has != page_has:
                return VARIANT_CONFLICT
        return VARIANT_MATCH

    def _check_brand(self, product: ProductQuery, page_name: str) -> str:
        tokens = self._tokens(product.main_text)
        if not tokens:
            return CHECK_NOT_APPLICABLE
        return CHECK_MATCHED if tokens[0] in _fold(page_name) else CHECK_ABSENT

    def _page_type(self, scrape: ScrapeResult) -> str:
        if scrape.is_soft_404:
            return PAGE_TYPE_SOFT_404
        url = (scrape.final_url or scrape.url or "").lower()
        if any(h in url for h in LISTING_URL_HINTS):
            return PAGE_TYPE_LISTING
        if scrape.looks_like_product_page or any(h in url for h in PRODUCT_URL_HINTS):
            return PAGE_TYPE_PRODUCT_DETAIL
        if scrape.looks_like_homepage:
            return PAGE_TYPE_NON_PRODUCT
        return PAGE_TYPE_UNKNOWN

    def _extract_qty(self, text: str) -> Optional[tuple[str, str]]:
        m = re.search(QUANTITY_REGEX, _fold(text or ""), flags=re.I)
        if not m:
            return None
        return m.group(1), m.group(2).lower()

    def _tokens(self, text: str) -> list[str]:
        folded = _fold(self._segment_compact_text(text))
        tokens = []
        for token in re.findall(TOKEN_REGEX, folded):
            is_format = bool(re.fullmatch(r"[abc]\d", token))
            if (len(token) < 3 and not is_format) or token in TITLE_STOPWORDS or token.isdigit():
                continue
            tokens.append(token)
        return list(dict.fromkeys(tokens))[:12]

    def _segment_compact_text(self, text: str) -> str:
        t = str(text or "")
        t = re.sub(r"([A-Za-zÀ-ž]+)([ABCabc][0-9])([A-Za-zÀ-ž]+)", r"\1 \2 \3", t)
        t = re.sub(r"(\d)([A-Za-zÀ-ž])", r"\1 \2", t)
        t = re.sub(r"([A-Za-zÀ-ž])(\d)", r"\1 \2", t)
        t = re.sub(r"[_/\-]+", " ", t)
        return " ".join(t.split())

    def _contains_phrase(self, text: str, phrase: str) -> bool:
        # Word-ish boundaries that work for accented Latin text after folding.
        escaped = re.escape(phrase)
        return bool(re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text))

    def _slug(self, url: str) -> str:
        return re.sub(r"[-_/]+", " ", urlparse(url or "").path)

    def _unverified(self, url: str, reason: str) -> MatchVerification:
        return MatchVerification(
            url=url,
            identity_status=IDENTITY_UNVERIFIED,
            ean_check=CHECK_UNKNOWN,
            title_check=CHECK_WEAK,
            quantity_check=CHECK_UNKNOWN,
            brand_check=CHECK_UNKNOWN,
            page_type_check=PAGE_TYPE_UNKNOWN,
            title_match_score=0.0,
            exact_product_check=EXACT_PRODUCT_WEAK,
            identity_driver="SCRAPE_UNUSABLE",
            blocking_reasons=(reason,),
        )
