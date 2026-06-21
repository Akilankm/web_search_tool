from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from src.serp_hybrid_url_finder.constants import (
    ORGANIC_DETAIL_TERMS,
    ORGANIC_NOISE_EXCLUSIONS,
    ORGANIC_QUERY_MAX_CHARS,
    QUERY_SITE_OPERATOR,
)
from src.serp_hybrid_url_finder.models import OrganicSearchResponse, ProductQuery


@dataclass(frozen=True)
class OrganicSearchPlanner:
    """
    Builds two organic queries used for candidate discovery.

    Search #1:
        Precision-oriented, but not over-constrained.

    Search #2:
        Adaptive. If Search #1 returned zero results, it relaxes the query
        and intentionally drops EAN because many retailer PDPs do not expose
        EAN in indexed text.
    """

    max_query_chars: int = ORGANIC_QUERY_MAX_CHARS

    def build_first_query(self, product: ProductQuery) -> str:
        parts: list[str] = []

        # Title is usually the strongest indexed signal for product-detail pages.
        parts.append(self._quote(product.main_text))

        # EAN can help, but keep it unquoted and late to avoid over-constraining.
        if product.ean:
            parts.append(product.ean.strip())

        if product.retailer_name:
            parts.append(product.retailer_name.strip())

        if product.country_code:
            parts.append(product.country_code.strip())

        # Keep this light. Heavy exclusions can produce zero results for rare products.
        parts.extend(("product", "produkt"))

        return self._truncate(" ".join(parts))

    def build_second_query(
        self,
        product: ProductQuery,
        first_response: Optional[OrganicSearchResponse] = None,
    ) -> str:
        inferred_domain = self.infer_retailer_domain_from_organic(product, first_response)
        first_had_results = bool(first_response and first_response.results)

        parts: list[str] = []

        if inferred_domain:
            parts.append(QUERY_SITE_OPERATOR.format(domain=inferred_domain))

        if not first_had_results:
            # Relax aggressively when Google returned zero results for the first query.
            # Do not add EAN here; EAN often kills recall.
            parts.extend(self._relaxed_title_tokens(product.main_text, max_tokens=6))

            if product.retailer_name:
                parts.append(product.retailer_name.strip())

            if product.country_code:
                parts.append(product.country_code.strip())

            parts.extend(("product", "produkt", "detail"))

        else:
            # If first search found candidates, second query can be more targeted.
            if product.ean:
                parts.append(product.ean.strip())

            parts.append(self._quote(product.main_text))

            if product.retailer_name and not inferred_domain:
                parts.append(product.retailer_name.strip())

            if product.country_code:
                parts.append(product.country_code.strip())

            parts.extend(ORGANIC_DETAIL_TERMS)

        parts.extend(self._light_exclusions())

        return self._truncate(" ".join(parts))

    def infer_retailer_domain_from_organic(
        self,
        product: ProductQuery,
        first_response: Optional[OrganicSearchResponse],
    ) -> Optional[str]:
        if not product.retailer_name or not first_response or not first_response.results:
            return None

        retailer_tokens = self._tokens(product.retailer_name)
        if not retailer_tokens:
            return None

        domain_scores: dict[str, int] = {}

        for result in first_response.results:
            domain = urlparse(result.url).netloc.lower().replace("www.", "")
            if not domain:
                continue

            evidence_text = " ".join(
                [
                    domain,
                    result.title.lower(),
                    result.snippet.lower(),
                    result.displayed_link.lower(),
                ]
            )

            score = sum(1 for token in retailer_tokens if token in evidence_text)

            if score > 0:
                position_bonus = max(0, 6 - int(result.position or 10))
                domain_scores[domain] = domain_scores.get(domain, 0) + score + position_bonus

        if not domain_scores:
            return None

        return sorted(domain_scores.items(), key=lambda item: item[1], reverse=True)[0][0]

    def _quote(self, value: str) -> str:
        clean = value.strip().replace('"', "")
        return f'"{clean}"' if clean else ""

    def _tokens(self, value: str) -> list[str]:
        return [
            token.lower()
            for token in re.findall(r"[a-zA-Z0-9À-ž]+", value or "")
        ]

    def _relaxed_title_tokens(self, value: str, *, max_tokens: int) -> list[str]:
        tokens = self._tokens(value)

        # Remove generic/common tokens; keep distinctive product tokens.
        stopish = {
            "ks",
            "pcs",
            "piece",
            "pieces",
            "toy",
            "toys",
            "figurka",
            "figure",
            "set",
        }

        strong = [
            token
            for token in tokens
            if len(token) >= 4 and token not in stopish
        ]

        seen: set[str] = set()
        unique: list[str] = []

        for token in strong:
            if token not in seen:
                seen.add(token)
                unique.append(token)

        return unique[:max_tokens]

    def _light_exclusions(self) -> list[str]:
        # Heavy exclusions can kill recall for long-tail products.
        allowed = {
            "-youtube",
            "-facebook",
            "-instagram",
            "-tiktok",
            "-pinterest",
            "-pdf",
            "-manual",
        }
        return [term for term in ORGANIC_NOISE_EXCLUSIONS if term in allowed]

    def _truncate(self, query: str) -> str:
        query = " ".join(query.split())
        if len(query) <= self.max_query_chars:
            return query
        return query[: self.max_query_chars].rsplit(" ", 1)[0]


@dataclass(frozen=True)
class AIValidationPromptBuilder:
    """Builds one AI Mode prompt that validates many candidate URLs."""

    max_query_chars: int

    def build_validation_prompt(
        self,
        *,
        product: ProductQuery,
        candidates_text: str,
    ) -> str:
        from src.serp_hybrid_url_finder.constants import (
            AI_VALIDATOR_OUTPUT_CONTRACT,
            AI_VALIDATOR_ROLE,
            AI_VALIDATOR_RULES,
            AI_VALIDATOR_TASK,
        )

        if not candidates_text.strip():
            candidates_text = "NO_ORGANIC_CANDIDATES_FOUND"

        parts = [
            AI_VALIDATOR_ROLE,
            "TASK:",
            AI_VALIDATOR_TASK,
            "PRODUCT INPUT:",
            f'main_text: "{self._clean(product.main_text)}"',
        ]

        if product.ean:
            parts.append(f'ean_gtin: "{self._clean(product.ean)}"')
        else:
            parts.append("ean_gtin: not_provided")

        if product.retailer_name:
            parts.append(f"retailer_name: {product.retailer_name.strip()}")
        else:
            parts.append("retailer_name: not_provided")

        if product.country_code:
            parts.append(f"country_code: {product.country_code.strip()}")
        else:
            parts.append("country_code: not_provided")

        parts.append("VALIDATION RULES:")
        parts.extend(f"- {rule}" for rule in AI_VALIDATOR_RULES)
        parts.append("CANDIDATE_URLS:")
        parts.append(candidates_text)
        parts.append("OUTPUT FORMAT:")
        parts.extend(AI_VALIDATOR_OUTPUT_CONTRACT)

        return self._truncate("\n".join(parts))

    def build_repair_prompt(
        self,
        *,
        product: ProductQuery,
        candidates_text: str,
        previous_answer: str,
        rejection_reason: str,
    ) -> str:
        from src.serp_hybrid_url_finder.constants import (
            AI_REPAIR_TASK,
            AI_VALIDATOR_OUTPUT_CONTRACT,
            AI_VALIDATOR_ROLE,
            AI_VALIDATOR_RULES,
        )

        if not candidates_text.strip():
            candidates_text = "NO_ORGANIC_CANDIDATES_FOUND"

        parts = [
            AI_VALIDATOR_ROLE,
            "REPAIR TASK:",
            AI_REPAIR_TASK,
            "PRODUCT INPUT:",
            f'main_text: "{self._clean(product.main_text)}"',
        ]

        if product.ean:
            parts.append(f'ean_gtin: "{self._clean(product.ean)}"')
        else:
            parts.append("ean_gtin: not_provided")

        if product.retailer_name:
            parts.append(f"retailer_name: {product.retailer_name.strip()}")
        else:
            parts.append("retailer_name: not_provided")

        if product.country_code:
            parts.append(f"country_code: {product.country_code.strip()}")
        else:
            parts.append("country_code: not_provided")

        parts.append("PREVIOUS ANSWER:")
        parts.append(previous_answer[:1500])
        parts.append("DETERMINISTIC REJECTION REASON:")
        parts.append(rejection_reason)
        parts.append("VALIDATION RULES:")
        parts.extend(f"- {rule}" for rule in AI_VALIDATOR_RULES)
        parts.append("CANDIDATE_URLS:")
        parts.append(candidates_text)
        parts.append("OUTPUT FORMAT:")
        parts.extend(AI_VALIDATOR_OUTPUT_CONTRACT)

        return self._truncate("\n".join(parts))

    def _clean(self, value: str) -> str:
        return value.strip().replace('"', "")

    def _truncate(self, query: str) -> str:
        if len(query) <= self.max_query_chars:
            return query
        return query[: self.max_query_chars].rsplit("\n", 1)[0]