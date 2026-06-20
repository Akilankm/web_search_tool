from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import urlparse

from serp_hybrid_url_finder.models import DomainResolution, OrganicSearchResponse, ProductQuery, RetailerResolution
from serp_hybrid_url_finder.stages.signature import fold_text


@dataclass(frozen=True)
class RetailerDomainResolver:
    """Resolves retailer domains from live organic evidence, never from aliases."""

    max_domains: int = 3

    def resolve_from_organic(
        self,
        *,
        product: ProductQuery,
        responses: list[OrganicSearchResponse],
    ) -> RetailerResolution:
        if not product.retailer_name:
            return RetailerResolution(
                requested_retailer=None,
                country_code=product.country_code.upper(),
                resolution_status="NOT_PROVIDED",
            )

        retailer_tokens = self._tokens(product.retailer_name)
        if not retailer_tokens:
            return RetailerResolution(
                requested_retailer=product.retailer_name,
                country_code=product.country_code.upper(),
                resolution_status="UNRESOLVED",
            )

        scores: dict[str, float] = defaultdict(float)
        evidence: dict[str, str] = {}
        country = product.country_code.lower().strip()

        for response in responses:
            for result in response.results:
                parsed = urlparse(result.url)
                domain = parsed.netloc.lower().replace("www.", "")
                if not domain:
                    continue
                text = fold_text(" ".join([domain, result.title, result.snippet, result.displayed_link]))
                token_hits = sum(1 for token in retailer_tokens if token in text)
                if token_hits <= 0:
                    continue
                position_bonus = max(0.0, (12 - float(result.position or 12)) / 12)
                country_bonus = 0.15 if domain.endswith(f".{country}") or f".{country}." in domain else 0.0
                score = min(1.0, token_hits / max(1, len(retailer_tokens)) + 0.20 * position_bonus + country_bonus)
                scores[domain] = max(scores[domain], score)
                evidence[domain] = f"{result.title} | {result.snippet}"[:500]

        domains = tuple(
            DomainResolution(domain=domain, confidence=round(score, 4), evidence_source="organic_search", evidence_text=evidence.get(domain, ""))
            for domain, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)[: self.max_domains]
        )
        return RetailerResolution(
            requested_retailer=product.retailer_name,
            country_code=product.country_code.upper(),
            resolved_domains=domains,
            resolution_status="RESOLVED" if domains else "UNRESOLVED",
        )

    @staticmethod
    def _tokens(value: str) -> list[str]:
        folded = fold_text(value)
        return [token for token in re.findall(r"[a-z0-9]+", folded) if len(token) >= 2]
