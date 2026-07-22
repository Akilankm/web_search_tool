from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

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
from src.product_evidence_harness.contracts import ProductQuery, URLCandidate
from src.product_evidence_harness.numeric_safety import safe_int
from src.product_evidence_harness.ranker import ProductURLRanker
from src.product_evidence_harness.selector import FinalSelector
from src.product_evidence_harness.source_authority import (
    SourceAuthorityPolicy,
    SourceTier,
    source_role,
    source_tier,
    source_tier_name,
)
from src.product_evidence_harness.three_stage_pipeline import (
    SearchStage,
    ThreeStageProductEvidenceHarness,
)


_PATCHED = False
_RETAILER_ROLES = {
    "REQUESTED_RETAILER",
    "MAJOR_COUNTRY_RETAILER",
    "GLOBAL_RETAILER",
    "MARKETPLACE",
}


def _identity_query(product: ProductQuery) -> str:
    parts: list[str] = []
    if product.ean:
        parts.append(f'"{product.ean}"')
    if product.main_text:
        parts.append(f'"{" ".join(product.main_text.split())}"')
    return " ".join(parts)


def _manufacturer_stage(product: ProductQuery) -> SearchStage:
    identity = _identity_query(product)
    return SearchStage(
        name="manufacturer_primary",
        scope="country",
        query=(
            f"{identity} official manufacturer brand product page "
            f"{product.country_code} -search -category -collection"
        ).strip(),
        language_code=product.language_code or "en",
    )


def _retailer_stage(product: ProductQuery) -> SearchStage:
    identity = _identity_query(product)
    if product.retailer_name:
        return SearchStage(
            name="requested_retailer_country",
            scope="country",
            query=(
                f'{identity} "{product.retailer_name}" direct product page '
                f"{product.country_code} -search -category"
            ).strip(),
            language_code=product.language_code or "en",
        )
    return SearchStage(
        name="country_alternative",
        scope="country",
        query=(
            f"{identity} retailer direct product page {product.country_code} "
            "-search -category -collection"
        ).strip(),
        language_code=product.language_code or "en",
    )


def _global_stage(product: ProductQuery, language_code: str) -> SearchStage:
    identity = _identity_query(product)
    return SearchStage(
        name="global_fallback",
        scope="global",
        query=(
            f"{identity} official manufacturer or retailer exact product page "
            "-search -category -collection"
        ).strip(),
        language_code=language_code or "en",
    )


def _authority_sort_key(card) -> tuple[Any, ...]:
    scrape = card.scrape
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
    exact = 1 if card.llm_decision in {"EXACT_MATCH", "EXACT_MATCH_WITH_WARNING"} else 0
    usable = 1 if not card.hard_failures else 0
    scrapable = 1 if scrape and scrape.is_scrapable else 0
    product_page = 1 if scrape and scrape.looks_like_product_page else 0
    reachable = 1 if scrape and scrape.reachable else 0
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
    return (
        identity_rank,
        usable,
        exact,
        scrapable,
        product_page,
        reachable,
        authority,
        in_country,
        retailer,
        float(card.richness_score or 0.0),
        float(card.final_confidence or 0.0),
    )


def _selected_card(scorecards: Sequence[Any], url: str | None):
    if not url:
        return None
    return next(
        (card for card in scorecards if card.candidate.url == url),
        None,
    )


def _tier_from_name(value: Any) -> int | None:
    name = str(value or "").strip().upper()
    member = SourceTier.__members__.get(name)
    return int(member) if member is not None else None


def _primary_role(result: dict[str, Any], product: ProductQuery) -> tuple[str, int, str]:
    """Resolve normalized source metadata at the output-writing boundary."""

    raw_acceptance = result.get("primary_url_acceptance")
    acceptance = dict(raw_acceptance) if isinstance(raw_acceptance, Mapping) else {}
    role = str(acceptance.get("source_role") or "UNKNOWN").strip().upper()
    tier_name = str(
        acceptance.get("source_tier_name") or SourceTier.UNKNOWN.name
    ).strip().upper()

    named_tier = _tier_from_name(tier_name)
    tier = safe_int(
        acceptance.get("source_tier"),
        named_tier if named_tier is not None else int(SourceTier.UNKNOWN),
        minimum=int(SourceTier.LOCAL_MANUFACTURER),
        maximum=int(SourceTier.UNKNOWN),
        field_name="primary_url_acceptance.source_tier",
    )

    primary_url = str(result.get("primary_url") or "").strip()
    metadata_incomplete = (
        role == "UNKNOWN"
        or tier == int(SourceTier.UNKNOWN)
        or tier_name not in SourceTier.__members__
    )
    if primary_url and metadata_incomplete:
        decision = SourceAuthorityPolicy().classify(
            product,
            URLCandidate(url=primary_url, title=product.main_text),
        )
        if role == "UNKNOWN":
            role = decision.source_role
        if tier == int(SourceTier.UNKNOWN):
            tier = safe_int(
                decision.source_tier,
                int(SourceTier.UNKNOWN),
                minimum=int(SourceTier.LOCAL_MANUFACTURER),
                maximum=int(SourceTier.UNKNOWN),
                field_name="classified_source_tier",
            )
        if tier_name not in SourceTier.__members__:
            tier_name = decision.source_tier_name

    if tier_name not in SourceTier.__members__:
        try:
            tier_name = SourceTier(tier).name
        except ValueError:
            tier = int(SourceTier.UNKNOWN)
            tier_name = SourceTier.UNKNOWN.name

    return role, tier, tier_name


def _public_role(role: str) -> str:
    if role == "MANUFACTURER":
        return "OFFICIAL_MANUFACTURER"
    if role in _RETAILER_ROLES:
        return "RETAILER"
    if role == "MARKETPLACE":
        return "MARKETPLACE"
    return "OTHER_PRODUCT_SOURCE"


def _write_artifacts(result: dict[str, Any]) -> None:
    root_value = result.get("artifact_dir")
    if not root_value:
        return
    root = Path(str(root_value))
    if not root.is_dir():
        return
    source_selection = result.get("source_selection") or {}
    (root / "source_selection.json").write_text(
        json.dumps(source_selection, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    (root / "orchestrated_result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    (root / "mandatory_url_delivery.json").write_text(
        json.dumps(result.get("url_delivery") or {}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )


def _annotate_result(payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    product_payload = dict(payload.get("product") or payload)
    product_payload.pop("feature_set", None)
    product = ProductQuery(**product_payload)

    acceptance = dict(result.get("primary_url_acceptance") or {})
    role, tier, tier_name = _primary_role(result, product)
    primary_url = str(result.get("primary_url") or "") or None
    manufacturer_url = acceptance.get("manufacturer_url")
    retailer_url = acceptance.get("retailer_url")

    if role == "MANUFACTURER" and not manufacturer_url:
        manufacturer_url = primary_url
    if role in _RETAILER_ROLES and not retailer_url:
        retailer_url = primary_url

    primary_public_role = _public_role(role)
    selection_reason = str(acceptance.get("selection_reason") or "")
    if not selection_reason:
        selection_reason = (
            "OFFICIAL_MANUFACTURER_PRIMARY_AFTER_STRICT_GATES"
            if role == "MANUFACTURER"
            else "RETAILER_OR_BEST_PRODUCT_SOURCE_FALLBACK"
        )

    result["primary_url_role"] = primary_public_role
    result["manufacturer_url"] = manufacturer_url
    result["retailer_url"] = retailer_url
    result["source_selection"] = {
        "policy": "MANUFACTURER_FIRST_AFTER_PRODUCTION_GATES",
        "primary_url": primary_url,
        "primary_url_role": primary_public_role,
        "source_role": role,
        "source_tier": tier,
        "source_tier_name": tier_name,
        "manufacturer_url": manufacturer_url,
        "retailer_url": retailer_url,
        "selection_reason": selection_reason,
        "manufacturer_priority_is_conditional": True,
        "required_gates": [
            "exact_product_identity",
            "browser_openable",
            "text_scrapable",
            "rendered_product_verified",
            "requested_feature_coverage",
            "durable_non_expiring_url",
        ],
        "fallback_rule": (
            "Use the strongest qualified retailer/product page when no official "
            "manufacturer page passes every required gate."
        ),
    }

    acceptance.update(
        {
            "source_role": role,
            "source_tier": tier,
            "source_tier_name": tier_name,
            "manufacturer_url": manufacturer_url,
            "retailer_url": retailer_url,
            "selection_reason": selection_reason,
        }
    )
    result["primary_url_acceptance"] = acceptance

    product_match = dict(result.get("product_match") or {})
    product_match.update(
        {
            "primary_url_role": primary_public_role,
            "manufacturer_url": manufacturer_url,
            "retailer_url": retailer_url,
            "source_selection_reason": selection_reason,
        }
    )
    result["product_match"] = product_match

    evidence_set = dict(result.get("evidence_set") or {})
    evidence_set.update(
        {
            "primary_url_role": primary_public_role,
            "manufacturer_url": manufacturer_url,
            "retailer_url": retailer_url,
        }
    )
    result["evidence_set"] = evidence_set

    delivery = dict(result.get("url_delivery") or {})
    delivery.update(
        {
            "primary_url_role": primary_public_role,
            "manufacturer_url": manufacturer_url,
            "retailer_url": retailer_url,
            "manufacturer_first_policy": True,
        }
    )
    result["url_delivery"] = delivery

    search = dict(result.get("search") or {})
    search.update(
        {
            "manufacturer_first_primary_url": True,
            "source_authority_path": [
                "LOCAL_MANUFACTURER",
                "GLOBAL_MANUFACTURER",
                "REQUESTED_RETAILER_LOCAL",
                "REQUESTED_RETAILER_GLOBAL",
                "MAJOR_COUNTRY_RETAILER",
                "OTHER_LOCAL_WEBSITE",
                "OTHER_GLOBAL_WEBSITE",
                "MARKETPLACE_LAST_RESORT",
            ],
            "search_stage_order": [
                "manufacturer_primary",
                (
                    "requested_retailer_country"
                    if product.retailer_name
                    else "country_alternative"
                ),
                "global_fallback",
            ],
        }
    )
    result["search"] = search
    _write_artifacts(result)
    return result


def apply_manufacturer_primary_policy() -> None:
    """Install the final manufacturer-first product-truth contract."""

    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    # Belief compatibility previously replaced this hierarchy with a purely
    # market-oriented route. Restore the product-truth authority order last.
    SourceAuthorityPolicy.hierarchy = lambda self, product: (
        (
            "LOCAL_MANUFACTURER",
            "GLOBAL_MANUFACTURER",
            "REQUESTED_RETAILER_LOCAL",
            "REQUESTED_RETAILER_GLOBAL",
            "MAJOR_COUNTRY_RETAILER",
            "OTHER_LOCAL_WEBSITE",
            "OTHER_GLOBAL_WEBSITE",
            "MARKETPLACE_LAST_RESORT",
        )
        if product.retailer_name
        else (
            "LOCAL_MANUFACTURER",
            "GLOBAL_MANUFACTURER",
            "MAJOR_COUNTRY_RETAILER",
            "OTHER_LOCAL_WEBSITE",
            "OTHER_GLOBAL_WEBSITE",
            "MARKETPLACE_LAST_RESORT",
        )
    )

    def build_stage(self, product, state, stage_index):
        if stage_index == 0:
            return _manufacturer_stage(product)
        if stage_index == 1:
            return _retailer_stage(product)
        return _global_stage(
            product,
            self.config.global_fallback_language_code or "en",
        )

    ThreeStageProductEvidenceHarness._build_stage = build_stage
    ProductURLRanker._sort_key = lambda self, card: _authority_sort_key(card)

    def select_exact(self, cards):
        return next(
            (
                card
                for card in sorted(cards, key=_authority_sort_key, reverse=True)
                if card.validation_status == "VERIFIED"
                and self._is_final_usable(card)
            ),
            None,
        )

    def select_best(self, cards, *, allow_hard_rejected: bool = False):
        candidates = (
            list(cards)
            if allow_hard_rejected
            else [card for card in cards if not card.hard_failures]
        )
        return (
            sorted(candidates, key=_authority_sort_key, reverse=True)[0]
            if candidates
            else None
        )

    FinalSelector._select_exact_card = select_exact
    FinalSelector._select_best_available_card = select_best

    current_select = FinalSelector.select

    def select(
        self,
        *,
        task,
        scorecards,
        termination_reason,
        budget_snapshot,
        llm_calls_used=0,
        state=None,
    ):
        match = current_select(
            self,
            task=task,
            scorecards=scorecards,
            termination_reason=termination_reason,
            budget_snapshot=budget_snapshot,
            llm_calls_used=llm_calls_used,
            state=state,
        )
        # A retailer returned by the manufacturer-targeted first credit is kept
        # as best_available_url, but it may not stop the search before the
        # manufacturer opportunity has been exhausted.
        if "MANUFACTURER_PRIMARY" in str(termination_reason).upper():
            card = _selected_card(scorecards, match.product_url)
            if card is not None and source_role(card.candidate) != "MANUFACTURER":
                return replace(
                    match,
                    product_url=None,
                    best_available_url=match.product_url or match.best_available_url,
                    match_reason="MANUFACTURER_STAGE_RETAILER_DEFERRED",
                    url_decision_status="CONTINUE_TO_RETAILER_STAGE",
                    resolution_status="SEARCH_CONTINUES",
                    needs_review=True,
                )
        return match

    FinalSelector.select = select

    from src.product_evidence_harness.agent_service.strict_orchestrator import (
        StrictProductEvidenceOrchestrator,
    )

    current_run = StrictProductEvidenceOrchestrator.run

    def run(self, payload, *, progress=None):
        return _annotate_result(
            payload,
            current_run(self, payload, progress=progress),
        )

    StrictProductEvidenceOrchestrator.run = run
