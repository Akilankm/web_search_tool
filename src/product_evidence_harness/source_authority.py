from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import IntEnum
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

from src.product_evidence_harness.contracts import ProductQuery, ScrapeResult, URLCandidate
from src.product_evidence_harness.country_profiles import CountryProfileRegistry
from src.product_evidence_harness.retailer_strategy import candidate_matches_requested_retailer


class SourceTier(IntEnum):
    REQUESTED_RETAILER_LOCAL = 0
    REQUESTED_RETAILER_GLOBAL = 1
    LOCAL_MANUFACTURER = 2
    GLOBAL_MANUFACTURER = 3
    MAJOR_COUNTRY_RETAILER = 4
    OTHER_LOCAL_WEBSITE = 5
    OTHER_GLOBAL_WEBSITE = 6
    MARKETPLACE_LAST_RESORT = 7
    UNKNOWN = 8


WITH_RETAILER = tuple(item.name for item in SourceTier if item is not SourceTier.UNKNOWN)
WITHOUT_RETAILER = (
    "LOCAL_MANUFACTURER",
    "GLOBAL_MANUFACTURER",
    "MAJOR_COUNTRY_RETAILER",
    "OTHER_LOCAL_WEBSITE",
    "OTHER_GLOBAL_WEBSITE",
    "MARKETPLACE_LAST_RESORT",
)


@dataclass(frozen=True, slots=True)
class SourceAuthorityDecision:
    source_tier: int
    source_tier_name: str
    source_role: str
    country_alignment: str
    requested_retailer_match: bool = False
    manufacturer_match: bool = False
    major_country_retailer: bool = False
    marketplace: str = ""
    source_priority_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True)
class SourceAuthorityPolicy:
    country_profiles: CountryProfileRegistry = CountryProfileRegistry.load()

    def hierarchy(self, product: ProductQuery) -> tuple[str, ...]:
        return WITH_RETAILER if product.retailer_name else WITHOUT_RETAILER

    def classify(
        self,
        product: ProductQuery,
        candidate: URLCandidate,
        scrape: ScrapeResult | None = None,
    ) -> SourceAuthorityDecision:
        local = self._local(candidate.url, product.country_code)
        alignment = "LOCAL_OR_REGIONAL" if local else "GLOBAL_OR_UNKNOWN"
        market = marketplace_name(candidate.url)
        requested = bool(
            product.retailer_name
            and candidate_matches_requested_retailer(candidate, product.retailer_name)
        )
        if requested:
            tier = SourceTier.REQUESTED_RETAILER_LOCAL if local else SourceTier.REQUESTED_RETAILER_GLOBAL
            return SourceAuthorityDecision(
                int(tier), tier.name, "REQUESTED_RETAILER", alignment,
                requested_retailer_match=True, marketplace=market,
                source_priority_reason="Explicit retailer input overrides the default hierarchy",
            )

        manufacturer, reason = self._manufacturer(candidate, product, scrape)
        if manufacturer:
            tier = SourceTier.LOCAL_MANUFACTURER if local else SourceTier.GLOBAL_MANUFACTURER
            return SourceAuthorityDecision(
                int(tier), tier.name, "MANUFACTURER", alignment,
                manufacturer_match=True, marketplace=market,
                source_priority_reason=reason,
            )

        if market:
            tier = SourceTier.MARKETPLACE_LAST_RESORT
            return SourceAuthorityDecision(
                int(tier), tier.name, "MARKETPLACE", alignment,
                marketplace=market,
                source_priority_reason=f"{market} is last resort unless explicitly requested",
            )

        product_surface = any(
            marker in set(candidate.source_types)
            for marker in (
                "engine_google_shopping",
                "engine_google_immersive_product",
                "engine_walmart",
                "engine_home_depot",
            )
        )
        if local and product_surface:
            tier = SourceTier.MAJOR_COUNTRY_RETAILER
            return SourceAuthorityDecision(
                int(tier), tier.name, "MAJOR_COUNTRY_RETAILER", alignment,
                major_country_retailer=True,
                source_priority_reason="Country-aligned merchant from a product-oriented search surface",
            )
        tier = SourceTier.OTHER_LOCAL_WEBSITE if local else SourceTier.OTHER_GLOBAL_WEBSITE
        return SourceAuthorityDecision(
            int(tier), tier.name,
            "OTHER_LOCAL_WEBSITE" if local else "OTHER_GLOBAL_WEBSITE",
            alignment,
            source_priority_reason="Valid product website outside stronger authority tiers",
        )

    def tag_candidates(
        self,
        product: ProductQuery,
        candidates: Sequence[URLCandidate],
        scrapes: Mapping[str, ScrapeResult] | None = None,
    ) -> list[URLCandidate]:
        scrapes = scrapes or {}
        output = []
        for candidate in candidates:
            decision = self.classify(product, candidate, scrapes.get(candidate.url))
            retained = {
                item for item in candidate.source_types
                if not str(item).startswith(("source_tier_", "source_role_", "country_alignment_", "marketplace_"))
            }
            markers = {
                f"source_tier_{decision.source_tier:02d}_{decision.source_tier_name}",
                f"source_role_{decision.source_role}",
                f"country_alignment_{decision.country_alignment}",
            }
            if decision.marketplace:
                markers.add(f"marketplace_{decision.marketplace}")
            output.append(replace(candidate, source_types=tuple(sorted(retained | markers))))
        return output

    def next_target(self, product: ProductQuery, observations: Sequence[Any]) -> str:
        attempted = {
            tier_from_signals(getattr(getattr(item, "action", None), "expected_signals", ()))
            for item in observations
        }
        for tier in self.hierarchy(product):
            if tier not in attempted:
                return tier
        return self.hierarchy(product)[-1]

    def _local(self, url: str, country: str) -> bool:
        if self.country_profiles.domain_matches_country(url, country):
            return True
        cc = (country or "").lower()
        folded = (url or "").lower()
        return bool(cc and any(mark in folded for mark in (f"/{cc}/", f"/{cc}-", f"-{cc}/")))

    def _manufacturer(
        self,
        candidate: URLCandidate,
        product: ProductQuery,
        scrape: ScrapeResult | None,
    ) -> tuple[bool, str]:
        host = compact(urlparse(candidate.url).netloc)
        names = [scrape.brand, scrape.manufacturer] if scrape else []
        names.extend(likely_brand_names(product.main_text))
        matched = [name for name in names if len(compact(name)) >= 3 and compact(name) in host]
        if not matched:
            return False, ""
        evidence = " ".join((candidate.title, candidate.snippet, scrape.brand if scrape else "", scrape.manufacturer if scrape else "")).lower()
        structured = bool(scrape and any(compact(value) == compact(name) for value in (scrape.brand, scrape.manufacturer) if value for name in matched))
        official = any(word in evidence for word in ("official", "manufacturer", "brand site"))
        input_brand = compact(likely_brand_names(product.main_text)[0]) if likely_brand_names(product.main_text) else ""
        accepted = structured or official or bool(input_brand and input_brand in host)
        return accepted, f"Domain matches manufacturer/brand token '{matched[0]}'" if accepted else ""


def source_tier(candidate: URLCandidate) -> int:
    for marker in candidate.source_types:
        match = re.match(r"source_tier_(\d{2})_", str(marker))
        if match:
            return int(match.group(1))
    return int(SourceTier.UNKNOWN)


def source_tier_name(candidate: URLCandidate) -> str:
    for marker in candidate.source_types:
        match = re.match(r"source_tier_\d{2}_(.+)", str(marker))
        if match:
            return match.group(1)
    return SourceTier.UNKNOWN.name


def source_role(candidate: URLCandidate) -> str:
    for marker in candidate.source_types:
        if str(marker).startswith("source_role_"):
            return str(marker).removeprefix("source_role_")
    return "UNKNOWN"


def tier_from_signals(signals: Sequence[str]) -> str:
    for signal in signals:
        if str(signal).startswith("SOURCE_TIER:"):
            return str(signal).split(":", 1)[1]
    return ""


def marketplace_name(value: str) -> str:
    folded = (value or "").lower()
    if "amazon" in folded:
        return "AMAZON"
    if "ebay" in folded:
        return "EBAY"
    return ""


def compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def likely_brand_names(text: str) -> list[str]:
    generic = {"the", "and", "with", "for", "product", "item", "toy", "set", "pack", "new"}
    tokens = [t for t in re.findall(r"[A-Za-z0-9À-ž&+.-]+", text or "") if len(compact(t)) >= 3 and t.lower() not in generic and not t.isdigit()]
    if not tokens:
        return []
    return [tokens[0], f"{tokens[0]} {tokens[1]}"] if len(tokens) > 1 else [tokens[0]]
