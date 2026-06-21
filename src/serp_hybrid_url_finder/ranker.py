from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

from loguru import logger

from src.serp_hybrid_url_finder.constants import (
    AI_DECLARED_FINAL_SOURCE_SCORE,
    AI_EVIDENCE_FIELD_SCORES,
    AI_MATCH_DECISION_SCORES,
    CAP_DEAD_URL,
    CAP_EAN_UNCONFIRMED_ON_PAGE,
    CAP_IDENTITY_MISMATCH,
    CAP_IDENTITY_PROBABLE,
    CAP_IDENTITY_UNVERIFIED,
    CAP_IDENTITY_WEAK,
    CAP_NON_PRODUCT_PAGE,
    CAP_NOT_IN_CANDIDATES_OR_REFERENCES,
    CAP_NOT_SCRAPABLE,
    CAP_NOT_SCRAPED,
    CAP_OUT_OF_COUNTRY,
    CAP_RETAILER_ALTERNATIVE,
    CAP_UNJUSTIFIED_HIGH_CONFIDENCE,
    CHECK_EAN_ABSENT,
    CHECK_EAN_MATCHED,
    CONFIDENCE_ROUND_DIGITS,
    COUNTRY_CHECK_ALTERNATIVE,
    COUNTRY_CHECK_MATCHED,
    COUNTRY_CHECK_NOT_PROVIDED,
    COUNTRY_MATCH_THRESHOLD,
    DEFAULT_SCORE_WEIGHTS,
    EXACT_MATCH_CONFIDENCE_THRESHOLD,
    HIGH_CONFIDENCE_THRESHOLD,
    ID_REGEX,
    IDENTITY_MISMATCH,
    IDENTITY_PROBABLE,
    IDENTITY_SCORE_MAP,
    IDENTITY_UNVERIFIED,
    IDENTITY_VERIFIED,
    IDENTITY_WEAK,
    MIN_PRODUCT_PATH_SEGMENTS,
    MIN_TOKEN_LENGTH_FOR_TEXT_MATCH,
    NEUTRAL_OPTIONAL_SIGNAL_SCORE,
    NON_PRODUCT_PATH_KEYWORDS,
    NON_PRODUCT_PENALTY,
    NON_PRODUCT_SHAPE_SCORE,
    NON_REFERENCE_SOURCE_SCORE,
    ORGANIC_SOURCE_SCORE_OTHER,
    ORGANIC_SOURCE_SCORE_POSITION_1,
    ORGANIC_SOURCE_SCORE_POSITION_2_TO_5,
    PATH_COUNTRY_SCORE,
    PERFECT_SCORE,
    PRODUCT_PAGE_MATCH_THRESHOLD,
    PRODUCT_PATH_KEYWORDS,
    PRODUCT_SHAPE_DEEP_PATH_SCORE,
    PRODUCT_SHAPE_ID_SCORE,
    PRODUCT_SHAPE_KEYWORD_SCORE,
    PRODUCT_SHAPE_SLUG_SCORE,
    REASON_COUNTRY_MATCHED,
    REASON_COUNTRY_WEAK,
    REASON_NOT_SCRAPABLE,
    REASON_NOT_SCRAPED,
    REASON_RETAILER_MATCHED,
    REASON_RETAILER_WEAK,
    REASON_SCRAPABLE,
    AI_REFERENCE_SOURCE_SCORE,
    RETAILER_CHECK_ALTERNATIVE,
    RETAILER_CHECK_MATCHED,
    RETAILER_CHECK_NOT_PROVIDED,
    RETAILER_MATCH_THRESHOLD,
    SCORE_KEY_AI_EVIDENCE,
    SCORE_KEY_COUNTRY,
    SCORE_KEY_EAN,
    SCORE_KEY_IDENTITY,
    SCORE_KEY_MAIN_TEXT,
    SCORE_KEY_NON_PRODUCT_PENALTY,
    SCORE_KEY_ORGANIC_CONSENSUS,
    SCORE_KEY_PRODUCT_PAGE_SHAPE,
    SCORE_KEY_RETAILER,
    SCORE_KEY_SCRAPE,
    SCORE_KEY_SOURCE_TYPE,
    SLUG_REGEX,
    TOKEN_REGEX,
    URL_SOURCE_AI_DECLARED_FINAL,
    URL_SOURCE_AI_REFERENCE,
    URL_SOURCE_ORGANIC_1,
    URL_SOURCE_ORGANIC_2,
    VALIDATION_NEEDS_REVIEW,
    VALIDATION_REJECTED,
    VALIDATION_VERIFIED,
    WEAK_COUNTRY_SCORE,
    ZERO_SCORE,
    ScoreWeights,
)
from src.serp_hybrid_url_finder.models import (
    AIMatchEvidence,
    ConfidenceBreakdown,
    ConfidenceComponent,
    MatchVerification,
    ProductQuery,
    ScoredURLCandidate,
    ScrapeResult,
    URLCandidate,
)

_TOKEN_PATTERN = re.compile(TOKEN_REGEX)


@dataclass(frozen=True)
class ProductURLRanker:
    """Deterministic evidence ranker."""

    product_path_keywords: tuple[str, ...] = PRODUCT_PATH_KEYWORDS
    non_product_path_keywords: tuple[str, ...] = NON_PRODUCT_PATH_KEYWORDS
    weights: ScoreWeights = DEFAULT_SCORE_WEIGHTS

    def score(
        self,
        *,
        product: ProductQuery,
        candidates: List[URLCandidate],
        ai_evidence: AIMatchEvidence,
        scrapes: dict[str, ScrapeResult],
        verifications: Optional[dict[str, MatchVerification]] = None,
    ) -> List[ScoredURLCandidate]:
        verifications = verifications or {}
        scored = [
            self._score_one(
                product=product,
                candidate=candidate,
                ai_evidence=ai_evidence,
                scrape=scrapes.get(candidate.url),
                verification=verifications.get(candidate.url),
            )
            for candidate in candidates
        ]
        # Order so the richest CORRECT + in-scope page wins: identity gate first,
        # then scrapability, then in-country, then richness, then confidence.
        scored.sort(key=self._sort_key, reverse=True)
        logger.info("Ranked {} candidate(s)", len(scored))
        return scored

    def _score_one(
        self,
        *,
        product: ProductQuery,
        candidate: URLCandidate,
        ai_evidence: AIMatchEvidence,
        scrape: Optional[ScrapeResult],
        verification: Optional[MatchVerification],
    ) -> ScoredURLCandidate:
        evidence_text = unquote(candidate.evidence_text()).lower()
        breakdown: Dict[str, float] = {}

        organic_score = self._organic_consensus_score(candidate)
        ai_score = self._ai_evidence_score(candidate, ai_evidence)
        retailer_score = self._retailer_score(product, candidate)
        retailer_check = self._retailer_check(product, retailer_score)
        country_score = self._country_score(product, candidate.url)
        country_check = self._country_check(product, country_score)
        ean_score = self._ean_score(product, evidence_text, ai_evidence, scrape, verification)
        text_score = self._text_similarity_score(product.main_text, evidence_text, scrape)
        product_page_score = self._product_page_score(candidate.url, ai_evidence, scrape)
        source_score = self._source_score(candidate)
        penalty = self._non_product_penalty(candidate.url)
        scrape_score = self._scrape_score(scrape)
        identity_score = self._identity_score(verification)

        breakdown[SCORE_KEY_ORGANIC_CONSENSUS] = organic_score
        breakdown[SCORE_KEY_AI_EVIDENCE] = ai_score
        breakdown[SCORE_KEY_RETAILER] = retailer_score
        breakdown[SCORE_KEY_COUNTRY] = country_score
        breakdown[SCORE_KEY_EAN] = ean_score
        breakdown[SCORE_KEY_MAIN_TEXT] = text_score
        breakdown[SCORE_KEY_PRODUCT_PAGE_SHAPE] = product_page_score
        breakdown[SCORE_KEY_SOURCE_TYPE] = source_score
        breakdown[SCORE_KEY_NON_PRODUCT_PENALTY] = penalty
        breakdown[SCORE_KEY_SCRAPE] = scrape_score
        breakdown[SCORE_KEY_IDENTITY] = identity_score

        weights = self.weights
        base_confidence = (
            weights.organic_consensus * organic_score
            + weights.ai_evidence * ai_score
            + weights.retailer * retailer_score
            + weights.country * country_score
            + weights.ean * ean_score
            + weights.main_text * text_score
            + weights.product_page_shape * product_page_score
            + source_score
            + weights.scrape * scrape_score
            + weights.identity * identity_score
            - penalty
        )
        base_confidence = max(ZERO_SCORE, min(PERFECT_SCORE, base_confidence))

        confidence, caps_applied = self._apply_caps(
            confidence=base_confidence,
            product=product,
            candidate=candidate,
            ean_score=ean_score,
            retailer_score=retailer_score,
            retailer_check=retailer_check,
            country_score=country_score,
            country_check=country_check,
            product_page_score=product_page_score,
            scrape=scrape,
            verification=verification,
            ai_evidence=ai_evidence,
        )
        confidence = round(confidence, CONFIDENCE_ROUND_DIGITS)

        validation_status = self._validation_status(confidence, verification)

        exact = (
            confidence >= EXACT_MATCH_CONFIDENCE_THRESHOLD
            and verification is not None
            and verification.identity_status == IDENTITY_VERIFIED
            and bool(scrape and scrape.is_scrapable)
        )

        reason = self._build_reason(product, breakdown, candidate, scrape, verification, ai_evidence)
        confidence_breakdown = self._build_breakdown(
            base_confidence=base_confidence,
            final_confidence=confidence,
            validation_status=validation_status,
            weights=weights,
            scores={
                SCORE_KEY_IDENTITY: identity_score,
                SCORE_KEY_EAN: ean_score,
                SCORE_KEY_MAIN_TEXT: text_score,
                SCORE_KEY_AI_EVIDENCE: ai_score,
                SCORE_KEY_PRODUCT_PAGE_SHAPE: product_page_score,
                SCORE_KEY_SCRAPE: scrape_score,
                SCORE_KEY_ORGANIC_CONSENSUS: organic_score,
                SCORE_KEY_RETAILER: retailer_score,
                SCORE_KEY_COUNTRY: country_score,
            },
            caps_applied=caps_applied,
            verification=verification,
        )

        return ScoredURLCandidate(
            candidate=candidate,
            confidence=confidence,
            is_exact_product_match=exact,
            reason=reason,
            score_breakdown=breakdown,
            scrape=scrape,
            verification=verification,
            confidence_breakdown=confidence_breakdown,
            retailer_check=retailer_check,
            country_check=country_check,
        )

    def _identity_score(self, verification: Optional[MatchVerification]) -> float:
        if verification is None:
            return 0.30
        return IDENTITY_SCORE_MAP.get(verification.identity_status, 0.15)

    @staticmethod
    def _identity_rank(verification: Optional[MatchVerification]) -> int:
        if verification is None:
            return 1
        return {
            IDENTITY_VERIFIED: 4,
            IDENTITY_PROBABLE: 3,
            IDENTITY_WEAK: 2,
            IDENTITY_UNVERIFIED: 1,
            IDENTITY_MISMATCH: 0,
        }.get(verification.identity_status, 1)

    def _sort_key(
        self, item: ScoredURLCandidate
    ) -> tuple[int, int, int, float, float]:
        """Ranking key (all descending): correct identity, then scrapable, then
        in-country, then richest extractable content (weighted when scrapable),
        then confidence."""
        scrapable = 1 if (item.scrape and item.scrape.is_scrapable) else 0
        in_country = 0 if item.country_check == COUNTRY_CHECK_ALTERNATIVE else 1
        richness = item.scrape.richness_score if item.scrape else 0.0
        
        # When the URL is scrapable, weight richness heavily (x100) so it dominates 
        # over confidence. Even tiny richness differences (0.05 vs 0.06 → 5 vs 6)
        # will outweigh large confidence differences.
        richness_weighted = richness * 100 if scrapable else richness
        
        return (
            self._identity_rank(item.verification),
            scrapable,
            in_country,
            richness_weighted,
            item.confidence,
        )

    def _organic_consensus_score(self, candidate: URLCandidate) -> float:
        score = min(1.0, candidate.organic_count / 2)
        if candidate.best_position == 1:
            score = max(score, 0.90)
        elif candidate.best_position and candidate.best_position <= 5:
            score = max(score, 0.70)
        return score

    def _ai_evidence_score(self, candidate: URLCandidate, evidence: AIMatchEvidence) -> float:
        decision_score = AI_MATCH_DECISION_SCORES.get(evidence.match_decision.upper(), 0.0)
        ean_score = AI_EVIDENCE_FIELD_SCORES.get(evidence.ean_evidence.lower(), 0.0)
        title_score = AI_EVIDENCE_FIELD_SCORES.get(evidence.title_evidence.lower(), 0.0)
        retailer_score = AI_EVIDENCE_FIELD_SCORES.get(evidence.retailer_evidence.lower(), 0.0)
        country_score = AI_EVIDENCE_FIELD_SCORES.get(evidence.country_evidence.lower(), 0.0)
        page_score = AI_EVIDENCE_FIELD_SCORES.get(evidence.product_page_evidence.lower(), 0.0)

        selected_bonus = 0.0
        if evidence.final_url and self._same_url_or_domain_path(evidence.final_url, candidate.url):
            selected_bonus = 0.15

        return min(
            1.0,
            0.30 * decision_score
            + 0.18 * ean_score
            + 0.18 * title_score
            + 0.14 * retailer_score
            + 0.08 * country_score
            + 0.12 * page_score
            + selected_bonus,
        )

    def _retailer_score(self, product: ProductQuery, candidate: URLCandidate) -> float:
        if not product.retailer_name:
            return NEUTRAL_OPTIONAL_SIGNAL_SCORE

        retailer_tokens = self._tokens(product.retailer_name)
        if not retailer_tokens:
            return NEUTRAL_OPTIONAL_SIGNAL_SCORE

        text = " ".join([candidate.domain, candidate.title, candidate.snippet, candidate.url]).lower()
        matches = sum(1 for token in retailer_tokens if token in text)
        return matches / max(len(retailer_tokens), 1)

    def _retailer_check(self, product: ProductQuery, retailer_score: float) -> str:
        if not product.retailer_name:
            return RETAILER_CHECK_NOT_PROVIDED
        if retailer_score >= RETAILER_MATCH_THRESHOLD:
            return RETAILER_CHECK_MATCHED
        return RETAILER_CHECK_ALTERNATIVE

    def _country_score(self, product: ProductQuery, url: str) -> float:
        if not product.country_code:
            return NEUTRAL_OPTIONAL_SIGNAL_SCORE

        country = product.country_code.lower().strip()
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path.lower()

        if domain.endswith(f".{country}"):
            return PERFECT_SCORE
        if f".com.{country}" in domain or f".co.{country}" in domain:
            return PERFECT_SCORE
        if f"/{country}/" in path or f"-{country}-" in path or f"_{country}_" in path:
            return PATH_COUNTRY_SCORE
        return WEAK_COUNTRY_SCORE

    def _country_check(self, product: ProductQuery, country_score: float) -> str:
        if not product.country_code:
            return COUNTRY_CHECK_NOT_PROVIDED
        if country_score >= COUNTRY_MATCH_THRESHOLD:
            return COUNTRY_CHECK_MATCHED
        return COUNTRY_CHECK_ALTERNATIVE

    def _ean_score(
        self,
        product: ProductQuery,
        evidence_text: str,
        ai_evidence: AIMatchEvidence,
        scrape: Optional[ScrapeResult],
        verification: Optional[MatchVerification],
    ) -> float:
        if not product.ean:
            return NEUTRAL_OPTIONAL_SIGNAL_SCORE

        # Verified EAN match on the scraped page is the strongest possible signal.
        if verification and verification.ean_check == CHECK_EAN_MATCHED:
            return PERFECT_SCORE

        if scrape and scrape.contains_ean:
            return PERFECT_SCORE

        if ai_evidence.ean_evidence == "matched":
            return 0.85

        ean = re.sub(r"\D", "", product.ean)
        if not ean:
            return NEUTRAL_OPTIONAL_SIGNAL_SCORE
        compact_evidence = re.sub(r"\D", "", evidence_text)
        return PERFECT_SCORE if ean in compact_evidence else ZERO_SCORE

    def _text_similarity_score(
        self,
        main_text: str,
        evidence_text: str,
        scrape: Optional[ScrapeResult],
    ) -> float:
        base = self._token_overlap(main_text, evidence_text)
        if scrape:
            base = max(base, scrape.text_overlap)
        return base

    def _product_page_score(
        self,
        url: str,
        ai_evidence: AIMatchEvidence,
        scrape: Optional[ScrapeResult],
    ) -> float:
        parsed = urlparse(url)
        path = parsed.path.lower()
        query = parsed.query.lower()
        full = f"{path}?{query}"

        if any(bad in full for bad in self.non_product_path_keywords):
            return NON_PRODUCT_SHAPE_SCORE

        if scrape and scrape.looks_like_product_page:
            return PERFECT_SCORE

        if ai_evidence.product_page_evidence == "product_detail":
            ai_page_score = 0.85
        elif ai_evidence.product_page_evidence in {"category", "search", "homepage", "listing"}:
            ai_page_score = 0.0
        else:
            ai_page_score = 0.0

        keyword_hit = any(keyword in full for keyword in self.product_path_keywords)
        has_deep_path = len([segment for segment in path.split("/") if segment]) >= MIN_PRODUCT_PATH_SEGMENTS
        has_slug = bool(re.search(SLUG_REGEX, path))
        has_id = bool(re.search(ID_REGEX, path))

        score = ZERO_SCORE
        if keyword_hit:
            score += PRODUCT_SHAPE_KEYWORD_SCORE
        if has_deep_path:
            score += PRODUCT_SHAPE_DEEP_PATH_SCORE
        if has_slug:
            score += PRODUCT_SHAPE_SLUG_SCORE
        if has_id:
            score += PRODUCT_SHAPE_ID_SCORE

        return min(PERFECT_SCORE, max(score, ai_page_score))

    def _source_score(self, candidate: URLCandidate) -> float:
        score = 0.0
        if candidate.ai_declared_final or URL_SOURCE_AI_DECLARED_FINAL in candidate.source_types:
            score = max(score, AI_DECLARED_FINAL_SOURCE_SCORE)
        if URL_SOURCE_AI_REFERENCE in candidate.source_types:
            score = max(score, AI_REFERENCE_SOURCE_SCORE)
        if URL_SOURCE_ORGANIC_1 in candidate.source_types or URL_SOURCE_ORGANIC_2 in candidate.source_types:
            if candidate.best_position == 1:
                score = max(score, ORGANIC_SOURCE_SCORE_POSITION_1)
            elif candidate.best_position and candidate.best_position <= 5:
                score = max(score, ORGANIC_SOURCE_SCORE_POSITION_2_TO_5)
            else:
                score = max(score, ORGANIC_SOURCE_SCORE_OTHER)
        return max(score, NON_REFERENCE_SOURCE_SCORE)

    def _scrape_score(self, scrape: Optional[ScrapeResult]) -> float:
        if scrape is None or not scrape.scraped:
            return 0.50
        if not scrape.is_scrapable:
            return ZERO_SCORE
        if scrape.looks_like_product_page:
            return PERFECT_SCORE
        if scrape.looks_like_homepage:
            return 0.10
        return 0.60

    def _non_product_penalty(self, url: str) -> float:
        parsed = urlparse(url)
        full = f"{parsed.path.lower()}?{parsed.query.lower()}"
        return NON_PRODUCT_PENALTY if any(term in full for term in self.non_product_path_keywords) else ZERO_SCORE

    def _apply_caps(
        self,
        *,
        confidence: float,
        product: ProductQuery,
        candidate: URLCandidate,
        ean_score: float,
        retailer_score: float,
        retailer_check: str,
        country_score: float,
        country_check: str,
        product_page_score: float,
        scrape: Optional[ScrapeResult],
        verification: Optional[MatchVerification],
        ai_evidence: AIMatchEvidence,
    ) -> tuple[float, list[Dict[str, Any]]]:
        capped = confidence
        caps_applied: list[Dict[str, Any]] = []

        def cap(value: float, reason: str) -> None:
            nonlocal capped
            if value < capped:
                capped = value
                caps_applied.append({"cap": round(value, 3), "reason": reason})

        # 1. Identity is the dominant hard gate: a returned URL must be the
        #    CORRECT product, not just a scrapable page.
        status = verification.identity_status if verification else None
        if status == IDENTITY_MISMATCH:
            reasons = "; ".join(verification.blocking_reasons) if verification else "identity mismatch"
            cap(CAP_IDENTITY_MISMATCH, f"identity MISMATCH ({reasons})")
        elif status == IDENTITY_UNVERIFIED or verification is None:
            cap(CAP_IDENTITY_UNVERIFIED, "product identity could not be verified on scraped content")
        elif status == IDENTITY_WEAK:
            cap(CAP_IDENTITY_WEAK, "only partial product-identity corroboration")
        elif status == IDENTITY_PROBABLE:
            cap(CAP_IDENTITY_PROBABLE, "probable match (not EAN-proven) — needs review")

        # 2. EAN provided but not confirmed on the scraped page.
        if product.ean and verification is not None and verification.ean_check in {CHECK_EAN_ABSENT}:
            cap(CAP_EAN_UNCONFIRMED_ON_PAGE, "requested EAN not confirmed on the scraped page")

        # 3. Retailer preference. When the requested retailer does not carry the
        #    product, an ALTERNATIVE retailer with the correct product is still a
        #    valid answer — but it stays in the review band (never silently
        #    treated as the requested retailer). The hard-requirement enforcement
        #    (rejecting alternatives outright) is applied in the pipeline.
        if retailer_check == RETAILER_CHECK_ALTERNATIVE:
            cap(
                CAP_RETAILER_ALTERNATIVE,
                "requested retailer not found; this is an ALTERNATIVE retailer (review recommended)",
            )

        # 4. Country preference. When the requested country has no suitable URL,
        #    an ALTERNATIVE country's URL is still acceptable — but forced into
        #    the review band. The hard-requirement enforcement is applied in the pipeline.
        if country_check == COUNTRY_CHECK_ALTERNATIVE:
            cap(
                CAP_OUT_OF_COUNTRY,
                "out-of-country result (requested country not matched); small honesty penalty",
            )

        # 5. Scrapability gate.
        if scrape is None or not scrape.scraped:
            cap(CAP_NOT_SCRAPED, "candidate was not scraped with crawl4ai")
        elif not scrape.is_scrapable:
            cap(CAP_NOT_SCRAPABLE, "crawl4ai could not scrape usable content")
        elif not scrape.reachable:
            cap(CAP_DEAD_URL, "scraped URL was not reachable")
        elif scrape.looks_like_homepage:
            cap(CAP_NON_PRODUCT_PAGE, "scraped URL resolved to a homepage")

        if product_page_score < PRODUCT_PAGE_MATCH_THRESHOLD:
            cap(CAP_NON_PRODUCT_PAGE, "URL shape is not product-detail-like")

        if ai_evidence.final_url and not self._same_url_or_domain_path(ai_evidence.final_url, candidate.url):
            if candidate.ai_declared_final:
                cap(CAP_NOT_IN_CANDIDATES_OR_REFERENCES, "AI final URL not corroborated by candidates")

        # 5. High confidence MUST be backed by hard justification.
        if capped >= HIGH_CONFIDENCE_THRESHOLD:
            has_hard = bool(verification and verification.has_hard_justification)
            if not has_hard:
                cap(
                    CAP_UNJUSTIFIED_HIGH_CONFIDENCE,
                    "high confidence requires hard justification (confirmed EAN, or matched "
                    "pack-size with strong title); none present",
                )

        return capped, caps_applied

    def _validation_status(
        self,
        confidence: float,
        verification: Optional[MatchVerification],
    ) -> str:
        status = verification.identity_status if verification else None
        if status == IDENTITY_VERIFIED and confidence >= HIGH_CONFIDENCE_THRESHOLD:
            return VALIDATION_VERIFIED
        if status in {IDENTITY_VERIFIED, IDENTITY_PROBABLE, IDENTITY_WEAK} and confidence > ZERO_SCORE:
            return VALIDATION_NEEDS_REVIEW
        return VALIDATION_REJECTED

    def _build_breakdown(
        self,
        *,
        base_confidence: float,
        final_confidence: float,
        validation_status: str,
        weights: Any,
        scores: Dict[str, float],
        caps_applied: list[Dict[str, Any]],
        verification: Optional[MatchVerification],
    ) -> ConfidenceBreakdown:
        weight_map = {
            SCORE_KEY_IDENTITY: weights.identity,
            SCORE_KEY_EAN: weights.ean,
            SCORE_KEY_MAIN_TEXT: weights.main_text,
            SCORE_KEY_AI_EVIDENCE: weights.ai_evidence,
            SCORE_KEY_PRODUCT_PAGE_SHAPE: weights.product_page_shape,
            SCORE_KEY_SCRAPE: weights.scrape,
            SCORE_KEY_ORGANIC_CONSENSUS: weights.organic_consensus,
            SCORE_KEY_RETAILER: weights.retailer,
            SCORE_KEY_COUNTRY: weights.country,
        }
        justify_map = {
            SCORE_KEY_IDENTITY: "Product-identity verdict from scraped content",
            SCORE_KEY_EAN: "EAN/GTIN evidence",
            SCORE_KEY_MAIN_TEXT: "Distinctive title-token overlap",
            SCORE_KEY_AI_EVIDENCE: "AI Mode validation evidence",
            SCORE_KEY_PRODUCT_PAGE_SHAPE: "Product-detail page shape",
            SCORE_KEY_SCRAPE: "crawl4ai scrape verdict",
            SCORE_KEY_ORGANIC_CONSENSUS: "Organic search corroboration",
            SCORE_KEY_RETAILER: "Retailer match",
            SCORE_KEY_COUNTRY: "Country signal",
        }
        components: list[ConfidenceComponent] = []
        for key, raw in scores.items():
            weight = weight_map.get(key, 0.0)
            components.append(
                ConfidenceComponent(
                    name=key,
                    raw_score=raw,
                    weight=weight,
                    contribution=raw * weight,
                    justification=justify_map.get(key, key),
                )
            )
        components.sort(key=lambda c: c.contribution, reverse=True)

        return ConfidenceBreakdown(
            base_confidence=base_confidence,
            final_confidence=final_confidence,
            validation_status=validation_status,
            components=tuple(components),
            caps_applied=tuple(caps_applied),
            justification_summary=self.build_justification(verification, validation_status),
        )

    def build_justification(
        self,
        verification: Optional[MatchVerification],
        validation_status: str,
    ) -> str:
        if verification is None:
            return "No scraped content was available to verify product identity."
        parts: list[str] = [f"Identity: {verification.identity_status}."]
        if verification.justifications:
            parts.append("Evidence: " + "; ".join(verification.justifications) + ".")
        if verification.blocking_reasons:
            parts.append("Concerns: " + "; ".join(verification.blocking_reasons) + ".")
        parts.append(f"Submission status: {validation_status}.")
        return " ".join(parts)

    def _build_reason(
        self,
        product: ProductQuery,
        breakdown: Dict[str, float],
        candidate: URLCandidate,
        scrape: Optional[ScrapeResult],
        verification: Optional[MatchVerification],
        ai_evidence: AIMatchEvidence,
    ) -> str:
        reasons: List[str] = []

        if verification is not None:
            reasons.append(f"identity={verification.identity_status}")
            reasons.append(f"ean_check={verification.ean_check}")
            reasons.append(f"qty_check={verification.quantity_check}")
            reasons.append(f"title_check={verification.title_check}")
            reasons.append(f"page_type={verification.page_type_check}")

        if product.retailer_name:
            if breakdown[SCORE_KEY_RETAILER] >= RETAILER_MATCH_THRESHOLD:
                reasons.append(REASON_RETAILER_MATCHED)
            else:
                reasons.append("retailer=ALTERNATIVE")
                reasons.append(REASON_RETAILER_WEAK)

        if product.country_code:
            reasons.append(REASON_COUNTRY_MATCHED if breakdown[SCORE_KEY_COUNTRY] >= COUNTRY_MATCH_THRESHOLD else REASON_COUNTRY_WEAK)

        if scrape is None or not scrape.scraped:
            reasons.append(REASON_NOT_SCRAPED)
        elif scrape.is_scrapable:
            reasons.append(REASON_SCRAPABLE)
            reasons.append(f"scrape_status={scrape.status_code}")
        else:
            reasons.append(REASON_NOT_SCRAPABLE)
            reasons.append(f"scrape_status={scrape.status_code}")

        reasons.append(f"ai_decision={ai_evidence.match_decision}")
        return "; ".join(reasons)

    def _token_overlap(self, main_text: str, evidence_text: str) -> float:
        query_tokens = [
            token
            for token in self._tokens(main_text)
            if len(token) >= MIN_TOKEN_LENGTH_FOR_TEXT_MATCH
        ]
        if not query_tokens:
            return ZERO_SCORE
        unique = set(query_tokens)
        evidence = (evidence_text or "").lower()
        matches = sum(1 for token in unique if token in evidence)
        return matches / max(len(unique), 1)

    def _tokens(self, text: str) -> List[str]:
        return [token.lower() for token in _TOKEN_PATTERN.findall(text or "")]

    def _same_url_or_domain_path(self, left: str, right: str) -> bool:
        left_p = urlparse(left)
        right_p = urlparse(right)
        left_domain = left_p.netloc.lower().replace("www.", "")
        right_domain = right_p.netloc.lower().replace("www.", "")
        return left_domain == right_domain and left_p.path.rstrip("/") == right_p.path.rstrip("/")
