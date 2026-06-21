from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from src.serp_hybrid_url_finder.constants import (
    ORGANIC_BUY_TERMS,
    ORGANIC_EDITORIAL_EXCLUSIONS,
    ORGANIC_INURL_PDP_HINTS,
    ORGANIC_QUERY_MAX_CHARS,
    QUERY_SITE_OPERATOR,
)
from src.serp_hybrid_url_finder.models import OrganicSearchResponse, ProductQuery


@dataclass(frozen=True)
class OrganicSearchPlanner:
    """
    Builds three organic queries using elite SEO operator strategies.

    Search #1  — EAN-Anchored Identity (Ultra-Precision)
        Quoted EAN forces exact barcode match; language buy verb filters to
        commerce pages. Only pages literally containing the barcode rank.

    Search #2  — intitle: + inurl: PDP-Targeted Recall
        intitle: targets the <title> HTML tag (highest SEO weight) using
        extracted model codes. inurl: targets known PDP URL path patterns.
        EAN intentionally omitted — most PDPs don't expose it in indexed text.

    Search #3  — Global Fallback (Maximum Recall)
        Model tokens unquoted, no geographic constraint. Minimal exclusions
        to preserve recall on rare/long-tail products.
    """

    max_query_chars: int = ORGANIC_QUERY_MAX_CHARS

    # -------------------------------------------------------------------------
    # Public query builders
    # -------------------------------------------------------------------------

    def build_first_query(self, product: ProductQuery) -> str:
        """
        EAN-Anchored Identity query.

        With EAN:    "EXACT TITLE" "EAN" BUY_VERB [retailer]
        Without EAN: "EXACT TITLE" inurl:PDP_HINT BUY_VERB [retailer]

        Quoting the EAN forces Google to surface only pages where the barcode
        literally appears in the HTML — the most discriminative possible signal.
        The local buy verb (kaufen / acheter / buy) pushes results toward
        commerce pages and away from editorial / review content.
        No exclusions needed: precision comes from positive signals only.
        """
        parts: list[str] = [self._quote(product.main_text)]

        if product.ean:
            # Quoted EAN = exact barcode identity anchor
            parts.append(self._quote(str(product.ean).strip()))
        else:
            inurl = self._inurl_hint(product.language_code)
            if inurl:
                parts.append(inurl)

        parts.append(self._buy_term(product.language_code))

        if product.retailer_name:
            parts.append(str(product.retailer_name).strip())

        return self._truncate(" ".join(parts))

    def build_second_query(
        self,
        product: ProductQuery,
        first_response: Optional[OrganicSearchResponse] = None,
    ) -> str:
        """
        intitle: + inurl: PDP-Targeted Recall query.

        Uses Google's intitle: operator (targets the <title> HTML tag, the
        highest-weight SEO field retailers optimise for) combined with inurl:
        (targets PDP URL path patterns like /produkt/, /product/, /artikel/).

        intitle:ME04 intitle:PKM → forces both model code AND brand abbreviation
        to appear in the page title, discriminating against category/listing pages
        that may contain these tokens elsewhere.

        EAN intentionally omitted: most retailer PDPs don't expose the barcode
        in Google-indexed text, so including it would kill recall.

        Zero results path: drops quoted title, keeps only intitle: tokens +
        PDP path hint for maximum relaxation.
        """
        inferred_domain = self.infer_retailer_domain_from_organic(product, first_response)
        first_had_results = bool(first_response and first_response.results)
        model_tokens = self._extract_model_tokens(product.main_text)

        parts: list[str] = []

        if inferred_domain:
            parts.append(QUERY_SITE_OPERATOR.format(domain=inferred_domain))

        if not first_had_results:
            # Zero-results relaxation: intitle: model tokens only, no quoted phrase
            for token in model_tokens[:2]:
                parts.append(f"intitle:{token}")
            if not model_tokens:
                # Absolute last resort: relaxed title tokens
                parts.extend(self._relaxed_title_tokens(product.main_text, max_tokens=4))
        else:
            # First search had results: intitle: model codes + full quoted title
            for token in model_tokens[:2]:
                parts.append(f"intitle:{token}")
            parts.append(self._quote(product.main_text))
            if product.retailer_name and not inferred_domain:
                parts.append(str(product.retailer_name).strip())
            # NOTE: EAN omitted intentionally — kills recall when not in indexed text

        inurl = self._inurl_hint(product.language_code)
        if inurl:
            parts.append(inurl)

        parts.append(self._buy_term(product.language_code))
        parts.extend(self._editorial_exclusions())

        return self._truncate(" ".join(parts))

    def build_global_fallback_query(
        self,
        product: ProductQuery,
        inferred_domain: Optional[str] = None,
    ) -> str:
        """
        Maximum-recall global fallback.

        No geographic constraint. Tokens are unquoted (relaxed matching).
        Only 2 editorial exclusions max — every extra exclusion costs recall
        on rare/long-tail products.

        With known retailer domain: site-scoped precision with quoted title + EAN.
        Without domain: model codes first, then relaxed title tokens, minimal
        exclusions.
        """
        parts: list[str] = []

        if inferred_domain:
            parts.append(QUERY_SITE_OPERATOR.format(domain=inferred_domain))
            parts.append(self._quote(product.main_text))
            if product.ean:
                parts.append(self._quote(str(product.ean).strip()))
            parts.append(self._buy_term(product.language_code))
        else:
            model_tokens = self._extract_model_tokens(product.main_text)
            parts.extend(model_tokens[:3])

            # Add relaxed title tokens, deduplicating against model tokens
            upper_model = {t.upper() for t in model_tokens}
            for t in self._relaxed_title_tokens(product.main_text, max_tokens=5):
                if t.upper() not in upper_model and len(parts) < 7:
                    parts.append(t)

            if product.retailer_name:
                parts.append(str(product.retailer_name).strip())
            if product.ean:
                # Unquoted EAN in fallback — allows partial match for max recall
                parts.append(str(product.ean).strip())

            parts.append(self._buy_term(product.language_code))
            # Only 2 exclusions max — preserve recall on rare products
            parts.extend(list(ORGANIC_EDITORIAL_EXCLUSIONS)[:2])

        return self._truncate(" ".join(parts))

    # -------------------------------------------------------------------------
    # Retailer domain inference
    # -------------------------------------------------------------------------

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

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _buy_term(self, language_code: Optional[str]) -> str:
        """Return the local commerce/purchase verb for the given language."""
        return ORGANIC_BUY_TERMS.get((language_code or "").lower(), "buy")

    def _inurl_hint(self, language_code: Optional[str]) -> str:
        """Return inurl:PDP_HINT for the given language (e.g. 'inurl:produkt')."""
        hints = ORGANIC_INURL_PDP_HINTS.get(
            (language_code or "").lower(),
            ORGANIC_INURL_PDP_HINTS["_default"],
        )
        return f"inurl:{hints[0]}" if hints else ""

    def _extract_model_tokens(self, title: str) -> list[str]:
        """
        Extract high-signal product identifier tokens for intitle: targeting.

        Priority 1 — Alphanumeric codes (contain both letters AND digits):
            ME04, 8GB, V2, 36x, TCG360 — SKU / model / version codes.
            These are the most distinctive tokens in any product title.

        Priority 2 — Short all-caps abbreviations (2–6 chars):
            PKM, GBA, TCG, USA — brand/series abbreviations.
            Only captured if not already in Priority 1 results.

        Returns at most 3 tokens (more intitle: constraints kill recall).

        Examples:
            "PKM ME04 WACHSENDES CHAOS BOOSTER" → ["ME04", "PKM"]
            "LEGO 42156 Technic Peugeot" → ["42156"]  (numeric-only, skip)
              wait — 42156 is digits only, so no letter; won't match P1.
              But "LEGO" is all-caps → P2 → ["LEGO"]
        """
        seen: set[str] = set()
        result: list[str] = []

        # Priority 1: tokens with at least one letter AND at least one digit
        for m in re.finditer(
            r'\b(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*[0-9])[A-Z0-9]{2,8}\b',
            title.upper(),
        ):
            t = m.group()
            if t not in seen:
                seen.add(t)
                result.append(t)

        # Priority 2: short all-caps abbreviations (not already captured)
        for m in re.finditer(r'\b[A-Z]{2,6}\b', title):
            t = m.group()
            if t not in seen:
                seen.add(t)
                result.append(t)

        return result[:3]

    def _editorial_exclusions(self) -> list[str]:
        """Return up to 4 editorial site exclusions (cap preserves recall)."""
        return list(ORGANIC_EDITORIAL_EXCLUSIONS)[:4]

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

        stopish = {
            "ks", "pcs", "piece", "pieces", "toy", "toys",
            "figurka", "figure", "set",
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