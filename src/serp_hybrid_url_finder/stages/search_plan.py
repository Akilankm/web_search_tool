from __future__ import annotations

import re
from dataclasses import dataclass

from serp_hybrid_url_finder.config import ProductURLPipelinePolicy
from serp_hybrid_url_finder.models import CountryContext, ProductQuery, ProductSignature, RetailerResolution, SearchPlan, SearchQuery


@dataclass(frozen=True)
class SearchPlanBuilder:
    policy: ProductURLPipelinePolicy

    def build_initial_plan(
        self,
        *,
        product: ProductQuery,
        signature: ProductSignature,
        country: CountryContext,
    ) -> SearchPlan:
        parts = [self._quote(product.main_text)]
        if signature.ean:
            parts.append(signature.ean)
        if product.retailer_name:
            parts.append(product.retailer_name.strip())
        parts.append(country.country_name or country.country_code)
        query = self._truncate(" ".join(part for part in parts if part))
        return SearchPlan(
            queries=(SearchQuery(query_id="organic_1", query=query, intent="exact_identity_market_discovery"),),
            plan_reason="Initial query uses exact main_text, optional EAN/retailer, and required country context.",
        )

    def build_followup_query(
        self,
        *,
        product: ProductQuery,
        signature: ProductSignature,
        country: CountryContext,
        retailer: RetailerResolution,
        first_had_results: bool,
    ) -> SearchQuery:
        parts: list[str] = []
        if retailer.primary_domain:
            parts.append(f"site:{retailer.primary_domain}")
            parts.append(self._quote(product.main_text))
            if signature.ean:
                parts.append(signature.ean)
            intent = "retailer_domain_scoped_identity_search"
        else:
            if signature.ean and first_had_results:
                parts.append(signature.ean)
                parts.append(self._quote(product.main_text))
            else:
                parts.extend(signature.distinctive_tokens[:8])
                if signature.ean:
                    parts.append(signature.ean)
            if product.retailer_name:
                parts.append(product.retailer_name.strip())
            parts.append(country.country_name or country.country_code)
            intent = "dynamic_recall_search"
        query = self._truncate(" ".join(part for part in parts if part))
        return SearchQuery(query_id="organic_2", query=query, intent=intent)

    def _quote(self, value: str) -> str:
        clean = re.sub(r"\s+", " ", (value or "").strip().replace('"', ""))
        return f'"{clean}"' if clean else ""

    def _truncate(self, query: str) -> str:
        query = re.sub(r"\s+", " ", query).strip()
        if len(query) <= self.policy.organic_query_max_chars:
            return query
        return query[: self.policy.organic_query_max_chars].rsplit(" ", 1)[0]
