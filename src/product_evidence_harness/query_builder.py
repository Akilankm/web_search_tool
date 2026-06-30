from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from src.product_evidence_harness.contracts import ProductQuery, ProductSearchState, URLCandidate
from src.product_evidence_harness.country_profiles import CountryProfileRegistry, LanguageProfile
from src.product_evidence_harness.gtin import normalize_gtin


@dataclass(frozen=True)
class QueryBuilder:
    """Builds bounded, auditable search queries.

    Country code controls TLD/geography and ordered language-market search.
    Retailer domains are not maintained in configuration; retailer_name, when
    supplied, is used only as a dynamic text signal in the query and scoring.
    """

    max_query_chars: int = 520
    country_profiles: CountryProfileRegistry = field(default_factory=CountryProfileRegistry.load)

    def country_language_count(self, task: ProductQuery) -> int:
        return len(self.country_profiles.language_profiles_for(task.country_code, task.language_code))

    def country_language_metadata(self, task: ProductQuery, language_index: int) -> dict[str, Any]:
        profile = self.country_profiles.get(task.country_code)
        languages = profile.language_profiles_for(task.language_code)
        idx = max(0, min(language_index, len(languages) - 1))
        lp = languages[idx]
        return {
            "scope": "country",
            "kind": "country_language",
            "country_code": task.country_code,
            "country_name": profile.country_name,
            "language_index": idx,
            "language_code": lp.language_code,
            "language_name": lp.language_name,
            "language_priority": lp.priority,
            "language_distribution_weight": lp.distribution_weight,
        }

    def country_language_search(self, task: ProductQuery, *, language_index: int = 0, repair: bool = False, state: ProductSearchState | None = None, include_retailer: bool = True) -> str:
        profile = self.country_profiles.get(task.country_code)
        languages = profile.language_profiles_for(task.language_code)
        idx = max(0, min(language_index, len(languages) - 1))
        lp = languages[idx]

        parts: list[str] = []
        ean = self._valid_ean(task)
        if ean:
            parts.append(ean)

        if repair and state:
            parts.extend(self._repair_clues(state))
        elif idx == 0:
            parts.extend(self._quoted_text_variants(task.main_text, max_variants=2))
        else:
            # Recall searches in non-primary languages use distinctive tokens so
            # translated/localized retailer pages are not blocked by an exact
            # main_text phrase in another language.
            parts.extend(self._distinctive_tokens(task.main_text, max_tokens=8))

        if include_retailer and task.retailer_name:
            parts.append(task.retailer_name)

        parts.extend(self._country_filter_terms(task))
        parts.extend(self._language_country_terms(lp, profile_country_name=profile.country_name, max_terms=3))
        parts.extend(self._localized_terms(lp, max_terms=4))
        return self._truncate(" ".join(parts))

    def primary(self, task: ProductQuery, *, global_fallback: bool = False) -> str:
        if not global_fallback:
            return self.country_language_search(task, language_index=0)
        return self.global_fallback(task)

    def secondary(self, task: ProductQuery, *, global_fallback: bool = False) -> str:
        if not global_fallback:
            return self.country_language_search(task, language_index=1)
        return self.global_fallback(task)

    def requested_retailer_search(self, task: ProductQuery) -> str:
        return self.country_language_search(task, language_index=0, include_retailer=True)

    def country_alternative_search(self, task: ProductQuery, *, language_index: int = 0) -> str:
        return self.country_language_search(task, language_index=language_index, include_retailer=False)

    def global_fallback(self, task: ProductQuery, *, include_retailer: bool = False) -> str:
        parts: list[str] = []
        ean = self._valid_ean(task)
        if ean:
            parts.append(ean)
        parts.extend(self._quoted_text_variants(task.main_text, max_variants=2))
        if include_retailer and task.retailer_name:
            parts.append(task.retailer_name)
        parts.append("retailer product page")
        parts.extend(["buy", "shop", "price"])
        return self._truncate(" ".join(parts))

    def repair_from_state(self, state: ProductSearchState, *, global_fallback: bool = False, include_retailer: bool = False) -> str:
        task = state.task
        parts: list[str] = []
        ean = self._valid_ean(task)
        if ean:
            parts.append(self._quote(ean))
        parts.extend(self._repair_clues(state) or self._distinctive_tokens(task.main_text, max_tokens=7))
        parts.extend(self._repair_negatives(state))
        if include_retailer and task.retailer_name:
            parts.append(task.retailer_name)

        if global_fallback:
            parts.extend(["product page", "buy", "shop"])
            return self._truncate(" ".join(parts))

        # Keep country repair in the highest-priority language by default while
        # preserving the original product identity. Do not drift toward terms
        # extracted from wrong variants.
        profile = self.country_profiles.get(task.country_code)
        lp = profile.language_profiles_for(task.language_code)[0]
        parts.extend(self._country_filter_terms(task))
        parts.extend(self._language_country_terms(lp, profile_country_name=profile.country_name, max_terms=2))
        parts.extend(self._localized_terms(lp, max_terms=3))
        return self._truncate(" ".join(parts))


    def exact_ean_repair_from_state(self, state: ProductSearchState) -> str:
        """Build an exact-EAN repair query after near-match/variant conflict.

        This is generic: it uses the expected EAN and domains of failed
        country-specific candidates. No retailer/product IDs are hardcoded.
        """
        task = state.task
        parts: list[str] = []
        ean = self._valid_ean(task)
        if ean:
            parts.append(self._quote(ean))

        domains: list[str] = []
        for card in state.scorecards:
            v = card.verification
            if not v:
                continue
            if v.ean_check == "CONFLICT" or v.variant_check == "CONFLICT" or v.exact_product_check == "MISMATCH":
                domain = urlparse(card.candidate.url).netloc.lower().removeprefix("www.")
                if domain and self.country_profiles.domain_matches_country(card.candidate.url, task.country_code):
                    domains.append(domain)
        domains = list(dict.fromkeys(domains))[:3]
        if domains:
            parts.append("(" + " OR ".join(f"site:{d}" for d in domains) + ")")
        else:
            parts.extend(self._country_filter_terms(task))

        parts.extend(self._quoted_text_variants(task.main_text, max_variants=2))
        if task.retailer_name:
            parts.append(task.retailer_name)
        parts.append("product page")
        return self._truncate(" ".join(parts))

    def ai_discovery_prompt(self, task: ProductQuery, *, allow_global_fallback: bool = True) -> str:
        profile = self.country_profiles.get(task.country_code)
        language_lines = self._language_profile_lines(task)
        country_terms = ", ".join(self.country_profiles.country_context_terms(task.country_code, task.language_code)) or "not_configured"
        return self._truncate("\n".join([
            "Find ecommerce product detail page URLs for a product evidence harness.",
            "Return only URLs that are likely product detail pages. Prefer requested-country URLs first.",
            "Do not return category/search/home/social/PDF/image URLs.",
            "Use FINAL_URL: <url> for the best candidate, or FINAL_URL: NO_MATCH if no plausible URL exists.",
            "Also list up to 5 alternate candidate URLs under REFERENCES.",
            "Retailers are not preconfigured. Discover retailer pages dynamically from the web.",
            "",
            "PRODUCT:",
            f"main_text: {task.main_text}",
            f"country_code: {task.country_code}",
            f"country_name: {profile.country_name}",
            f"country_tlds: {', '.join(profile.tlds) or 'not_configured'}",
            "country_language_priority:",
            *language_lines,
            f"country_terms: {country_terms}",
            f"retailer_name: {task.retailer_name or 'not_provided'}",
            f"ean_gtin: {self._valid_ean(task) or 'not_provided'}",
            f"global_fallback_allowed: {str(allow_global_fallback)}",
        ]))

    def ai_validation_prompt(self, task: ProductQuery, candidates: list[URLCandidate], *, allow_global_fallback: bool = True) -> str:
        profile = self.country_profiles.get(task.country_code)
        language_lines = self._language_profile_lines(task)
        country_terms = ", ".join(self.country_profiles.country_context_terms(task.country_code, task.language_code)) or "not_configured"
        lines = [
            "You are validating ecommerce product URL candidates for a product evidence harness.",
            "Decision policy:",
            "1. Prefer exact product detail pages from the requested country.",
            "2. Treat EAN/GTIN as a strong anchor, not the sole authority. Exact product identity is driven by main_text, product title, variant/form, pack/edition/language evidence.",
            "3. Reject sibling variants such as single item vs display/box/bundle even when title overlap is high.",
            "4. Retailers are not preconfigured. Use the URL/page evidence, not a static retailer list.",
            "5. If no requested-country product page is available, a global fallback URL is allowed but must be marked as fallback evidence.",
            "6. Reject category/search/home/social/PDF/image pages as final product URLs.",
            "7. Final URL must still be scraped and verified by the harness; you are only providing candidate evidence.",
            "Return concise evidence only.",
            "Use FINAL_URL: <url> if one candidate is the best match, else FINAL_URL: NO_MATCH.",
            "Also state EAN_EVIDENCE, TITLE_EVIDENCE, RETAILER_EVIDENCE, COUNTRY_EVIDENCE, PRODUCT_PAGE_EVIDENCE, FALLBACK_REASON.",
            "",
            "PRODUCT:",
            f"main_text: {task.main_text}",
            f"country_code: {task.country_code}",
            f"country_name: {profile.country_name}",
            f"country_tlds: {', '.join(profile.tlds) or 'not_configured'}",
            "country_language_priority:",
            *language_lines,
            f"country_terms: {country_terms}",
            f"retailer_name: {task.retailer_name or 'not_provided'}",
            f"ean_gtin: {self._valid_ean(task) or 'not_provided'}",
            f"global_fallback_allowed: {str(allow_global_fallback)}",
            "",
            "CANDIDATES:",
        ]
        for idx, c in enumerate(candidates[:12], start=1):
            country_specific = self.country_profiles.domain_matches_country(c.url, task.country_code)
            lines.extend([
                f"{idx}. url: {c.url}",
                f"   country_specific_domain: {country_specific}",
                f"   title: {c.title[:180]}",
                f"   snippet: {c.snippet[:240]}",
                f"   source_types: {', '.join(c.source_types)}",
            ])
        return self._truncate("\n".join(lines))

    def _language_profile_lines(self, task: ProductQuery) -> list[str]:
        lines = []
        for lp in self.country_profiles.language_profiles_for(task.country_code, task.language_code):
            lines.append(
                f"- {lp.language_code} ({lp.language_name}): priority={lp.priority}, distribution_weight={lp.distribution_weight}"
            )
        return lines

    def _country_filter_terms(self, task: ProductQuery, *, max_domain_hints: int = 4) -> list[str]:
        hints = list(self.country_profiles.country_hints(task.country_code, max_domain_hints=max_domain_hints))
        if not hints:
            return []
        if len(hints) == 1:
            return hints
        return ["(" + " OR ".join(hints[:max_domain_hints]) + ")"]

    def _language_country_terms(self, lp: LanguageProfile, *, profile_country_name: str, max_terms: int) -> list[str]:
        terms = list(lp.country_terms)
        if profile_country_name:
            terms.append(profile_country_name)
        terms = list(dict.fromkeys(t for t in terms if t))[:max_terms]
        if not terms:
            return []
        return ["(" + " OR ".join(terms) + ")"] if len(terms) > 1 else terms

    def _localized_terms(self, lp: LanguageProfile, *, max_terms: int) -> list[str]:
        terms = list(dict.fromkeys(t for t in lp.commerce_terms if t))[:max_terms]
        if not terms:
            return ["buy"]
        return ["(" + " OR ".join(terms) + ")"] if len(terms) > 1 else terms

    def _repair_clues(self, state: ProductSearchState) -> list[str]:
        """Return identity-preserving repair clues.

        Earlier versions used the best scraped page's title as repair input; that
        caused drift toward wrong variants. Repair must start from the requested
        product identity graph and only then use scraped evidence as optional
        weak clues.
        """
        graph = state.identity_graph
        clues: list[str] = []
        if graph is not None:
            search_name = getattr(graph, "search_name", "") or ""
            if search_name:
                clues.append(self._quote(search_name))
            for attr in ["model_or_series_terms", "must_match_terms", "variant_terms", "product_form_terms"]:
                clues.extend(str(x) for x in (getattr(graph, attr, ()) or ()))
        if not clues:
            clues.extend(self._quoted_text_variants(state.task.main_text, max_variants=1))
            clues.extend(self._distinctive_tokens(state.task.main_text, max_tokens=7))

        out: list[str] = []
        seen: set[str] = set()
        for token in clues:
            key = token.lower().strip()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(token)
            if len(out) >= 12:
                break
        return out

    def _repair_negatives(self, state: ProductSearchState) -> list[str]:
        negatives: list[str] = []
        for findings in state.detector_findings.values():
            for f in findings:
                if f.get("status") != "CONFLICT":
                    continue
                page_value = str(f.get("page_value") or "")
                for raw in re.split(r"[|,;]", page_value):
                    term = raw.strip()
                    if not term or term.startswith("missing=") or len(term) > 40:
                        continue
                    if re.search(r"[A-Za-zÀ-ž0-9]", term):
                        negatives.append("-" + self._quote(term) if " " in term else "-" + term)
        return list(dict.fromkeys(negatives))[:6]

    def _quoted_text_variants(self, text: str, *, max_variants: int = 2) -> list[str]:
        variants = []
        raw = (text or "").strip()
        if raw:
            variants.append(raw)
        expanded = self._segment_compact_text(raw)
        if expanded and expanded.lower() != raw.lower():
            variants.insert(0, expanded)
        out = []
        seen = set()
        for v in variants:
            key = v.lower()
            if key not in seen:
                seen.add(key)
                out.append(self._quote(v))
            if len(out) >= max_variants:
                break
        return out

    def _segment_compact_text(self, text: str) -> str:
        """Recover useful search terms from compact product text.

        Example: 1001KARTENA5FLIEDER -> 1001 KARTEN A5 FLIEDER.
        This is generic: it splits digit/letter boundaries and common paper/pack
        format tokens (A4/A5/B5/etc.) embedded in uppercase compact strings.
        """
        t = str(text or "").strip()
        if not t:
            return ""
        t = re.sub(r"([A-Za-zÀ-ž]+)([ABC][0-9])([A-Za-zÀ-ž]+)", r"\1 \2 \3", t)
        t = re.sub(r"(\d)([A-Za-zÀ-ž])", r"\1 \2", t)
        t = re.sub(r"([A-Za-zÀ-ž])(\d)", r"\1 \2", t)
        t = re.sub(r"[_/\-]+", " ", t)
        t = re.sub(r"\b([ABCabc])\s+([0-9]{1,2})\b", r"\1\2", t)
        t = re.sub(r"\b(\d+(?:[.,]\d+)?)\s+(mm|cm|m|inch|in|ml|l|g|kg)\b", r"\1\2", t, flags=re.I)
        return " ".join(t.split())

    def _valid_ean(self, task: ProductQuery) -> str | None:
        return normalize_gtin(task.ean)

    def _quote(self, text: str) -> str:
        return f'"{text.strip().replace(chr(34), "")}"'

    def _truncate(self, query: str) -> str:
        query = " ".join((query or "").split())
        return query[: self.max_query_chars].strip()

    def _distinctive_tokens(self, text: str, *, max_tokens: int = 8) -> list[str]:
        tokens = []
        for token in re.findall(r"[A-Za-zÀ-ž0-9]+", self._segment_compact_text(text or "")):
            if len(token) < 3:
                continue
            if token.lower() in {"the", "and", "for", "with", "product", "item"}:
                continue
            tokens.append(token)
        return list(dict.fromkeys(tokens))[:max_tokens]
