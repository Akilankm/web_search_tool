from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from urllib.parse import urlparse

from src.product_evidence_harness.config import HarnessPolicy
from src.product_evidence_harness.constants import (
    CHECK_ABSENT,
    CHECK_CONFLICT,
    CHECK_MATCHED,
    CHECK_NOT_PROVIDED,
    CHECK_PARTIAL,
    CHECK_STRONG,
    COUNTRY_ALTERNATIVE,
    COUNTRY_MATCHED,
    COUNTRY_NOT_PROVIDED,
    DEFAULT_SCORE_WEIGHTS,
    IDENTITY_MISMATCH,
    IDENTITY_PROBABLE,
    IDENTITY_UNVERIFIED,
    IDENTITY_VERIFIED,
    IDENTITY_WEAK,
    PAGE_TYPE_LISTING,
    PAGE_TYPE_NON_PRODUCT,
    PAGE_TYPE_PRODUCT_DETAIL,
    PAGE_TYPE_SOFT_404,
    RETAILER_ALTERNATIVE,
    RETAILER_MATCHED,
    RETAILER_NOT_PROVIDED,
    VALIDATION_NEEDS_REVIEW,
    VALIDATION_REJECTED,
    VALIDATION_VERIFIED,
    ScoreWeights,
)
from src.product_evidence_harness.contracts import CandidateScorecard, MatchVerification, ProductQuery, ScrapeResult, URLCandidate
from src.product_evidence_harness.country_profiles import CountryProfileRegistry
from src.product_evidence_harness.gtin import equivalent_gtins


@dataclass(frozen=True)
class ProductURLRanker:
    weights: ScoreWeights = DEFAULT_SCORE_WEIGHTS
    policy: HarnessPolicy = HarnessPolicy()
    country_profiles: CountryProfileRegistry = field(default_factory=CountryProfileRegistry.load)

    def score(self, *, product: ProductQuery, candidates: list[URLCandidate], scrapes: dict[str, ScrapeResult], verifications: dict[str, MatchVerification]) -> list[CandidateScorecard]:
        cards = [self._score_one(product, c, scrapes.get(c.url), verifications.get(c.url)) for c in candidates]
        return sorted(cards, key=self._sort_key, reverse=True)

    def _score_one(self, product: ProductQuery, candidate: URLCandidate, scrape: ScrapeResult | None, verification: MatchVerification | None) -> CandidateScorecard:
        evidence = " ".join([candidate.evidence_text(), scrape.verification_text if scrape else ""])
        organic = min(1.0, 0.35 * candidate.organic_count + (0.40 if candidate.best_position and candidate.best_position <= 3 else 0.0))
        ai = min(1.0, (0.75 if candidate.ai_declared_final else 0.0) + 0.25 * candidate.ai_reference_count)
        retailer_check, retailer = self._retailer_score(product, candidate)
        country_check, country = self._country_score(product, candidate)
        ean = self._ean_score(product, evidence, verification)
        title = max(self._token_overlap(product.main_text, candidate.evidence_text()), verification.title_match_score if verification else 0.0, scrape.text_overlap if scrape else 0.0)
        page_type = self._page_type_score(candidate, scrape, verification)
        scrape_score = 1.0 if scrape and scrape.is_scrapable else 0.0
        identity = self._identity_score(verification)
        richness = scrape.richness_score if scrape else 0.0

        base = (
            self.weights.organic * organic + self.weights.ai * ai + self.weights.retailer * retailer +
            self.weights.country * country + self.weights.ean * ean + self.weights.title * title +
            self.weights.page_type * page_type + self.weights.scrape * scrape_score +
            self.weights.identity * identity + self.weights.richness * richness
        ) / sum(self.weights.__dict__.values())

        hard: list[str] = []
        warn: list[str] = []
        cap = 1.0

        if verification:
            if verification.identity_status == IDENTITY_MISMATCH:
                hard.extend(verification.blocking_reasons or ("identity mismatch",))
                cap = min(cap, 0.05)
            elif verification.identity_status == IDENTITY_UNVERIFIED:
                warn.append("identity unverified")
                cap = min(cap, 0.25)
            elif verification.identity_status == IDENTITY_WEAK:
                warn.append("weak identity evidence")
                cap = min(cap, 0.50)
            elif verification.identity_status == IDENTITY_PROBABLE:
                cap = min(cap, 0.74)
            if verification.ean_check == CHECK_CONFLICT:
                if verification.ean_conflict_is_blocking or not self.policy.allow_ean_conflict:
                    hard.append("EAN conflict blocks candidate because exact product identity is not established")
                    cap = min(cap, 0.05)
                else:
                    warn.append("retailer/page EAN conflicts with input; kept only because exact product text/form matches")
                    cap = min(cap, self.policy.ean_conflict_confidence_cap)
            if verification.quantity_check == CHECK_CONFLICT and not self.policy.allow_pack_size_mismatch:
                hard.append("pack-size conflict")
                cap = min(cap, 0.05)
        else:
            warn.append("not scraped / not verified")
            cap = min(cap, 0.55)

        if self.policy.require_scrapable_primary and (not scrape or not scrape.is_scrapable):
            warn.append("candidate is not scrapable")
            cap = min(cap, 0.20)
        if scrape and verification and verification.page_type_check in {PAGE_TYPE_LISTING, PAGE_TYPE_NON_PRODUCT, PAGE_TYPE_SOFT_404}:
            hard.append(f"bad page type: {verification.page_type_check}")
            cap = min(cap, 0.20)
        if country_check == COUNTRY_ALTERNATIVE:
            warn.append("out-of-country candidate")
            if not self.policy.allow_global_fallback:
                hard.append("global fallback disabled")
                cap = min(cap, 0.05)
            else:
                cap = min(cap, 0.85)
        if retailer_check == RETAILER_ALTERNATIVE:
            warn.append("alternative retailer")
            cap = min(cap, 0.74)
        if self.policy.high_confidence_requires_hard_evidence and verification and not verification.has_hard_justification:
            cap = min(cap, 0.74)

        final = round(max(0.0, min(base, cap)), 4)
        validation = self._validation_status(verification, final, hard)
        reasons = self._reasons(candidate, scrape, verification, title, richness, final)
        primary_reject = hard[0] if hard else ""
        selected_warning = bool(warn and not hard and verification and verification.ean_check == CHECK_CONFLICT)
        lifecycle = self._candidate_lifecycle(scrape, verification, hard, validation)
        return CandidateScorecard(
            candidate=replace(candidate, lifecycle_status=lifecycle),
            organic_score=round(organic, 4), ai_score=round(ai, 4), retailer_score=round(retailer, 4),
            country_score=round(country, 4), ean_score=round(ean, 4), title_score=round(title, 4),
            product_page_score=round(page_type, 4), scrape_score=round(scrape_score, 4), identity_score=round(identity, 4),
            richness_score=round(richness, 4), weighted_confidence=round(base, 4), confidence_cap=round(cap, 4),
            final_confidence=final, validation_status=validation, hard_failures=tuple(dict.fromkeys(hard)),
            soft_warnings=tuple(dict.fromkeys(warn)), ranking_reasons=tuple(reasons), scrape=scrape,
            verification=verification, retailer_check=retailer_check, country_check=country_check,
            exact_product_check=verification.exact_product_check if verification else "UNKNOWN",
            variant_check=verification.variant_check if verification else "UNKNOWN",
            identity_driver=verification.identity_driver if verification else "UNKNOWN",
            selected_with_warning=selected_warning,
            primary_reject_reason=primary_reject,
        )

    def _candidate_lifecycle(self, scrape: ScrapeResult | None, verification: MatchVerification | None, hard: list[str], validation: str) -> str:
        if not scrape:
            return "RANKED_FOR_SCRAPE"
        if not scrape.is_scrapable:
            return "REJECTED_UNSCRAPABLE"
        if verification and verification.page_type_check in {PAGE_TYPE_LISTING, PAGE_TYPE_NON_PRODUCT, PAGE_TYPE_SOFT_404}:
            return "REJECTED_NON_PRODUCT_PAGE"
        if verification and verification.variant_check == "CONFLICT":
            return "REJECTED_VARIANT_MISMATCH"
        if hard:
            return "REJECTED_WRONG_PRODUCT"
        if validation == VALIDATION_VERIFIED:
            return "PROMOTED_FOR_LLM"
        return "REJECTED_WEAK_EVIDENCE" if verification and verification.identity_status in {IDENTITY_WEAK, IDENTITY_UNVERIFIED} else "SCORED"

    def _validation_status(self, verification: MatchVerification | None, final: float, hard: list[str]) -> str:
        if hard:
            return VALIDATION_REJECTED
        if verification and verification.identity_status == IDENTITY_VERIFIED and final >= self.policy.min_verified_confidence:
            return VALIDATION_VERIFIED
        return VALIDATION_NEEDS_REVIEW

    def _sort_key(self, card: CandidateScorecard) -> tuple[float, ...]:
        identity_rank = {
            IDENTITY_VERIFIED: 5,
            IDENTITY_PROBABLE: 4,
            IDENTITY_WEAK: 3,
            IDENTITY_UNVERIFIED: 2,
            IDENTITY_MISMATCH: 0,
        }.get(card.verification.identity_status if card.verification else IDENTITY_UNVERIFIED, 1)
        scrapable = 1 if card.scrape and card.scrape.is_scrapable else 0
        in_country = 1 if card.country_check in {COUNTRY_MATCHED, COUNTRY_NOT_PROVIDED} else 0
        retailer = 1 if card.retailer_check in {RETAILER_MATCHED, RETAILER_NOT_PROVIDED} else 0
        return (identity_rank, scrapable, in_country, retailer, card.richness_score * 100 if scrapable else card.richness_score, card.final_confidence)

    def _identity_score(self, verification: MatchVerification | None) -> float:
        if not verification:
            return 0.0
        return {
            IDENTITY_VERIFIED: 1.0,
            IDENTITY_PROBABLE: 0.75,
            IDENTITY_WEAK: 0.45,
            IDENTITY_UNVERIFIED: 0.15,
            IDENTITY_MISMATCH: 0.0,
        }.get(verification.identity_status, 0.0)

    def _ean_score(self, product: ProductQuery, evidence: str, verification: MatchVerification | None) -> float:
        if not product.ean:
            return 0.5
        if verification and verification.ean_check == CHECK_MATCHED:
            return 1.0
        if verification and verification.ean_check == CHECK_CONFLICT:
            return 0.20
        evidence_digits = re.sub(r"\D", "", evidence or "")
        equivalents = equivalent_gtins(product.ean) or {product.ean}
        return 0.8 if any(eq in evidence_digits for eq in equivalents) else 0.0

    def _page_type_score(self, candidate: URLCandidate, scrape: ScrapeResult | None, verification: MatchVerification | None) -> float:
        if verification and verification.page_type_check == PAGE_TYPE_PRODUCT_DETAIL:
            return 1.0
        if scrape and scrape.looks_like_product_page:
            return 0.8
        url = candidate.url.lower()
        if any(x in url for x in ["/product", "/produkt", "/p/", "/dp/"]):
            return 0.6
        return 0.2

    def _retailer_score(self, product: ProductQuery, candidate: URLCandidate) -> tuple[str, float]:
        evidence = candidate.evidence_text().lower()
        if product.retailer_name:
            tokens = [t.lower() for t in re.findall(r"[a-zA-Z0-9À-ž]+", product.retailer_name) if len(t) >= 2]
            matched = any(t in evidence for t in tokens)
            return (RETAILER_MATCHED, 1.0) if matched else (RETAILER_ALTERNATIVE, 0.2)

        # Retailer is not a controlled country-profile parameter. When the user
        # does not supply retailer_name, do not reward or punish domains as
        # "known retailers". Country specificity is handled independently.
        return RETAILER_NOT_PROVIDED, 0.5

    def _country_score(self, product: ProductQuery, candidate: URLCandidate) -> tuple[str, float]:
        if not product.country_code:
            return COUNTRY_NOT_PROVIDED, 0.5
        if self.country_profiles.domain_matches_country(candidate.url, product.country_code):
            return COUNTRY_MATCHED, 1.0
        return COUNTRY_ALTERNATIVE, 0.25

    def _token_overlap(self, query: str, evidence: str) -> float:
        tokens = {t.lower() for t in re.findall(r"[a-zA-Z0-9À-ž]+", query or "") if len(t) >= 3}
        if not tokens:
            return 0.0
        folded = (evidence or "").lower()
        return sum(1 for t in tokens if t in folded) / len(tokens)

    def _reasons(self, candidate: URLCandidate, scrape: ScrapeResult | None, verification: MatchVerification | None, title: float, richness: float, confidence: float) -> list[str]:
        reasons = [f"confidence={confidence:.2f}", f"title_overlap={title:.2f}", f"richness={richness:.2f}"]
        if candidate.ai_declared_final:
            reasons.append("AI declared as final URL")
        if candidate.best_position:
            reasons.append(f"best organic position={candidate.best_position}")
        if scrape:
            reasons.append(f"scrapable={scrape.is_scrapable}")
        if verification:
            reasons.append(f"identity={verification.identity_status}")
            reasons.extend(verification.justifications[:3])
        return reasons
