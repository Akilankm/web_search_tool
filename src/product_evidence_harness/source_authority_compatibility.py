from __future__ import annotations

from dataclasses import replace

from src.product_evidence_harness.adaptive_search import SearchAction, SearchEngine
from src.product_evidence_harness.constants import (
    COUNTRY_MATCHED,
    COUNTRY_NOT_PROVIDED,
    IDENTITY_MISMATCH,
    IDENTITY_PROBABLE,
    IDENTITY_UNVERIFIED,
    IDENTITY_VERIFIED,
    IDENTITY_WEAK,
    RETAILER_MATCHED,
    RETAILER_NOT_PROVIDED,
)
from src.product_evidence_harness.source_authority import source_tier


def _first_handle(handles, kind: str):
    return next(
        (
            handle
            for handle in handles
            if getattr(handle, "kind", "") == kind and getattr(handle, "value", "")
        ),
        None,
    )


def _exact_hierarchy_query(product) -> str:
    parts: list[str] = []
    if product.ean:
        parts.append(f'"{product.ean}"')
    main = " ".join(product.main_text.split())
    if main:
        parts.append(f'"{main}"')
    parts.extend(["official", "manufacturer", "product", product.country_code])
    return " ".join(part for part in parts if part)


def _patch_planner_class(planner_class) -> None:
    if getattr(planner_class, "_source_authority_compatibility_applied", False):
        return
    current_fallback = planner_class.deterministic_fallback

    def deterministic_fallback(
        self,
        *,
        product,
        credit_number,
        observations,
        handles,
        used_signatures,
        available_engines,
        fallback_reason="",
    ):
        token = _first_handle(handles, "immersive_product_page_token")
        if token and SearchEngine.GOOGLE_IMMERSIVE_PRODUCT.value in available_engines:
            action = SearchAction(
                engine=SearchEngine.GOOGLE_IMMERSIVE_PRODUCT.value,
                purpose="expand_product_token_to_direct_store_urls",
                page_token=token.value,
                scope="country",
                country_code=product.country_code,
                expected_signals=(
                    "SOURCE_TIER:MAJOR_COUNTRY_RETAILER",
                    "DIRECT_EXACT_PRODUCT_URL",
                ),
                reason=(
                    "Expand a real Shopping token into direct merchant product URLs "
                    "before spending a credit on a weaker generic route."
                ),
                planner_source="deterministic_fallback",
            )
            if action.signature() not in used_signatures:
                return action

        action = current_fallback(
            self,
            product=product,
            credit_number=credit_number,
            observations=observations,
            handles=handles,
            used_signatures=used_signatures,
            available_engines=available_engines,
            fallback_reason=fallback_reason,
        )
        if credit_number == 1 and product.ean and action.engine == SearchEngine.GOOGLE.value:
            action = replace(
                action,
                query=_exact_hierarchy_query(product),
                reason=(
                    "EAN/GTIN is preserved as a separately quoted exact identity anchor. "
                    + action.reason
                ),
            )
        return action

    planner_class.deterministic_fallback = deterministic_fallback
    planner_class._source_authority_compatibility_applied = True


def _patch_ranker_class(ranker_class) -> None:
    if getattr(ranker_class, "_source_authority_sort_applied", False):
        return

    def sort_key(self, card):
        identity_rank = {
            IDENTITY_VERIFIED: 5,
            IDENTITY_PROBABLE: 4,
            IDENTITY_WEAK: 3,
            IDENTITY_UNVERIFIED: 2,
            IDENTITY_MISMATCH: 0,
        }.get(
            card.verification.identity_status
            if card.verification
            else IDENTITY_UNVERIFIED,
            1,
        )
        scrapable = 1 if card.scrape and card.scrape.is_scrapable else 0
        authority = 100 - source_tier(card.candidate)
        in_country = (
            1
            if card.country_check in {COUNTRY_MATCHED, COUNTRY_NOT_PROVIDED}
            else 0
        )
        retailer = (
            1
            if card.retailer_check in {RETAILER_MATCHED, RETAILER_NOT_PROVIDED}
            else 0
        )
        richness = (
            card.richness_score * 100 if scrapable else card.richness_score
        )
        return (
            identity_rank,
            scrapable,
            authority,
            in_country,
            retailer,
            richness,
            card.final_confidence,
        )

    ranker_class._sort_key = sort_key
    ranker_class._source_authority_sort_applied = True


def apply_source_authority_compatibility() -> None:
    from src.product_evidence_harness.adaptive_search import BudgetAwareSearchPlanner
    from src.product_evidence_harness.ranker import ProductURLRanker

    _patch_planner_class(BudgetAwareSearchPlanner)
    _patch_ranker_class(ProductURLRanker)

    try:
        from product_evidence_harness.adaptive_search import (
            BudgetAwareSearchPlanner as AliasPlanner,
        )
        from product_evidence_harness.ranker import ProductURLRanker as AliasRanker
    except ImportError:
        return

    _patch_planner_class(AliasPlanner)
    _patch_ranker_class(AliasRanker)
