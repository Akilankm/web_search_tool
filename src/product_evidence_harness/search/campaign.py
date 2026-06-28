from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from src.product_evidence_harness.contracts import LLMSearchQuery, ProductQuery
from src.product_evidence_harness.country_profiles import CountryProfileRegistry
from src.product_evidence_harness.identity.graph import ProductIdentityGraph, ProductIdentityGraphBuilder
from src.product_evidence_harness.identity.normalizer import quoted


@dataclass(frozen=True)
class SearchCampaignStage:
    name: str
    scope: str
    intent: str
    queries: tuple[LLMSearchQuery, ...] = ()

    def to_dict(self) -> dict:
        return {"name": self.name, "scope": self.scope, "intent": self.intent, "queries": [q.to_dict() for q in self.queries]}


@dataclass(frozen=True)
class SearchCampaign:
    row_id: str
    identity: ProductIdentityGraph
    stages: tuple[SearchCampaignStage, ...] = ()

    def all_queries(self) -> tuple[LLMSearchQuery, ...]:
        out: list[LLMSearchQuery] = []
        for stage in self.stages:
            out.extend(stage.queries)
        return tuple(out)

    def to_dict(self) -> dict:
        return {"row_id": self.row_id, "identity": self.identity.to_dict(), "stages": [s.to_dict() for s in self.stages]}


@dataclass(frozen=True)
class SearchCampaignBuilder:
    country_profiles: CountryProfileRegistry = field(default_factory=CountryProfileRegistry.load)
    max_country_queries: int = 6
    max_global_queries: int = 4

    def build(self, product: ProductQuery, *, identity: ProductIdentityGraph | None = None) -> SearchCampaign:
        identity = identity or ProductIdentityGraphBuilder().build(product)
        qname = identity.search_name or product.main_text
        priority = 1
        country_queries: list[LLMSearchQuery] = []
        if product.ean:
            country_queries.append(LLMSearchQuery(quoted(product.ean), source="campaign_identifier", scope="country", reason="exact user-provided EAN search", priority=priority, must_include_ean=True)); priority += 1
            country_queries.append(LLMSearchQuery(f"{quoted(product.ean)} {quoted(qname)}", source="campaign_identifier_text", scope="country", reason="identifier plus expanded product identity", priority=priority, must_include_ean=True)); priority += 1
        country_queries.append(LLMSearchQuery(quoted(qname), source="campaign_exact_phrase", scope="country", reason="exact expanded product phrase", priority=priority)); priority += 1
        critical = " ".join(identity.must_match_terms[:6])
        if critical:
            country_queries.append(LLMSearchQuery(f"{quoted(qname)} {critical}", source="campaign_attribute_preserving", scope="country", reason="exact phrase plus critical attributes", priority=priority)); priority += 1
        for hint in self.country_profiles.country_hints(product.country_code, max_domain_hints=3):
            country_queries.append(LLMSearchQuery(f"{quoted(qname)} {hint}", source="campaign_country_market", scope="country", reason="requested-country market search", priority=priority)); priority += 1
        global_queries: list[LLMSearchQuery] = []
        if product.ean:
            global_queries.append(LLMSearchQuery(f"{quoted(product.ean)} {quoted(qname)}", source="campaign_global_identifier", scope="global", reason="global exact identifier fallback", priority=priority, must_include_ean=True)); priority += 1
        global_queries.append(LLMSearchQuery(f"{quoted(qname)} product page", source="campaign_global_fallback", scope="global", reason="global exact product fallback", priority=priority)); priority += 1
        return SearchCampaign(
            row_id=product.row_id,
            identity=identity,
            stages=(
                SearchCampaignStage("country_first", "country", "discover exact product pages in requested market", tuple(country_queries[: self.max_country_queries])),
                SearchCampaignStage("global_fallback", "global", "discover exact product outside requested market if country evidence is weak", tuple(global_queries[: self.max_global_queries])),
            ),
        )
