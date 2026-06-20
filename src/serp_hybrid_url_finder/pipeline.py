from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from serp_hybrid_url_finder.ai_evidence_parser import AIMatchEvidenceParser
from serp_hybrid_url_finder.budget import BudgetTracker
from serp_hybrid_url_finder.candidate_collector import CandidateCollector
from serp_hybrid_url_finder.config import PipelineConfig, SerpAPIConfig
from serp_hybrid_url_finder.constants import (
    AI_REPAIR_QUERY_MAX_CHARS,
    AI_VALIDATION_QUERY_MAX_CHARS,
    CALL_TYPE_AI_MODE,
    CALL_TYPE_ORGANIC,
    COUNTRY_CHECK_ALTERNATIVE,
    COUNTRY_CHECK_NOT_PROVIDED,
    HIGH_CONFIDENCE_THRESHOLD,
    IDENTITY_PROBABLE,
    IDENTITY_VERIFIED,
    REASON_AI_NO_MATCH,
    REASON_FORCED_IN_COUNTRY_WEAK,
    REASON_NO_URL_EXTRACTED,
    REASON_NO_VERIFIED_URL,
    REASON_OUT_OF_COUNTRY_FALLBACK,
    RETAILER_CHECK_ALTERNATIVE,
    VALIDATION_NEEDS_REVIEW,
    VALIDATION_NO_MATCH,
    VALIDATION_REJECTED,
)
from serp_hybrid_url_finder.identity_verifier import ProductIdentityVerifier
from serp_hybrid_url_finder.models import (
    AIMatchEvidence,
    MatchVerification,
    OrganicSearchResponse,
    PipelineTrace,
    ProductQuery,
    ProductURLMatch,
    ScoredURLCandidate,
    ScrapeResult,
    SerpAIResponse,
    URLCandidate,
)
from serp_hybrid_url_finder.query_planner import AIValidationPromptBuilder, OrganicSearchPlanner
from serp_hybrid_url_finder.ranker import ProductURLRanker
from serp_hybrid_url_finder.scraper import CrawlScraper
from serp_hybrid_url_finder.serp_clients import GoogleAIModeClient, GoogleOrganicSearchClient


@dataclass
class HybridProductURLFinderPipeline:
    """
    Product URL finder using exactly-bounded SerpAPI calls, crawl4ai scrape
    verification, and deterministic product-identity verification.

    External SerpAPI budget per product:
    - up to 2 Google organic search calls
    - up to 2 Google AI Mode calls

    Guarantees on the returned URL:
    1. It was scraped with crawl4ai and is genuinely consumable (real content).
    2. Its scraped content was verified to be THE requested product - same
       EAN/GTIN, same distinctive title, same pack-size / variant - and not a
       different variant (e.g. 18 KS vs 32 KS) or a soft-404 page.
    3. Its confidence is decomposed and auditable, and any high-confidence claim
       is backed by hard justification, so the result can be submitted for
       downstream validation.
    """

    serp_config: SerpAPIConfig
    pipeline_config: PipelineConfig = field(default_factory=PipelineConfig)
    organic_client: Optional[GoogleOrganicSearchClient] = None
    ai_client: Optional[GoogleAIModeClient] = None
    organic_planner: OrganicSearchPlanner = field(default_factory=OrganicSearchPlanner)
    candidate_collector: CandidateCollector = field(default_factory=CandidateCollector)
    evidence_parser: AIMatchEvidenceParser = field(default_factory=AIMatchEvidenceParser)
    ranker: Optional[ProductURLRanker] = None
    verifier: ProductIdentityVerifier = field(default_factory=ProductIdentityVerifier)
    scraper: Optional[CrawlScraper] = None

    def __post_init__(self) -> None:
        if self.organic_client is None:
            self.organic_client = GoogleOrganicSearchClient(self.serp_config)
        if self.ai_client is None:
            self.ai_client = GoogleAIModeClient(self.serp_config)
        if self.ranker is None:
            self.ranker = ProductURLRanker(weights=self.pipeline_config.score_weights)
        if self.scraper is None:
            self.scraper = CrawlScraper(
                headless=self.pipeline_config.crawl_headless,
                verbose=self.pipeline_config.crawl_verbose,
                page_timeout_ms=self.pipeline_config.crawl_page_timeout_ms,
                min_word_count=self.pipeline_config.crawl_min_word_count,
                market_profile=self.pipeline_config.market_profile,
            )

    def run(
        self,
        product: ProductQuery,
        *,
        return_trace: bool = False,
    ) -> ProductURLMatch | PipelineTrace:
        logger.info("Starting hybrid product URL finding | row_id={}", product.row_id)

        budget = BudgetTracker(
            max_organic=self.pipeline_config.max_organic_calls,
            max_ai_mode=self.pipeline_config.max_ai_mode_calls,
        )

        organic_queries: list[str] = []
        organic_responses: list[OrganicSearchResponse] = []

        # Organic Search #1: exact identity / high precision.
        q1 = self.organic_planner.build_first_query(product)
        organic_queries.append(q1)
        budget.consume(CALL_TYPE_ORGANIC)
        organic_responses.append(self.organic_client.search(q1, product=product))

        # Organic Search #2: adaptive fallback / domain-scoped recall.
        if budget.can_use_organic():
            q2 = self.organic_planner.build_second_query(
                product,
                first_response=organic_responses[0],
            )
            organic_queries.append(q2)
            budget.consume(CALL_TYPE_ORGANIC)
            organic_responses.append(self.organic_client.search(q2, product=product))

        candidates = self.candidate_collector.collect_from_organic(organic_responses)
        candidates_text = self.candidate_collector.to_ai_candidate_text(
            candidates,
            max_candidates=self.pipeline_config.max_candidates_for_ai,
        )

        ai_prompt_builder = AIValidationPromptBuilder(max_query_chars=AI_VALIDATION_QUERY_MAX_CHARS)
        ai_validation_query = ai_prompt_builder.build_validation_prompt(
            product=product,
            candidates_text=candidates_text,
        )

        budget.consume(CALL_TYPE_AI_MODE)
        ai_validation_response = self.ai_client.search(ai_validation_query, product=product)
        ai_validation_evidence = self.evidence_parser.parse(ai_validation_response.markdown)

        candidates = self.candidate_collector.merge_ai_response(candidates, ai_validation_response)

        scrapes: dict[str, ScrapeResult] = {}
        verifications: dict[str, MatchVerification] = {}
        scrapes, verifications = self._scrape_and_verify(
            product, candidates, ai_validation_evidence, scrapes, verifications
        )

        scored_candidates = self.ranker.score(
            product=product,
            candidates=candidates,
            ai_evidence=ai_validation_evidence,
            scrapes=scrapes,
            verifications=verifications,
        )
        final = self._select_final(scored_candidates)

        repair_query: Optional[str] = None
        repair_response: Optional[SerpAIResponse] = None
        repair_evidence: Optional[AIMatchEvidence] = None
        repair_used = False

        if self._should_repair(final, ai_validation_evidence) and budget.can_use_ai_mode():
            repair_used = True
            rejection_reason = self._build_repair_reason(
                final, scored_candidates, ai_validation_evidence, product
            )
            repair_prompt_builder = AIValidationPromptBuilder(max_query_chars=AI_REPAIR_QUERY_MAX_CHARS)
            candidates_text = self.candidate_collector.to_ai_candidate_text(
                candidates,
                max_candidates=self.pipeline_config.max_candidates_for_ai,
            )
            repair_query = repair_prompt_builder.build_repair_prompt(
                product=product,
                candidates_text=candidates_text,
                previous_answer=ai_validation_response.markdown,
                rejection_reason=rejection_reason,
            )

            budget.consume(CALL_TYPE_AI_MODE)
            repair_response = self.ai_client.search(repair_query, product=product)
            repair_evidence = self.evidence_parser.parse(repair_response.markdown)
            candidates = self.candidate_collector.merge_ai_response(candidates, repair_response)
            scrapes, verifications = self._scrape_and_verify(
                product, candidates, repair_evidence, scrapes, verifications
            )
            scored_candidates = self.ranker.score(
                product=product,
                candidates=candidates,
                ai_evidence=repair_evidence,
                scrapes=scrapes,
                verifications=verifications,
            )
            final = self._select_final(scored_candidates)

        final_evidence = repair_evidence if repair_evidence is not None else ai_validation_evidence
        best_match = self._to_best_match(
            product=product,
            final=final,
            scored_candidates=scored_candidates,
            ai_evidence=final_evidence,
            budget=budget,
            repair_used=repair_used,
        )

        logger.info(
            "Completed | row_id={} | status={} | identity={} | confidence={} | url={}",
            product.row_id,
            best_match.validation_status,
            best_match.identity_status,
            best_match.confidence,
            best_match.product_url,
        )

        if return_trace:
            return PipelineTrace(
                product_query=product,
                budget=budget.state(),
                organic_queries=organic_queries,
                organic_responses=organic_responses,
                candidates=candidates,
                ai_validation_query=ai_validation_query,
                ai_validation_response=ai_validation_response,
                ai_validation_evidence=ai_validation_evidence,
                repair_query=repair_query,
                repair_response=repair_response,
                repair_evidence=repair_evidence,
                scored_candidates=scored_candidates,
                scrapes=scrapes,
                verifications=verifications,
                best_match=best_match,
            )

        return best_match

    def _scrape_and_verify(
        self,
        product: ProductQuery,
        candidates: list[URLCandidate],
        ai_evidence: AIMatchEvidence,
        scrapes: dict[str, ScrapeResult],
        verifications: dict[str, MatchVerification],
    ) -> tuple[dict[str, ScrapeResult], dict[str, MatchVerification]]:
        if not self.pipeline_config.scrape_enabled or not candidates:
            return scrapes, verifications

        # Cheap pre-rank (using whatever info we already have) to choose the most
        # promising candidates worth spending a real browser fetch on.
        pre_ranked = self.ranker.score(
            product=product,
            candidates=candidates,
            ai_evidence=ai_evidence,
            scrapes=scrapes,
            verifications=verifications,
        )

        targets: list[str] = []
        for scored in pre_ranked:
            url = scored.candidate.url
            if url in scrapes:
                continue
            targets.append(url)
            if len(targets) >= self.pipeline_config.max_urls_to_scrape:
                break

        if not targets:
            return scrapes, verifications

        new_results = self.scraper.scrape_many(targets, product)
        merged_scrapes = dict(scrapes)
        merged_scrapes.update(new_results)

        # Verify product identity on every freshly scraped page.
        merged_verifications = dict(verifications)
        for url, scrape in new_results.items():
            merged_verifications[url] = self.verifier.verify(product, scrape)

        verified = sum(
            1 for v in merged_verifications.values()
            if v.identity_status in {IDENTITY_VERIFIED, IDENTITY_PROBABLE}
        )
        logger.info(
            "Scrape+verify pass | scraped={} | identity_acceptable={}",
            len(merged_scrapes),
            verified,
        )
        return merged_scrapes, merged_verifications

    def _select_final(
        self,
        scored_candidates: list[ScoredURLCandidate],
    ) -> Optional[ScoredURLCandidate]:
        if not scored_candidates:
            return None

        # Primary pass: stay inside the requested country. Country is a hard scope
        # by default; candidates are pre-sorted richest-correct-first by the ranker,
        # so the first acceptable one is the best in-country product page.
        in_scope = self._first_acceptable(scored_candidates, allow_out_of_country=False)
        if in_scope is not None:
            return in_scope

        # Fallback pass: only when global fallback is explicitly enabled may we
        # return an out-of-country product page.
        if self.pipeline_config.allow_global_fallback:
            return self._first_acceptable(scored_candidates, allow_out_of_country=True)

        return None

    def _first_acceptable(
        self,
        scored_candidates: list[ScoredURLCandidate],
        *,
        allow_out_of_country: bool,
    ) -> Optional[ScoredURLCandidate]:
        for scored in scored_candidates:
            if scored.confidence <= 0:
                continue

            # Hard gate 1: the page must be genuinely scrapable.
            if self.pipeline_config.require_scrapable_final:
                if not (scored.scrape and scored.scrape.is_scrapable):
                    continue

            # Hard gate 2: country scope, unless we are explicitly falling back.
            if (
                not allow_out_of_country
                and scored.country_check == COUNTRY_CHECK_ALTERNATIVE
            ):
                continue

            # Optional richness floor (disabled by default).
            if (
                self.pipeline_config.min_richness > 0
                and scored.scrape is not None
                and scored.scrape.richness_score < self.pipeline_config.min_richness
            ):
                continue

            # Hard gate 3: product identity must be correct.
            if self.pipeline_config.require_identity_verified:
                verification = scored.verification
                if verification is None:
                    continue
                if verification.identity_status == IDENTITY_VERIFIED:
                    return scored
                if (
                    verification.identity_status == IDENTITY_PROBABLE
                    and self.pipeline_config.allow_probable_as_final
                ):
                    return scored
                continue

            return scored
        return None

    @staticmethod
    def _has_out_of_country_alternative(
        scored_candidates: list[ScoredURLCandidate],
    ) -> bool:
        """True when a correct, scrapable product page exists outside the requested
        country (used to explain a deliberately weaker in-country pick)."""
        return any(
            scored.country_check == COUNTRY_CHECK_ALTERNATIVE
            and scored.verification is not None
            and scored.verification.identity_status
            in {IDENTITY_VERIFIED, IDENTITY_PROBABLE}
            and scored.scrape is not None
            and scored.scrape.is_scrapable
            for scored in scored_candidates
        )

    def _should_repair(
        self,
        final: Optional[ScoredURLCandidate],
        ai_evidence: AIMatchEvidence,
    ) -> bool:
        if not self.pipeline_config.run_ai_repair:
            return False

        if ai_evidence.match_decision == "NO_MATCH":
            return True

        # No identity-verified, scrapable, confident URL yet: try one repair round.
        if final is None:
            return True

        if final.confidence < self.pipeline_config.repair_confidence_threshold:
            return True

        # A probable (not fully verified) best result is worth one repair attempt
        # to try to surface an EAN-confirmed page.
        if (
            final.verification
            and final.verification.identity_status == IDENTITY_PROBABLE
            and final.confidence < HIGH_CONFIDENCE_THRESHOLD
        ):
            return True

        return False

    def _build_repair_reason(
        self,
        final: Optional[ScoredURLCandidate],
        scored_candidates: list[ScoredURLCandidate],
        ai_evidence: AIMatchEvidence,
        product: ProductQuery,
    ) -> str:
        parts: list[str] = [f"AI decision: {ai_evidence.match_decision}."]

        if final is None:
            parts.append(
                "No candidate passed product-identity verification on its scraped content. "
                "Return a DIFFERENT, genuinely reachable product detail URL whose page is "
                "exactly the requested product (same EAN, same pack-size/quantity, same variant)."
            )
        else:
            parts.append(f"Current best URL: {final.candidate.url} (confidence {final.confidence}).")
            if final.retailer_check == RETAILER_CHECK_ALTERNATIVE and product.retailer_name:
                parts.append(
                    f"The current best is an ALTERNATIVE retailer. Strongly prefer a product "
                    f"detail page on the requested retailer '{product.retailer_name}' if one "
                    f"exists for the EXACT same product; otherwise the alternative is acceptable."
                )

        # Surface concrete identity problems so the AI avoids repeating them.
        rejected = []
        for scored in scored_candidates[:6]:
            verification = scored.verification
            if verification and verification.blocking_reasons:
                rejected.append(
                    f"- {scored.candidate.url}: {'; '.join(verification.blocking_reasons)}"
                )
        if rejected:
            parts.append("Rejected pages and why (do NOT pick these):")
            parts.extend(rejected)

        return "\n".join(parts)

    def _to_best_match(
        self,
        *,
        product: ProductQuery,
        final: Optional[ScoredURLCandidate],
        scored_candidates: list[ScoredURLCandidate],
        ai_evidence: AIMatchEvidence,
        budget: BudgetTracker,
        repair_used: bool,
    ) -> ProductURLMatch:
        if final is None:
            return self._no_match(
                product=product,
                scored_candidates=scored_candidates,
                ai_evidence=ai_evidence,
                budget=budget,
                repair_used=repair_used,
            )

        scrape = final.scrape
        verification = final.verification
        breakdown = final.confidence_breakdown
        validation_status = (
            breakdown.validation_status if breakdown else VALIDATION_NEEDS_REVIEW
        )
        justification = (
            breakdown.justification_summary
            if breakdown
            else self.ranker.build_justification(verification, validation_status)
        )

        # When the requested retailer was not found, make the alternative explicit
        # in the justification so the result is never mistaken for the requested
        # retailer downstream.
        if final.retailer_check == RETAILER_CHECK_ALTERNATIVE and product.retailer_name:
            justification = (
                f"{justification} Retailer note: requested retailer "
                f"'{product.retailer_name}' was not found carrying this product; "
                f"returned a verified ALTERNATIVE retailer instead."
            )

        if final.country_check == COUNTRY_CHECK_ALTERNATIVE:
            # Only reachable when allow_global_fallback is enabled.
            justification = (
                f"{justification} {REASON_OUT_OF_COUNTRY_FALLBACK} "
                f"(requested country '{product.country_code}')."
            )
        elif (
            product.country_code
            and not self.pipeline_config.allow_global_fallback
            and final.confidence < HIGH_CONFIDENCE_THRESHOLD
            and self._has_out_of_country_alternative(scored_candidates)
        ):
            # A richer out-of-country page existed, but country lock kept us on the
            # best in-country page instead.
            justification = f"{justification} {REASON_FORCED_IN_COUNTRY_WEAK}"

        return ProductURLMatch(
            row_id=product.row_id,
            main_text=product.main_text,
            ean=product.ean,
            retailer_name=product.retailer_name,
            country_code=product.country_code,
            product_url=final.candidate.url,
            confidence=final.confidence,
            is_exact_product_match=final.is_exact_product_match,
            match_reason=final.reason,
            validation_status=validation_status,
            identity_status=verification.identity_status if verification else "NONE",
            justification=justification,
            ean_check=verification.ean_check if verification else "NOT_PROVIDED",
            title_check=verification.title_check if verification else "WEAK",
            quantity_check=verification.quantity_check if verification else "UNKNOWN",
            page_type_check=verification.page_type_check if verification else "UNKNOWN",
            retailer_check=final.retailer_check,
            country_check=final.country_check,
            requested_quantity=verification.requested_quantity if verification else None,
            page_quantity=verification.page_quantity if verification else None,
            blocking_reasons="; ".join(verification.blocking_reasons) if verification else "",
            ai_match_decision=ai_evidence.match_decision,
            ai_confidence_reason=ai_evidence.confidence_reason,
            ean_evidence=ai_evidence.ean_evidence,
            title_evidence=ai_evidence.title_evidence,
            retailer_evidence=ai_evidence.retailer_evidence,
            country_evidence=ai_evidence.country_evidence,
            product_page_evidence=ai_evidence.product_page_evidence,
            organic_calls_used=budget.organic_used,
            ai_mode_calls_used=budget.ai_mode_used,
            repair_used=repair_used,
            is_scrapable=bool(scrape and scrape.is_scrapable),
            scrape_status_code=scrape.status_code if scrape else None,
            scrape_word_count=scrape.word_count if scrape else 0,
            scrape_markdown_chars=scrape.markdown_chars if scrape else 0,
            scrape_final_url=scrape.final_url if scrape else None,
            richness_score=scrape.richness_score if scrape else 0.0,
            price=scrape.price if scrape else None,
            currency=scrape.currency if scrape else "",
            brand=scrape.brand if scrape else "",
            manufacturer=scrape.manufacturer if scrape else "",
            description=scrape.description if scrape else "",
            specs_count=len(scrape.specs) if scrape else 0,
            image_count=len(scrape.image_urls) if scrape else 0,
            specs=dict(scrape.specs) if scrape else {},
            image_urls=tuple(scrape.image_urls) if scrape else (),
            confidence_breakdown=breakdown,
        )

    def _no_match(
        self,
        *,
        product: ProductQuery,
        scored_candidates: list[ScoredURLCandidate],
        ai_evidence: AIMatchEvidence,
        budget: BudgetTracker,
        repair_used: bool,
    ) -> ProductURLMatch:
        # Distinguish "nothing found" from "found but rejected by verification".
        top = scored_candidates[0] if scored_candidates else None
        top_verification = top.verification if top else None

        # Was a correct, scrapable product found, but only OUTSIDE the requested
        # country while the country scope is locked (global fallback disabled)?
        alt_country_verified = next(
            (
                scored
                for scored in scored_candidates
                if scored.country_check == COUNTRY_CHECK_ALTERNATIVE
                and scored.verification is not None
                and scored.verification.identity_status in {IDENTITY_VERIFIED, IDENTITY_PROBABLE}
                and scored.scrape is not None
                and scored.scrape.is_scrapable
            ),
            None,
        )
        country_locked_alt = (
            not self.pipeline_config.allow_global_fallback
            and alt_country_verified is not None
        )

        if not scored_candidates and ai_evidence.match_decision == "NO_MATCH":
            validation_status = VALIDATION_NO_MATCH
            reason = REASON_AI_NO_MATCH
        elif not scored_candidates:
            validation_status = VALIDATION_NO_MATCH
            reason = REASON_NO_URL_EXTRACTED
        else:
            validation_status = VALIDATION_REJECTED
            reason = REASON_NO_VERIFIED_URL

        blocking = ""
        if country_locked_alt and alt_country_verified is not None:
            justification = (
                f"A verified, scrapable product page was found, but only OUTSIDE the "
                f"requested country '{product.country_code}' "
                f"({alt_country_verified.candidate.url}). Country scope is locked, so no "
                f"URL is returned. Enable allow_global_fallback to accept out-of-country pages."
            )
            retailer_check_value = alt_country_verified.retailer_check
            country_check_value = COUNTRY_CHECK_ALTERNATIVE
        else:
            justification = (
                "No candidate URL could be verified as the exact requested product on its "
                "scraped content; returning no URL rather than an unverified or wrong one."
            )
            retailer_check_value = top.retailer_check if top else "NOT_PROVIDED"
            country_check_value = top.country_check if top else "NOT_PROVIDED"
            if top_verification and top_verification.blocking_reasons:
                blocking = "; ".join(top_verification.blocking_reasons)
                justification += f" Best rejected candidate: {blocking}."

        return ProductURLMatch(
            row_id=product.row_id,
            main_text=product.main_text,
            ean=product.ean,
            retailer_name=product.retailer_name,
            country_code=product.country_code,
            product_url=None,
            confidence=0.0,
            is_exact_product_match=False,
            match_reason=reason,
            validation_status=validation_status,
            identity_status=top_verification.identity_status if top_verification else "NONE",
            justification=justification,
            ean_check=top_verification.ean_check if top_verification else "NOT_PROVIDED",
            title_check=top_verification.title_check if top_verification else "WEAK",
            quantity_check=top_verification.quantity_check if top_verification else "UNKNOWN",
            page_type_check=top_verification.page_type_check if top_verification else "UNKNOWN",
            retailer_check=retailer_check_value,
            country_check=country_check_value,
            requested_quantity=top_verification.requested_quantity if top_verification else None,
            page_quantity=top_verification.page_quantity if top_verification else None,
            blocking_reasons=blocking,
            ai_match_decision=ai_evidence.match_decision,
            ai_confidence_reason=ai_evidence.confidence_reason,
            ean_evidence=ai_evidence.ean_evidence,
            title_evidence=ai_evidence.title_evidence,
            retailer_evidence=ai_evidence.retailer_evidence,
            country_evidence=ai_evidence.country_evidence,
            product_page_evidence=ai_evidence.product_page_evidence,
            organic_calls_used=budget.organic_used,
            ai_mode_calls_used=budget.ai_mode_used,
            repair_used=repair_used,
            is_scrapable=False,
            scrape_status_code=None,
            scrape_word_count=0,
            scrape_markdown_chars=0,
            scrape_final_url=None,
            confidence_breakdown=None,
        )
